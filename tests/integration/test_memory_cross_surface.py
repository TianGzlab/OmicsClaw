"""Cross-surface namespace integration tests (PR #5 §5.5).

Each surface (CLI workspace path, Desktop launch_id, Bot platform/user)
gets its own namespace; they share one engine and one DB. These tests
prove the partition boundaries hold across the full surface set.

Scenarios:
  - CLI write in workspace_A is invisible from Bot tg/user42 (and vice versa)
  - CLI remember_shared write IS visible from Bot recall (read fallback)
  - Desktop ReviewLog.rollback affects only desktop's namespace; CLI sees
    its own untouched chain
"""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def shared_engine(tmp_path, monkeypatch):
    """One DB, one engine, three surface clients on top."""
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/cross.db"
    )

    from omicsclaw.memory import (
        cli_namespace_from_workspace,
        close_db,
        desktop_namespace,
        get_engine_db,
        get_memory_client,
        get_review_log,
    )

    await close_db()
    await get_engine_db().init_db()

    cli_a_ns = cli_namespace_from_workspace(str(tmp_path / "workspace_a"))
    cli_b_ns = cli_namespace_from_workspace(str(tmp_path / "workspace_b"))

    monkeypatch.setenv("OMICSCLAW_DESKTOP_LAUNCH_ID", "test-launch-1")
    desktop_ns = desktop_namespace()

    cli_a = get_memory_client(namespace=cli_a_ns)
    cli_b = get_memory_client(namespace=cli_b_ns)
    desktop = get_memory_client(namespace=desktop_ns)
    review = get_review_log()

    yield {
        "cli_a": cli_a,
        "cli_b": cli_b,
        "desktop": desktop,
        "review": review,
        "cli_a_ns": cli_a_ns,
        "cli_b_ns": cli_b_ns,
        "desktop_ns": desktop_ns,
        "tmp_path": tmp_path,
    }

    await close_db()


@pytest.mark.asyncio
async def test_cli_write_invisible_from_bot_namespace(shared_engine, tmp_path):
    """CLI writes in its workspace namespace; bot in tg/user42 doesn't see it."""
    from omicsclaw.memory.compat import CompatMemoryStore, DatasetMemory

    cli_a = shared_engine["cli_a"]
    await cli_a.remember(
        "dataset://my_local.h5ad",
        "CLI A's local dataset",
    )

    # The bot uses its own CompatMemoryStore (not the same MemoryClient
    # instance); but they share the same DB by env var.
    bot = CompatMemoryStore()
    await bot.initialize()
    try:
        session = await bot.create_session("user42", "telegram")
        await bot.save_memory(
            session.session_id, DatasetMemory(file_path="bot_local.h5ad")
        )

        bot_mem = await bot.get_memories(session.session_id, "dataset")
        bot_paths = {m.file_path for m in bot_mem}
        assert "my_local.h5ad" not in bot_paths
        assert "bot_local.h5ad" in bot_paths
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_cli_remember_shared_visible_via_bot_recall(shared_engine):
    """remember_shared writes to __shared__; recall from any namespace
    sees it via fallback."""
    from omicsclaw.memory.compat import CompatMemoryStore

    cli_a = shared_engine["cli_a"]
    await cli_a.remember_shared(
        "core://agent",
        "you are a global helpful agent",
    )

    bot = CompatMemoryStore()
    await bot.initialize()
    try:
        session = await bot.create_session("user42", "telegram")
        # Bot's session-scoped client falls back to __shared__ on recall.
        client = await bot._client_for_session(session.session_id)
        record = await client.recall("core://agent")
        assert record is not None
        assert record.content == "you are a global helpful agent"
        assert record.loaded_namespace == "__shared__"
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_desktop_rollback_does_not_affect_cli_chain(shared_engine):
    """Desktop and CLI both have their own preference://style chain.
    Rolling back desktop's chain leaves CLI's untouched."""
    cli_a = shared_engine["cli_a"]
    desktop = shared_engine["desktop"]
    review = shared_engine["review"]

    # CLI builds its own chain.
    cli_v1 = await cli_a.remember("preference://style", "cli v1")
    cli_v2 = await cli_a.remember("preference://style", "cli v2")

    # Desktop builds its own chain (separate namespace).
    dt_v1 = await desktop.remember("preference://style", "desktop v1")
    dt_v2 = await desktop.remember("preference://style", "desktop v2")

    # Roll back the desktop chain to v1.
    await review.rollback_to(
        dt_v1["id"], namespace=shared_engine["desktop_ns"]
    )

    # Desktop now reads v1; CLI still reads its own v2.
    desktop_record = await desktop.recall("preference://style")
    cli_record = await cli_a.recall("preference://style")

    assert desktop_record is not None
    assert cli_record is not None
    assert desktop_record.content == "desktop v1"
    assert cli_record.content == "cli v2"


@pytest.mark.asyncio
async def test_two_cli_workspaces_isolate_their_writes(shared_engine):
    """Two CLI sessions in different workspace dirs don't see each
    other's per-workspace memories."""
    cli_a = shared_engine["cli_a"]
    cli_b = shared_engine["cli_b"]

    await cli_a.remember("analysis://run_42", "ws_a's analysis")
    await cli_b.remember("analysis://run_42", "ws_b's analysis")

    a_record = await cli_a.recall("analysis://run_42", fallback_to_shared=False)
    b_record = await cli_b.recall("analysis://run_42", fallback_to_shared=False)

    assert a_record is not None
    assert b_record is not None
    assert a_record.content == "ws_a's analysis"
    assert b_record.content == "ws_b's analysis"
    assert a_record.namespace != b_record.namespace


# ---------------------------------------------------------------------------
# T2 S8 — memories survive engine close/reopen (server restart simulation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memories_survive_engine_close_and_reopen(tmp_path, monkeypatch):
    """The memory system's promise to the user — 'the agent remembers what
    I told it across sessions' — only holds if writes survive a server
    restart. Simulate: write → close engine → reopen engine pointing at
    the same DB file → recall.

    Without this, the namespace machinery could be in-memory and we
    wouldn't notice. The pin: SQLite file persists, init_db is
    idempotent, and engine cache reset is clean.
    """
    db_path = f"{tmp_path}/persist.db"
    monkeypatch.setenv("OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    from omicsclaw.memory import (
        close_db,
        get_engine_db,
        get_memory_client,
    )

    # First "process": write a memory in a per-user namespace and a
    # shared one, then close the engine cleanly.
    await close_db()
    await get_engine_db().init_db()
    user = get_memory_client(namespace="telegram/alice")
    await user.remember("preference://qc/threshold", "20% mito")
    await user.remember("core://agent/style", "concise")  # → __shared__
    await close_db()

    # Second "process": reopen against the same DB file. The package's
    # singletons reset on close_db; init_db is a no-op for an already-
    # migrated schema.
    await get_engine_db().init_db()
    user2 = get_memory_client(namespace="telegram/alice")

    pref = await user2.recall("preference://qc/threshold")
    assert pref is not None, "preference vanished across restart"
    assert pref.content == "20% mito"

    style = await user2.recall("core://agent/style")
    assert style is not None, "shared row vanished across restart"
    assert style.content == "concise"

    # And isolation is still enforced after restart: a different
    # namespace must not see alice's preference.
    bob = get_memory_client(namespace="telegram/bob")
    bob_view = await bob.recall(
        "preference://qc/threshold", fallback_to_shared=False
    )
    assert bob_view is None, (
        "Namespace isolation lost across restart — bob saw alice's row"
    )

    await close_db()

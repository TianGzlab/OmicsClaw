"""Backward-compat contract for bot.skill_orchestration.

The module collects skill-execution helpers carved out of bot/core.py
across slice #119 (PR #122) and slice #119-remainder (this PR). These
identity tests pin the contract: every previously-public symbol on
``bot.core`` must resolve to the **same object** as on
``bot.skill_orchestration`` — not parallel copies, not aliases.

External tests (``tests/test_oauth_regressions.py``,
``tests/test_skill_listing.py``, etc.) import these names from
``bot.core``; the regression net only stays meaningful if the two
paths point at the same callable.
"""

from __future__ import annotations


SKILL_ORCH_REEXPORTS = (
    # Slice #119 (PR #122) — already in bot.skill_orchestration
    "OutputMediaPaths",
    "_collect_output_media_paths",
    "_AUTO_DISAMBIGUATE_GAP",
    "_format_auto_disambiguation",
    "_format_auto_route_banner",
    # Slice #119-remainder (this PR) — execution path
    "_normalize_extra_args",
    "_run_omics_skill_step",
    "_run_skill_via_shared_runner",
    # Skill lookup + param inference
    "_lookup_skill_info",
    "_resolve_param_hint_info",
    "_infer_skill_for_method",
    "_build_method_preview",
    "_build_param_hint",
    # Memory auto-capture
    "_auto_capture_dataset",
    "_auto_capture_analysis",
    # Env-error parsing
    "_extract_env_snippet",
    "_extract_fix_hint",
    "_classify_env_error",
    # Output state
    "_resolve_last_output_dir",
    "_read_result_json",
    "_update_preprocessing_state",
    "_format_next_steps",
)


def test_skill_orchestration_re_exports_share_identity_with_bot_core():
    """Every previously-public symbol must resolve to the *same object*
    when looked up via ``bot.core`` or via ``bot.skill_orchestration``."""
    import bot.core
    import bot.skill_orchestration

    missing_on_skill_orch = [
        name for name in SKILL_ORCH_REEXPORTS
        if not hasattr(bot.skill_orchestration, name)
    ]
    assert not missing_on_skill_orch, (
        f"Missing on bot.skill_orchestration: {missing_on_skill_orch}"
    )

    missing_on_core = [
        name for name in SKILL_ORCH_REEXPORTS
        if not hasattr(bot.core, name)
    ]
    assert not missing_on_core, (
        f"Missing on bot.core (re-export): {missing_on_core}"
    )

    mismatched_identity = [
        name for name in SKILL_ORCH_REEXPORTS
        if getattr(bot.core, name) is not getattr(bot.skill_orchestration, name)
    ]
    assert not mismatched_identity, (
        f"Parallel copies (must be same object): {mismatched_identity}"
    )


# ---------------------------------------------------------------------------
# T2 S7 — _auto_capture_dataset lands at session namespace (production trigger #2)
# ---------------------------------------------------------------------------


import pytest
import pytest_asyncio
import sqlalchemy as sa


@pytest_asyncio.fixture
async def memory_store(tmp_path, monkeypatch):
    """Real CompatMemoryStore wired into bot.core.memory_store, the global
    that _auto_capture_dataset reads via late binding."""
    from omicsclaw.memory.compat import CompatMemoryStore
    import bot.core

    store = CompatMemoryStore(database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await store.initialize()
    monkeypatch.setattr(bot.core, "memory_store", store)
    try:
        yield store
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_auto_capture_dataset_lands_in_session_namespace(memory_store, tmp_path):
    """When a skill processes a dataset file, the bot's auto-capture
    helper must persist a `dataset://...` row in the running session's
    namespace — not silently leak to `__shared__` (D5 fix).

    Existing tests for skill orchestration monkeypatch `_auto_capture_dataset`
    to a no-op; this is the first behavior-level coverage of the real
    function. A non-h5ad file is fine — the function tolerates failed
    h5py introspection by leaving n_obs/n_vars as None.
    """
    from bot.skill_orchestration import _auto_capture_dataset
    from omicsclaw.memory.models import Path

    session = await memory_store.create_session("alice", "telegram")

    # A plain text file, not under OMICSCLAW_DIR — _auto_capture_dataset
    # falls back to using just the basename for the URI path.
    fake_dataset = tmp_path / "sample.h5ad"
    fake_dataset.write_text("(not real h5ad payload)")

    await _auto_capture_dataset(
        session_id=session.session_id,
        input_path=str(fake_dataset),
        data_type="h5ad",
    )

    async with memory_store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(Path.domain == "dataset")
            )
        ).scalars().all()

    namespaces = {r.namespace for r in rows}
    paths = {r.path for r in rows}

    assert "telegram/alice" in namespaces, (
        f"auto-capture did not land in session namespace; got namespaces={namespaces}"
    )
    assert "__shared__" not in namespaces, (
        f"auto-capture leaked into __shared__ — D5 silent fallback regressed"
    )
    assert any("sample.h5ad" in p for p in paths), (
        f"dataset URI not derived from filename; got paths={paths}"
    )


@pytest.mark.asyncio
async def test_auto_capture_dataset_skips_when_session_missing(
    memory_store, tmp_path
):
    """If a skill execution races ahead of session creation, auto-capture
    must NOT silently land the dataset URI in __shared__ — D5's fix
    raises LookupError from _client_for_session, and _auto_capture_dataset
    swallows it via its broad try/except. The result: a logged warning,
    no row written anywhere."""
    from bot.skill_orchestration import _auto_capture_dataset
    from omicsclaw.memory.models import Path

    fake_dataset = tmp_path / "orphan.h5ad"
    fake_dataset.write_text("x")

    # Pass a session_id that was never created. Pre-D5 fix this would
    # have written to __shared__; post-fix it must skip silently.
    await _auto_capture_dataset(
        session_id="nonexistent-session",
        input_path=str(fake_dataset),
        data_type="h5ad",
    )

    async with memory_store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(Path.domain == "dataset")
            )
        ).scalars().all()
    assert rows == [], (
        f"auto-capture leaked a row despite missing session: "
        f"{[(r.namespace, r.path) for r in rows]}"
    )

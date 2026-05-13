"""Backward-compat contract for bot.tool_executors.

The module collects the 24 ``execute_*`` async tool implementations + the
dispatch table builder, carved out of bot/core.py per ADR 0001 (#120).
External tests (``tests/test_bot_completion_messages.py``,
``tests/test_skill_listing.py``) import these names from ``bot.core``;
this identity test guarantees the two paths point at the same callable.
"""

from __future__ import annotations


TOOL_EXECUTORS_REEXPORTS = (
    # 24 execute_* async functions
    "execute_omicsclaw",
    "execute_replot_skill",
    "execute_save_file",
    "execute_write_file",
    "execute_generate_audio",
    "execute_parse_literature",
    "execute_fetch_geo_metadata",
    "execute_list_directory",
    "execute_inspect_file",
    "execute_inspect_data",
    "execute_make_directory",
    "execute_move_file",
    "execute_remove_file",
    "execute_get_file_size",
    "execute_remember",
    "execute_recall",
    "execute_forget",
    "execute_read_knowhow",
    "execute_consult_knowledge",
    "execute_resolve_capability",
    "execute_list_skills_in_domain",
    "execute_create_omics_skill",
    "execute_web_method_search",
    "execute_custom_analysis_execute",
    # Dispatch surface
    "_available_tool_executors",
    "_build_tool_runtime",
    "get_tool_runtime",
    "get_tool_executors",
)


def test_tool_executors_re_exports_share_identity_with_bot_core():
    """Every previously-public symbol must resolve to the *same object*
    when looked up via ``bot.core`` or via ``bot.tool_executors``."""
    import bot.core
    import bot.tool_executors

    missing_on_tool_exec = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if not hasattr(bot.tool_executors, name)
    ]
    assert not missing_on_tool_exec, (
        f"Missing on bot.tool_executors: {missing_on_tool_exec}"
    )

    missing_on_core = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if not hasattr(bot.core, name)
    ]
    assert not missing_on_core, (
        f"Missing on bot.core (re-export): {missing_on_core}"
    )

    mismatched_identity = [
        name for name in TOOL_EXECUTORS_REEXPORTS
        if getattr(bot.core, name) is not getattr(bot.tool_executors, name)
    ]
    assert not mismatched_identity, (
        f"Parallel copies (must be same object): {mismatched_identity}"
    )


# ---------------------------------------------------------------------------
# T2 S1 — bot's manage_memory tool path lands writes in session namespace
# ---------------------------------------------------------------------------


import pytest
import pytest_asyncio
import sqlalchemy as sa


@pytest_asyncio.fixture
async def memory_store(tmp_path, monkeypatch):
    """A real CompatMemoryStore wired to ``bot.core.memory_store``.

    The bot tool ``execute_remember`` reads ``_core.memory_store`` (late
    binding from bot.core's module-level global), so the test must mutate
    that global to inject a temp-DB store. ``monkeypatch`` restores it
    cleanly.
    """
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
async def test_execute_remember_lands_in_session_namespace(memory_store):
    """When the LLM tool ``execute_remember`` saves a preference for an
    active Telegram session, the resulting row must land in the
    session-derived namespace ``f"{platform}/{user_id}"`` — the
    production guarantee that two bot users cannot see each other's
    preferences. This test exercises the real bot→CompatMemoryStore→
    MemoryEngine→DB path; the only thing it skips is the LLM emitting
    the tool call."""
    from bot.tool_executors import execute_remember
    from omicsclaw.memory.models import Path

    session = await memory_store.create_session("alice", "telegram")

    result = await execute_remember(
        args={
            "memory_type": "preference",
            "domain": "global",
            "key": "qc_threshold",
            "value": "20%",
        },
        session_id=session.session_id,
    )

    assert "✓" in result or "saved" in result.lower(), (
        f"execute_remember reported failure: {result!r}"
    )

    async with memory_store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "preference",
                    Path.path == "global/qc_threshold",
                )
            )
        ).scalars().all()

    assert len(rows) == 1, (
        f"Expected exactly 1 path row, got {len(rows)}: "
        f"{[(r.namespace, r.domain, r.path) for r in rows]}"
    )
    assert rows[0].namespace == "telegram/alice", (
        f"Preference landed in {rows[0].namespace!r}; expected 'telegram/alice'"
    )


@pytest.mark.asyncio
async def test_execute_remember_preference_update_versions_existing_value(
    memory_store,
):
    """User says 'remember reply in Chinese' then later 'change to English'.
    Both messages route to ``execute_remember`` with the same
    ``(memory_type=preference, domain=global, key=language)`` triple but
    different ``value``. The desktop preference panel must reflect the new
    value, not the old one.

    Contract:
      - Exactly one Path row at ``preference/global/language``
      - Path resolves to a node whose **active** memory carries the new
        value (``English``)
      - The old value (``Chinese``) is preserved as a deprecated row in
        the chain (preference://* lives in VERSIONED_PREFIXES so the
        rollback UI can restore it)

    Regression: the user reported the desktop preference panel didn't
    update after the second tool call. If ``execute_remember`` no-ops on
    the second call (e.g., dedupe on URI without re-reading content) or
    if the path's edge_id never repoints to the new active memory, the
    panel keeps showing the stale value.
    """
    from bot.tool_executors import execute_remember
    from omicsclaw.memory.models import Edge, Memory, Path

    session = await memory_store.create_session("alice", "telegram")

    result_v1 = await execute_remember(
        args={
            "memory_type": "preference",
            "domain": "global",
            "key": "language",
            "value": "Chinese",
        },
        session_id=session.session_id,
    )
    assert "✓" in result_v1 or "saved" in result_v1.lower(), (
        f"v1 save failed: {result_v1!r}"
    )

    result_v2 = await execute_remember(
        args={
            "memory_type": "preference",
            "domain": "global",
            "key": "language",
            "value": "English",
        },
        session_id=session.session_id,
    )
    assert "✓" in result_v2 or "saved" in result_v2.lower(), (
        f"v2 save failed: {result_v2!r}"
    )

    async with memory_store._db.session() as s:
        path_rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "preference",
                    Path.path == "global/language",
                    Path.namespace == "telegram/alice",
                )
            )
        ).scalars().all()
        assert len(path_rows) == 1, (
            f"Expected exactly one preference/global/language path; got "
            f"{len(path_rows)}. The bot is creating a sibling instead of "
            f"updating in place."
        )

        edge = (
            await s.execute(sa.select(Edge).where(Edge.id == path_rows[0].edge_id))
        ).scalar_one()

        memories = (
            await s.execute(
                sa.select(Memory)
                .where(Memory.node_uuid == edge.child_uuid)
                .order_by(Memory.id)
            )
        ).scalars().all()

    active = [m for m in memories if not m.deprecated]
    assert len(active) == 1, (
        f"Expected exactly one active memory after the second remember; "
        f"got {len(active)}. Active rows: "
        f"{[(m.id, m.deprecated, m.content[:60]) for m in active]}"
    )
    assert "English" in active[0].content, (
        f"Active preference still has the old value. Active content: "
        f"{active[0].content!r} (expected 'English' to appear). This is "
        f"the user-visible bug: the desktop panel keeps showing Chinese "
        f"after the user asks the bot to switch to English."
    )

    deprecated = [m for m in memories if m.deprecated]
    assert len(deprecated) == 1, (
        f"Expected exactly one deprecated memory (the prior Chinese row "
        f"so the rollback UI can restore it); got {len(deprecated)}."
    )
    assert "Chinese" in deprecated[0].content


def test_tool_executors_dispatch_table_lists_all_24_executors():
    """``_available_tool_executors()`` returns the full dispatch map.
    The lazy ``bot.core.TOOL_EXECUTORS`` attribute also adds the
    engineering tool executors (file_read / write_file / list_directory /
    edit_file / shell). Pin the count so an accidental dropped registration
    (e.g. typo on ``execute_X.__name__``) is caught."""
    import bot.tool_executors

    table = bot.tool_executors._available_tool_executors()
    # 24 native executors are mapped; engineering tools are added on top
    # by ``executors.update(build_engineering_tool_executors(...))``.
    assert len(table) >= 24
    # Spot-check a few canonical entries
    for name in ("omicsclaw", "save_file", "inspect_data", "remember", "consult_knowledge"):
        assert name in table, f"Tool name '{name}' missing from dispatch table"


# ---------------------------------------------------------------------------
# Regression: path_validation helpers must be importable from bot.tool_executors
# ---------------------------------------------------------------------------


PATH_VALIDATION_SYMBOLS = (
    "_ensure_trusted_dirs",
    "TRUSTED_DATA_DIRS",
    "validate_input_path",
    "discover_file",
    # Also missed by the carve-out — used by execute_save_file /
    # execute_write_file / execute_generate_audio (lines ~758, 787, 814).
    "resolve_dest",
    "sanitize_filename",
    "validate_path",
)


# Symbols from bot.core / bot.skill_orchestration / preflight.sc_batch that
# the carve-out left as bare references inside ``execute_*`` bodies. Each
# one is an unexercised NameError waiting for the right tool call. Pinning
# them at module level catches the whole class of bug, not just the
# _ensure_trusted_dirs incident.
CARVED_OUT_SIBLING_SYMBOLS = (
    # bot.core
    "DEEP_LEARNING_METHODS",
    "OMICSCLAW_PY",
    "_path_names",
    # bot.skill_orchestration
    "_infer_skill_for_method",
    "_run_skill_via_shared_runner",
    # omicsclaw.runtime.preflight.sc_batch
    "_resolve_requested_batch_key",
)


def test_tool_executors_imports_path_validation_helpers():
    """bot.tool_executors uses ``_ensure_trusted_dirs`` / ``TRUSTED_DATA_DIRS``
    / ``validate_input_path`` / ``discover_file`` in several executors (lines
    ~140, 224, 1012, 1057, 1088, 1277, 1307, 1334, 1361, 1666, 1786, 1788 at
    the time of writing). When the module was carved out of bot.core per
    ADR 0001, the import of these names was left behind in bot.core. Every
    call into ``execute_omicsclaw`` with ``mode='file'`` (no staged input)
    fires ``_ensure_trusted_dirs()`` and raises ``NameError`` instead of
    returning the friendly 'place your file in a data directory' message.

    Pin the contract: the four names must resolve as module-level
    attributes on bot.tool_executors."""
    import bot.core  # noqa: F401 — load bot.core first (production order)
    import bot.tool_executors

    missing = [
        name for name in PATH_VALIDATION_SYMBOLS
        if not hasattr(bot.tool_executors, name)
    ]
    assert not missing, (
        f"bot.tool_executors is missing path_validation symbols: {missing}. "
        f"Add them to the `from bot.path_validation import ...` block."
    )


def test_tool_executors_imports_carved_out_sibling_helpers():
    """Same bug class as ``test_tool_executors_imports_path_validation_helpers``,
    but covers the carve-out leftovers from bot.core / bot.skill_orchestration
    / preflight.sc_batch. Each is referenced bare inside an ``execute_*``
    body and would raise NameError on the first call that exercises it
    (pyflakes audit on 2026-05-13)."""
    import bot.core  # noqa: F401 — load bot.core first (production order)
    import bot.tool_executors

    missing = [
        name for name in CARVED_OUT_SIBLING_SYMBOLS
        if not hasattr(bot.tool_executors, name)
    ]
    assert not missing, (
        f"bot.tool_executors is missing carve-out sibling symbols: {missing}. "
        f"Each one is an unexercised NameError waiting for the right tool "
        f"call. Add them to the existing per-module import blocks at the "
        f"top of bot/tool_executors.py."
    )


def test_trusted_data_dirs_mutation_visible_to_tool_executors():
    """``_ensure_trusted_dirs()`` populates ``bot.path_validation.TRUSTED_DATA_DIRS``,
    but if it *rebinds* the global instead of mutating in place, modules
    that imported the name (bot.tool_executors, bot.core,
    omicsclaw.app.server) stay stuck on the original empty list.

    Symptom observed via the executor probe on 2026-05-13:
        Trusted data dirs: ['/.../data', '/.../examples', ...]   (path_validation)
        Access denied: /.../data is not in trusted directories ()  (tool_executors)

    omicsclaw/app/server.py:686-691 also relies on appending to
    ``bot.core.TRUSTED_DATA_DIRS`` being visible to ``validate_input_path``
    — same root cause.

    Contract: after the helper runs, every module's view is non-empty and
    is the *same list object* as ``bot.path_validation.TRUSTED_DATA_DIRS``."""
    import bot.core
    import bot.path_validation
    import bot.tool_executors

    bot.path_validation._ensure_trusted_dirs()

    pv = bot.path_validation.TRUSTED_DATA_DIRS
    assert pv, "Sanity: path_validation.TRUSTED_DATA_DIRS unexpectedly empty after _ensure"

    assert bot.tool_executors.TRUSTED_DATA_DIRS, (
        "bot.tool_executors.TRUSTED_DATA_DIRS is empty after _ensure_trusted_dirs() "
        "ran in bot.path_validation. The helper rebinds the global instead of "
        "mutating in place — fix it with `TRUSTED_DATA_DIRS[:] = _build_trusted_dirs()`."
    )
    assert bot.tool_executors.TRUSTED_DATA_DIRS is pv, (
        "bot.tool_executors.TRUSTED_DATA_DIRS diverged from "
        "bot.path_validation.TRUSTED_DATA_DIRS — they must be the same list "
        "object so server.py's runtime append() is visible to validate_input_path."
    )
    assert bot.core.TRUSTED_DATA_DIRS is pv, (
        "bot.core.TRUSTED_DATA_DIRS diverged from path_validation. server.py "
        "appends workspace dirs to bot.core.TRUSTED_DATA_DIRS — that mutation "
        "must propagate to validate_input_path."
    )


@pytest.mark.asyncio
async def test_execute_list_directory_allows_data_dir_after_ensure():
    """Behavioral consequence of the rebind bug: ``execute_list_directory``
    rejects the legit DATA_DIR with 'Access denied ... is not in trusted
    directories ()' because its module-local TRUSTED_DATA_DIRS view is still
    the empty list. Once the helper mutates in place, DATA_DIR is trusted
    and the listing proceeds."""
    import bot.core
    from bot.tool_executors import execute_list_directory

    result = await execute_list_directory({"path": str(bot.core.DATA_DIR)})
    assert "Access denied" not in result, (
        f"execute_list_directory denied access to DATA_DIR — the trusted-dirs "
        f"check is reading a stale empty list. Got: {result!r}"
    )


@pytest.mark.asyncio
async def test_execute_omicsclaw_file_mode_without_input_returns_friendly_error():
    """End-to-end regression for the 2026-05-13 incident: user invoked
    ``omicsclaw({"mode": "file", "skill": "sc-standardize-input", ...})``
    and got ``NameError: name '_ensure_trusted_dirs' is not defined``
    instead of the documented 'no input file' guidance.

    Contract: when ``mode='file'`` and nothing is staged for the session,
    the executor returns a human-readable error string starting with
    'No input file available' — never raises NameError."""
    import bot.core  # noqa: F401 — load bot.core first (production order)
    from bot.tool_executors import execute_omicsclaw

    result = await execute_omicsclaw(
        args={"mode": "file", "skill": "sc-standardize-input"},
        session_id="missing-session-for-regression-test",
    )
    assert isinstance(result, str), f"expected str, got {type(result).__name__}"
    assert "No input file available" in result, (
        f"execute_omicsclaw did not return the friendly no-input-file guidance; "
        f"got: {result!r}"
    )

"""Tests for the CLI/TUI `/memory remember|recall|search` graph subcommands.

These exercise ``build_graph_memory_command_view`` — the async helper that
binds CLI/TUI to the graph MemoryClient using
``cli_namespace_from_workspace(workspace_dir)`` as the namespace.

Each test isolates state via ``OMICSCLAW_MEMORY_DB_URL`` + ``close_db()``
so the singleton MemoryEngine is rebuilt against a fresh temp DB.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def isolated_memory_db(tmp_path, monkeypatch):
    """Point the singleton memory engine at a fresh per-test DB."""
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/cli_graph.db"
    )
    yield tmp_path


@pytest.mark.asyncio
async def test_recall_on_empty_namespace_returns_clean_miss(
    isolated_memory_db, tmp_path
):
    """Tracer bullet: a recall against an empty graph reports a clean miss."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    db = get_engine_db()
    await db.init_db()
    try:
        view = await build_graph_memory_command_view(
            "recall dataset://pbmc.h5ad",
            workspace_dir=str(tmp_path),
        )
    finally:
        await close_db()

    assert view.success is True
    assert "no memory" in view.output_text.lower()
    assert "dataset://pbmc.h5ad" in view.output_text


@pytest.mark.asyncio
async def test_remember_then_recall_round_trip(isolated_memory_db, tmp_path):
    """`remember` writes to the workspace namespace; `recall` reads it back."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    db = get_engine_db()
    await db.init_db()
    try:
        write_view = await build_graph_memory_command_view(
            'remember dataset://pbmc.h5ad "10x PBMC, mito 20%"',
            workspace_dir=str(tmp_path),
        )
        read_view = await build_graph_memory_command_view(
            "recall dataset://pbmc.h5ad",
            workspace_dir=str(tmp_path),
        )
    finally:
        await close_db()

    assert write_view.success is True
    assert "remembered" in write_view.output_text.lower()
    assert "dataset://pbmc.h5ad" in write_view.output_text

    assert read_view.success is True
    assert "10x PBMC, mito 20%" in read_view.output_text


@pytest.mark.asyncio
async def test_recall_isolated_across_workspaces(isolated_memory_db, tmp_path):
    """Two different workspaces map to two namespaces — no cross-read."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    ws_a = tmp_path / "ws_a"
    ws_b = tmp_path / "ws_b"
    ws_a.mkdir()
    ws_b.mkdir()

    db = get_engine_db()
    await db.init_db()
    try:
        await build_graph_memory_command_view(
            'remember dataset://pbmc.h5ad "from ws_a"',
            workspace_dir=str(ws_a),
        )
        miss = await build_graph_memory_command_view(
            "recall dataset://pbmc.h5ad",
            workspace_dir=str(ws_b),
        )
    finally:
        await close_db()

    assert miss.success is True
    assert "no memory" in miss.output_text.lower()
    assert "from ws_a" not in miss.output_text


@pytest.mark.asyncio
async def test_search_finds_remembered_content(isolated_memory_db, tmp_path):
    """`search` returns FTS hits within the workspace namespace."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    db = get_engine_db()
    await db.init_db()
    try:
        await build_graph_memory_command_view(
            'remember dataset://pbmc.h5ad "10x PBMC sample with mitochondrial cutoff"',
            workspace_dir=str(tmp_path),
        )
        view = await build_graph_memory_command_view(
            "search mitochondrial",
            workspace_dir=str(tmp_path),
        )
    finally:
        await close_db()

    assert view.success is True
    assert "dataset://pbmc.h5ad" in view.output_text


@pytest.mark.asyncio
async def test_remember_rejects_malformed_uri(isolated_memory_db, tmp_path):
    """A bad URI fails fast with an actionable error, not a stacktrace."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    db = get_engine_db()
    await db.init_db()
    try:
        view = await build_graph_memory_command_view(
            'remember not-a-uri "content"',
            workspace_dir=str(tmp_path),
        )
    finally:
        await close_db()

    assert view.success is False
    assert "uri" in view.output_text.lower()


@pytest.mark.asyncio
async def test_recall_missing_arg_shows_usage(isolated_memory_db, tmp_path):
    """`recall` with no URI prints usage rather than crashing."""
    from omicsclaw.interactive._memory_command_support import (
        build_graph_memory_command_view,
    )
    from omicsclaw.memory import close_db, get_engine_db

    db = get_engine_db()
    await db.init_db()
    try:
        view = await build_graph_memory_command_view(
            "recall",
            workspace_dir=str(tmp_path),
        )
    finally:
        await close_db()

    assert view.success is False
    assert "usage" in view.output_text.lower()


def test_bare_memory_help_lists_graph_subcommands(tmp_path):
    """Bare `/memory` help text mentions the new graph subcommands."""
    from omicsclaw.interactive._memory_command_support import (
        build_memory_command_view,
    )

    view = build_memory_command_view(
        "",
        session_metadata={},
        workspace_dir=str(tmp_path),
    )
    text = view.output_text.lower()
    assert "remember" in text
    assert "recall" in text
    assert "search" in text

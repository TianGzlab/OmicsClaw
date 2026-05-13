"""Tests for surface-namespace helpers (PR #5).

Each surface (CLI, Desktop, Bot) derives its namespace differently:

  - CLI/TUI:    absolute workspace path (cwd or --workspace flag)
  - Desktop:    OMICSCLAW_DESKTOP_USER_ID, falling back to "app/desktop_user"
  - Bot:        f"{platform}/{user_id}" (already done in CompatMemoryStore)

OMICSCLAW_DESKTOP_LAUNCH_ID is a *separate* per-launch random token used
only by the Electron shell's /health probe (cross-launch port collision
detection). It deliberately does NOT participate in namespace derivation
— mixing it in would create a fresh empty partition on every launch
and orphan previous writes.

These helpers live in ``omicsclaw.memory`` so any surface can derive a
namespace consistently. Bot's logic stays in CompatMemoryStore because
it needs session lookup.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ----------------------------------------------------------------------
# CLI namespace derivation
# ----------------------------------------------------------------------


def test_cli_namespace_from_workspace_uses_absolute_path(tmp_path):
    from omicsclaw.memory import cli_namespace_from_workspace

    ns = cli_namespace_from_workspace(str(tmp_path))
    assert ns == str(tmp_path.resolve())


def test_cli_namespace_from_workspace_handles_relative_path(tmp_path, monkeypatch):
    """A relative path is resolved against the current working directory."""
    from omicsclaw.memory import cli_namespace_from_workspace

    monkeypatch.chdir(tmp_path)
    (tmp_path / "subdir").mkdir()

    ns = cli_namespace_from_workspace("subdir")
    assert ns == str((tmp_path / "subdir").resolve())


def test_cli_namespace_defaults_to_cwd(tmp_path, monkeypatch):
    """No argument → use the current working directory."""
    from omicsclaw.memory import cli_namespace_from_workspace

    monkeypatch.chdir(tmp_path)

    ns = cli_namespace_from_workspace(None)
    assert ns == str(tmp_path.resolve())


def test_cli_namespace_strips_trailing_slash(tmp_path):
    from omicsclaw.memory import cli_namespace_from_workspace

    # Path("/foo/").resolve() drops the trailing slash, so this is just a
    # documentation test that the helper produces canonical paths.
    ns = cli_namespace_from_workspace(str(tmp_path) + "/")
    assert not ns.endswith("/") or ns == "/"


# ----------------------------------------------------------------------
# Desktop namespace derivation
# ----------------------------------------------------------------------


def test_desktop_namespace_uses_user_id_when_set(monkeypatch):
    from omicsclaw.memory import desktop_namespace

    monkeypatch.setenv("OMICSCLAW_DESKTOP_USER_ID", "alice")
    monkeypatch.delenv("OMICSCLAW_DESKTOP_LAUNCH_ID", raising=False)
    assert desktop_namespace() == "app/alice"


def test_desktop_namespace_default_when_no_user_id(monkeypatch):
    from omicsclaw.memory import desktop_namespace

    monkeypatch.delenv("OMICSCLAW_DESKTOP_USER_ID", raising=False)
    monkeypatch.delenv("OMICSCLAW_DESKTOP_LAUNCH_ID", raising=False)
    assert desktop_namespace() == "app/desktop_user"


def test_desktop_namespace_strips_whitespace(monkeypatch):
    from omicsclaw.memory import desktop_namespace

    monkeypatch.setenv("OMICSCLAW_DESKTOP_USER_ID", "  bob  ")
    assert desktop_namespace() == "app/bob"


def test_desktop_namespace_ignores_launch_id(monkeypatch):
    """LAUNCH_ID is a per-launch health-check token, not a namespace.

    Regression test for memory_bug.png: with the old behavior, every
    Electron launch would generate a random UUID launch_id and the
    desktop namespace would become ``app/<random-uuid>`` — orphaning
    all data written under the previous launch's namespace.
    """
    from omicsclaw.memory import desktop_namespace

    monkeypatch.delenv("OMICSCLAW_DESKTOP_USER_ID", raising=False)
    monkeypatch.setenv("OMICSCLAW_DESKTOP_LAUNCH_ID", "random-uuid-12345")
    assert desktop_namespace() == "app/desktop_user"


# ----------------------------------------------------------------------
# Memory client factory
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_client_returns_namespace_bound_client(tmp_path, monkeypatch):
    """``get_memory_client(namespace=...)`` returns a lightweight MemoryClient
    sharing the singleton engine, bound to the given namespace."""
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db"
    )
    from omicsclaw.memory import close_db, get_memory_client, get_memory_engine

    engine = get_memory_engine()
    await engine.db.init_db()

    try:
        client = get_memory_client(namespace="tg/userA")
        assert client.namespace == "tg/userA"

        # Two clients with different namespaces share the same engine.
        client2 = get_memory_client(namespace="tg/userB")
        assert client2.namespace == "tg/userB"
        assert client._engine is client2._engine
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_get_review_log_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db"
    )
    from omicsclaw.memory import close_db, get_engine_db, get_review_log

    db = get_engine_db()
    await db.init_db()

    try:
        log1 = get_review_log()
        log2 = get_review_log()
        assert log1 is log2
    finally:
        await close_db()

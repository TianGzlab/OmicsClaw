"""Regression tests for `_expand_sqlite_home` in `omicsclaw.memory.database`.

Background — the onboard wizard used to write
``OMICSCLAW_MEMORY_DB_URL=sqlite+aiosqlite:///~/.config/omicsclaw/memory.db``
into ``.env``. aiosqlite does not expand ``~`` and silently opened a
literal ``~`` directory relative to the process cwd, creating a ghost
database invisible to the rest of the system. These tests pin the
expansion contract so the regression cannot return.
"""

from __future__ import annotations

import os
from pathlib import Path

from omicsclaw.memory import database as database_mod
from omicsclaw.memory.database import DatabaseManager, _expand_sqlite_home


def test_expand_sqlite_home_with_leading_tilde() -> None:
    raw = "sqlite+aiosqlite:///~/.config/omicsclaw/memory.db"
    expanded = _expand_sqlite_home(raw)
    home = str(Path.home())
    assert expanded == f"sqlite+aiosqlite:///{home}/.config/omicsclaw/memory.db"
    # Path inside the URL must be absolute (starts with '/').
    assert expanded.split("///", 1)[1].startswith("/")


def test_expand_sqlite_home_absolute_url_is_unchanged() -> None:
    raw = "sqlite+aiosqlite:////home/alice/db.sqlite"
    assert _expand_sqlite_home(raw) == raw


def test_expand_sqlite_home_relative_url_is_unchanged() -> None:
    # Relative paths without ~ are caller's responsibility — we don't touch them.
    raw = "sqlite+aiosqlite:///./relative.db"
    assert _expand_sqlite_home(raw) == raw


def test_expand_sqlite_home_in_memory_is_unchanged() -> None:
    assert _expand_sqlite_home("sqlite+aiosqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"
    assert _expand_sqlite_home("sqlite:///:memory:") == "sqlite:///:memory:"


def test_expand_sqlite_home_non_sqlite_is_unchanged() -> None:
    # Postgres URLs may contain ~ as part of a password or query string —
    # this helper only acts on sqlite, so the URL must round-trip.
    raw = "postgresql+asyncpg://user:p~assw0rd@host/db"
    assert _expand_sqlite_home(raw) == raw


def test_database_manager_expands_explicit_url(tmp_path, monkeypatch) -> None:
    # Direct caller (CompatMemoryStore-style) passing the URL bypasses
    # _get_database_url; __init__ must still expand for safety.
    monkeypatch.setenv("HOME", str(tmp_path))
    mgr = DatabaseManager("sqlite+aiosqlite:///~/scoped.db")
    assert mgr.database_url == f"sqlite+aiosqlite:///{tmp_path}/scoped.db"


def test_get_database_url_expands_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL",
        "sqlite+aiosqlite:///~/from_env.db",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    assert database_mod._get_database_url() == f"sqlite+aiosqlite:///{tmp_path}/from_env.db"


def test_get_database_url_default_url_has_no_tilde(monkeypatch) -> None:
    monkeypatch.delenv("OMICSCLAW_MEMORY_DB_URL", raising=False)
    url = database_mod._get_database_url()
    # Default already used Path.home() — expansion is a no-op but the
    # path must not start with literal ~.
    db_path = url.split("///", 1)[1]
    assert not db_path.startswith("~")
    assert os.path.isabs(db_path)

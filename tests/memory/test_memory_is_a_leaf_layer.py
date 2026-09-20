"""``omicsclaw/memory/`` may import ``omicsclaw.schema`` and ``omicsclaw.context``.

The one that matters is ``omicsclaw.entry``. This package exists to
satisfy that layer's ``SessionStore`` protocol, and the protocol is
structural precisely so the arrow keeps pointing one way: the entry layer
composes a store in, and the store knows nothing about the entry layer.

Importing it would look reasonable in a diff — ``Session`` is right
there, already has the five fields :class:`StoredSession` restates, and
reusing it would delete a file. It would also make the composition root
import the thing that imports the composition root, and the structural
twin is the price of not doing that.

*A whitelist, not a blacklist.* Naming what is forbidden means predicting
every package a future step adds; naming what is allowed does not.

*Relative imports are resolved.* ``from ..entry import Session`` leaves
the package, so the level is resolved to an absolute name before it is
judged.

**The last check is behavioural.** An ``ast`` walk cannot see a module
named as a string inside a function body, so
:func:`test_using_the_layer_does_not_pull_in_the_entry_layer` exercises
every real path in a fresh process and inspects :data:`sys.modules`
afterwards.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MEMORY_DIR = _REPO_ROOT / "omicsclaw" / "memory"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.context", "omicsclaw.memory")
"""``omicsclaw.context`` is allowed because ``CompactionState`` is what a
session carries between exchanges, and its own docstring names this layer
as one of the places it may live."""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.entry",
    "omicsclaw.skill",
    "omicsclaw.skills",
    "omicsclaw.engine",
    "omicsclaw.tools",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.runtime",
    "omicsclaw.surfaces",
)
"""Named as well as covered by the whitelist, so a reader sees the point.

``omicsclaw.entry`` is the dangerous one and the reason this file exists.
``omicsclaw.engine`` is the second: a store that summarised on write
would need a provider, and that is the compaction layer's job, not this
one's.
"""


def _modules() -> list[pathlib.Path]:
    return sorted(_MEMORY_DIR.rglob("*.py"))


def _imported_names(path: pathlib.Path) -> set[str]:
    """Every module name *path* imports, with relative levels resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = "omicsclaw.memory"
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0]
                names.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                names.add(node.module)
    return names


def test_the_package_has_modules_to_check() -> None:
    assert _modules(), "no modules found; the guard would pass vacuously"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_only_whitelisted_internal_packages_are_imported(
    path: pathlib.Path,
) -> None:
    offenders = {
        name
        for name in _imported_names(path)
        if name.startswith("omicsclaw")
        and not any(
            name == allowed or name.startswith(allowed + ".")
            for allowed in _ALLOWED_INTERNAL
        )
    }
    assert not offenders, f"{path.name} imports {sorted(offenders)}"


@pytest.mark.parametrize("forbidden", _TEMPTING_NEIGHBOURS)
def test_the_tempting_neighbours_stay_out(forbidden: str) -> None:
    for path in _modules():
        for name in _imported_names(path):
            assert not (
                name == forbidden or name.startswith(forbidden + ".")
            ), f"{path.name} imports {name}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_third_parties_stay_out(path: pathlib.Path) -> None:
    """The layer is standard library only.

    SQLite comes from ``sqlite3`` and the async hop from ``asyncio``; an
    optional driver that changed transaction semantics underneath a store
    would not be optional.
    """
    outsiders = {
        name.split(".")[0]
        for name in _imported_names(path)
        if not name.startswith("omicsclaw")
        and name.split(".")[0] not in sys.stdlib_module_names
    }
    assert not outsiders, f"{path.name} imports {sorted(outsiders)}"


def test_using_the_layer_does_not_pull_in_the_entry_layer() -> None:
    """Exercise every real path, then look at what got imported.

    A string-named late import inside a method is invisible to the ``ast``
    walk above, so this drives the store for real and checks
    :data:`sys.modules` in a fresh interpreter.
    """
    script = """
import asyncio, sys
from omicsclaw.memory import (
    Database, LongTermStore, MemoryEntry, Precis, SqliteSessionStore,
    StoredSession,
)
from omicsclaw.schema import Message, Role

async def main(tmp):
    db = Database()
    store = SqliteSessionStore(db)
    await store.save(StoredSession(
        session_id="s", history=(Message(role=Role.USER, content="hi"),)))
    await store.load("s")
    await store.list()
    await store.delete("s")
    lt = LongTermStore(db)
    eid = await lt.add(MemoryEntry(title="t", content="body", importance=3))
    await lt.get(eid)
    await lt.update(eid, content="other")
    await lt.search("other")
    await lt.list()
    await lt.touch(eid)
    await lt.soft_delete(eid)
    await lt.purge_expired()
    await Precis(lt, tmp).regenerate()
    db.close()

import tempfile, pathlib
with tempfile.TemporaryDirectory() as d:
    asyncio.run(main(pathlib.Path(d) / "MEMORY.md"))

leaked = sorted(
    m for m in sys.modules
    if m == "omicsclaw.entry" or m.startswith("omicsclaw.entry.")
)
print(";".join(leaked))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"leaked: {result.stdout.strip()}"

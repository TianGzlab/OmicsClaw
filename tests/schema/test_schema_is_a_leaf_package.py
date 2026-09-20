"""The schema package must stay importable by everything (ADR 0077).

Its value is that provider, agent loop, tool executor, transcript store,
compaction, and every Surface can depend on it without depending on each
other. One ``from omicsclaw.runtime.agent import ...`` inside it would
turn the shared contract into a dependency on the loop and quietly
reintroduce the coupling it exists to remove.

This is a static check on purpose: it fails on the import *statement*,
before a cycle has a chance to become a runtime import error somewhere
far away.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _REPO_ROOT / "omicsclaw" / "schema"

_ALLOWED_INTERNAL_PREFIX = "omicsclaw.schema"


def _module_paths() -> list[pathlib.Path]:
    return sorted(_SCHEMA_DIR.glob("*.py"))


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside the package
                continue
            if node.module:
                names.append(node.module)
    return names


def test_the_package_has_modules_to_check():
    assert _module_paths(), f"no schema modules found under {_SCHEMA_DIR}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_schema_module_imports_nothing_from_omicsclaw(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        name
        for name in _imported_modules(tree)
        if name.split(".")[0] == "omicsclaw"
        and not name.startswith(_ALLOWED_INTERNAL_PREFIX)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — the schema package is a leaf and "
        "must depend only on the standard library"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_schema_module_uses_no_third_party_dependency(path: pathlib.Path):
    """Stdlib only, so importing the contract can never need an optional extra."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    third_party = {
        "openai", "pydantic", "requests", "httpx", "anyio", "numpy", "pandas",
    }
    offenders = [
        name for name in _imported_modules(tree) if name.split(".")[0] in third_party
    ]

    assert not offenders, f"{path.name} imports {offenders}"


def test_importing_the_package_drags_in_no_other_omicsclaw_module():
    """Guards the real runtime cost, not just the source text.

    This is the assertion that forced the package out of
    ``omicsclaw/runtime/`` (ADR 0077). Under that path it failed: the
    parent ``omicsclaw/runtime/__init__.py`` eagerly re-exports the query
    engine, so importing the contract loaded 166 modules across five
    unrelated packages. As a top-level peer its only parent is the
    13-line lazy ``omicsclaw/__init__.py``, so the leaf property is now
    real rather than something a test has to stub its way around.
    """
    import subprocess
    import sys

    probe = (
        "import sys, omicsclaw.schema as schema;"
        "call = schema.ToolCall(id='c', name='t', arguments='{\"a\":1}');"
        "msg = schema.Message.assistant('ok', tool_calls=[call]);"
        "assert msg.is_action and call.parsed_arguments() == {'a': 1};"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    # ``omicsclaw.version`` is the one permitted straggler: the lazy
    # top-level ``__init__`` imports it for ``__version__``.
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the schema package dragged in {result.stdout.strip()}"
    )

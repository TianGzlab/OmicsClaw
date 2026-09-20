"""The engine may depend on schema and provider, and on nothing else.

Plan 0027 §9, criterion 4. Mirrors
``tests/schema/test_schema_is_a_leaf_package.py`` and its provider
counterpart: the schema package is a leaf, the provider layer is
leaf-adjacent, and this layer is leaf-adjacent to both.

The rule is what makes the rebuild a rebuild rather than a rename. One
``from omicsclaw.runtime...`` here and the new loop would drag the legacy
agent stack in behind it — which is exactly the state plan 0027 §4 Q2
found the old ``omicsclaw/engine/`` in, where importing anything from the
package executed ``import openai`` at module scope and failed outright in
an environment with no vendor SDK installed. ``omicsclaw.providers``
(plural) is forbidden for the same reason plan 0026 forbids it: it is
imported by ``runtime/agent/query_engine.py``, so an edge to it would put
a cycle one refactor away.

Static, like both counterparts: it fails on the import *statement*,
before a cycle becomes a runtime error somewhere far away. The two
subprocess probes at the end check the property itself rather than the
proxy.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENGINE_DIR = _REPO_ROOT / "omicsclaw" / "engine"

_ALLOWED_INTERNAL_PREFIXES = (
    "omicsclaw.schema",
    "omicsclaw.provider",
    "omicsclaw.engine",
)

_FORBIDDEN_THIRD_PARTY = {
    "openai",
    "anthropic",
    "httpx",
    "requests",
    "pydantic",
    "langchain",
    "langchain_openai",
    "langchain_anthropic",
    "litellm",
    "numpy",
    "pandas",
}


def _module_paths() -> list[pathlib.Path]:
    return sorted(_ENGINE_DIR.glob("*.py"))


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
    assert _module_paths(), f"no engine modules found under {_ENGINE_DIR}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_an_engine_module_imports_no_other_omicsclaw_package(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        name
        for name in _imported_modules(tree)
        if name.split(".")[0] == "omicsclaw"
        and not name.startswith(_ALLOWED_INTERNAL_PREFIXES)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — the engine may depend only on "
        "omicsclaw.schema, omicsclaw.provider and the standard library"
    )


@pytest.mark.parametrize(
    "forbidden",
    ["omicsclaw.runtime", "omicsclaw.providers", "omicsclaw.memory"],
)
def test_the_named_neighbours_appear_nowhere_in_the_package(forbidden: str):
    """The three edges that would actually be tempting to draw.

    ``runtime`` holds the legacy loop this layer replaces, ``providers``
    (plural) is the package plan 0026 is folding in, and ``memory`` is
    step 6's business. Each is checked by name as well as by the rule
    above, so a future reader sees which imports the rule is *for*.
    """
    offenders = [
        path.name
        for path in _module_paths()
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for name in _imported_modules(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            )
        )
    ]

    assert not offenders, f"{offenders} import {forbidden}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_an_engine_module_uses_no_third_party_dependency(path: pathlib.Path):
    """Stdlib only, so importing the loop never needs an optional extra.

    A vendor SDK belongs to one adapter module inside
    ``omicsclaw/provider``; the loop must not name one at all, or the
    layering test above would be enforcing a rule the import graph had
    already broken underneath it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        name
        for name in _imported_modules(tree)
        if name.split(".")[0] in _FORBIDDEN_THIRD_PARTY
    ]

    assert not offenders, f"{path.name} imports {offenders}"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    """Guards the real runtime cost, not just the source text.

    ``omicsclaw.version`` is the one permitted straggler: the lazy
    top-level ``__init__`` imports it for ``__version__``.
    """
    source = (
        "import sys, omicsclaw.engine as engine;"
        "assert engine.AgentEngine is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.engine')"
        " and not m.startswith('omicsclaw.provider')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the engine dragged in {result.stdout.strip()}"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_every_engine_module_imports_with_no_vendor_sdk_installed(
    path: pathlib.Path,
):
    """The property the SDK ban exists to protect, checked directly.

    This is the regression that named the whole eviction task: the
    package that used to occupy this path could not be imported at all in
    this environment, because its ``__init__`` eagerly reached a module
    that did ``from openai import APIError``. The probe blocks both
    vendor names outright, so the test keeps its meaning on a machine
    where they *are* installed.
    """
    module = (
        "omicsclaw.engine"
        if path.stem == "__init__"
        else f"omicsclaw.engine.{path.stem}"
    )
    source = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('openai', 'anthropic') else None))"
        "})());"
        f"import {module};"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, (
        f"{path.name} could not be imported without a vendor SDK:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"


def test_the_public_surface_is_exactly_what_the_plan_promised():
    """``__init__`` is an interface, so widening it should be deliberate.

    ``retry`` is absent on purpose: how many attempts a model call gets
    is the loop's own business, and nothing outside it should be reaching
    for that function. ``HistoryCompactor`` joined in plan 0035, as the
    optional per-run seam through which compaction reaches the loop, and
    ``TurnAugmentor`` in plan 0039 as its sibling — consulted after it,
    and able only to append to the call being made.
    """
    import omicsclaw.engine as engine

    assert engine.__all__ == [
        "AgentEngine",
        "ConcurrencyAwareExecutor",
        "DeadlineAwareExecutor",
        "EngineConfig",
        "EngineError",
        "EngineEvent",
        "EngineEventType",
        "HistoryCompactor",
        "RunResult",
        "StopReason",
        "TimeoutPause",
        "ToolExecutor",
        "TurnAugmentor",
        "execute_tool_calls",
        "observations",
    ]
    assert all(hasattr(engine, name) for name in engine.__all__)

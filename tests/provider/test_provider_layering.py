"""The provider layer may depend on the schema contract and nothing else.

Plan 0026 §7, criteria 2 and 3. Mirrors
``tests/schema/test_schema_is_a_leaf_package.py``: the schema package is a
leaf, and this package is leaf-adjacent — ``omicsclaw.schema`` plus the
standard library, full stop.

Two separate properties are at stake.

*No ``omicsclaw`` edge except schema.* The whole point of the layer is
that the Engine programs against one interface; an import of the loop or
a Surface would make the interface a participant in the thing it
abstracts. The plural ``omicsclaw.providers`` used to be the sharpest
case — it was imported by the legacy agent loop, so an edge back out of
the singular package put a cycle one refactor away. The framework rebuild
deleted it, and a test below now holds it deleted.

*No vendor SDK in the contract.* ``base.py``, ``config.py`` and
``_model_limits.py`` must import neither ``openai`` nor ``anthropic``.
Those belong to the adapter modules, so that importing the interface
never requires an optional extra to be installed.

Static, like its schema counterpart: it fails on the import *statement*,
before a cycle becomes a runtime error somewhere far away.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROVIDER_DIR = _REPO_ROOT / "omicsclaw" / "provider"

_ALLOWED_INTERNAL_PREFIXES = ("omicsclaw.schema", "omicsclaw.provider")

# The adapter modules of tasks B and C own these; the contract must not.
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
}


def _module_paths() -> list[pathlib.Path]:
    return sorted(_PROVIDER_DIR.glob("*.py"))


def _contract_module_paths() -> list[pathlib.Path]:
    """Everything except the vendor adapters.

    The SDK ban applies here and only here. An adapter exists precisely to
    import its vendor's SDK; applying the ban to ``*_provider.py`` would
    forbid the layer's whole purpose, and the only way to satisfy it would
    be to reach the SDK through ``importlib`` — buying a green run by
    making a real dependency invisible to grep, to dependency scanners,
    and to this test.
    """
    return [p for p in _module_paths() if not p.name.endswith("_provider.py")]


def _adapter_module_paths() -> list[pathlib.Path]:
    return [p for p in _module_paths() if p.name.endswith("_provider.py")]


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
    assert _module_paths(), f"no provider modules found under {_PROVIDER_DIR}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_provider_module_imports_nothing_from_omicsclaw_but_schema(
    path: pathlib.Path,
):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        name
        for name in _imported_modules(tree)
        if name.split(".")[0] == "omicsclaw"
        and not name.startswith(_ALLOWED_INTERNAL_PREFIXES)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — the provider layer may depend "
        "only on omicsclaw.schema and the standard library"
    )


@pytest.mark.parametrize("path", _contract_module_paths(), ids=lambda p: p.name)
def test_the_contract_modules_import_no_vendor_sdk(path: pathlib.Path):
    """The contract must stay installable with no optional extra present."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        name
        for name in _imported_modules(tree)
        if name.split(".")[0] in _FORBIDDEN_THIRD_PARTY
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — vendor SDKs belong to the "
        "adapter modules, not to the contract"
    )


@pytest.mark.parametrize("path", _adapter_module_paths(), ids=lambda p: p.name)
def test_an_adapter_declares_its_vendor_sdk_where_tooling_can_see_it(
    path: pathlib.Path,
):
    """An adapter's SDK dependency must be a real import statement.

    Reaching the SDK through ``importlib.import_module("anthropic")``
    also works at runtime, and also defers the cost — but it hides the
    dependency from grep, from dependency and licence scanners, and from
    the AST check above, which would then pass while enforcing nothing.
    Laziness is achieved by *where* the import sits (inside the client
    factory), not by making it dynamic.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported = set(_imported_modules(tree))

    assert imported & _FORBIDDEN_THIRD_PARTY, (
        f"{path.name} declares no vendor SDK import. If it reaches one via "
        "importlib, replace that with a plain import inside the client "
        "factory so the dependency stays visible."
    )


def _run(probe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


def test_the_plural_package_is_gone():
    """The migration plan 0026 §9 Q2 scheduled is over.

    The two packages coexisted for its length and this asserted they
    imported in either order. The framework rebuild deleted the plural
    one, so the property worth holding is the opposite: ``provider`` is
    the only spelling, and nothing may quietly restore the other.
    """
    result = _run("import omicsclaw.providers")

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    """Guards the real runtime cost, not just the source text.

    ``omicsclaw.version`` is the one permitted straggler: the lazy
    top-level ``__init__`` imports it for ``__version__``.
    """
    probe = (
        "import sys, omicsclaw.provider as provider;"
        "config = provider.resolve_config('anthropic', env={});"
        "assert config.model == 'claude-sonnet-4-6';"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.provider')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = _run(probe)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the provider package dragged in {result.stdout.strip()}"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_every_provider_module_imports_without_any_vendor_sdk_installed(
    path: pathlib.Path,
):
    """The property the SDK ban exists to protect, checked directly.

    The AST rules above are proxies; this is the thing itself. Neither
    ``openai`` nor ``anthropic`` is installed in this environment, so a
    module that reached its SDK at import time would fail here — and the
    probe blocks both names outright so the test keeps its meaning on a
    machine where they *are* installed. A missing SDK must surface later,
    as a ``ProviderError`` when a client is actually built, never as an
    ``ImportError`` when someone imports the interface.
    """
    module = f"omicsclaw.provider.{path.stem}" if path.stem != "__init__" else (
        "omicsclaw.provider"
    )
    probe = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('openai', 'anthropic') else None))"
        "})());"
        f"import {module};"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, (
        f"{path.name} could not be imported without a vendor SDK:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"

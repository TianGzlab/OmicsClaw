"""``omicsclaw/observability/`` is an adapter over four leaves, one way only.

Unlike ``hooks``, ``permission`` or ``schema``, this package is **not** a
leaf: instrumenting a model call means knowing what a model call is. What
makes it safe is the direction. It may import :mod:`omicsclaw.schema`,
:mod:`omicsclaw.provider`, :mod:`omicsclaw.engine` and
:mod:`omicsclaw.hooks`; **none of those four may import it**, which is
what lets a deployment delete this package without anything else
noticing, and what keeps ``omicsclaw/engine/``'s own "no I/O, no logging"
promise true after a telemetry layer exists.

Three further rules are checked here:

- :mod:`omicsclaw.entry` is forbidden. The composition root joins the two
  in three lines; an arrow back would make a sub-agent or a test unable
  to build telemetry without a whole deployment.
- Only :mod:`omicsclaw.observability.otel` may name a vendor SDK, and
  only inside a function. That is the exemption argued in its docstring
  and it is bounded here rather than taken on trust.
- Importing the package must not drag the OpenTelemetry SDK in.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "omicsclaw" / "observability"

_ALLOWED_INTERNAL = (
    "omicsclaw.schema",
    "omicsclaw.provider",
    "omicsclaw.engine",
    "omicsclaw.hooks",
    "omicsclaw.observability",
)

_FORBIDDEN_NEIGHBOURS = (
    "omicsclaw.entry",
    "omicsclaw.tools",
    "omicsclaw.permission",
    "omicsclaw.context",
    "omicsclaw.planning",
    "omicsclaw.skills",
    "omicsclaw.mcp",
    "omicsclaw.sandbox",
    "omicsclaw.memory",
    "omicsclaw.runtime",
    "omicsclaw.surfaces",
)
"""``omicsclaw.tools`` is the quiet one worth naming.

A tracing hook is *about* tool calls, so reaching for
``omicsclaw.tools.context`` to read a session id — which
``hooks/audit.py`` legitimately does — looks natural. It is not this
package's to read: the session arrives on
:meth:`~omicsclaw.observability.Telemetry.run` from the surface that
knows it, and importing the tool layer to find it a second way would make
two answers to one question out of a fact that is already an argument.
"""

_VENDOR_MODULE = "opentelemetry"
_VENDOR_OWNER = "otel.py"


def _module_paths() -> list[pathlib.Path]:
    return sorted(_PACKAGE_DIR.rglob("*.py"))


def _package_of(path: pathlib.Path) -> str:
    parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    return ".".join(parts[:-1])


def _imports(path: pathlib.Path) -> list[tuple[str, int, int]]:
    """``(module, lineno, col_offset)`` for every import in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path).split(".")
    found: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                (alias.name, node.lineno, node.col_offset) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    found.append((node.module, node.lineno, node.col_offset))
                continue
            climbed = len(package) - (node.level - 1)
            base = package[:climbed] if climbed > 0 else []
            found.append(
                (
                    ".".join([*base, node.module] if node.module else base),
                    node.lineno,
                    node.col_offset,
                )
            )
    return found


def _is_allowed(name: str) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in _ALLOWED_INTERNAL)


def test_the_package_has_modules_to_check():
    """A rule that vacuously passes over an empty directory is not a rule."""
    assert len(_module_paths()) >= 10


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_module_imports_only_the_four_layers_it_is_an_adapter_over(
    path: pathlib.Path,
):
    offenders = [
        name
        for name, _, _ in _imports(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — this layer may import "
        "omicsclaw.schema, .provider, .engine and .hooks"
    )


@pytest.mark.parametrize("forbidden", _FORBIDDEN_NEIGHBOURS)
def test_the_named_neighbours_appear_nowhere(forbidden: str):
    offenders = [
        path.name
        for path in _module_paths()
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for name, _, _ in _imports(path)
        )
    ]

    assert not offenders, f"{offenders} import {forbidden}"


@pytest.mark.parametrize(
    "layer", ["schema", "provider", "engine", "hooks", "tools", "context"]
)
def test_no_layer_below_imports_this_one(layer: str):
    """The direction is the whole safety argument.

    Checked on the **import graph**, not on the text. A docstring in a
    lower layer may name this package — ``hooks/audit.py`` does, to say
    that ``outcome_of`` was made public because a tracing hook shares its
    vocabulary — and a cross-reference in prose is the opposite of a
    coupling: it is how the one-way arrow gets documented at the end it
    points away from. The next test pins that distinction so this one is
    not later "tightened" into forbidding it.
    """
    directory = _REPO_ROOT / "omicsclaw" / layer
    offenders = [
        path.name
        for path in sorted(directory.rglob("*.py"))
        if any(
            name.startswith("omicsclaw.observability") for name, _, _ in _imports(path)
        )
    ]

    assert not offenders, (
        f"omicsclaw/{layer}/ imports this package in {offenders} — the arrow "
        "points one way, and the engine in particular must not learn that it "
        "is being watched"
    )


def test_a_lower_layer_may_still_mention_this_one_in_prose():
    """The shared-vocabulary note in ``hooks/audit.py``, pinned as intentional."""
    audit = (_REPO_ROOT / "omicsclaw" / "hooks" / "audit.py").read_text("utf-8")

    assert "omicsclaw.observability.hook.TracingHook" in audit
    assert not any(
        name.startswith("omicsclaw.observability")
        for name, _, _ in _imports(_REPO_ROOT / "omicsclaw" / "hooks" / "audit.py")
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_only_the_adapter_names_the_vendor_sdk(path: pathlib.Path):
    vendor = [name for name, _, _ in _imports(path) if name.startswith(_VENDOR_MODULE)]

    if path.name == _VENDOR_OWNER:
        assert vendor, "the adapter is the module that is supposed to import it"
    else:
        assert not vendor, f"{path.name} imports {vendor}; only {_VENDOR_OWNER} may"


def test_the_vendor_import_is_inside_a_function_so_it_stays_optional():
    """A top-level one would make ``import omicsclaw.entry`` need the SDK."""
    offenders = [
        f"{name}:{lineno}"
        for name, lineno, col in _imports(_PACKAGE_DIR / _VENDOR_OWNER)
        if name.startswith(_VENDOR_MODULE) and col == 0
    ]

    assert not offenders, f"{offenders} are imported at module scope"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_no_module_imports_a_third_party_package(path: pathlib.Path):
    offenders = [
        name
        for name, _, _ in _imports(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] not in {"omicsclaw", _VENDOR_MODULE}
    ]

    assert not offenders, f"{path.name} imports {offenders}"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


def test_importing_the_package_does_not_load_the_opentelemetry_sdk():
    """The property that keeps the dependency optional, checked for real."""
    result = _probe(
        "import sys, omicsclaw.observability as obs;"
        "t = obs.build_telemetry(obs.ObservabilityConfig());"
        "assert t.active is False;"
        "print([m for m in sys.modules if m.startswith('opentelemetry')])"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"importing the layer loaded {result.stdout.strip()}"
    )


def test_a_stdout_deployment_runs_without_the_sdk_too():
    """The console backend is what makes "works with nothing installed" true."""
    result = _probe(
        "import sys, io, omicsclaw.observability as obs;"
        "cfg = obs.ObservabilityConfig(enabled=True, exporter='stdout');"
        "t = obs.build_telemetry(cfg);"
        "assert t.active is True;"
        "s = t.tracer.start_span('x'); s.end();"
        "print([m for m in sys.modules if m.startswith('opentelemetry')])"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "[]"


def test_the_public_surface_is_deliberate():
    import omicsclaw.observability as obs

    assert obs.__all__ == sorted(obs.__all__), "keep the list sorted"
    assert all(hasattr(obs, name) for name in obs.__all__)

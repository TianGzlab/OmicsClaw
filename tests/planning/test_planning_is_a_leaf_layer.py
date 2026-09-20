"""``omicsclaw/planning/`` may import ``omicsclaw.schema`` and ``omicsclaw.tools``.

Copied from the guard beside the skill loader, which was itself the
repaired version of the tool layer's. The entry that matters most here is
``omicsclaw.engine``: :class:`~omicsclaw.planning.PlanInjector` satisfies
that layer's ``TurnAugmentor`` **structurally**, and importing it to
"make the relationship explicit" is exactly the move that would turn two
leaves into a cycle waiting to happen.

*A whitelist, not a blacklist.* Naming what is forbidden means predicting
every package a future step adds; naming what is allowed does not.

**And the last check is behavioural.** An ``ast`` walk cannot see a
module named as a string inside a function body, so the probe below runs
every real path this package has in a fresh process and inspects
``sys.modules`` afterwards.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PLANNING_DIR = _REPO_ROOT / "omicsclaw" / "planning"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.tools", "omicsclaw.planning")
"""``omicsclaw.tools`` is allowed because ``plan_write`` declares its own
:class:`~omicsclaw.tools.base.ToolPolicy` and resolves its session through
:func:`~omicsclaw.tools.context.context_value`; leaving the policy to
default would put an approval prompt in front of every plan update."""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.engine",
    "omicsclaw.context",
    "omicsclaw.entry",
    "omicsclaw.memory",
    "omicsclaw.runtime",
    "omicsclaw.skill",
    "omicsclaw.provider",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

``omicsclaw.engine`` is the dangerous one, for the reason in the module
docstring. ``omicsclaw.context`` is the second: this package renders text
for a prompt section, so importing ``Section`` to return one looks
helpful and would make two leaves depend on each other rather than on the
composition root that joins them — the same trap the skill loader names.
``omicsclaw.memory`` is the third: a plan is persisted, and reaching for
the session store is how the plan would acquire a database.
"""


def _module_paths() -> list[pathlib.Path]:
    return sorted(_PLANNING_DIR.rglob("*.py"))


def _package_of(path: pathlib.Path) -> str:
    parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    return ".".join(parts[:-1])


def _imported_modules(path: pathlib.Path) -> list[str]:
    """Absolute module names imported by ``path``, relative ones resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path).split(".")
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    names.append(node.module)
                continue
            climbed = len(package) - (node.level - 1)
            base = package[:climbed] if climbed > 0 else []
            names.append(".".join([*base, node.module] if node.module else base))

    return names


_DYNAMIC_IMPORT_CALLS = frozenset(
    {
        "__import__",
        "import_module",
        "reload",
        "spec_from_file_location",
        "module_from_spec",
        "exec_module",
        "load_module",
    }
)


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _dynamic_import_calls(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{_called_name(node)}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in _DYNAMIC_IMPORT_CALLS
    ]


def _is_allowed(name: str) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in _ALLOWED_INTERNAL)


def test_the_package_has_modules_to_check():
    """A rule that vacuously passes over an empty directory is not a rule."""
    assert _module_paths(), f"no modules found under {_PLANNING_DIR}"


def test_the_whitelist_does_not_let_the_engine_through():
    """The guard itself, checked."""
    assert _is_allowed("omicsclaw.planning.injector")
    assert _is_allowed("omicsclaw.tools.context")
    assert not _is_allowed("omicsclaw.engine")
    assert not _is_allowed("omicsclaw.engine.augmentor")


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_planning_module_imports_only_schema_and_tools(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the planning layer may import omicsclaw.schema and omicsclaw.tools"
    )


@pytest.mark.parametrize("forbidden", _TEMPTING_NEIGHBOURS)
def test_the_named_neighbours_appear_nowhere_in_the_package(forbidden: str):
    offenders = [
        path.name
        for path in _module_paths()
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for name in _imported_modules(path)
        )
    ]

    assert not offenders, f"{offenders} import {forbidden}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_planning_module_imports_nothing_at_runtime(path: pathlib.Path):
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — a module named as "
        "a string is a module the import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_planning_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_only_the_tool_reaches_the_tool_layer(path: pathlib.Path):
    """The state, the rules and the rendering are standard library only.

    ``plan.py`` is the one worth naming: a module that can name a
    ``Message`` is a module someone will make a ``PlanStore`` produce one.
    """
    if path.name in {"tool.py", "guidance.py", "injector.py", "__init__.py"}:
        pytest.skip("mounts the tool, or names it")
    offenders = [
        name
        for name in _imported_modules(path)
        if name.startswith("omicsclaw.tools") or name.startswith("omicsclaw.schema")
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
    source = (
        "import sys, omicsclaw.planning as planning;"
        "assert planning.plan_write_tool is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.planning')"
        " and not m.startswith('omicsclaw.schema')"
        " and not m.startswith('omicsclaw.tools') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the planning layer dragged in {result.stdout.strip()}"
    )


_BEHAVIOUR_PROBE = '''
import asyncio
import json
import pathlib
import sys
import tempfile

from omicsclaw.planning import (
    FilePlanArchive,
    PlanBook,
    PlanInjector,
    PlanItem,
    PlanStatus,
    format_plan,
    plan_write_tool,
    render_document,
)
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.context import use_tool_context

directory = pathlib.Path(tempfile.mkdtemp()) / "plans"
book = PlanBook(FilePlanArchive(directory))
registry = ToolRegistry()
registry.register(plan_write_tool(book))


async def drive():
    with use_tool_context(values={"session_id": "probe"}):
        await registry.execute(
            ToolCall(
                id="c1",
                name="plan_write",
                arguments=json.dumps(
                    {"steps": [{"id": "1", "content": "step", "status": "in_progress"}]}
                ),
            )
        )
        await registry.execute(
            ToolCall(id="c2", name="plan_write", arguments="{}")
        )
    store = book.for_session("probe")
    injector = PlanInjector(store, gate_turns=2)
    return await injector.augment(
        (Message(role=Role.ASSISTANT, content="thinking"),), ()
    )


appended = asyncio.run(drive())
assert appended and "step" in appended[0].content, appended
assert PlanBook(FilePlanArchive(directory)).for_session("probe").read()
assert format_plan(book.for_session("probe").read())
assert render_document("probe", book.for_session("probe").read())
print(sorted(
    m for m in sys.modules
    if m.startswith("omicsclaw")
    and not m.startswith("omicsclaw.planning")
    and not m.startswith("omicsclaw.schema")
    and not m.startswith("omicsclaw.tools")
    and m not in ("omicsclaw", "omicsclaw.version")
))
'''


def test_running_the_layer_pulls_in_nothing_it_may_not_import():
    """Static checks inspect spelling; only a behavioural probe inspects fact.

    Plan 0028 lost 286 green tests to one lazy ``importlib.import_module``,
    and the repaired guard it left behind is this one: run the real paths
    in a subprocess and then look at what is loaded.
    """
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"driving the planning layer loaded {result.stdout.strip()}"
    )

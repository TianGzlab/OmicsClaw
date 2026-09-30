"""``omicsclaw/subagent/`` may import ``omicsclaw.schema`` and ``omicsclaw.tools``.

Copied from the guard beside the planning layer, which was itself the
repaired version of the skill loader's. The entry that matters most here
is ``omicsclaw.engine``: :class:`~omicsclaw.subagent.ChildPrompt`
satisfies that layer's ``PromptSource`` and ``RenderedPrompt``
**structurally**, and importing the engine to "make the relationship
explicit" is the move that would turn two leaves into a cycle. The second
is ``omicsclaw.entry``: building a child engine needs a provider, a
registry and a deployment's sandbox state, and reaching for the
composition root to get them is how this package would acquire all three.

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
_SUBAGENT_DIR = _REPO_ROOT / "omicsclaw" / "subagent"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.tools", "omicsclaw.subagent")
"""``omicsclaw.tools`` is allowed because ``task`` declares its own
:class:`~omicsclaw.tools.base.ToolPolicy`, holds the engine's timeout
pause through :func:`~omicsclaw.tools.context.pause_tool_timeout`, and
re-binds the tool context to record which sub-agent is running."""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.engine",
    "omicsclaw.entry",
    "omicsclaw.skills",
    "omicsclaw.provider",
    "omicsclaw.context",
    "omicsclaw.permission",
    "omicsclaw.planning",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

``omicsclaw.engine`` and ``omicsclaw.entry`` are the two the module
docstring argues. ``omicsclaw.skills`` is the third: a sub-agent
preloads skill bodies, so importing the loader to fetch one looks
helpful — which is why the fetch arrives as a plain callable instead.
``omicsclaw.permission`` is the fourth: the child tool set is filtered
from already-gated objects, and a package that could name ``GatedTool``
is a package someone will make re-wrap them.
"""


def _module_paths() -> list[pathlib.Path]:
    return sorted(_SUBAGENT_DIR.rglob("*.py"))


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
    assert _module_paths(), f"no modules found under {_SUBAGENT_DIR}"


def test_the_whitelist_does_not_let_the_engine_through():
    """The guard itself, checked."""
    assert _is_allowed("omicsclaw.subagent.prompt")
    assert _is_allowed("omicsclaw.tools.context")
    assert not _is_allowed("omicsclaw.engine")
    assert not _is_allowed("omicsclaw.engine.prompt")


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_subagent_module_imports_only_schema_and_tools(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the subagent layer may import omicsclaw.schema and omicsclaw.tools"
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
def test_a_subagent_module_imports_nothing_at_runtime(path: pathlib.Path):
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — a module named as "
        "a string is a module the import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_subagent_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_only_the_tool_reaches_the_tool_layer(path: pathlib.Path):
    """The definition, the registry and the file loader are stdlib only.

    ``definition.py`` is the one worth naming: a module that can name a
    ``ToolPolicy`` is a module someone will make a definition carry one,
    and a sub-agent's permissions would then live somewhere other than
    the parent registry they are filtered from.
    """
    if path.name in {"task_tool.py", "__init__.py"}:
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
        "import sys, omicsclaw.subagent as subagent;"
        "assert subagent.TaskTool is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.subagent')"
        " and not m.startswith('omicsclaw.schema')"
        " and not m.startswith('omicsclaw.tools') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the subagent layer dragged in {result.stdout.strip()}"
    )


_BEHAVIOUR_PROBE = '''
import asyncio
import json
import pathlib
import sys
import tempfile

from omicsclaw.subagent import (
    ChildPrompt,
    SubAgentDefinition,
    SubAgentRegistry,
    TaskTool,
    load_agents,
    parse_agent_file,
)
from omicsclaw.schema import ToolCall
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.context import use_tool_context

directory = pathlib.Path(tempfile.mkdtemp()) / "agents"
directory.mkdir()
(directory / "surveyor.md").write_text(
    "---\\nname: surveyor\\ndescription: Surveys\\ntools: read_file\\n---\\nSurvey.\\n",
    encoding="utf-8",
)

agents = SubAgentRegistry([SubAgentDefinition(
    name="general-purpose", description="Anything", system_prompt="Work."
)])
for definition in load_agents(directory):
    agents.register(definition)
assert agents.names() == ("general-purpose", "surveyor"), agents.names()
assert parse_agent_file(
    "---\\nname: x\\ndescription: d\\n---\\nbody\\n"
).system_prompt == "body"

seen = []


class Runner:
    async def delegate(self, definition, prompt):
        seen.append((definition.name, prompt))
        return ChildPrompt(
            instructions=definition.system_prompt,
            workspace="/tmp/ws",
            environment="## Execution sandbox\\n\\n- degraded",
            skills=("missing",),
            loader=lambda name: (_ for _ in ()).throw(LookupError(name)),
        ).render().system_prompt


registry = ToolRegistry()
registry.register(TaskTool(agents, Runner()))


async def drive():
    with use_tool_context(values={"workspace": "/tmp/ws"}):
        return await registry.execute(
            ToolCall(
                id="c1",
                name="task",
                arguments=json.dumps(
                    {"subagent_type": "surveyor", "prompt": "count the files"}
                ),
            )
        )


result = asyncio.run(drive())
assert not result.is_error, result.output
assert "Survey." in result.output and "/tmp/ws" in result.output, result.output
assert "degraded" in result.output, result.output
assert seen == [("surveyor", "count the files")], seen
assert agents.get("surveyor").resolve_tools(("read_file", "task")) == ("read_file",)
assert registry.get("task").definition().input_schema["properties"][
    "subagent_type"
]["enum"] == ["general-purpose", "surveyor"]
print(sorted(
    m for m in sys.modules
    if m.startswith("omicsclaw")
    and not m.startswith("omicsclaw.subagent")
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
        f"driving the subagent layer loaded {result.stdout.strip()}"
    )

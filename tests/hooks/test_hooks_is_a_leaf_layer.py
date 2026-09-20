"""``omicsclaw/hooks/`` may import ``omicsclaw.schema`` and ``omicsclaw.tools``.

The same whitelist as the permission layer, which copied it from the skill
loader, and for a related reason: this package's whole vocabulary is
``Tool`` / ``ToolPolicy`` / ``ToolDefinition``, and its one shipped hook
reads a per-turn fact through ``omicsclaw.tools.context``.

**``omicsclaw.permission`` is the forbidden neighbour that matters most
here**, and it is forbidden in the direction a reader would least
expect. A hook chain and a permission gate are composed together in one
line of ``entry/assembly.py`` and the chain runs *inside* the gate, so it
looks natural for one to import the other. Neither does. The gate does
not know hooks exist — that is what lets a deployment mount hooks with no
gate, or a gate with no hooks, and what stopped this package from
re-implementing ``allow``/``deny``/``ask`` a second time. Two leaves that
import each other are one package with a slash in its name.

**``omicsclaw.entry`` is the second.** Every ingredient a configured
chain needs is over there — a log path, an ``AppConfig``, the session a
record is filed under. Reaching for any of them would invert the arrow
and make a sub-agent or a test unable to build a chain without a whole
deployment.

**``omicsclaw.engine`` is the third.** The engine is handed a registry
and must never learn that anything wraps a tool. An import in this
direction is the first step towards a ``hooks`` field on the loop.

*A whitelist, not a blacklist.* Naming what is forbidden means predicting
every package a future step adds; naming what is allowed does not.

**And the last check is behavioural.** An ``ast`` walk cannot see a
module named as a string inside a function body, so
:func:`test_running_the_layer_pulls_in_nothing_it_should_not` runs every
real path this package has in a fresh process and inspects
:data:`sys.modules` afterwards.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "omicsclaw" / "hooks"

_ALLOWED_INTERNAL = (
    "omicsclaw.schema",
    "omicsclaw.tools",
    "omicsclaw.hooks",
)

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.permission",
    "omicsclaw.entry",
    "omicsclaw.engine",
    "omicsclaw.context",
    "omicsclaw.planning",
    "omicsclaw.skills",
    "omicsclaw.skill",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.mcp",
    "omicsclaw.sandbox",
    "omicsclaw.memory",
    "omicsclaw.runtime",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

``omicsclaw.permission`` and the two the module docstring explains come
first. ``omicsclaw.context`` is the quiet fourth: it owns the
``Offloader``, which is the reference harness's ``OffloadHook`` living
somewhere else, and importing it to "also" offload at tool-execution
time would give one deployment two things moving the same bytes.
``omicsclaw.planning`` is the fifth for the same shape of reason — the
reference keeps its plan writer in ``internal/hooks`` and this tree does
not.
"""


def _module_paths() -> list[pathlib.Path]:
    return sorted(_PACKAGE_DIR.rglob("*.py"))


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
    assert _module_paths(), f"no modules found under {_PACKAGE_DIR}"


def test_the_whitelist_does_not_accidentally_admit_a_neighbour():
    assert _is_allowed("omicsclaw.tools.base")
    assert _is_allowed("omicsclaw.tools.context")
    assert _is_allowed("omicsclaw.schema")
    assert not _is_allowed("omicsclaw.permission")
    assert not _is_allowed("omicsclaw.entry")
    assert not _is_allowed("omicsclaw.hook"), "the singular is not this package"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_hooks_module_imports_only_schema_and_tools(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the hooks layer may import omicsclaw.schema and omicsclaw.tools"
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
def test_a_hooks_module_imports_nothing_at_runtime(path: pathlib.Path):
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — a module named as "
        "a string is a module the import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_hooks_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


def test_the_layer_never_reads_the_environment_or_a_default_path():
    """Where a record goes is the composition root's answer, not this one's.

    A hook that quietly resolved ``~/.omicsclaw/audit.jsonl`` would be a
    file about a person written because nobody said no, and the one an
    operator reading ``AppConfig`` would not find.
    """
    offenders = [
        path.name
        for path in _module_paths()
        if any(
            token in path.read_text(encoding="utf-8")
            for token in ("os.environ", "getenv", "Path.home", "expanduser")
        )
    ]

    assert not offenders, f"{offenders} reach for configuration of their own"


def _probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


_LEAK_QUERY = """
print(sorted(
    m for m in sys.modules
    if m.startswith("omicsclaw")
    and not m.startswith("omicsclaw.hooks")
    and not m.startswith("omicsclaw.schema")
    and not m.startswith("omicsclaw.tools")
    and m not in ("omicsclaw", "omicsclaw.version")
))
"""


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    source = (
        "import sys, omicsclaw.hooks as hooks;"
        "assert hooks.HookedTool is not None;" + _LEAK_QUERY
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"importing the hooks layer dragged in {result.stdout.strip()}"
    )


_BEHAVIOUR_PROBE = '''
import asyncio
import pathlib
import sys
import tempfile

from omicsclaw.hooks import (
    SESSION_ID_KEY,
    AuditHook,
    AuditOutcome,
    AuditRecord,
    AuditSink,
    Hook,
    HookAction,
    HookCall,
    HookDecision,
    HookDenied,
    HookedTool,
    JsonlAuditSink,
    ToolHook,
    allow,
    arguments_digest,
    deny,
    hook_tools,
)
from omicsclaw.schema import ToolDefinition


class Echo:
    @property
    def name(self):
        return "echo"

    def definition(self):
        return ToolDefinition(name="echo", description="", input_schema={})

    async def execute(self, arguments):
        return "echo:" + arguments


class Blocker(Hook):
    async def before_execute(self, call):
        return deny("no")


async def main():
    assert isinstance(Hook(), ToolHook)
    assert allow().action is HookAction.ALLOW
    assert deny("x").action is HookAction.DENY
    assert len(arguments_digest("{}")) == 16
    assert HookCall(name="echo", arguments="{}").name == "echo"
    assert HookDecision().arguments is None

    tool = Echo()
    assert hook_tools([tool], ())[0] is tool

    with tempfile.TemporaryDirectory() as raw:
        path = pathlib.Path(raw) / "nested" / "audit.jsonl"
        sink = JsonlAuditSink(path)
        assert isinstance(sink, AuditSink)
        assert sink.path == path

        hooked = hook_tools([Echo()], (AuditHook(sink),))[0]
        assert isinstance(hooked, HookedTool)
        assert hooked.name == "echo"
        assert hooked.definition().name == "echo"
        assert hooked.policy is None
        assert hooked.inner is not None
        assert hooked.hooks
        assert await hooked.execute("{}") == "echo:{}"

        blocked = hook_tools([Echo()], (AuditHook(sink), Blocker()))[0]
        try:
            await blocked.execute("{}")
        except HookDenied:
            pass
        else:
            raise AssertionError("a denied tool ran")

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2, lines
        assert AuditOutcome.DENIED.value in lines[1]

    record = AuditRecord(
        tool="echo", outcome=AuditOutcome.OK, arguments_digest="0" * 16, at=0.0
    )
    assert "echo" in record.as_json()

    try:
        HookedTool(Echo(), (object(),))
    except TypeError:
        pass
    else:
        raise AssertionError("a non-hook was accepted")


asyncio.run(main())
''' + _LEAK_QUERY
"""Every execution path this layer has, run for real in a fresh process.

The assertions inside are there so a probe that silently stopped doing
anything fails loudly instead of printing an empty leak list. The product
is the line after ``asyncio.run``: what :data:`sys.modules` holds once the
layer has actually *run*, which is the only question a lazy import in a
function body answers honestly. The list has to grow when a public
function does.
"""


def test_running_the_layer_pulls_in_nothing_it_should_not():
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"running the hooks layer loaded {result.stdout.strip()}"
    )


def test_the_public_surface_is_deliberate():
    """``__init__`` is an interface, so widening it should be a decision."""
    import omicsclaw.hooks as hooks

    assert hooks.__all__ == [
        "AuditHook",
        "AuditOutcome",
        "AuditRecord",
        "AuditSink",
        "Hook",
        "HookAction",
        "HookCall",
        "HookDecision",
        "HookDenied",
        "HookedTool",
        "JsonlAuditSink",
        "SESSION_ID_KEY",
        "ToolHook",
        "allow",
        "arguments_digest",
        "deny",
        "hook_tools",
        "outcome_of",
    ]
    assert all(hasattr(hooks, name) for name in hooks.__all__)
    assert hooks.__all__ == sorted(hooks.__all__), "keep the list sorted"


def test_the_package_does_not_reimplement_ask():
    """The one thing the reference has that this deliberately does not.

    ``HookAction`` having a third member would mean two layers decide who
    talks to a person. The check is on the enum rather than on a
    docstring, because the docstring is what a second implementation
    would leave untouched.
    """
    from omicsclaw.hooks import HookAction

    assert [member.value for member in HookAction] == ["allow", "deny"]

"""``omicsclaw/permission/`` may import ``omicsclaw.schema`` and ``omicsclaw.tools``.

Copied from the repaired guard beside the skill loader, which is the version
plans 0032 and 0036 said to copy. The whitelist is the same two packages and
for the same reason: this layer's entire vocabulary is ``ToolPolicy`` /
``ApprovalMode`` / ``RiskLevel``, and it publishes its settled decisions back
down through the same ``use_effective_policy`` the registry uses.

The forbidden neighbour that matters most here is **``omicsclaw.entry``**.
Every ingredient this package needs is over there — a configured rule-file
path, the approval broker that turns a question into a stream event, the mode
a surface chose. Reaching for any of them would invert the arrow: the
composition root is the only thing allowed to know both a configuration file
and a permission gate, which is what lets a sub-agent, a benchmark runner or
a test build a gate with three lines and no ``AppConfig``.

**``omicsclaw.engine`` is the second.** The engine is handed a registry and
must never learn that anything was gated; an import in this direction would
be the first step towards a ``permissionMode`` field on the loop, which is
where the reference keeps it and why its mode enum ended up with three values
nothing reads.

*A whitelist, not a blacklist.* Naming what is forbidden means predicting
every package a future step adds; naming what is allowed does not.

**And the last check is behavioural.** An ``ast`` walk cannot see a module
named as a string inside a function body, so
:func:`test_running_the_layer_pulls_in_nothing_it_should_not` runs every real
path this package has in a fresh process and inspects :data:`sys.modules`
afterwards.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "omicsclaw" / "permission"

_ALLOWED_INTERNAL = (
    "omicsclaw.schema",
    "omicsclaw.tools",
    "omicsclaw.permission",
)

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.entry",
    "omicsclaw.engine",
    "omicsclaw.context",
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

``omicsclaw.entry`` and ``omicsclaw.engine`` are the two the module docstring
explains. ``omicsclaw.sandbox`` is the quiet third: ``entry/sandbox.py``
already decides that ``bash`` in a network-less container need not ask, which
looks like this package's business and is not — it is a *policy* decision, so
it belongs where policies are resolved, and importing the sandbox to re-derive
it here would make two leaves depend on each other.
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
    """The guard itself, checked, including the one-letter skill distinction."""
    assert _is_allowed("omicsclaw.tools.base")
    assert _is_allowed("omicsclaw.schema")
    assert not _is_allowed("omicsclaw.entry")
    assert not _is_allowed("omicsclaw.skill")
    assert not _is_allowed("omicsclaw.skills")
    assert not _is_allowed("omicsclaw.toolsmith")


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_permission_module_imports_only_schema_and_tools(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the permission layer may import omicsclaw.schema and omicsclaw.tools"
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
def test_a_permission_module_imports_nothing_at_runtime(path: pathlib.Path):
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — a module named as "
        "a string is a module the import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_permission_module_imports_only_the_standard_library(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "omicsclaw"
    ]

    assert not offenders, f"{path.name} imports non-stdlib {offenders}"


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
    and not m.startswith("omicsclaw.permission")
    and not m.startswith("omicsclaw.schema")
    and not m.startswith("omicsclaw.tools")
    and m not in ("omicsclaw", "omicsclaw.version")
))
"""


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    source = (
        "import sys, omicsclaw.permission as permission;"
        "assert permission.PermissionGate is not None;" + _LEAK_QUERY
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"importing the permission layer dragged in {result.stdout.strip()}"
    )


_BEHAVIOUR_PROBE = '''
import asyncio
import json
import pathlib
import sys
import tempfile

from omicsclaw.permission import (
    DEFAULT_DANGER_PATTERNS,
    DangerPatterns,
    DecisionSource,
    GatedTool,
    PermissionConfigError,
    PermissionDenied,
    PermissionGate,
    PermissionMode,
    Rule,
    RuleStore,
    Rules,
    Verdict,
    gate_tools,
    literal_pattern,
    load_rules,
    principal_argument,
    principal_key,
    save_rules,
)
from omicsclaw.schema import ToolCall, ToolDefinition
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import (
    ApprovalDecision,
    require_approval,
    use_tool_context,
)

SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string"}},
    "required": ["command"],
}


class Shell:
    policy = ToolPolicy(
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.ASK,
        prompts_for_itself=True,
    )

    def __init__(self):
        self.calls = []

    @property
    def name(self):
        return "bash"

    def definition(self):
        return ToolDefinition(name="bash", description="", input_schema=SCHEMA)

    async def execute(self, arguments):
        await require_approval(self.name, arguments, policy=self.policy, reason="own")
        self.calls.append(arguments)
        return "ok"


async def main():
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        path = root / "nested" / "settings.json"

        assert len(load_rules(path)) == 0
        save_rules(path, Rules([Rule(Verdict.DENY, "bash(rm -rf /)")]))
        store = RuleStore(path)
        assert len(store.current) == 1
        store.remember(literal_pattern("bash", "git status"))
        assert len(RuleStore(path).current) == 2

        try:
            Rule(Verdict.ALLOW, "bash(oops")
        except PermissionConfigError:
            pass
        else:
            raise AssertionError("a malformed pattern loaded")

        assert principal_key(SCHEMA) == "command"
        assert principal_argument(json.dumps({"command": "ls"}), SCHEMA) == "ls"

        patterns = DangerPatterns(DEFAULT_DANGER_PATTERNS)
        assert patterns.inspect("rm -rf /") is not None
        assert patterns.inspect("echo hi") is None

        for mode in PermissionMode:
            gate = PermissionGate(mode=mode, rules=store)
            resolution = gate.resolve(
                "bash", json.dumps({"command": "ls"}),
                policy=Shell.policy, schema=SCHEMA,
            )
            assert isinstance(resolution.verdict, Verdict)
            assert isinstance(resolution.source, DecisionSource)

        gate = PermissionGate(rules=store)
        assert gate.store is store
        assert gate.mode is PermissionMode.DEFAULT
        assert gate.remember("bash", json.dumps({"command": "uname"}), schema=SCHEMA)

        tool = Shell()
        gated = gate_tools([tool], gate)
        assert isinstance(gated[0], GatedTool)
        assert gated[0].inner is tool
        assert gated[0].definition().name == "bash"
        assert gated[0].policy == Shell.policy

        registry = ToolRegistry(gated)
        with use_tool_context(approval=lambda r: ApprovalDecision(approved=True)):
            allowed = await registry.execute(
                ToolCall(id="1", name="bash", arguments=json.dumps(
                    {"command": "git status"}))
            )
            assert not allowed.is_error, allowed.output
            denied = await registry.execute(
                ToolCall(id="2", name="bash", arguments=json.dumps(
                    {"command": "rm -rf /"}))
            )
            assert denied.is_error
            assert "PermissionDenied" in denied.output
            dangerous = await registry.execute(
                ToolCall(id="3", name="bash", arguments=json.dumps(
                    {"command": "sudo apt install x"}))
            )
            assert not dangerous.is_error, dangerous.output

        try:
            await GatedTool(Shell(), PermissionGate(
                rules=Rules([Rule(Verdict.DENY, "bash")]))).execute("{}")
        except PermissionDenied:
            pass
        else:
            raise AssertionError("a denied tool ran")


asyncio.run(main())
''' + _LEAK_QUERY
"""Every execution path this layer has, run for real in a fresh process.

The assertions inside are there so a probe that silently stopped doing
anything fails loudly instead of printing an empty leak list. The product is
the line after ``asyncio.run``: what :data:`sys.modules` holds once the layer
has actually *run*, which is the only question a lazy import in a function
body answers honestly. The list has to grow when a public function does.
"""


def test_running_the_layer_pulls_in_nothing_it_should_not():
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"running the permission layer loaded {result.stdout.strip()}"
    )


def test_the_public_surface_is_deliberate():
    """``__init__`` is an interface, so widening it should be a decision."""
    import omicsclaw.permission as permission

    assert permission.__all__ == [
        "COMMAND_ARGUMENT",
        "CONFIG_KEY",
        "DEFAULT_DANGER_PATTERNS",
        "DangerPattern",
        "DangerPatterns",
        "DecisionSource",
        "GatedTool",
        "PermissionConfigError",
        "PermissionDenied",
        "PermissionGate",
        "PermissionMode",
        "Resolution",
        "Rule",
        "RuleStore",
        "Rules",
        "Verdict",
        "gate_tools",
        "literal_pattern",
        "load_rules",
        "principal_argument",
        "principal_key",
        "save_rules",
    ]
    assert all(hasattr(permission, name) for name in permission.__all__)
    assert permission.__all__ == sorted(permission.__all__), "keep the list sorted"


def test_the_layer_never_reads_the_environment_or_a_default_path():
    """Configuration belongs to the composition root, and this checks it.

    A gate that quietly resolved ``~/.omicsclaw/settings.json`` on its own
    would be a second source for "which rules are in force", and the one a
    reader of ``AppConfig`` would not find.
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

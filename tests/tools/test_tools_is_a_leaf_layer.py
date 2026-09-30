"""``omicsclaw/tools/`` may import ``omicsclaw.schema`` and nothing else.

Plan 0028 §9-4, and the reason it is written as strictly as it is: plan
0028 §4 Q7 cancelled the task that would have moved the legacy tool layer
out of ``omicsclaw.runtime.tools``, on the grounds that a package name
only stops a human reviewer. **This file is therefore the sole mechanism
enforcing the boundary.** If it is weak, there is nothing behind it.

Three ways it is stricter than its counterparts in ``tests/schema/``,
``tests/provider/`` and ``tests/engine/``:

*A whitelist, not a blacklist.* Only ``omicsclaw.schema`` is permitted
inside the ``omicsclaw`` namespace — not ``provider``, not ``engine``, and
not ``runtime.tools``. Naming what is forbidden would mean predicting
every package a future step adds; naming what is allowed does not.

*Relative imports are resolved, not skipped.* The engine's counterpart
skips ``ImportFrom`` nodes with a non-zero level on the reasoning that
they stay inside the package. That is false above level one:
``from ..runtime import tools`` is a relative import that leaves. Plan
0028 §6 records that a grep for ``runtime.tools`` missed seven files
written exactly that way, so the level is resolved to an absolute module
name before it is judged.

*Third parties are checked against the standard library*, via
:data:`sys.stdlib_module_names`, rather than against a list of the
libraries someone thought of. Importing a tool must never require an
optional extra to be installed.

**The fourth strictness was bought with a hole.** An ``ast`` walk that
looks only at ``Import`` and ``ImportFrom`` nodes cannot see
``importlib.import_module("omicsclaw.runtime.tools.validation")``, and
neither could the subprocess probe below, which inspected
:data:`sys.modules` at *import* time while the offending import happens
in a function body called later. Replacing ``validate_arguments``' body
with a four-line delegation to the legacy validator left all of this
green — so the sole mechanism enforcing the boundary did not enforce the
one crossing plan 0028 §5 names by hand ("reuse ``validation.py``"). Two
checks close it: :func:`_dynamic_import_calls` refuses the call forms at
source level, and
:func:`test_running_the_tools_does_not_pull_in_a_single_runtime_module`
runs the layer and inspects :data:`sys.modules` **afterwards**, which is
the only check that does not depend on guessing the syntax.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "omicsclaw" / "tools"

_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.tools")
"""``omicsclaw.tools`` is on the list so the package may import itself."""

_TEMPTING_NEIGHBOURS = (
    "omicsclaw.runtime",
    "omicsclaw.engine",
    "omicsclaw.provider",
    "omicsclaw.providers",
    "omicsclaw.memory",
)
"""Named as well as covered by the rule, so a reader sees what it is for.

``omicsclaw.runtime`` holds the tool layer this one replaces and is the
dangerous one: after Q7 it is still called ``tools``, so reaching into it
for a helper looks entirely unremarkable in a diff.
"""


def _module_paths() -> list[pathlib.Path]:
    """Every module in the package, subpackages included.

    Globbed recursively rather than listed, so tasks B and C inherit the
    rule the moment they add a file instead of the moment they remember
    to add it here.
    """
    return sorted(_TOOLS_DIR.rglob("*.py"))


def _package_of(path: pathlib.Path) -> str:
    """The dotted package a module lives in, for resolving relative imports.

    Dropping the final component gives the package for a plain module
    (``omicsclaw/tools/base.py`` → ``omicsclaw.tools``) and for a package
    initialiser alike (``omicsclaw/tools/__init__.py`` → ``omicsclaw.tools``,
    since ``__init__`` is the component dropped).
    """
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
            # PEP 328: level 1 is the current package, each further level
            # ascends one. A level that ascends past the top is reported
            # as the empty string, which no whitelist entry matches.
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
"""Every way of naming a module at runtime, and **the whitelist is empty**.

Not "these are forbidden targets" but "this layer has no business
importing anything dynamically at all". A whitelist of permitted dynamic
targets would be unenforceable — the argument is an expression, and
``importlib.import_module("omicsclaw." + suffix)`` defeats any check that
reads it — so the call itself is what is refused. Nothing in the layer
needs an exception: a module here that wants to look something up at
runtime is reaching for the legacy package, because there is nothing else
inside ``omicsclaw`` it is allowed to reach for.

``spec_from_file_location`` and its two companions are here because
``tests/tools/test_function_tool.py`` loads the legacy validator that way
— by path, with no package name to match — which is the form a production
module would reach for once told not to say ``omicsclaw.runtime``.
"""


def _called_name(node: ast.Call) -> str:
    """The trailing identifier of whatever is being called, or ``""``.

    Attribute and bare-name forms collapse to the same answer on purpose:
    ``importlib.import_module(...)`` and the ``import_module(...)`` left
    behind by ``from importlib import import_module`` are one crossing
    written two ways, and a check that caught only the dotted one would be
    a check that rewards renaming the import.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _dynamic_import_calls(path: pathlib.Path) -> list[str]:
    """``name:lineno`` for every runtime-import call in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{_called_name(node)}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _called_name(node) in _DYNAMIC_IMPORT_CALLS
    ]


def _is_allowed(name: str) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in _ALLOWED_INTERNAL)


def test_the_package_has_modules_to_check():
    """A rule that vacuously passes over an empty directory is not a rule."""
    assert _module_paths(), f"no modules found under {_TOOLS_DIR}"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_tools_module_imports_only_schema_from_omicsclaw(path: pathlib.Path):
    offenders = [
        name
        for name in _imported_modules(path)
        if name.split(".")[0] == "omicsclaw" and not _is_allowed(name)
    ]

    assert not offenders, (
        f"{path.name} imports {offenders} — inside the omicsclaw namespace "
        "the tool layer may import omicsclaw.schema and nothing else"
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
def test_a_tools_module_imports_nothing_at_runtime(path: pathlib.Path):
    """The hole the two tests above share, closed at source level.

    Both of them read ``Import`` and ``ImportFrom`` nodes, so both are
    blind to a module named as a *string* and fetched inside a function
    body. That is not a theoretical gap: the crossing plan 0028 §5 names
    outright — reusing ``omicsclaw/runtime/tools/validation.py`` rather
    than re-implementing it — is four lines of ``import_module`` in
    :func:`~omicsclaw.tools.function_tool.validate_arguments`, and it
    passed every other check in this file.
    """
    offenders = _dynamic_import_calls(path)

    assert not offenders, (
        f"{path.name} imports at runtime via {offenders} — this layer has no "
        "dynamic imports, and a module named as a string is a module the "
        "import rules above cannot see"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_a_tools_module_imports_only_the_standard_library(path: pathlib.Path):
    """Checked against :data:`sys.stdlib_module_names`, not a blacklist.

    A tool that needs ``httpx`` imports it inside its own ``execute``, the
    way each provider adapter loads its vendor SDK inside its client
    factory — so importing the registry never pulls a dependency in.
    """
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


def test_importing_the_package_drags_in_no_unrelated_omicsclaw_module():
    """The property the source rule is a proxy for, checked directly.

    ``omicsclaw.version`` is the permitted straggler: the top-level
    ``__init__`` imports it for ``__version__``.
    """
    source = (
        "import sys, omicsclaw.tools as tools;"
        "assert tools.ToolRegistry is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.tools')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = _probe(source)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the tool layer dragged in {result.stdout.strip()}"
    )


_BEHAVIOUR_PROBE = '''
import asyncio
import sys
import tempfile

from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    BashTool,
    EditTool,
    MCPTool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
    read_tool,
    use_tool_context,
)
from omicsclaw.tools._websafety import HttpResponse
from omicsclaw.tools._workspace import Workspace


class Canned:
    async def request(self, method, url, **kwargs):
        return HttpResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "text/html"},
            body=b"<html><body><p>hi</p></body></html>",
            url=url,
        )


CALLS = [
    ("write_file", '{"path": "probe.txt", "content": "hello"}', False),
    ("read_file", '{"path": "probe.txt"}', False),
    ("read_file", '{"path": "probe.txt", "start_line": 0}', True),
    ("read_file", "{not json", True),
    (
        "edit_file",
        '{"path": "probe.txt", "source_text": "hello", "target_text": "bye"}',
        False,
    ),
    ("edit_file", '{"path": "probe.txt", "source_text": "gone"}', True),
    ("bash", '{"command": "echo hi"}', False),
    ("web_fetch", '{"url": "https://example.org/p"}', False),
    ("web_fetch", '{"url": "file:///etc/passwd"}', True),
    ("web_search", '{"query": "anything"}', False),
    ("mcp__srv__remote", '{"q": 1}', False),
    ("no_such_tool", "{}", True),
]


async def main():
    with tempfile.TemporaryDirectory() as root:
        workspace = Workspace(root)
        registry = ToolRegistry(
            (
                read_tool(workspace),
                WriteTool(workspace),
                EditTool(workspace),
                BashTool(workspace),
                WebFetchTool(transport=Canned()),
                WebSearchTool(transport=Canned()),
            )
        )
        registry.register(
            MCPTool("srv", "remote", caller=lambda payload: "remote: " + payload)
        )
        with use_tool_context(
            approval=lambda request: True,
            progress=lambda update: None,
            values={"workspace": root},
        ):
            for name, arguments, expected in CALLS:
                call = ToolCall(id="c", name=name, arguments=arguments)
                result = await registry.execute(call)
                assert result.is_error is expected, (name, result.output)


asyncio.run(main())
print(sorted(m for m in sys.modules if m.startswith("omicsclaw.runtime")))
'''
"""Every execution path this layer has, run for real in a fresh process.

The assertions inside are not the product — they are there so a probe
that silently stopped doing anything fails loudly instead of printing an
empty leak list. The product is the line after ``asyncio.run``: what
:data:`sys.modules` holds **once the tools have run**, which is the only
question a lazy ``import_module`` in a function body answers honestly.

Twelve calls, chosen to cover each way into the layer:
:class:`~omicsclaw.tools.function_tool.FunctionTool` succeeding, failing
validation and failing to decode; **every foundation tool**, including
the ones that need a workspace, an approval channel and a progress sink,
and the two that stand on the network boundary rather than the filesystem
one; :meth:`~omicsclaw.tools.mcp_tool.MCPTool.execute`; and the
registry's unknown-name path.

The list has to grow when a tool does. It did not when ``edit_file``,
``web_fetch`` and ``web_search`` arrived, so for one step the only check
here that does not depend on guessing a spelling covered none of them.
"""


def test_running_the_tools_does_not_pull_in_a_single_runtime_module():
    """Plan 0028 §5's forbidden reuse, checked by behaviour rather than syntax.

    The AST rules above are a proxy, and every proxy has a spelling they
    do not cover. This one has none: whatever a module did to reach the
    legacy layer — a dotted import, a string, a ``__import__`` built out
    of concatenation — the module it reached is in :data:`sys.modules`
    when the run finishes.

    Deliberately *not* also asserting on an import-time snapshot; that is
    :func:`test_importing_the_package_drags_in_no_unrelated_omicsclaw_module`
    above, and this one exists because that one was the whole check.
    """
    result = _probe(_BEHAVIOUR_PROBE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"running the tool layer loaded {result.stdout.strip()} — "
        "omicsclaw.runtime is the layer this one replaces"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_every_tools_module_imports_with_no_vendor_sdk_installed(
    path: pathlib.Path,
):
    """Keeps its meaning on a machine where the SDKs *are* installed."""
    relative = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    source = (
        "import sys;"
        "sys.meta_path.insert(0, type('Blocker', (), {"
        "  'find_spec': staticmethod(lambda name, *a, **k: ("
        "      (_ for _ in ()).throw(ImportError('blocked: ' + name))"
        "      if name.split('.')[0] in ('openai', 'anthropic') else None))"
        "})());"
        f"import {'.'.join(parts)};"
        "print('ok')"
    )
    result = _probe(source)

    assert result.returncode == 0, (
        f"{path.name} could not be imported without a vendor SDK:\n{result.stderr}"
    )
    assert result.stdout.strip() == "ok"


def test_the_public_surface_is_exactly_what_the_two_plans_delivered():
    """``__init__`` is an interface, so widening it should be deliberate.

    Renamed from ``…_what_tasks_a_b_and_c_delivered``: that named plan
    0028's three tasks, and plan 0029 has its own A/B/C/D, so the old name
    had quietly become ambiguous about which A it meant.

    Task B extended this list — the two adapters, their one public
    exception, and the whole of the out-of-band context convention — and
    updating it here is how that extension got noticed rather than
    absorbed. Plan 0029 extended it by three — ``read_tool``,
    ``WriteTool``, ``BashTool`` — and the owner's removal of plan 0028's
    three reference tools shrank it by four, which is the same mechanism
    working in the other direction.

    The context names dominate because the convention *is* the deliverable:
    a surface has to be able to bind a channel (``use_tool_context``,
    ``set_tool_context``) and a tool has to be able to read one
    (``require_approval``, ``report_progress``, ``context_value``) without
    either importing a private module.

    The repair round added the last two of those: ``use_effective_policy``
    and ``effective_policy``. They are the wire that makes
    ``register(policy=)`` mean something at execution time — the registry
    publishes what ``policy_for`` resolved, ``require_approval`` reads it
    — and they are exported rather than kept private because a dispatcher
    that is not this registry has to be able to publish one, and a tool
    written against the Protocol may want to read one. Exporting only the
    reader would leave the binder to be re-invented, which is how two
    implementations of one rule start.

    **The parallel-tool-calling round added three more**, on that same
    argument and for the second thing a dispatcher publishes:
    ``TimeoutPause``, ``use_timeout_pause`` and ``pause_tool_timeout`` are
    how the engine's per-call timeout is stopped while a human decides. A
    dispatcher other than this registry has to be able to publish one, and
    a tool that waits on a person has to be able to enter one, without
    either reaching into ``omicsclaw.engine`` or into a private module
    here.

    One of the three foundation tools is a factory and two are classes,
    which reads as an inconsistency and is not: ``read_file`` is a
    :class:`~omicsclaw.tools.function_tool.FunctionTool` and a function is
    not a tool until something configures one, while a hand-written tool
    already has a constructor. ``read_file`` is hand-written's opposite
    for a reason — it is the only one of the three that never asks a
    human, so it is the only one that does not need the bytes the model
    sent.

    **Plan 0029 adds exactly three**, and the count is the interesting
    part. Its task A delivered ``_workspace.py`` and ``_pathlock.py`` and
    widened this list by **nothing**: they are helpers that ``read``,
    ``write``, ``edit`` and ``bash`` share, not tools a surface mounts,
    and the underscore is the whole statement. Its task B adds
    ``read_tool`` and ``WriteTool`` — the same factory-versus-constructor
    asymmetry as above, for the same reason: ``read`` is a
    :class:`~omicsclaw.tools.function_tool.FunctionTool` and needs
    configuring, ``write`` is hand-written and already has a constructor.
    Its task C adds ``BashTool``, hand-written for ``write``'s reason —
    an ``ASK`` tool's approval prompt has to show the bytes the model
    sent — so it is a constructor too.

    **Plan 0029's §12 follow-ups add three more, and the same arithmetic
    holds.** ``EditTool`` completes the canonical file set and is
    hand-written for ``write``'s reason. ``WebFetchTool`` and
    ``WebSearchTool`` were ruled back into scope by the owner on
    2026-09-18, against plan 0029 §2, and are hand-written for the same
    reason again — both ask a human, and what a person reviewing a
    request needs to see is the URL exactly as the model spelled it.
    ``_websafety.py`` and ``_html.py`` widen this list by **nothing**,
    exactly as task A's two helpers did: an SSRF gate and an HTML reducer
    are things the tools stand on, not things a surface mounts.

    What is deliberately absent: ``Workspace``, ``read_lock`` and
    ``write_lock``, the four ``Environment`` Protocols, ``Transport``,
    ``PinnedTransport``, ``UrlRefused`` and ``CommandOutcome``. A surface
    that genuinely needs one imports the module that defines it; putting
    them here would make the package surface the place to look for
    internals. ``UrlRefused`` is the one worth arguing about, since a
    surface may want to recognise a blocked-URL refusal — but
    :exc:`~omicsclaw.tools._workspace.PathRefused` is not exported either,
    and inventing an exception hierarchy on the package surface for one of
    the two boundaries would be the inconsistency.

    ``ask_every_time`` (plan 0049) is here for the same reason
    ``use_effective_policy`` is: it is the permission gate's half of a
    channel whose other half, :func:`require_approval`, a tool calls.
    """
    import omicsclaw.tools as tools

    assert tools.__all__ == [
        "ApprovalChannel",
        "ApprovalDecision",
        "ApprovalDenied",
        "ApprovalMode",
        "ApprovalRequest",
        "ApprovalUnavailable",
        "BashTool",
        "EditTool",
        "FunctionTool",
        "MCPCaller",
        "MCPTool",
        "ProgressSink",
        "ProgressUpdate",
        "RiskLevel",
        "TimeoutPause",
        "Tool",
        "ToolAlreadyRegistered",
        "ToolArgumentError",
        "ToolContext",
        "ToolNameMismatch",
        "ToolPolicy",
        "ToolRegistrationError",
        "ToolRegistry",
        "WebFetchTool",
        "WebSearchTool",
        "WriteTool",
        "ask_every_time",
        "context_value",
        "current_context",
        "effective_policy",
        "mcp_tool_name",
        "pause_tool_timeout",
        "read_tool",
        "report_progress",
        "require_approval",
        "reset_tool_context",
        "sanitize_mcp_name",
        "set_tool_context",
        "use_effective_policy",
        "use_timeout_pause",
        "use_tool_context",
    ]
    assert all(hasattr(tools, name) for name in tools.__all__)
    assert tools.__all__ == sorted(tools.__all__), "keep the list sorted"

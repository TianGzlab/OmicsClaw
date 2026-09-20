"""The composition root's obligations to the hook chain.

Three of them, in the order they would go wrong.

**A deployment that mounts no hooks is unchanged.** Not "behaves the
same": *is the same objects*. This is what makes adding the seam cheap —
a regression in a hook-less deployment cannot be blamed on
:mod:`omicsclaw.hooks`.

**The chain goes inside the gate.** ``gate_tools(hook_tools(...))``.
Reverse the two and a hook can ask a second question, and a payload a
hook rewrote gets judged instead of the one the model sent.

**Every wrapper is unwrapped by whoever looks through one.** This is the
defect the step found on itself: ``_is_bash`` unwrapped one level, which
was right while the gate was the only wrapper. With a chain mounted,
``bash`` is a ``GatedTool`` around a ``HookedTool`` around the
``BashTool``, the search finds nothing, :func:`bash_policy` is never
consulted, and a sandboxed session asks for approval on every command —
with nothing raised, no test failing on the tool's own behaviour, and no
log line saying so.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.engine.executor import ConcurrencyAwareExecutor, DeadlineAwareExecutor
from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app, build_hooks, foundation_tools
from omicsclaw.entry.config import AppConfig, resolve_app_config
from omicsclaw.hooks import (
    AuditHook,
    Hook,
    HookCall,
    HookDecision,
    HookedTool,
    JsonlAuditSink,
    deny,
)
from omicsclaw.permission import CONFIG_KEY, GatedTool, Rules, save_rules
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.base import ToolPolicy
from omicsclaw.tools.builtin.bash import BashTool

_T = TypeVar("_T")
_DEADLINE = 10.0


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


@dataclasses.dataclass
class _ScriptedProvider:
    """Structural conformance only; this file never calls a model."""

    reply: str = "a summary"

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        return Completion(message=Message(role=Role.ASSISTANT, content=self.reply))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return _ScriptedProvider(reply=self.reply)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda provider, model: _ScriptedProvider()
    )


def _config(workspace: pathlib.Path, **overrides: object) -> AppConfig:
    return AppConfig(workspace=workspace, **overrides)


class Watcher(Hook):
    def __init__(self) -> None:
        self.seen: list[HookCall] = []

    async def before_execute(self, call: HookCall) -> HookDecision:
        self.seen.append(call)
        return HookDecision()


class ListSink:
    def __init__(self) -> None:
        self.records: list[Any] = []

    async def write(self, record) -> None:
        self.records.append(record)


def _unwrap(tool):
    while isinstance(tool, (GatedTool, HookedTool)):
        tool = tool.inner
    return tool


# ---- off by default -----------------------------------------------------


def test_no_hooks_are_configured_by_default(tmp_path):
    assert build_hooks(_config(tmp_path)) == ()


def test_the_default_deployment_wraps_nothing(tmp_path, offline):
    """Identity. "No hooks" has to mean the object graph did not change."""
    app = build_app(_config(tmp_path))

    hooked = [
        name
        for name in app.registry.names()
        if isinstance(_one_level(app.registry.get(name)), HookedTool)
    ]

    assert hooked == []


def _one_level(tool):
    return tool.inner if isinstance(tool, GatedTool) else tool


def test_naming_an_audit_log_is_the_whole_of_switching_it_on(tmp_path):
    hooks = build_hooks(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    assert len(hooks) == 1
    assert isinstance(hooks[0], AuditHook)
    assert isinstance(hooks[0].sink, JsonlAuditSink)
    assert hooks[0].sink.path == tmp_path / "audit.jsonl"


def test_there_is_no_default_audit_location(tmp_path):
    """Unlike every other file this config names.

    A missing rule file is an empty rule set, which costs nothing. An
    audit trail that appeared without being asked for would be a file
    about a person, written because nobody said no.
    """
    assert _config(tmp_path).audit_log is None
    assert not (tmp_path / ".omicsclaw" / "audit.jsonl").exists()


def test_the_flag_and_the_environment_both_reach_it(tmp_path):
    from_env = resolve_app_config(
        argv=(),
        env={"OMICSCLAW_AUDIT_LOG": str(tmp_path / "from-env.jsonl")},
        workspace=tmp_path,
    )

    from_flag = resolve_app_config(
        argv=("--audit-log", str(tmp_path / "from-flag.jsonl")),
        env={},
        workspace=tmp_path,
    )

    assert from_env.audit_log == tmp_path / "from-env.jsonl"
    assert from_flag.audit_log == tmp_path / "from-flag.jsonl"


# ---- the chain reaches the registry -------------------------------------


def test_a_configured_hook_wraps_every_mounted_tool(tmp_path, offline):
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    unhooked = [
        name
        for name in app.registry.names()
        if not isinstance(_one_level(app.registry.get(name)), HookedTool)
    ]

    assert app.registry.names(), "nothing was mounted, so nothing was checked"
    assert not unhooked, f"{unhooked} reached the registry unhooked"


def test_an_explicit_chain_replaces_the_configured_one(tmp_path, offline):
    watcher = Watcher()
    app = build_app(
        _config(tmp_path, audit_log=tmp_path / "audit.jsonl"), hooks=(watcher,)
    )

    chain = _one_level(app.registry.get("read_file"))
    assert isinstance(chain, HookedTool)
    assert chain.hooks == (watcher,)


def test_an_empty_chain_means_no_hooks_even_when_configured(tmp_path, offline):
    """``hooks=()`` is how a caller overrules the configuration."""
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"), hooks=())

    assert not isinstance(_one_level(app.registry.get("read_file")), HookedTool)


def test_a_callers_own_tools_are_hooked_too(tmp_path, offline):
    from tests.hooks._support import Echo

    watcher = Watcher()
    app = build_app(_config(tmp_path), tools=[Echo("custom")], hooks=(watcher,))

    assert isinstance(_one_level(app.registry.get("custom")), HookedTool)


def test_the_audit_file_is_written_when_a_tool_actually_runs(tmp_path, offline):
    log = tmp_path / "audit.jsonl"
    app = build_app(_config(tmp_path, audit_log=log))

    result = _run(
        app.registry.execute(
            ToolCall(
                id="1",
                name="read_file",
                arguments=json.dumps({"path": "nothing-here.txt"}),
            )
        )
    )

    assert result.is_error, "the read was expected to fail; the record is the point"
    written = json.loads(log.read_text("utf-8").splitlines()[0])
    assert written["tool"] == "read_file"
    assert written["outcome"] == "error"
    # The record names the failure class and not the path the tool was
    # asked for: a tool's error message quotes its own arguments, and an
    # audit file outlives the transcript that may legitimately hold them.
    assert written["detail"] == "ToolArgumentError"
    assert "nothing-here.txt" not in log.read_text("utf-8")


# ---- the order of the two wrappers --------------------------------------


def test_the_gate_is_outside_the_chain(tmp_path, offline):
    """``gate_tools(hook_tools(...))``, and the nesting says which is which."""
    app = build_app(_config(tmp_path), hooks=(Watcher(),))
    mounted = app.registry.get("read_file")

    assert isinstance(mounted, GatedTool)
    assert isinstance(mounted.inner, HookedTool)


def test_a_call_a_rule_denied_never_reaches_a_hook(tmp_path, offline):
    """The consequence of the ordering, and the reference's own blind spot.

    Permission decides first, so a refused call is not audited here. It is
    logged by the gate. A deployment that needs refusals in the audit file
    is asking for a different ordering, and this test is where that
    trade-off is written down rather than discovered.
    """
    save_rules(
        tmp_path / ".omicsclaw" / "settings.json",
        Rules.from_config({CONFIG_KEY: {"deny": ["read_file"]}}),
    )
    watcher = Watcher()
    app = build_app(_config(tmp_path), hooks=(watcher,))

    result = _run(
        app.registry.execute(
            ToolCall(id="1", name="read_file", arguments=json.dumps({"path": "a.txt"}))
        )
    )

    assert result.is_error
    assert "PermissionDenied" in result.output
    assert watcher.seen == []


def test_a_hook_denial_reaches_the_model_as_an_error(tmp_path, offline):
    class Guard(Hook):
        async def before_execute(self, call: HookCall) -> HookDecision:
            return deny("this deployment does not read files")

    app = build_app(_config(tmp_path), hooks=(Guard(),))

    result = _run(
        app.registry.execute(
            ToolCall(id="1", name="read_file", arguments=json.dumps({"path": "a.txt"}))
        )
    )

    assert result.is_error
    assert "HookDenied" in result.output
    assert "does not read files" in result.output


# ---- what must survive the extra wrapper --------------------------------


def test_the_registry_still_goes_to_the_engine_unwrapped(tmp_path, offline):
    """Defect R3: both optional Protocols must still be satisfied.

    A hook chain decorates a *tool*, so the registry is untouched — this
    is the assertion that says so rather than the docstring that claims
    it.
    """
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    assert isinstance(app.registry, ToolRegistry)
    assert isinstance(app.registry, DeadlineAwareExecutor)
    assert isinstance(app.registry, ConcurrencyAwareExecutor)


def test_the_authors_policy_survives_two_wrappers(tmp_path, offline):
    """A wrapper that ate ``policy`` would tighten every tool to ``ASK``
    and turn every ``concurrency_safe`` tool into a scheduling barrier."""
    bare = {tool.name: tool for tool in foundation_tools(_config(tmp_path))}
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    for name, tool in bare.items():
        declared = getattr(tool, "policy", None)
        if isinstance(declared, ToolPolicy):
            assert app.registry.policy_for(name) == declared, name


def test_bash_is_still_recognised_through_two_wrappers(tmp_path, offline):
    """The defect this step found on itself. See the module docstring."""
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    assert isinstance(_unwrap(app.registry.get("bash")), BashTool)
    assert assembly._is_bash(app.registry.get("bash"))


def test_the_one_level_unwrap_would_have_missed_it(tmp_path, offline):
    """The negative, so the fix above is not mistaken for decoration."""
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))
    mounted = app.registry.get("bash")

    assert not isinstance(_one_level(mounted), BashTool), (
        "one unwrap reaches the HookedTool, which is why _is_bash loops"
    )


def test_the_plan_tool_is_still_found_before_the_wrappers_go_on(tmp_path, offline):
    """The planning section is decided on names read off unwrapped tools."""
    app = build_app(_config(tmp_path, audit_log=tmp_path / "audit.jsonl"))

    assert "plan_write" in app.registry.names()
    assert app.plans is not None

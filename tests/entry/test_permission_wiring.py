"""The composition root's obligation: nothing reaches the registry ungated.

:class:`~omicsclaw.permission.GatedTool` decorates a tool rather than the
registry, which buys the layer three properties
(``omicsclaw/permission/gate.py``) at one cost: a tool registered without
passing through :func:`~omicsclaw.permission.gate_tools` is not gated. That
cost is paid here, and this file is what holds :func:`build_app` to it.

The failure this guards against is quiet. An ungated tool still works — it
still asks for itself, still resolves its policy — so nothing breaks. It just
stops consulting the rule file and the dangerous-command patterns, and the
only way to notice is to look.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
import re
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.engine.executor import ConcurrencyAwareExecutor, DeadlineAwareExecutor
from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app, build_permission_gate, foundation_tools
from omicsclaw.entry.config import AppConfig, AppConfigError, resolve_app_config
from omicsclaw.permission import (
    CONFIG_KEY,
    GatedTool,
    PermissionConfigError,
    PermissionMode,
    Rules,
    Verdict,
    save_rules,
)
from omicsclaw.provider import Completion, LLMProvider
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.base import ApprovalMode, ToolPolicy
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context

_T = TypeVar("_T")
_DEADLINE = 10.0

MOUNTED = (
    "read_file",
    "write_file",
    "edit_file",
    "bash",
    "web_fetch",
    "web_search",
    "use_skill",
    "plan_write",
    "memory_search",
    "memory_write",
    "task",
)

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


def _write_rules(workspace: pathlib.Path, **sections: list[str]) -> pathlib.Path:
    path = workspace / ".omicsclaw" / "settings.json"
    save_rules(path, Rules.from_config({CONFIG_KEY: sections}))
    return path


# ---- everything is gated ------------------------------------------------


def test_every_mounted_tool_is_gated(tmp_path, offline):
    app = build_app(_config(tmp_path))
    registry = app.registry

    ungated = [
        name
        for name in registry.names()
        if not isinstance(registry.get(name), GatedTool)
    ]

    assert registry.names() == MOUNTED
    assert not ungated, f"{ungated} reached the registry ungated"


def test_a_caller_s_own_tools_are_gated_too(tmp_path, offline):
    """The case where losing the gate would be least visible (plan 0031 Q13).

    ``build_registry``'s docstring leaves ``tools=`` as the seam that hooks,
    MCP and sub-agents arrive through. Gating them here rather than trusting
    each caller to is what makes "is this deployment gated" answerable in one
    place.
    """
    app = build_app(_config(tmp_path), tools=[_Custom()])

    # ``task`` is appended by the composition root whatever tool list it
    # was given, and goes behind the same gate as the caller's own.
    assert app.registry.names() == ("custom", "task")
    assert isinstance(app.registry.get("custom"), GatedTool)
    assert isinstance(app.registry.get("task"), GatedTool)
    assert app.permission is not None


class _Custom:
    policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, read_only=True)

    @property
    def name(self) -> str:
        return "custom"

    def definition(self):
        from omicsclaw.schema import ToolDefinition

        return ToolDefinition(name="custom", description="")

    async def execute(self, arguments: str) -> str:
        return "ok"


def test_the_gate_is_on_the_app_so_a_surface_can_reach_it(tmp_path, offline):
    app = build_app(_config(tmp_path, permission_mode=PermissionMode.READ_ONLY))

    assert app.permission is not None
    assert app.permission.mode is PermissionMode.READ_ONLY
    assert app.permission.store is not None


def test_the_bash_policy_pass_keeps_bash_gated(tmp_path, offline, monkeypatch):
    """``_apply_bash_policy`` re-registers a tool; it must be the wrapper.

    Handing ``replace`` the inner :class:`~omicsclaw.tools.BashTool` would
    swap the one tool most worth gating for an ungated one — and ``bash``
    would keep working, so only this assertion would notice.
    """
    monkeypatch.setattr(
        assembly,
        "bash_policy",
        lambda binding, current, auto_approve: dataclasses.replace(
            current, approval_mode=ApprovalMode.AUTO
        ),
    )

    app = build_app(_config(tmp_path))

    assert isinstance(app.registry.get("bash"), GatedTool)
    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.AUTO


def test_the_author_s_policy_survives_the_wrapper(tmp_path, offline):
    """A wrapper that hid ``tool.policy`` would silently default everything.

    And the default is ``ASK``, so the symptom would read as caution rather
    than as a lost declaration.
    """
    app = build_app(_config(tmp_path))

    assert app.registry.policy_for("read_file").approval_mode is ApprovalMode.AUTO
    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.ASK
    assert app.registry.policy_for("bash").prompts_for_itself


def test_the_registry_still_answers_both_optional_protocols(tmp_path, offline):
    """The R3 guard, restated where the gate could have broken it.

    Decorating a tool rather than the registry is what keeps this true. A
    registry-level wrapper that forgot either Protocol would not fail — it
    would quietly charge a human's approval time to ``tool_timeout``.
    """
    app = build_app(_config(tmp_path))

    assert isinstance(app.registry, ToolRegistry)
    assert isinstance(app.registry, DeadlineAwareExecutor)
    assert isinstance(app.registry, ConcurrencyAwareExecutor)


_POLICY_WORDS = (
    "gate",
    "gated",
    "Gated",
    "GatedTool",
    "permission gate",
    "permission mode",
    "PermissionMode",
    "auto-approve",
    "auto_approve",
    "approval_mode",
    "prompts_for_itself",
)
"""Words that would mean the gate, a tool's policy or the session's posture reached the model."""


def _policy_words_shown(app, *, tool: str | None = None) -> list[str]:
    """The policy words, as whole words, in the definitions the model gets.

    *tool* limits the search to that one tool's definition.
    """
    rendered = json.dumps(
        [
            dataclasses.asdict(d)
            for d in app.tools_snapshot
            if tool is None or d.name == tool
        ],
        ensure_ascii=False,
    )
    return [
        word
        for word in _POLICY_WORDS
        if re.search(rf"\b{re.escape(word)}\b", rendered)
    ]


def test_the_gate_does_not_change_what_the_model_is_shown(tmp_path, offline):
    """Policy never enters a prompt, and nor does the fact of being gated.

    The words are matched whole (``\\bgate\\b``), not as substrings.
    ``gate`` is a substring of ``delegate``, ``investigate``,
    ``aggregate`` and ``navigate`` — ordinary words in a tool description —
    so a substring check turned red twice on descriptions that leaked
    nothing, and a check that fails on innocent prose teaches people to
    delete it.
    The inflected forms that did carry meaning (``gated``, the
    ``GatedTool`` class name) are listed as words of their own.

    Saying that the user may be asked to approve a call, and that whether
    they are depends on the session's permission settings, is not a leak:
    the sentence is the same in every mode and names no rule, so it tells
    the model nothing about the posture it is running under. What this
    guards is the mechanism (the gate, its wrapper, a policy field) and the
    posture itself (a named mode). The bare word ``permission`` was on the
    list once and turned red on exactly that sentence, so the list names
    the phrases that carry posture instead.
    """
    app = build_app(_config(tmp_path))

    assert [d.name for d in app.tools_snapshot] == list(MOUNTED)
    assert _policy_words_shown(app) == []


class _Described(_Custom):
    """:class:`_Custom`, with a description chosen by the test."""

    def __init__(self, description: str) -> None:
        self._description = description

    def definition(self):
        from omicsclaw.schema import ToolDefinition

        return ToolDefinition(name="custom", description=self._description)


@pytest.mark.parametrize(
    ("description", "found"),
    [
        (
            "Delegate one step to a sub-agent to investigate, aggregate "
            "and navigate the results.",
            [],
        ),
        (
            "Depending on the session's permission settings, the user may be "
            "asked to approve a command before it runs.",
            [],
        ),
        ("Every call passes the permission gate first.", ["gate", "permission gate"]),
        ("This tool is gated by the rule file.", ["gated"]),
        ("Wrapped in GatedTool(bash).", ["GatedTool"]),
        (
            '{"approval_mode": "ask", "prompts_for_itself": true}',
            ["approval_mode", "prompts_for_itself"],
        ),
        (
            "The permission mode is auto-approve, so nobody is asked.",
            ["permission mode", "auto-approve"],
        ),
        ("Running under PermissionMode.AUTO_APPROVE.", ["PermissionMode"]),
    ],
    ids=[
        "innocent-substrings",
        "approval-is-conditional",
        "gate",
        "gated",
        "class-name",
        "policy-fields",
        "named-mode",
        "mode-enum",
    ],
)
def test_the_policy_word_check_tells_a_leak_from_a_substring(
    tmp_path, offline, description, found
):
    """The check above still catches what it is for, and only that.

    Each description goes through the same gate and the same snapshot as a
    real tool's. One that says the tool is gated, names the wrapper or
    carries a policy field is caught; one that merely contains ``gate``
    inside ``delegate`` or ``investigate`` is not.
    """
    app = build_app(_config(tmp_path), tools=[_Described(description)])

    assert _policy_words_shown(app, tool="custom") == found


# ---- the rule file reaches a real call ----------------------------------


def test_a_deny_rule_in_the_workspace_stops_a_real_bash_call(tmp_path, offline):
    """End to end through the assembled app: config file to refused tool."""
    _write_rules(tmp_path, deny=["bash(rm -rf /)"])
    app = build_app(_config(tmp_path))

    async def scenario():
        with use_tool_context(approval=lambda r: ApprovalDecision(approved=True)):
            return await app.registry.execute(
                ToolCall(
                    id="1",
                    name="bash",
                    arguments=json.dumps({"command": "rm -rf /"}),
                )
            )

    result = _run(scenario())

    assert result.is_error
    assert "PermissionDenied" in result.output


def test_an_allow_rule_in_the_workspace_silences_a_real_bash_call(tmp_path, offline):
    _write_rules(tmp_path, allow=["bash(echo gated)"])
    app = build_app(_config(tmp_path))
    asked: list[ApprovalRequest] = []

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=True)

    async def scenario():
        with use_tool_context(approval=channel):
            return await app.registry.execute(
                ToolCall(
                    id="1",
                    name="bash",
                    arguments=json.dumps({"command": "echo gated"}),
                )
            )

    result = _run(scenario())

    assert not result.is_error, result.output
    assert asked == [], "an allowed command must not interrupt anybody"
    assert "gated" in result.output


def test_remembering_through_the_app_writes_the_workspace_rule_file(
    tmp_path, offline
):
    app = build_app(_config(tmp_path))
    assert app.permission is not None

    pattern = app.permission.remember(
        "bash",
        json.dumps({"command": "git status"}),
        schema=app.registry.get("bash").definition().input_schema,
    )

    assert pattern == "bash(git status)"
    written = tmp_path / ".omicsclaw" / "settings.json"
    assert written.is_file()
    assert "bash(git status)" in written.read_text(encoding="utf-8")


def test_a_malformed_rule_file_stops_the_app_from_starting(tmp_path, offline):
    """Loud at start-up rather than on the first ``bash`` call mid-analysis."""
    path = tmp_path / ".omicsclaw" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PermissionConfigError):
        build_app(_config(tmp_path))


def test_a_missing_rule_file_is_not_an_error(tmp_path, offline):
    app = build_app(_config(tmp_path))

    assert app.permission is not None
    assert len(app.permission.rules) == 0


# ---- configuration ------------------------------------------------------


def test_the_default_rule_file_sits_inside_the_workspace(tmp_path):
    config = _config(tmp_path)

    assert config.permission_rules_path() == tmp_path / ".omicsclaw" / "settings.json"


def test_an_explicit_rule_file_is_used_as_given(tmp_path):
    elsewhere = tmp_path / "shared" / "rules.json"
    config = _config(tmp_path, permission_rules=elsewhere)

    assert config.permission_rules_path() == elsewhere


def test_the_default_mode_is_the_guarded_one(tmp_path):
    assert _config(tmp_path).permission_mode is PermissionMode.DEFAULT


@pytest.mark.parametrize("mode", list(PermissionMode))
def test_the_mode_arrives_from_a_flag(tmp_path, mode: PermissionMode):
    config = resolve_app_config(
        ["--workspace", str(tmp_path), "--permission-mode", mode.value], env={}
    )

    assert config.permission_mode is mode


def test_the_mode_arrives_from_the_environment(tmp_path):
    config = resolve_app_config(
        [], env={"OMICSCLAW_WORKSPACE": str(tmp_path), "OMICSCLAW_PERMISSION_MODE": "read-only"}
    )

    assert config.permission_mode is PermissionMode.READ_ONLY


def test_a_misspelled_mode_is_refused_rather_than_defaulted(tmp_path):
    """A typo that fell back to ``default`` is a control nobody notices lost."""
    with pytest.raises(AppConfigError, match="permission mode"):
        resolve_app_config(
            ["--workspace", str(tmp_path), "--permission-mode", "bypass_all"], env={}
        )


def test_the_rule_file_path_arrives_from_a_flag(tmp_path):
    elsewhere = tmp_path / "rules.json"
    config = resolve_app_config(
        ["--workspace", str(tmp_path), "--permission-rules", str(elsewhere)], env={}
    )

    assert config.permission_rules == elsewhere


def test_build_permission_gate_reads_the_config_and_nothing_else(tmp_path):
    _write_rules(tmp_path, deny=["bash"])
    gate = build_permission_gate(
        _config(tmp_path, permission_mode=PermissionMode.AUTO_APPROVE)
    )

    assert gate.mode is PermissionMode.AUTO_APPROVE
    assert len(gate.rules) == 1
    assert gate.store is not None
    assert gate.store.path == tmp_path / ".omicsclaw" / "settings.json"


def test_the_foundation_tools_themselves_are_not_gated(tmp_path):
    """:func:`foundation_tools` builds tools; gating is :func:`build_app`'s job.

    Kept separate so a sub-agent or a test can compose a narrower set and
    choose its own gate, which is the reason the wrapper is a decorator
    rather than something baked into each tool.
    """
    tools = foundation_tools(_config(tmp_path))

    assert not any(isinstance(tool, GatedTool) for tool in tools)


def test_a_read_only_app_refuses_bash_and_permits_read_file(tmp_path, offline):
    (tmp_path / "present.txt").write_text("alpha\n", encoding="utf-8")
    app = build_app(_config(tmp_path, permission_mode=PermissionMode.READ_ONLY))

    async def call(name: str, arguments: dict):
        with use_tool_context(approval=lambda r: ApprovalDecision(approved=True)):
            return await app.registry.execute(
                ToolCall(id="1", name=name, arguments=json.dumps(arguments))
            )

    refused = _run(call("bash", {"command": "echo hi"}))
    permitted = _run(call("read_file", {"path": "present.txt"}))

    assert refused.is_error
    assert "read_only" in refused.output
    assert not permitted.is_error, permitted.output
    assert "alpha" in permitted.output


def test_the_assembly_log_records_the_posture(tmp_path, offline, caplog):
    """An operator reading a log should be able to tell what was in force."""
    _write_rules(tmp_path, deny=["bash"])

    with caplog.at_level("INFO", logger="omicsclaw.entry.assembly"):
        build_app(_config(tmp_path, permission_mode=PermissionMode.BYPASS_ALL))

    assert "permission=bypass-all" in caplog.text
    assert "rules=1" in caplog.text


def test_the_provider_protocol_is_satisfied_structurally():
    """Keeps the LLMProvider import honest: no SDK, no vendor package."""
    assert isinstance(_ScriptedProvider(), LLMProvider)


def test_verdict_names_survive_a_round_trip():
    """``Verdict`` is what a rule file spells; the spelling is the contract."""
    for verdict in Verdict:
        assert Verdict(verdict.value) is verdict

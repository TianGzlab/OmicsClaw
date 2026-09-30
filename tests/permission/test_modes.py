"""The four postures, each pinned to an effect the others do not have.

The reference declares the same four and reads one of them, so ``read-only``
and ``auto-approve`` there are names in an enum with no behaviour attached.
The point of this file is that such a thing cannot happen here quietly: every
value has a test that fails if the value stops mattering, and
:func:`test_no_two_modes_agree_on_everything` fails if two of them collapse
into each other.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.permission import (
    CONFIG_KEY,
    DecisionSource,
    PermissionGate,
    PermissionMode,
    Rules,
    Verdict,
    gate_tools,
)
from omicsclaw.schema import ToolCall, ToolDefinition
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context

_T = TypeVar("_T")
_DEADLINE = 5.0

BASH_SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string"}},
    "required": ["command"],
}

SHELL_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
)

READER_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=True,
)

SEARCH_POLICY = ToolPolicy(
    risk_level=RiskLevel.MEDIUM,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    touches_network=True,
)


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


class Tool:
    """Records whether it ran; asks nobody, so the gate is the only asker."""

    def __init__(self, name: str, policy: ToolPolicy, schema: dict) -> None:
        self._name = name
        self.policy = policy
        self._schema = schema
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name, description="", input_schema=self._schema
        )

    async def execute(self, arguments: str) -> str:
        self.calls.append(arguments)
        return "ok"


def shell() -> Tool:
    return Tool("bash", SHELL_POLICY, BASH_SCHEMA)


def reader() -> Tool:
    return Tool(
        "read_file",
        READER_POLICY,
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


def searcher() -> Tool:
    return Tool(
        "web_search",
        SEARCH_POLICY,
        {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def rules(**sections: list[str]) -> Rules:
    return Rules.from_config({CONFIG_KEY: sections})


def verdict(
    mode: PermissionMode,
    tool: Tool,
    command: str,
    *,
    ruleset: Rules | None = None,
) -> tuple[Verdict, DecisionSource]:
    gate = PermissionGate(mode=mode, rules=ruleset)
    key = next(iter(tool.definition().input_schema["required"]))
    resolution = gate.resolve(
        tool.name,
        json.dumps({key: command}),
        policy=tool.policy,
        schema=tool.definition().input_schema,
    )
    return resolution.verdict, resolution.source


def approvals(mode: PermissionMode, tool: Tool, arguments: dict) -> int:
    """How many humans this call interrupts, driven through the registry."""
    asked: list[ApprovalRequest] = []

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=True)

    async def scenario() -> None:
        registry = ToolRegistry(gate_tools([tool], PermissionGate(mode=mode)))
        with use_tool_context(approval=channel):
            await registry.execute(
                ToolCall(id="1", name=tool.name, arguments=json.dumps(arguments))
            )

    _run(scenario())
    return len(asked)


# ---- default ------------------------------------------------------------


def test_default_falls_back_to_the_tool_s_own_policy():
    assert verdict(PermissionMode.DEFAULT, shell(), "ls") == (
        Verdict.ASK,
        DecisionSource.POLICY,
    )
    assert verdict(PermissionMode.DEFAULT, reader(), "counts.csv") == (
        Verdict.ALLOW,
        DecisionSource.POLICY,
    )


def test_default_is_the_guarded_value():
    """A deployment that says nothing gets the tools' own declarations."""
    assert PermissionGate().mode is PermissionMode.DEFAULT


# ---- auto-approve -------------------------------------------------------


def test_auto_approve_allows_what_default_would_have_asked_about():
    """The difference from ``default``, stated as the one call that differs."""
    assert verdict(PermissionMode.DEFAULT, shell(), "ls")[0] is Verdict.ASK
    assert verdict(PermissionMode.AUTO_APPROVE, shell(), "ls") == (
        Verdict.ALLOW,
        DecisionSource.MODE,
    )
    assert approvals(PermissionMode.AUTO_APPROVE, shell(), {"command": "ls"}) == 0


def test_auto_approve_still_honours_a_deny_rule():
    """"Stop asking me about ordinary work", not "stop checking"."""
    decided = verdict(
        PermissionMode.AUTO_APPROVE,
        shell(),
        "rm -rf /",
        ruleset=rules(deny=["bash(rm -rf /)"]),
    )

    assert decided == (Verdict.DENY, DecisionSource.RULE)


def test_auto_approve_still_asks_about_a_dangerous_command():
    decided = verdict(PermissionMode.AUTO_APPROVE, shell(), "sudo rm -rf /")

    assert decided == (Verdict.ASK, DecisionSource.DANGER)
    assert approvals(
        PermissionMode.AUTO_APPROVE, shell(), {"command": "sudo rm -rf /"}
    ) == 1


# ---- read-only ----------------------------------------------------------


def test_read_only_allows_a_tool_that_declares_read_only():
    assert verdict(PermissionMode.READ_ONLY, reader(), "counts.csv") == (
        Verdict.ALLOW,
        DecisionSource.POLICY,
    )


def test_read_only_denies_a_shell_outright():
    """Wider than the reference, which tries to classify shell text instead.

    ``bash`` cannot honestly claim ``read_only``, and "does this command
    write" is undecidable, so the honest answer is to refuse the tool.
    """
    assert verdict(PermissionMode.READ_ONLY, shell(), "ls") == (
        Verdict.DENY,
        DecisionSource.MODE,
    )


def test_read_only_denies_a_search_because_a_query_is_an_egress():
    """``SAFETY_RULES`` rule 1: genetic data never leaves this machine."""
    assert verdict(PermissionMode.READ_ONLY, searcher(), "BRCA1 cohort")[0] is (
        Verdict.DENY
    )


def test_read_only_denies_a_tool_that_declared_nothing():
    """A claim nobody wrote is not a claim. ``ToolPolicy()`` is undeclared."""
    undeclared = Tool("mystery", ToolPolicy(), BASH_SCHEMA)

    assert verdict(PermissionMode.READ_ONLY, undeclared, "x") == (
        Verdict.DENY,
        DecisionSource.MODE,
    )


def test_read_only_outranks_an_allow_rule():
    """Stage 2 sits above the rule file, so a stale whitelist cannot reopen it."""
    gate = PermissionGate(
        mode=PermissionMode.READ_ONLY, rules=rules(allow=["bash(git status)"])
    )

    resolution = gate.resolve(
        "bash",
        json.dumps({"command": "git status"}),
        policy=SHELL_POLICY,
        schema=BASH_SCHEMA,
    )

    assert resolution.verdict is Verdict.DENY


def test_read_only_stops_the_tool_and_asks_nobody():
    tool = shell()

    assert approvals(PermissionMode.READ_ONLY, tool, {"command": "ls"}) == 0
    assert tool.calls == []


# ---- bypass-all ---------------------------------------------------------


def test_bypass_all_runs_what_a_deny_rule_forbids():
    """The one value whose content is the removal of every control here."""
    gate = PermissionGate(
        mode=PermissionMode.BYPASS_ALL, rules=rules(deny=["bash(rm -rf /)"])
    )

    resolution = gate.resolve(
        "bash",
        json.dumps({"command": "rm -rf /"}),
        policy=SHELL_POLICY,
        schema=BASH_SCHEMA,
    )

    assert resolution.verdict is Verdict.ALLOW
    assert resolution.source is DecisionSource.MODE


def test_bypass_all_asks_nobody_even_about_a_fork_bomb():
    tool = shell()

    assert approvals(PermissionMode.BYPASS_ALL, tool, {"command": ":(){ :|:& };:"}) == 0
    assert tool.calls


def test_bypass_all_runs_a_write_under_read_only_s_own_test_case():
    """Bypass is checked first, so it is not narrowed by the read-only stage."""
    assert verdict(PermissionMode.BYPASS_ALL, shell(), "ls")[0] is Verdict.ALLOW


def test_bypass_all_records_that_the_session_was_ungated():
    """A transcript should show it, since nothing else in it will."""
    resolution = PermissionGate(mode=PermissionMode.BYPASS_ALL).resolve(
        "bash", "{}", policy=SHELL_POLICY, schema=BASH_SCHEMA
    )

    assert "bypass-all" in resolution.reason


# ---- the four are four --------------------------------------------------


def test_no_two_modes_agree_on_everything():
    """If two collapse into each other, one of them is a name with no behaviour.

    The reference's ``auto-approve`` and ``read-only`` are exactly that: both
    behave as ``default``, because nothing reads them.
    """
    probes = [
        (shell(), "ls"),
        (shell(), "rm -rf /"),
        (reader(), "counts.csv"),
    ]
    ruleset = rules(deny=["bash(rm -rf /)"])

    signatures = {
        mode: tuple(
            verdict(mode, tool, argument, ruleset=ruleset)
            for tool, argument in probes
        )
        for mode in PermissionMode
    }

    assert len(set(signatures.values())) == len(PermissionMode), signatures


@pytest.mark.parametrize("mode", list(PermissionMode))
def test_every_mode_round_trips_through_its_own_name(mode: PermissionMode):
    """The value logged is the value written: a ``StrEnum``, checked."""
    assert PermissionMode(mode.value) is mode
    assert str(mode) == mode.value

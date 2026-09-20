"""The gate: what it decides, and — the part that matters — what that does.

Plan 0028 §4 Q5's lesson is the spine of this file. A two-source policy with
a precedence table and four passing tests shipped once in this repository
while *no production code read the resolved policy at all*, so a deployment
tightening a tool to ``ASK`` was silently ignored. So every rule here is
tested through :meth:`omicsclaw.tools.ToolRegistry.execute` — resolution
*and* effect — and pinned in the **tightening** direction: a test that a
loosening works proves nothing, because a gate that does nothing passes it.

The three questions each test answers one of:

* did the tool run?
* how many humans were asked?
* which reason did the human read?
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

import pytest

from omicsclaw.permission import (
    CONFIG_KEY,
    DecisionSource,
    GatedTool,
    PermissionDenied,
    PermissionGate,
    PermissionMode,
    RuleStore,
    Rules,
    Verdict,
    gate_tools,
)
from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.schema import ToolCall, ToolDefinition, ToolResult
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.base import ApprovalMode, RiskLevel, Tool, ToolPolicy
from omicsclaw.tools.context import (
    ApprovalDecision,
    ApprovalRequest,
    effective_policy,
    require_approval,
    use_tool_context,
)

BASH_SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string"}},
    "required": ["command"],
}

_T = TypeVar("_T")

PATH_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}


class Asking:
    """A tool that asks for itself, with a prompt of its own. Like ``bash``."""

    def __init__(
        self,
        name: str = "bash",
        *,
        policy: ToolPolicy | None = None,
        schema: dict | None = None,
    ) -> None:
        self._name = name
        self.policy = policy or ToolPolicy(
            risk_level=RiskLevel.HIGH,
            approval_mode=ApprovalMode.ASK,
            prompts_for_itself=True,
        )
        self._schema = schema if schema is not None else BASH_SCHEMA
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name, description="", input_schema=self._schema
        )

    async def execute(self, arguments: str) -> str:
        await require_approval(
            self._name,
            arguments,
            policy=self.policy,
            reason=f"{self._name}'s own prompt",
        )
        self.calls.append(arguments)
        return "done"


class Silent:
    """A tool that never asks, because its policy says it need not. Like ``read_file``."""

    def __init__(
        self,
        name: str = "read_file",
        *,
        policy: ToolPolicy | None = None,
        schema: dict | None = None,
    ) -> None:
        self._name = name
        self.policy = policy or ToolPolicy(
            risk_level=RiskLevel.LOW,
            approval_mode=ApprovalMode.AUTO,
            read_only=True,
        )
        self._schema = schema if schema is not None else PATH_SCHEMA
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
        return "content"


@dataclass
class Human:
    """A scripted approver that records every question it was asked."""

    answers: list[bool] = field(default_factory=list)
    asked: list[ApprovalRequest] = field(default_factory=list)

    def __call__(self, request: ApprovalRequest) -> ApprovalDecision:
        self.asked.append(request)
        index = len(self.asked) - 1
        approved = self.answers[index] if index < len(self.answers) else True
        return ApprovalDecision(
            approved=approved, reason="" if approved else "not this time"
        )

    @property
    def count(self) -> int:
        return len(self.asked)


def rules(**sections: list[str]) -> Rules:
    return Rules.from_config({CONFIG_KEY: sections})


_DEADLINE = 5.0
"""Seconds one scenario may take. A hang guard, not a measurement."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; this is the repository's convention."""

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


def run(
    gate: PermissionGate,
    tool: Tool,
    arguments: dict,
    human: Human | None = None,
    *,
    policy: ToolPolicy | None = None,
) -> tuple[ToolResult, Human]:
    """Drive one call the way production does: through the registry."""

    async def scenario() -> tuple[ToolResult, Human]:
        registry = ToolRegistry()
        registry.register(gate_tools([tool], gate)[0], policy)
        with use_tool_context(approval=asker):
            result = await registry.execute(
                ToolCall(id="1", name=tool.name, arguments=json.dumps(arguments))
            )
        return result, asker

    asker = human if human is not None else Human()
    return _run(scenario())


# ---- deny ---------------------------------------------------------------


def test_a_deny_rule_stops_the_tool_before_it_runs():
    """The capability that did not exist at all before this layer."""
    tool = Asking()
    gate = PermissionGate(rules=rules(deny=["bash(rm -rf /)"]))

    result, human = run(gate, tool, {"command": "rm -rf /"})

    assert result.is_error
    assert tool.calls == []
    assert human.count == 0, "a denial is not a question"


def test_a_denial_names_the_rule_that_decided():
    """So an operator reading the transcript knows which line to edit."""
    gate = PermissionGate(rules=rules(deny=["bash(rm -rf /)"]))

    result, _ = run(gate, Asking(), {"command": "rm -rf /"})

    assert "bash(rm -rf /)" in result.output


def test_a_denial_reaches_the_model_as_an_error_it_can_read():
    """Not a silent no-op returning "done", which teaches a model to retry."""
    gate = PermissionGate(rules=rules(deny=["bash"]))

    result, _ = run(gate, Asking(), {"command": "ls"})

    assert result.is_error
    assert "PermissionDenied" in result.output


def test_permission_denied_is_an_approval_denial():
    """One ``except`` covers all three ways consent can be absent."""
    from omicsclaw.tools.context import ApprovalDenied

    assert issubclass(PermissionDenied, ApprovalDenied)


# ---- allow --------------------------------------------------------------


def test_an_allow_rule_silences_a_tool_whose_own_policy_asks():
    """The whole point of the rule file: per-argument granularity for ``bash``."""
    tool = Asking()
    gate = PermissionGate(rules=rules(allow=["bash(git status)"]))

    result, human = run(gate, tool, {"command": "git status"})

    assert not result.is_error
    assert tool.calls, "the tool must have run"
    assert human.count == 0, "an allowed call must not prompt"


def test_an_allow_rule_does_not_silence_a_different_command():
    """Same tool, one argument away: the allow must not leak sideways."""
    tool = Asking()
    gate = PermissionGate(rules=rules(allow=["bash(git status)"]))

    _, human = run(gate, tool, {"command": "git push --force"})

    assert human.count == 1


# ---- who asks -----------------------------------------------------------


def test_an_unmatched_call_leaves_the_tool_to_ask_with_its_own_prompt():
    """``edit_file`` shows a diff and ``web_fetch`` a URL; those must survive.

    "When a human's reading is the control, what they read has to be the
    thing that happens" — plan 0029. A gate that replaced every prompt with
    its own generic one would be a downgrade dressed as a control.
    """
    tool = Asking()
    gate = PermissionGate()

    _, human = run(gate, tool, {"command": "ls -la"})

    assert human.count == 1
    assert human.asked[0].reason == "bash's own prompt"


def test_an_ask_rule_on_a_tool_that_already_asks_does_not_double_prompt():
    """The rule adds nothing here, so it must not cost a second question."""
    gate = PermissionGate(rules=rules(ask=["bash(pip install*)"]))

    _, human = run(gate, Asking(), {"command": "pip install scanpy"})

    assert human.count == 1
    assert human.asked[0].reason == "bash's own prompt"


def test_an_ask_rule_on_an_auto_tool_really_does_ask():
    """**The tightening direction.** Q5's failure shape, pinned.

    ``read_file`` self-approves. Without the gate asking, an ``ask`` rule
    naming it resolves correctly, reads correctly in ``policy_for``, and has
    no effect whatsoever.
    """
    tool = Silent()
    gate = PermissionGate(rules=rules(ask=["read_file(/etc/shadow)"]))

    result, human = run(gate, tool, {"path": "/etc/shadow"})

    assert human.count == 1
    assert not result.is_error
    assert tool.calls


def test_refusing_an_escalated_auto_tool_stops_it():
    """And the refusal has to bite, not merely be recorded."""
    tool = Silent()
    gate = PermissionGate(rules=rules(ask=["read_file(/etc/shadow)"]))

    result, human = run(
        gate, tool, {"path": "/etc/shadow"}, Human(answers=[False])
    )

    assert human.count == 1
    assert result.is_error
    assert tool.calls == [], "a refused tool must not have run"


def test_an_auto_tool_with_nothing_said_about_it_is_not_interrupted():
    tool = Silent()

    result, human = run(PermissionGate(), tool, {"path": "counts.csv"})

    assert not result.is_error
    assert human.count == 0
    assert tool.calls


# ---- danger -------------------------------------------------------------


def test_a_dangerous_command_is_asked_about_once_with_the_danger_reason():
    """``bash`` would ask anyway — but it would not say what is dangerous."""
    tool = Asking()

    _, human = run(PermissionGate(), tool, {"command": "rm -rf /"})

    assert human.count == 1, "asked twice is how a person learns to click yes"
    assert "deletes" in human.asked[0].reason
    assert human.asked[0].risk_level is RiskLevel.HIGH


def test_a_dangerous_command_carries_the_pattern_s_risk_not_the_tool_s():
    tool = Asking(policy=ToolPolicy(risk_level=RiskLevel.LOW))

    _, human = run(PermissionGate(), tool, {"command": "systemctl restart x"})

    assert human.asked[0].risk_level is RiskLevel.MEDIUM


def test_refusing_a_dangerous_command_stops_it():
    tool = Asking()

    result, _ = run(
        PermissionGate(), tool, {"command": "rm -rf /"}, Human(answers=[False])
    )

    assert result.is_error
    assert tool.calls == []


def test_an_allow_rule_outranks_a_danger_pattern():
    """Rules are stage 3 and danger is stage 4: a deployment's word wins.

    Somebody who writes ``allow: ["bash(rm -rf ./tmp_run)"]`` has read the
    command more carefully than a regular expression can.
    """
    tool = Asking()
    gate = PermissionGate(rules=rules(allow=["bash(rm -rf ./tmp_run)"]))

    result, human = run(gate, tool, {"command": "rm -rf ./tmp_run"})

    assert not result.is_error
    assert human.count == 0
    assert tool.calls


def test_the_danger_patterns_only_read_a_shell_argument():
    """Applicability comes from the schema, not from the name ``bash``."""
    tool = Silent(name="write_file", schema=PATH_SCHEMA)

    _, human = run(gate_for(), tool, {"path": "rm -rf /"})

    assert human.count == 0


def gate_for() -> PermissionGate:
    return PermissionGate()


def test_a_renamed_shell_tool_is_still_scanned():
    """A sandboxed or renamed shell inherits the patterns with no table edit."""
    tool = Asking(name="run_in_container", schema=BASH_SCHEMA)

    _, human = run(PermissionGate(), tool, {"command": "rm -rf /"})

    assert human.count == 1
    assert "deletes" in human.asked[0].reason


# ---- no channel bound ---------------------------------------------------


def test_an_escalation_with_nobody_to_ask_fails_closed():
    """The absence of a channel is not consent — and now nor is an AUTO policy."""
    tool = Silent()
    gate = PermissionGate(rules=rules(ask=["read_file(/etc/shadow)"]))
    registry = ToolRegistry()
    registry.register(gate_tools([tool], gate)[0])

    # No use_tool_context, so no approval channel is bound at all.
    result = _run(
        registry.execute(
            ToolCall(
                id="1",
                name="read_file",
                arguments=json.dumps({"path": "/etc/shadow"}),
            )
        )
    )

    assert result.is_error
    assert "ApprovalUnavailable" in result.output
    assert tool.calls == []


# ---- the deployment's policy outranks the author's ----------------------


def test_a_deployment_tightening_a_tool_to_ask_is_honoured():
    """``register(policy=)`` beats ``tool.policy``, through the gate as well.

    The gate reads the registry's *published* resolution rather than the
    tool's attribute, so the precedence the tool layer established is not
    quietly re-derived from a second source here.

    **This test found a hole.** ``Silent`` never calls ``require_approval``,
    and an earlier gate inferred "the tool will ask" from ``approval_mode``
    being ``ASK`` — so this call ran with nobody asked. That is why
    :attr:`~omicsclaw.tools.ToolPolicy.prompts_for_itself` exists and why it
    defaults to ``False``.
    """
    tool = Silent()

    result, human = run(
        PermissionGate(),
        tool,
        {"path": "counts.csv"},
        policy=ToolPolicy(approval_mode=ApprovalMode.ASK),
    )

    assert human.count == 1, "the deployment said ask"
    assert not result.is_error


def test_a_tool_that_does_not_claim_to_prompt_is_asked_about_by_the_gate():
    """The claim is opt-in, so an undeclared tool is gated, not trusted."""
    tool = Silent(
        policy=ToolPolicy(approval_mode=ApprovalMode.ASK, prompts_for_itself=False)
    )

    result, human = run(PermissionGate(), tool, {"path": "counts.csv"})

    assert human.count == 1
    assert not result.is_error
    assert tool.calls


def test_refusing_an_undeclared_tool_stops_it():
    tool = Silent(
        policy=ToolPolicy(approval_mode=ApprovalMode.ASK, prompts_for_itself=False)
    )

    result, human = run(
        PermissionGate(), tool, {"path": "counts.csv"}, Human(answers=[False])
    )

    assert human.count == 1
    assert result.is_error
    assert tool.calls == []


def test_the_claim_never_widens_what_a_rule_denied():
    """A tool cannot talk its way past a ``deny`` by claiming to prompt."""
    tool = Asking()
    gate = PermissionGate(rules=rules(deny=["bash"]))

    result, human = run(gate, tool, {"command": "ls"})

    assert result.is_error
    assert human.count == 0
    assert tool.calls == []


def test_a_deployment_loosening_a_tool_to_auto_is_honoured_too():
    tool = Asking()

    result, human = run(
        PermissionGate(),
        tool,
        {"command": "ls"},
        policy=ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    assert human.count == 0
    assert not result.is_error
    assert tool.calls


# ---- resolve, on its own ------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (PermissionMode.DEFAULT, Verdict.ASK),
        (PermissionMode.AUTO_APPROVE, Verdict.ALLOW),
        (PermissionMode.READ_ONLY, Verdict.DENY),
        (PermissionMode.BYPASS_ALL, Verdict.ALLOW),
    ],
)
def test_resolve_is_a_pure_function_of_its_arguments(
    mode: PermissionMode, expected: Verdict
):
    """No event loop, no channel, nothing run: a decision table is testable."""
    gate = PermissionGate(mode=mode)

    resolution = gate.resolve(
        "bash",
        json.dumps({"command": "ls"}),
        policy=ToolPolicy(approval_mode=ApprovalMode.ASK),
        schema=BASH_SCHEMA,
    )

    assert resolution.verdict is expected


def test_resolve_reports_which_stage_answered():
    gate = PermissionGate(rules=rules(deny=["bash"]))
    payload = json.dumps({"command": "rm -rf /"})

    by_rule = gate.resolve(
        "bash", payload, policy=ToolPolicy(), schema=BASH_SCHEMA
    )
    by_danger = PermissionGate().resolve(
        "bash", payload, policy=ToolPolicy(), schema=BASH_SCHEMA
    )
    by_policy = PermissionGate().resolve(
        "read_file",
        json.dumps({"path": "a"}),
        policy=ToolPolicy(approval_mode=ApprovalMode.AUTO),
        schema=PATH_SCHEMA,
    )

    assert by_rule.source is DecisionSource.RULE
    assert by_danger.source is DecisionSource.DANGER
    assert by_policy.source is DecisionSource.POLICY


def test_resolve_survives_a_tool_with_no_schema():
    resolution = PermissionGate(rules=rules(deny=["mystery"])).resolve(
        "mystery", "{}", policy=ToolPolicy(), schema=None
    )

    assert resolution.verdict is Verdict.DENY


# ---- always allow -------------------------------------------------------


def test_remember_writes_a_rule_that_silences_exactly_that_call(tmp_path):
    path = tmp_path / "settings.json"
    gate = PermissionGate(rules=RuleStore(path))
    payload = json.dumps({"command": "git status"})

    pattern = gate.remember("bash", payload, schema=BASH_SCHEMA)

    assert pattern == "bash(git status)"
    after = gate.resolve(
        "bash", payload, policy=ToolPolicy(), schema=BASH_SCHEMA
    )
    assert after.verdict is Verdict.ALLOW
    assert after.source is DecisionSource.RULE


def test_remember_does_not_silence_a_command_it_was_not_asked_about(tmp_path):
    gate = PermissionGate(rules=RuleStore(tmp_path / "settings.json"))
    gate.remember("bash", json.dumps({"command": "git status"}), schema=BASH_SCHEMA)

    after = gate.resolve(
        "bash",
        json.dumps({"command": "git status; rm -rf /"}),
        policy=ToolPolicy(),
        schema=BASH_SCHEMA,
    )

    assert after.verdict is not Verdict.ALLOW


def test_remember_reports_honestly_when_there_is_nowhere_to_write():
    """A remembered decision that was not written is a prompt they see again."""
    gate = PermissionGate(rules=rules(allow=["read_file"]))

    assert gate.store is None
    assert gate.remember("bash", "{}") is None


def test_remembering_takes_effect_on_the_next_call(tmp_path):
    """End to end: the reason the store re-reads its file."""
    gate = PermissionGate(rules=RuleStore(tmp_path / "settings.json"))
    tool = Asking()
    payload = {"command": "git status"}

    _, first = run(gate, tool, payload)
    gate.remember("bash", json.dumps(payload), schema=BASH_SCHEMA)
    _, second = run(gate, tool, payload)

    assert first.count == 1
    assert second.count == 0


# ---- the wrapper --------------------------------------------------------


def test_a_gated_tool_is_indistinguishable_in_a_prompt():
    tool = Asking()
    gated = GatedTool(tool, PermissionGate())

    assert gated.name == tool.name
    assert gated.definition() == tool.definition()
    assert isinstance(gated, Tool)


def test_a_gated_tool_passes_the_author_s_policy_through():
    """Otherwise every gated tool falls back to the registry's ``ASK`` default.

    Which looks like an excess of caution rather than a lost declaration, so
    nobody would chase it.
    """
    tool = Silent()
    registry = ToolRegistry(gate_tools([tool], PermissionGate()))

    assert registry.policy_for("read_file") == tool.policy


def test_a_tool_with_no_policy_attribute_still_gates():
    class Bare:
        @property
        def name(self) -> str:
            return "bare"

        def definition(self) -> ToolDefinition:
            return ToolDefinition(name="bare", description="")

        async def execute(self, arguments: str) -> str:
            return "ok"

    gated = GatedTool(Bare(), PermissionGate())

    assert gated.policy is None
    assert isinstance(gated, Tool)


def test_gating_is_idempotent():
    """Two wrappers around one tool resolve twice and ask twice."""
    tool = Asking()
    gate = PermissionGate()
    once = gate_tools([tool], gate)
    twice = gate_tools(once, gate)

    assert twice[0] is once[0]


def test_gating_preserves_order():
    """Tool-list order is the prompt-prefix cache's order (plan 0028)."""
    tools = [Asking("a"), Asking("b"), Asking("c")]

    gated = gate_tools(tools, PermissionGate())

    assert [tool.name for tool in gated] == ["a", "b", "c"]


def test_the_wrapper_exposes_what_it_wraps():
    tool = Asking()

    assert GatedTool(tool, PermissionGate()).inner is tool


def test_a_gated_tool_called_with_no_registry_in_the_path_still_gates():
    """A script or a test driving the wrapper directly is not an escape hatch."""
    tool = Asking()
    gated = GatedTool(tool, PermissionGate(rules=rules(deny=["bash"])))

    with pytest.raises(PermissionDenied):
        _run(gated.execute(json.dumps({"command": "ls"})))

    assert tool.calls == []


def test_four_concurrent_calls_each_get_their_own_decision():
    """Driven through the engine's real scheduler, with forced interleaving.

    The gate publishes its settled decision through a
    :class:`~contextvars.ContextVar`, which is only safe because
    ``engine/executor.py`` runs each call in its own :class:`asyncio.Task`
    and ``Task.__init__`` copies the context. That is an argument, and this
    is the test of it — with ``await asyncio.sleep(0)`` on both sides of
    each approval so the four workers genuinely interleave rather than
    running to completion one at a time.

    The repository has been bitten by the other kind of concurrency test:
    ``edit_file``'s locks could both be deleted with the whole suite still
    green, because the tasks never actually overlapped. Four different
    verdicts in one turn is what makes cross-talk visible — a leaked
    resolution would show up as a call seeing the wrong ``approval_mode``,
    a missing prompt, or a prompt carrying another call's risk level.
    """
    interleaving: list[tuple[str, str, str]] = []

    class Interleaved(Asking):
        async def execute(self, arguments: str) -> str:
            for _ in range(3):
                await asyncio.sleep(0)
            before = effective_policy()
            await require_approval(
                self._name, arguments, policy=self.policy, reason="own"
            )
            for _ in range(3):
                await asyncio.sleep(0)
            after = effective_policy()
            assert before is not None and after is not None
            interleaving.append(
                (
                    json.loads(arguments)["command"],
                    before.approval_mode.value,
                    after.approval_mode.value,
                )
            )
            self.calls.append(arguments)
            return "done"

    tools = [Interleaved("a"), Interleaved("b"), Interleaved("c")]
    gate = PermissionGate(rules=rules(allow=["a(free)"], deny=["c(nope)"]))
    asked: list[tuple[str, str, str]] = []

    async def channel(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(
            (
                request.tool_name,
                json.loads(request.arguments)["command"],
                request.risk_level.value,
            )
        )
        await asyncio.sleep(0)
        return ApprovalDecision(approved=True)

    calls = [
        ToolCall(id="1", name="a", arguments=json.dumps({"command": "free"})),
        ToolCall(id="2", name="b", arguments=json.dumps({"command": "sudo thing"})),
        ToolCall(id="3", name="c", arguments=json.dumps({"command": "nope"})),
        ToolCall(id="4", name="b", arguments=json.dumps({"command": "ls -la"})),
    ]

    async def scenario() -> list[Any]:
        registry = ToolRegistry(gate_tools(tools, gate))
        collected: list[Any] = []
        with use_tool_context(approval=channel):
            async for _event in execute_tool_calls(
                registry, calls, EngineConfig(), collected
            ):
                pass
        return collected

    results = _run(scenario())

    # One result per call, in call order.
    assert [r.tool_call_id for r in results] == ["1", "2", "3", "4"]
    assert [r.is_error for r in results] == [False, False, True, False]

    # Exactly two humans interrupted for four calls: the allowed one and the
    # denied one ask nobody, the dangerous one is the gate's question, and
    # the ordinary one is the tool's.
    assert sorted(asked) == [
        ("b", "ls -la", "high"),
        ("b", "sudo thing", "medium"),
    ]

    # The settled AUTO reached the gate-asked call and *only* it: the
    # ordinary call saw ASK on both sides of its own approval.
    assert sorted(interleaving) == [
        ("free", "auto", "auto"),
        ("ls -la", "ask", "ask"),
        ("sudo thing", "auto", "auto"),
    ]

    # The denied tool never ran at all.
    assert tools[2].calls == []


def test_nothing_is_left_bound_after_a_turn():
    """A resolution outliving its call is one the next thing to run would read."""
    tool = Asking()

    run(PermissionGate(rules=rules(allow=["bash(ls)"])), tool, {"command": "ls"})

    assert effective_policy() is None


def test_a_settled_call_does_not_rewrite_the_rest_of_the_policy():
    """Consent for one call is not a licence to relax ``read_only`` too."""
    seen: list[ToolPolicy | None] = []

    class Observer:
        policy = ToolPolicy(
            approval_mode=ApprovalMode.AUTO, read_only=True, risk_level=RiskLevel.LOW
        )

        @property
        def name(self) -> str:
            return "observer"

        def definition(self) -> ToolDefinition:
            return ToolDefinition(name="observer", description="")

        async def execute(self, arguments: str) -> str:
            from omicsclaw.tools.context import effective_policy

            seen.append(effective_policy())
            return "ok"

    run(PermissionGate(), Observer(), {})

    assert seen and seen[0] is not None
    assert seen[0].approval_mode is ApprovalMode.AUTO
    assert seen[0].read_only is True
    assert seen[0].risk_level is RiskLevel.LOW

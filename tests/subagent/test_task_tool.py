"""The ``task`` tool: what the model is shown, and what it is refused.

Plan 0046 §5 and §6. The definition is rebuilt from the registry on every
read because it is the only thing the model chooses a sub-agent on, so a
definition loaded from a file has to reach the enum without anything else
being told. The refusals all name the sub-agents that do exist: a model
that misspelled one can correct itself in the same turn.

The second anti-recursion guard lives here, behind
``resolve_tools``. It is deliberately redundant — it fires only if that
removal stops working — and the mutation that proves it is the same one
``tests/subagent/test_definition.py`` names.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from omicsclaw.schema import ToolCall
from omicsclaw.subagent import (
    TASK_TOOL_NAME,
    RecursionRefused,
    SubAgentDefinition,
    SubAgentRegistry,
    TaskTool,
)
from omicsclaw.tools import ApprovalMode, RiskLevel, ToolRegistry
from omicsclaw.tools.function_tool import ToolArgumentError

SURVEYOR = SubAgentDefinition(
    name="surveyor",
    description="Surveys a tree of files",
    system_prompt="You survey.",
)
REVIEWER = SubAgentDefinition(
    name="reviewer",
    description="Reviews a diff",
    system_prompt="You review.",
    tools=("read_file",),
)


class _Recorder:
    """A :class:`~omicsclaw.subagent.Delegate` that answers from a script."""

    def __init__(self, answer: str = "done") -> None:
        self.answer = answer
        self.seen: list[tuple[str, str]] = []

    async def delegate(self, definition, prompt: str) -> str:
        self.seen.append((definition.name, prompt))
        return self.answer


def _tool(*definitions: SubAgentDefinition) -> tuple[TaskTool, _Recorder]:
    recorder = _Recorder()
    return TaskTool(SubAgentRegistry(definitions or (SURVEYOR,)), recorder), recorder


def _call(**arguments: object) -> str:
    return json.dumps(arguments)


# ---- what the model is shown ---------------------------------------------


def test_the_tool_answers_to_one_name():
    tool, _ = _tool()

    assert tool.name == TASK_TOOL_NAME == tool.definition().name


def test_the_enum_is_every_registered_sub_agent_in_order():
    tool, _ = _tool(SURVEYOR, REVIEWER)

    schema = tool.definition().input_schema

    assert schema["properties"]["subagent_type"]["enum"] == ["surveyor", "reviewer"]


def test_the_description_carries_each_sub_agent_s_own_brief():
    """It is the only thing the model chooses between them on."""
    tool, _ = _tool(SURVEYOR, REVIEWER)

    description = tool.definition().description

    assert "surveyor: Surveys a tree of files" in description
    assert "reviewer: Reviews a diff" in description


def test_a_sub_agent_registered_later_reaches_the_enum():
    """The definition is rebuilt per read, not snapshotted at construction."""
    registry = SubAgentRegistry([SURVEYOR])
    tool = TaskTool(registry, _Recorder())
    registry.register(REVIEWER)

    assert tool.definition().input_schema["properties"]["subagent_type"]["enum"] == [
        "surveyor",
        "reviewer",
    ]


def test_an_empty_registry_still_produces_a_usable_definition():
    tool = TaskTool(SubAgentRegistry(), _Recorder())

    assert tool.definition().input_schema["properties"]["subagent_type"]["enum"] == []


def test_both_required_arguments_are_declared_required():
    tool, _ = _tool()

    assert tool.definition().input_schema["required"] == ["subagent_type", "prompt"]


def test_the_policy_is_declared_rather_than_defaulted():
    """``AUTO`` is the deliberate part: the sub-agent's own tools still gate."""
    tool, _ = _tool()

    assert tool.policy.approval_mode is ApprovalMode.AUTO
    assert tool.policy.risk_level is RiskLevel.HIGH
    assert tool.policy.concurrency_safe is False
    assert tool.policy.allowed_in_background is False


def test_the_registry_adopts_the_declared_policy():
    tool, _ = _tool()
    registry = ToolRegistry([tool])

    assert registry.policy_for(TASK_TOOL_NAME) == tool.policy
    assert registry.is_concurrency_safe(TASK_TOOL_NAME) is False


# ---- delegating ----------------------------------------------------------


def test_a_well_formed_call_reaches_the_delegate_and_returns_its_text():
    tool, recorder = _tool()

    output = asyncio.run(
        tool.execute(_call(subagent_type="surveyor", prompt="count the files"))
    )

    assert output == "done"
    assert recorder.seen == [("surveyor", "count the files")]


def test_the_optional_title_is_accepted_and_is_not_the_task():
    tool, recorder = _tool()

    asyncio.run(
        tool.execute(
            _call(subagent_type="surveyor", prompt="count", description="Count files")
        )
    )

    assert recorder.seen == [("surveyor", "count")]


def test_an_unknown_sub_agent_is_refused_with_the_available_names():
    tool, recorder = _tool(SURVEYOR, REVIEWER)

    with pytest.raises(ToolArgumentError, match="surveyor, reviewer"):
        asyncio.run(tool.execute(_call(subagent_type="survey0r", prompt="x")))
    assert recorder.seen == []


def test_a_missing_sub_agent_type_is_refused_with_the_available_names():
    tool, _ = _tool(SURVEYOR)

    with pytest.raises(ToolArgumentError, match="surveyor"):
        asyncio.run(tool.execute(_call(prompt="x")))


def test_a_blank_prompt_is_refused_because_nothing_else_is_carried():
    tool, recorder = _tool()

    with pytest.raises(ToolArgumentError, match="cannot see this conversation"):
        asyncio.run(tool.execute(_call(subagent_type="surveyor", prompt="   ")))
    assert recorder.seen == []


def test_a_payload_that_is_not_json_is_refused():
    tool, _ = _tool()

    with pytest.raises(ToolArgumentError):
        asyncio.run(tool.execute("{not json"))


def test_a_failing_delegate_becomes_an_error_observation_not_a_crash():
    """The registry is what translates; this pins that nothing swallows it."""

    class _Broken:
        async def delegate(self, definition, prompt: str) -> str:
            raise RuntimeError("the child engine died")

    registry = ToolRegistry([TaskTool(SubAgentRegistry([SURVEYOR]), _Broken())])

    result = asyncio.run(
        registry.execute(
            ToolCall(
                id="c1",
                name=TASK_TOOL_NAME,
                arguments=_call(subagent_type="surveyor", prompt="x"),
            )
        )
    )

    assert result.is_error
    assert "the child engine died" in result.output


# ---- the second anti-recursion guard -------------------------------------


def test_the_tool_never_appears_in_the_set_it_hands_a_sub_agent():
    """``task`` is not among the names any sub-agent resolves to."""
    parent = ("read_file", "bash", TASK_TOOL_NAME)

    for definition in (SURVEYOR, REVIEWER):
        assert TASK_TOOL_NAME not in definition.resolve_tools(parent)


def test_a_definition_that_resolves_the_delegation_tool_is_refused():
    """The redundant guard, exercised through a definition that lies.

    Nothing in the package can produce this today, which is the point:
    the guard exists for the day ``resolve_tools`` stops removing the
    name, and a guard with no test is a guard nobody will notice
    disappearing.
    """

    class _Leaky(SubAgentDefinition):
        def resolve_tools(self, all_names):  # type: ignore[override]
            return tuple(all_names)

    leaky = _Leaky(
        name="leaky", description="Leaks", system_prompt="Leak.",
    )
    tool = TaskTool(SubAgentRegistry([leaky]), _Recorder())

    with pytest.raises(RecursionRefused, match="leaky"):
        asyncio.run(tool.execute(_call(subagent_type="leaky", prompt="x")))

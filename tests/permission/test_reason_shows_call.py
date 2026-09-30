"""When the gate puts a question itself, does its reason show the call?

The gate writes its own reasons on three paths — a dangerous-command
match, a rule, and the tool's policy — and none of them quotes the call:
``rm -rf ./build`` is asked about as "deletes files and directories
recursively, with no prompt and no recovery". A Channel does not deliver
``TOOL_START``, so on an IM card that reason was all a person had when
approving a dangerous ``bash``. The gate therefore leaves
``reason_shows_call`` ``False`` on those paths and a surface shows the
arguments below the reason.

The protected-file reason does quote the principal argument, so it is
``True`` exactly when that argument is the whole payload: a ``bash`` call
with only ``command``. A ``write_file`` is asked about by its path, and
the content that would be written is not in the reason.

Every call is refused, so nothing runs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Coroutine, TypeVar

from omicsclaw.permission import (
    CONFIG_KEY,
    DecisionSource,
    PermissionGate,
    Rules,
    gate_tools,
)
from omicsclaw.schema import ToolCall, ToolDefinition
from omicsclaw.tools import BashTool, ToolRegistry, WriteTool
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context

_T = TypeVar("_T")


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, 10.0))


class _Plain:
    """An ``ASK`` tool that does not prompt for itself, so the gate asks."""

    name = "lookup"
    policy = ToolPolicy(risk_level=RiskLevel.MEDIUM, approval_mode=ApprovalMode.ASK)

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )

    async def execute(self, arguments: str) -> str:
        raise AssertionError("ran after a refusal")


def _asked(gate: PermissionGate, tool: Any, arguments: dict) -> ApprovalRequest:
    """The one request put about *arguments* through a gated registry, refused."""
    asked: list[ApprovalRequest] = []

    def refuse(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=False, reason="test")

    registry = ToolRegistry(gate_tools([tool], gate))
    with use_tool_context(approval=refuse):
        result = _run(
            registry.execute(
                ToolCall(id="1", name=tool.name, arguments=json.dumps(arguments))
            )
        )
    assert result.is_error
    (request,) = asked
    return request


def test_a_dangerous_command_card_is_told_to_show_the_command(tmp_path: Path):
    """The gate's reason names the danger and not the command."""
    request = _asked(
        PermissionGate(), BashTool(Workspace(tmp_path)), {"command": "rm -rf ./build"}
    )

    assert "recursively" in request.reason
    assert "rm -rf ./build" not in request.reason
    assert request.reason_shows_call is False
    assert request.ask_every_time is True


def test_a_rule_question_the_gate_asks_is_told_to_show_the_arguments():
    gate = PermissionGate(rules=Rules.from_config({CONFIG_KEY: {"ask": ["lookup"]}}))

    request = _asked(gate, _Plain(), {"query": "TP53"})

    assert request.reason.startswith("permission rule ask")
    assert request.reason_shows_call is False


def test_a_policy_question_is_told_to_show_the_arguments():
    request = _asked(PermissionGate(), _Plain(), {"query": "TP53"})

    assert request.reason == "tool policy approval_mode=ask"
    assert request.reason_shows_call is False


def test_a_protected_command_is_quoted_whole_in_its_reason(tmp_path: Path):
    command = "echo OMICSCLAW_PERMISSION_MODE=bypass-all >> .env"

    request = _asked(
        PermissionGate(), BashTool(Workspace(tmp_path)), {"command": command}
    )

    assert request.reason.endswith(f"\n{command}")
    assert request.reason_shows_call is True


def test_a_protected_command_with_another_argument_is_not_quoted_whole(
    tmp_path: Path,
):
    """The reason quotes ``command`` only, so ``timeout_secs`` is not in it."""
    request = _asked(
        PermissionGate(),
        BashTool(Workspace(tmp_path)),
        {"command": "cat .env", "timeout_secs": 5},
    )

    assert request.reason_shows_call is False


def test_a_protected_write_does_not_show_what_it_would_write(tmp_path: Path):
    request = _asked(
        PermissionGate(),
        WriteTool(Workspace(tmp_path)),
        {"path": ".omicsclaw/settings.json", "content": '{"allow": ["bash(*)"]}'},
    )

    assert "bash(*)" not in request.reason
    assert request.reason_shows_call is False


def test_resolve_says_which_reasons_quote_the_call():
    """The flag is part of the decision, so a preview of it is complete."""
    gate = PermissionGate()
    schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }
    policy = ToolPolicy()

    protected = gate.resolve(
        "bash", json.dumps({"command": "cat .env"}), policy=policy, schema=schema
    )
    danger = gate.resolve(
        "bash", json.dumps({"command": "rm -rf /"}), policy=policy, schema=schema
    )

    assert protected.source is DecisionSource.PROTECTED
    assert protected.reason_shows_call is True
    assert danger.source is DecisionSource.DANGER
    assert danger.reason_shows_call is False

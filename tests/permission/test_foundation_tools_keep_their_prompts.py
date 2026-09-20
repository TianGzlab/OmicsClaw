"""``prompts_for_itself=True`` is a claim. This is what checks it is true.

The claim asks the gate to stand back so a tool can put a better question —
``edit_file``'s diff, ``web_fetch``'s whole URL. A tool that claims it and
then does not ask is a call nobody saw, and the claim is the only thing
standing between the two outcomes. "Has tests" is not "is wired up" and a
static check inspects spelling, so this runs the **real** tools with a
channel that refuses and asserts each one stopped.

Refusing is what makes the probe cheap and safe: ``require_approval`` raises
before any tool reaches a socket, a subprocess or a file, so no fake
transport, no container and no network is needed. It also means a tool that
asks *after* doing its work would fail here, which is the other half of the
claim.

The negative case matters as much: every tool that does **not** claim it must
not ask, or the claim carries no information.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.skills import SkillIndex, use_skill_tool
from omicsclaw.tools import (
    BashTool,
    EditTool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
    read_tool,
)
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.base import ApprovalMode, Tool, ToolPolicy
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context

_T = TypeVar("_T")
_DEADLINE = 10.0

REFUSED = "no, thank you"


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


def foundation(workspace: Workspace) -> list[tuple[Tool, dict]]:
    """Every foundation tool, with arguments its schema accepts.

    Arguments that would be *valid*, so a tool refusing them for a reason of
    its own would not be mistaken for a tool declining to ask. ``edit_file``
    is the one that must find a real file, because it reads before it asks —
    that ordering is deliberate there, since the approval carries the diff.
    """
    (workspace.root / "present.txt").write_text("alpha\n", encoding="utf-8")
    return [
        (read_tool(workspace), {"path": "present.txt"}),
        (WriteTool(workspace), {"path": "out.txt", "content": "x"}),
        (
            EditTool(workspace),
            {
                "path": "present.txt",
                "source_text": "alpha",
                "target_text": "beta",
            },
        ),
        (BashTool(workspace), {"command": "echo hello"}),
        (WebFetchTool(), {"url": "https://example.com/doc"}),
        (WebSearchTool(), {"query": "spatial transcriptomics"}),
        (use_skill_tool(SkillIndex()), {"skill_name": "anything"}),
    ]


def ask_and_refuse(tool: Tool, arguments: dict) -> list[ApprovalRequest]:
    """Run *tool* through a registry with a refusing channel; collect the asks."""
    asked: list[ApprovalRequest] = []

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=False, reason=REFUSED)

    async def scenario() -> None:
        registry = ToolRegistry([tool])
        with use_tool_context(approval=channel):
            from omicsclaw.schema import ToolCall

            await registry.execute(
                ToolCall(id="1", name=tool.name, arguments=json.dumps(arguments))
            )

    _run(scenario())
    return asked


def policy_of(tool: Tool) -> ToolPolicy:
    declared = getattr(tool, "policy", None)
    return declared if isinstance(declared, ToolPolicy) else ToolPolicy()


def test_the_probe_covers_every_foundation_tool(tmp_path):
    """A probe that silently stopped covering something would pass in silence."""
    tools = foundation(Workspace(tmp_path))

    assert {tool.name for tool, _ in tools} == {
        "read_file",
        "write_file",
        "edit_file",
        "bash",
        "web_fetch",
        "web_search",
        "use_skill",
    }


def test_at_least_one_tool_claims_and_one_does_not(tmp_path):
    """Both branches below must actually have cases, or both pass vacuously."""
    claims = [
        tool.name
        for tool, _ in foundation(Workspace(tmp_path))
        if policy_of(tool).prompts_for_itself
    ]

    assert claims, "nothing claims the exemption, so the claim means nothing"
    assert len(claims) < 7, "nothing is left to check the negative case with"


def test_every_tool_claiming_to_prompt_really_does(tmp_path):
    """The claim, checked by behaviour rather than by reading the declaration."""
    failures: list[str] = []
    for tool, arguments in foundation(Workspace(tmp_path)):
        if not policy_of(tool).prompts_for_itself:
            continue
        if not ask_and_refuse(tool, arguments):
            failures.append(tool.name)

    assert not failures, (
        f"{failures} declare prompts_for_itself=True and never consulted the "
        "approval channel — the gate stands back for that claim, so each of "
        "these is a call a human would not have seen"
    )


def test_a_tool_claiming_to_prompt_stops_when_refused(tmp_path):
    """Asking is not enough; the refusal has to end the call."""
    failures: list[str] = []
    for tool, arguments in foundation(Workspace(tmp_path)):
        if not policy_of(tool).prompts_for_itself:
            continue
        registry = ToolRegistry([tool])

        def channel(_request: ApprovalRequest) -> ApprovalDecision:
            return ApprovalDecision(approved=False, reason=REFUSED)

        async def scenario(t=tool, a=arguments) -> Any:
            from omicsclaw.schema import ToolCall

            with use_tool_context(approval=channel):
                return await registry.execute(
                    ToolCall(id="1", name=t.name, arguments=json.dumps(a))
                )

        result = _run(scenario())
        if not result.is_error or REFUSED not in result.output:
            failures.append(f"{tool.name}: {result.output[:60]}")

    assert not failures, failures


def test_no_tool_that_declines_the_claim_asks_anyway(tmp_path):
    """Otherwise the claim carries no information and the gate cannot use it."""
    surprises: list[str] = []
    for tool, arguments in foundation(Workspace(tmp_path)):
        policy = policy_of(tool)
        if policy.prompts_for_itself:
            continue
        if policy.approval_mode is not ApprovalMode.AUTO:
            continue
        if ask_and_refuse(tool, arguments):
            surprises.append(tool.name)

    assert not surprises, (
        f"{surprises} ask without declaring prompts_for_itself, so the gate "
        "would ask as well and a person would be interrupted twice"
    )


@pytest.mark.parametrize(
    "name", ["bash", "write_file", "edit_file", "web_fetch", "web_search"]
)
def test_the_five_asking_tools_are_named_as_well_as_covered(name: str, tmp_path):
    """Named so that a tool quietly dropping its claim is visible in a diff."""
    by_name = {tool.name: tool for tool, _ in foundation(Workspace(tmp_path))}

    assert policy_of(by_name[name]).prompts_for_itself, name


@pytest.mark.parametrize("name", ["read_file", "use_skill"])
def test_the_two_silent_tools_are_named_too(name: str, tmp_path):
    by_name = {tool.name: tool for tool, _ in foundation(Workspace(tmp_path))}

    assert not policy_of(by_name[name]).prompts_for_itself, name

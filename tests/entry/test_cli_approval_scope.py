"""The middle grant: "allow this for the rest of this conversation".

``y`` costs a prompt per call and ``a`` writes a rule that outlives the
reason it was written, so the interesting assertions here are about what
*separates* the new option from the old ones: the second call is not
asked about, and the rule file on disk is still not there.

No ``pytest-asyncio`` here, so every test drives :func:`asyncio.run`
itself and bounds every await with :func:`asyncio.wait_for`.
"""

from __future__ import annotations

import asyncio

import json

from omicsclaw.schema import Message, Role, ToolCall, ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import require_approval
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    build,
    repl_over,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
    calling,
)


def _twice(*extra: Message) -> Scripted:
    """A backend that calls ``ask`` twice, answering in between."""
    return Scripted(
        calling("ask"),
        Message(role=Role.ASSISTANT, content="first done"),
        calling("ask"),
        Message(role=Role.ASSISTANT, content="second done"),
        *extra,
    )


def test_allowing_for_this_conversation_stops_asking_and_writes_nothing(
    tmp_path,
):
    """Both halves, because either one alone is a different feature.

    "Stops asking" without "writes nothing" is what ``a`` already did;
    "writes nothing" without "stops asking" is what ``y`` already did.
    The rule file's absence is asserted against the same path
    ``test_cli_repl.py`` finds it at after an ``a``, so the two tests
    disagree about the file if this one ever starts persisting.
    """

    async def drive():
        app = build(tmp_path, _twice(), tools=(Asking("ask"),))
        repl, source, buffer = repl_over(
            app, ["once", "s", "twice", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts, buffer.getvalue()

    prompts, printed = asyncio.run(drive())

    approvals = [one for one in prompts if one.startswith("approve ask [")]
    assert len(approvals) == 1, f"asked {len(approvals)} times: {prompts}"
    assert "Will not ask about ask again in this conversation" in printed
    assert "allowed for this conversation" in printed
    assert "first done" in printed and "second done" in printed
    assert not (tmp_path / ".omicsclaw" / "settings.json").exists(), (
        "the session-scoped grant reached the rule file"
    )


def test_a_new_conversation_asks_again(tmp_path):
    """The grant is scoped to the conversation, or it is ``a`` by another
    name. ``/new`` is the cheapest way to leave one."""

    async def drive():
        app = build(tmp_path, _twice(), tools=(Asking("ask"),))
        repl, source, _buffer = repl_over(
            app, ["once", "s", "/new", "twice", "n", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts

    prompts = asyncio.run(drive())

    approvals = [one for one in prompts if one.startswith("approve ask [")]
    assert len(approvals) == 2, f"asked {len(approvals)} times: {prompts}"


def test_the_card_says_the_middle_grant_exists(tmp_path):
    """A key nobody is told about is a key nobody presses.

    The prompt itself still reads ``[y/N/a=always]`` — it is what the
    approval tests name and it is as wide as a narrow terminal wants — so
    the legend above the card is the only place the third option is
    announced.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="ok")),
            tools=(Asking("ask"),),
        )
        repl, _source, buffer = repl_over(app, ["once", "n", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "s = allow this tool for the rest of the conversation" in printed
    assert "a = always, and write a rule" in printed


# ---- per tool, not per call (plan 0049) --------------------------------


class Shell:
    """Shaped like ``bash`` where the gate looks: a required ``command``
    argument, so danger patterns apply, and ``prompts_for_itself``, so an
    ordinary question is handed down to it."""

    policy = ToolPolicy(
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.ASK,
        prompts_for_itself=True,
    )

    def __init__(self) -> None:
        self.ran: list[str] = []

    @property
    def name(self) -> str:
        return "shell"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Runs a command.",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )

    async def execute(self, arguments: str) -> str:
        command = json.loads(arguments)["command"]
        await require_approval("shell", arguments, reason=f"run: {command}")
        self.ran.append(command)
        return "ok"


def _commands(*commands: str) -> Scripted:
    """One tool call per model message, then a final answer."""
    turns = [
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(
                    id=f"c{index}",
                    name="shell",
                    arguments=json.dumps({"command": command}),
                ),
            ),
        )
        for index, command in enumerate(commands)
    ]
    return Scripted(*turns, Message(role=Role.ASSISTANT, content="all done"))


def _session(tmp_path, commands, answers, **overrides):
    shell = Shell()

    async def drive():
        app = build(tmp_path, _commands(*commands), tools=(shell,), **overrides)
        repl, source, buffer = repl_over(app, ["go", *answers, "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts, buffer.getvalue()

    prompts, printed = asyncio.run(drive())
    asked = [one for one in prompts if one.startswith("approve shell [")]
    return asked, printed, shell


def test_s_covers_the_tool_not_the_exact_command(tmp_path):
    """The owner's complaint: ``s`` on ``bash`` was a ``y`` with a longer
    name, because it was keyed by the whole command line."""
    asked, printed, shell = _session(
        tmp_path, ["ls -la", "pwd", "head README.md"], ["s"]
    )

    assert len(asked) == 1, asked
    assert shell.ran == ["ls -la", "pwd", "head README.md"]
    assert "Will not ask about shell again in this conversation" in printed


def test_s_does_not_cover_a_dangerous_command(tmp_path):
    asked, printed, shell = _session(
        tmp_path, ["ls -la", "rm -rf /tmp/x"], ["s", "n"]
    )

    assert len(asked) == 2, asked
    assert shell.ran == ["ls -la"]
    assert "this call is always asked about" in printed


def test_s_on_a_dangerous_command_allows_that_call_only(tmp_path):
    """Otherwise ``s`` on ``rm -rf`` would grant the ordinary calls after it
    on the strength of an answer to an extraordinary one."""
    asked, printed, shell = _session(
        tmp_path, ["rm -rf /tmp/x", "ls -la"], ["s", "y"]
    )

    assert len(asked) == 2, asked
    assert shell.ran == ["rm -rf /tmp/x", "ls -la"]
    assert "Allowed this call only" in printed


def test_a_broad_ask_rule_keeps_asking_after_s(tmp_path):
    """``ask: ["shell(*)"]`` is an operator saying "always ask". ``s`` is a
    person at the terminal saying "not for the ordinary calls". The rule
    is more specific, and wins —— including over ``rm -rf``, which under
    this rule is a *rule* question rather than a *danger* one."""
    settings = tmp_path / ".omicsclaw" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"permissions": {"ask": ["shell(*)"]}}), encoding="utf-8"
    )

    asked, _printed, shell = _session(
        tmp_path, ["pip install scanpy", "rm -rf /tmp/x"], ["s", "n"]
    )

    assert len(asked) == 2, asked
    assert shell.ran == ["pip install scanpy"]

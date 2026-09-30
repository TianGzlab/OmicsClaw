"""The approval card every surface shows: what is on it, and what cannot be.

``render._approval_line`` is the one card the CLI and every Channel print.
Two defects met there:

- **The card could be forged.** A reason reached the terminal through
  rich's ``Text``, which strips only BEL, BS, VT, FF and CR; ESC, the C1
  CSI and the bidi override went through, and ``bash``'s reason carries
  the model's whole command. Line breaks were a second way: blank lines to
  push the dangerous start off the screen, or a line that looks like the
  header of another, harmless card.
- **A card could hide the call.** When the permission gate asks — a
  dangerous command, a rule, a tool's policy — its reason says why and not
  what, and a Channel never shows ``TOOL_START``; so a person approving
  ``rm -rf ./build`` in an IM chat read "deletes files and directories
  recursively" and no command.

The card now shows the reason made inert, then — unless the reason's
writer declared that it shows the call — the arguments as an indented,
redacted block. Neither reaches a log or the audit file.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging
import pathlib
import unicodedata
from typing import Any, Coroutine, TypeVar

import pytest
from rich.console import Console

from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app
from omicsclaw.entry.cli._transcript import ToolTranscript
from omicsclaw.entry.config import AppConfig
from omicsclaw.entry.display import CONTINUATION_PREFIX, approval_body
from omicsclaw.entry.events import TurnEvent
from omicsclaw.entry.render import TextRenderer
from omicsclaw.permission import PermissionGate, gate_tools
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, ToolCall, ToolDefinition
from omicsclaw.tools import BashTool, MCPTool, ToolRegistry
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context
from omicsclaw.tools.preview import MAX_PREVIEW_CHARS, REDACTED

_T = TypeVar("_T")

_UNSAFE = {"Cc", "Cf", "Cs", "Zl", "Zp"}

_FORGED = "Approval required [t#9]: read_file (risk low) - read README.md"

_ARGUMENTS = f"\n{CONTINUATION_PREFIX}arguments: "
"""Where the arguments block starts on a card."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, 10.0))


def _card(request: ApprovalRequest, *, batched: bool = False) -> str:
    """The card a surface prints for *request*."""
    renderer = TextRenderer(batched=batched)
    line = renderer.feed(TurnEvent.approval_required(request, "t#1"))
    assert line is not None
    return line


def _unsafe_in(text: str) -> list[str]:
    return [
        char
        for char in text
        if char != "\n" and unicodedata.category(char) in _UNSAFE
    ]


def _asked(
    tool: Any, arguments: dict, *, gate: PermissionGate | None = None
) -> ApprovalRequest:
    """The one request put about *arguments*, through a gated registry, refused."""
    asked: list[ApprovalRequest] = []

    def refuse(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=False, reason="test")

    registry = ToolRegistry(gate_tools([tool], gate or PermissionGate()))
    with use_tool_context(approval=refuse):
        result = _run(
            registry.execute(
                ToolCall(id="1", name=tool.name, arguments=json.dumps(arguments))
            )
        )
    assert result.is_error
    (request,) = asked
    return request


class _Plain:
    """An ``ASK`` tool that does not prompt for itself, so the gate asks."""

    name = "lookup"
    policy = ToolPolicy(risk_level=RiskLevel.MEDIUM, approval_mode=ApprovalMode.ASK)

    def __init__(self) -> None:
        self.ran: list[str] = []

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
        self.ran.append(arguments)
        return "found"


# ---- nothing on the card can act on the display ----------------------------------


_HOSTILE_REASON = (
    "run this:\n"
    "ls\x1b[2J\x1b[H"  # ESC: clear the screen, home the cursor
    "\x9b2J"  # C1 CSI
    "\u202eflah"  # RLO
    "\u200b\u2066x\u2069"  # zero width, bidi isolate
    f"\r{_FORGED}"  # CR back over the line
    f"\n{_FORGED}"
)


def test_escapes_bidi_and_zero_width_characters_in_a_reason_are_neutralised():
    card = _card(
        ApprovalRequest(tool_name="bash\x1b[8m", reason=_HOSTILE_REASON)
    )

    assert _unsafe_in(card) == []
    assert "\\u001b[2J" in card and "\\u009b2J" in card and "\\u202eflah" in card
    assert card.startswith("Approval required [t#1]: bash\\u001b[8m (risk high)")


def test_no_line_of_the_card_but_its_first_can_pass_for_a_header():
    lines = _card(ApprovalRequest(tool_name="bash", reason=_HOSTILE_REASON)).split(
        "\n"
    )

    assert lines[0].startswith("Approval required [t#1]: bash")
    assert all(line.startswith(CONTINUATION_PREFIX) for line in lines[1:])
    assert not any(line.startswith("Approval required [") for line in lines[1:])


def test_hundreds_of_blank_lines_cannot_push_the_command_off_the_screen():
    """Folded, the 499 blank lines are one, so the command and the harmless
    line after it are on one screen; the first line still says how many
    lines the reason really had, and how many of them were blank."""
    reason = "run:\nrm -rf ~" + "\n" * 500 + "echo harmless"

    lines = _card(ApprovalRequest(tool_name="bash", reason=reason)).split("\n")

    assert len(lines) == 4
    assert lines[0].startswith(
        "Approval required [t#1]: bash (risk high) - [502 lines, "
    )
    assert lines[0].endswith("; 498 blank lines folded] run:")
    assert lines[1:] == [
        f"{CONTINUATION_PREFIX}rm -rf ~",
        CONTINUATION_PREFIX,
        f"{CONTINUATION_PREFIX}echo harmless",
    ]


def test_the_card_is_its_header_and_the_shared_body():
    """One body for every surface: the terminal's card and, later, a
    Channel's are the same function's output behind the same header."""
    request = ApprovalRequest(
        tool_name="lookup", arguments='{"q": 1}', reason="look it up"
    )

    assert _card(request) == (
        "Approval required [t#1]: lookup (risk high) - "
        f"{approval_body(request)[0]}"
    )
    assert _card(ApprovalRequest(tool_name="lookup", reason="")) == (
        "Approval required [t#1]: lookup (risk high)"
    )


def test_a_two_hundred_line_heredoc_is_on_the_card_whole(tmp_path: pathlib.Path):
    """The real gate over the real ``bash``. A heredoc that writes an
    analysis script is the longest command people routinely approve; a
    card that cut it would ask them to approve lines they never saw."""
    script = "\n".join(f"df_{n:03d} = run(step={n}, cells='all')" for n in range(200))
    command = f"cat > analysis.py <<'EOF'\n{script}\nEOF"
    request = _asked(BashTool(Workspace(tmp_path)), {"command": command})

    card = _card(request)

    assert approval_body(request)[1] is False
    for line in command.split("\n"):
        assert f"\n{CONTINUATION_PREFIX}{line}\n" in f"{card}\n", line
    assert f"[{len(request.reason.splitlines())} lines, " in card.split("\n")[0]


def test_the_terminal_receives_no_byte_the_card_did_not_intend():
    """The path the defect was found on: the rendered line becomes a rich
    ``Text`` in the CLI transcript and is written to a real terminal. Only
    rich's own style codes may appear."""
    card = _card(ApprovalRequest(tool_name="bash", reason=_HOSTILE_REASON))
    event = TurnEvent.approval_required(
        ApprovalRequest(tool_name="bash", reason=_HOSTILE_REASON), "t#1"
    )
    buffer = io.StringIO()
    console = Console(
        file=buffer, force_terminal=True, color_system="standard", width=200
    )

    for line in ToolTranscript().render(event, card):
        console.print(line)

    written = buffer.getvalue()
    assert "\x1b[2J" not in written and "\x1b[H" not in written
    assert not {"\x9b", "\u202e", "\u200b", "\u2066", "\r"} & set(written)
    assert written.replace("\x1b[2m", "").replace("\x1b[0m", "").count("\x1b") == 0


# ---- the call is on the card --------------------------------------------------


def test_a_dangerous_command_card_shows_the_command(tmp_path: pathlib.Path):
    """The real gate over the real ``bash``: the gate's reason is the
    danger, and the command follows it on the card — on the Channel's
    batched renderer exactly as on the terminal's."""
    request = _asked(BashTool(Workspace(tmp_path)), {"command": "rm -rf ./build"})
    card = _card(request)

    assert "recursively" in card
    assert f'{_ARGUMENTS}{{\n{CONTINUATION_PREFIX}  "command": "rm -rf ./build"' in card
    assert _card(request, batched=True) == card


def test_bash_asking_for_itself_shows_the_command_once(tmp_path: pathlib.Path):
    """Its reason already quotes the command; the card does not repeat it."""
    request = _asked(BashTool(Workspace(tmp_path)), {"command": "ls -la ./results"})
    card = _card(request)

    assert request.reason_shows_call is True
    assert card.count("ls -la ./results") == 1
    assert _ARGUMENTS not in card


def test_an_mcp_card_adds_the_arguments_only_when_its_preview_was_cut():
    """A cut preview is not the whole call, so the block goes below it."""
    tool = MCPTool("context7", "resolve", caller=lambda arguments: "ok")
    whole = _asked(tool, {"q": "TP53"})
    cut = _asked(tool, {"q": "x" * MAX_PREVIEW_CHARS, "tail": "the end"})

    assert _ARGUMENTS not in _card(whole)
    card = _card(cut)
    assert "[truncated: showing the first" in card
    assert f'{_ARGUMENTS}{{\n{CONTINUATION_PREFIX}  "q": "xxx' in card
    assert f'{CONTINUATION_PREFIX}  "tail": "the end"' in card


def test_credentials_are_hidden_on_the_card():
    """The gate's policy question shows the arguments, redacted by the same
    rule as the MCP preview."""
    request = _asked(_Plain(), {"query": "TP53", "api_key": "sk-live-123"})
    card = _card(request)

    assert "sk-live-123" not in card
    assert f'"api_key": "{REDACTED}"' in card
    assert '"query": "TP53"' in card
    assert request.arguments == json.dumps({"query": "TP53", "api_key": "sk-live-123"})


# ---- shown, never logged -------------------------------------------------------


@dataclasses.dataclass
class _ScriptedProvider:
    """Structural conformance only; no model is called."""

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        return Completion(message=Message(role=Role.ASSISTANT, content="x"))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return _ScriptedProvider()


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda provider, model: _ScriptedProvider()
    )


def _approve_and_render(app: Any, call: ToolCall) -> tuple[str, Any]:
    asked: list[ApprovalRequest] = []

    def approve(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        return ApprovalDecision(approved=True)

    with use_tool_context(approval=approve):
        result = _run(app.registry.execute(call))
    (request,) = asked
    return _card(request), result


def test_the_arguments_on_a_card_reach_no_log_and_no_audit_record(
    tmp_path: pathlib.Path, offline, caplog: pytest.LogCaptureFixture
):
    """The production assembly, with the audit log on and every logger at
    DEBUG: the command and the credential are on the card and nowhere
    else. A log and an audit file outlive the session and are read by
    whoever operates the machine."""
    audit = tmp_path / "audit.jsonl"
    marker = "build-7f3a91"
    secret = "sk-live-5c2e"
    lookup = _Plain()
    app = build_app(
        AppConfig(workspace=tmp_path, audit_log=audit),
        tools=[*assembly.foundation_tools(AppConfig(workspace=tmp_path)), lookup],
    )
    caplog.set_level(logging.DEBUG)

    danger_card, danger = _approve_and_render(
        app,
        ToolCall(
            id="1", name="bash", arguments=json.dumps({"command": f"rm -rf ./{marker}"})
        ),
    )
    policy_card, looked = _approve_and_render(
        app,
        ToolCall(
            id="2",
            name="lookup",
            arguments=json.dumps({"query": marker, "api_key": secret}),
        ),
    )
    _run(app.aclose())

    assert not danger.is_error and not looked.is_error
    assert marker in danger_card and marker in policy_card
    assert secret not in policy_card
    records = audit.read_text("utf-8")
    assert [json.loads(line)["tool"] for line in records.splitlines()] == [
        "bash",
        "lookup",
    ]
    for value in (marker, secret):
        assert value not in caplog.text
        assert value not in records

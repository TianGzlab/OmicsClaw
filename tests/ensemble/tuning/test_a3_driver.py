"""The A3 driver: token counting, the cap, the reminder, and refusing unreported usage.

Tokens are counted from every main-engine turn and every sub-agent turn, on
the streaming path only, because a blocking call reports zero usage when the
backend reports none and the two cannot be told apart; a turn without usage
therefore refuses the unit. Past the cap the exchange is ended at its next
model call (so the trajectory is committed), and the pre-registered reminder
runs as one exchange of at most two turns with that trajectory as history.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType, ToolCall, Usage

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "docs" / "plans" / "0057-validation"))

import run_arms  # noqa: E402


@dataclasses.dataclass
class _Provider:
    replies: list[Message]
    usage: Usage | None = dataclasses.field(default_factory=lambda: Usage(input_tokens=7, output_tokens=3))
    seen: list[tuple[Message, ...]] = dataclasses.field(default_factory=list)

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        self.seen.append(tuple(messages))
        reply = self.replies[min(len(self.seen) - 1, len(self.replies) - 1)]
        return Completion(message=reply, finish_reason="stop")

    def generate_stream(self, messages, tools=None):
        async def stream():
            completion = await self.generate(messages, tools)
            yield StreamChunk(type=StreamChunkType.DONE, message=completion.message, finish_reason="stop",
                              usage=self.usage)
        return stream()

    def bind(self, **overrides):
        return self


def _calls(name: str, **arguments: Any) -> Message:
    return Message(role=Role.ASSISTANT, tool_calls=(ToolCall(id=f"c{len(arguments)}", name=name,
                                                             arguments=json.dumps(arguments)),))


def _app(tmp_path, monkeypatch, provider):
    monkeypatch.setattr(assembly, "provider_from_env", lambda p, m: provider)
    (tmp_path / "x.txt").write_text("x")
    return assembly.build_app(AppConfig(workspace=tmp_path, memory=False, subagents=False))


def test_the_turn_ceilings_are_the_registered_ones():
    assert run_arms.A3_MAX_TURNS == 50 and run_arms.REMINDER_TURNS == 2
    assert run_arms.REMINDER == "Please finish now by calling select_result."
    import inspect

    defaults = inspect.signature(run_arms.drive_a3).parameters
    assert defaults["max_turns"].default == 50 and defaults["reminder_turns"].default == 2


def test_past_the_cap_the_exchange_ends_and_the_reminder_sees_its_history(tmp_path, monkeypatch):
    provider = _Provider([_calls("read_file", path="x.txt"), Message(role=Role.ASSISTANT, content="done")])
    app = _app(tmp_path, monkeypatch, provider)
    result = asyncio.run(run_arms.drive_a3(app, "s", "THE TASK", token_cap=5, finished=lambda: False))
    assert result["capped"] and result["reminded"]
    assert result["usage"]["turns"] == 3 and result["usage"]["input"] == 14  # the stop reply costs nothing
    reminder_call = provider.seen[-1]
    texts = [m.content for m in reminder_call]
    assert "THE TASK" in texts and run_arms.STOP_TEXT in texts and run_arms.REMINDER in texts
    assert any(m.tool_calls for m in reminder_call)
    assert any(m.content == run_arms.REMINDER for m in result["history"])


def test_the_reminder_runs_at_most_two_turns(tmp_path, monkeypatch):
    provider = _Provider([_calls("read_file", path="x.txt")])
    app = _app(tmp_path, monkeypatch, provider)
    result = asyncio.run(run_arms.drive_a3(app, "s", "task", token_cap=10**9, finished=lambda: False,
                                           max_turns=3))
    assert result["reminded"] and not result["capped"]
    assert result["usage"]["turns"] == 3 + 2


def test_no_reminder_when_the_task_finished(tmp_path, monkeypatch):
    provider = _Provider([Message(role=Role.ASSISTANT, content="done")])
    app = _app(tmp_path, monkeypatch, provider)
    result = asyncio.run(run_arms.drive_a3(app, "s", "task", token_cap=10**9, finished=lambda: True))
    assert not result["reminded"] and len(provider.seen) == 1


def test_a_turn_without_usage_refuses_the_unit(tmp_path, monkeypatch):
    provider = _Provider([Message(role=Role.ASSISTANT, content="done")], usage=None)
    app = _app(tmp_path, monkeypatch, provider)
    with pytest.raises(run_arms.UsageNotReported):
        asyncio.run(run_arms.drive_a3(app, "s", "task", token_cap=10**9, finished=lambda: True))

"""``open_app``: MCP servers connected before the registry is built.

The ordering is the decision under test. harness9 injects MCP tools from a
background goroutine after its TUI is up, so its tool list changes during
the session. Here the tool list is part of the cached prompt prefix and
the budget's ``reserve_tool_tokens`` is computed once in ``build_app``, so
tools that arrived later would be tools the budget never counted. Every
test that asserts "the MCP tool is in the snapshot" or "the budget grew"
is pinning that choice.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import sys
from pathlib import Path

import pytest

from omicsclaw.engine import AgentEngine
from omicsclaw.entry import assembly, attach_sessions, open_app, resolve_app_config
from omicsclaw.entry.approval import ApprovalBroker
from omicsclaw.entry.config import AppConfig, SkillsIndex
from omicsclaw.entry.display import CONTINUATION_PREFIX
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.render import TextRenderer
from omicsclaw.entry.stream import TurnStream
from omicsclaw.entry.turn import TurnRunner, run_turn
from omicsclaw.mcp import MCPConfigError, ServerState
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ApprovalDecision, ToolAlreadyRegistered, use_tool_context
from tests.entry.test_turn import _Scripted  # type: ignore[import-not-found]
from tests.mcp._support import FAKE_SERVER, pid_alive

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX processes")


class _RecordingProvider(_Scripted):
    """Also records the tool list each call was offered."""

    def __init__(self, *replies: Message) -> None:
        super().__init__(*replies)
        self.offered: list[tuple[str, ...]] = []

    async def generate(self, messages, tools=None):
        self.offered.append(tuple(tool.name for tool in tools or ()))
        return await super().generate(messages, tools)


def _write_config(workspace: Path, servers: dict) -> Path:
    path = workspace / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return path


def _fake(*flags: str) -> dict:
    return {"command": sys.executable, "args": [str(FAKE_SERVER), *flags]}


def _config(workspace: Path, **overrides) -> AppConfig:
    return AppConfig(workspace=workspace, skills_index=SkillsIndex.OFF, **overrides)


async def _open(config: AppConfig, provider=None, **kwargs):
    provider = provider or _Scripted()
    real = assembly.provider_from_env
    assembly.provider_from_env = lambda p, m: provider
    try:
        app = await open_app(config, **kwargs)
    finally:
        assembly.provider_from_env = real
    return dataclasses.replace(
        app, engine=AgentEngine(provider, app.registry, config.engine_config())
    )


def _run(main, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(main, timeout))


# ---- configuration ------------------------------------------------------


def test_the_file_defaults_to_the_workspace_and_can_be_moved(tmp_path: Path):
    default = resolve_app_config(argv=["--workspace", str(tmp_path)], env={})
    moved = resolve_app_config(
        argv=["--workspace", str(tmp_path), "--mcp-config", "/etc/omics/mcp.json"],
        env={"OMICSCLAW_MCP_CONNECT_TIMEOUT_S": "5"},
    )

    assert default.mcp_config_path() == tmp_path.resolve() / ".mcp.json"
    assert moved.mcp_config_path() == Path("/etc/omics/mcp.json")
    assert moved.mcp_connect_timeout_s == 5.0


def test_a_bad_timeout_is_refused_not_defaulted(tmp_path: Path):
    with pytest.raises(ValueError, match="OMICSCLAW_MCP_CONNECT_TIMEOUT_S"):
        resolve_app_config(
            argv=["--workspace", str(tmp_path)],
            env={"OMICSCLAW_MCP_CONNECT_TIMEOUT_S": "thirty"},
        )


# ---- assembly -----------------------------------------------------------


def test_without_a_file_open_app_is_build_app(tmp_path: Path):
    async def main():
        app = await _open(_config(tmp_path))
        await app.aclose()
        return app

    app = _run(main())

    assert app.mcp is None
    assert not any(t.name.startswith("mcp__") for t in app.tools_snapshot)


def test_mcp_tools_are_in_the_snapshot_and_the_budget_from_the_start(tmp_path: Path):
    async def main():
        plain = await _open(_config(tmp_path))
        await plain.aclose()
        _write_config(tmp_path, {"fake": {**_fake(), "tools": ["echo", "fail"]}})
        app = await _open(_config(tmp_path))
        await app.aclose()
        return plain, app

    plain, app = _run(main())

    names = [tool.name for tool in app.tools_snapshot]
    plain_names = [tool.name for tool in plain.tools_snapshot]
    # The MCP tools go on after the foundation tools and before ``task``,
    # which the composition root appends last of all because it narrows
    # the very registry it is mounted into.
    assert names[-3:-1] == ["mcp__fake__echo", "mcp__fake__fail"]
    assert names[-1] == plain_names[-1] == "task"
    assert names[:-3] == plain_names[:-1]
    assert app.budget.reserve_tool_tokens > plain.budget.reserve_tool_tokens
    assert [tool.name for tool in app.registry.available_tools()] == names


def test_a_failing_server_is_logged_and_the_app_still_starts(tmp_path: Path, caplog):
    _write_config(tmp_path, {"good": _fake(), "bad": _fake("--crash")})

    async def main():
        app = await _open(_config(tmp_path))
        await app.aclose()
        return app

    with caplog.at_level(logging.WARNING, logger="omicsclaw.entry"):
        app = _run(main())

    states = {s.name: s.state for s in app.mcp.statuses()}
    assert states == {"good": ServerState.CONNECTED, "bad": ServerState.FAILED}
    assert any("MCP server bad failed" in r.getMessage() for r in caplog.records)
    assert "mcp__good__echo" in [tool.name for tool in app.tools_snapshot]


def test_an_unreadable_file_stops_start_up(tmp_path: Path):
    (tmp_path / ".mcp.json").write_text("{", encoding="utf-8")

    with pytest.raises(MCPConfigError):
        _run(_open(_config(tmp_path)))


def test_status_changes_reach_the_caller_while_servers_connect(tmp_path: Path):
    _write_config(tmp_path, {"fake": _fake()})
    seen: list[str] = []

    async def main():
        app = await _open(
            _config(tmp_path),
            on_mcp_change=lambda statuses: seen.append(statuses[0].state.value),
        )
        await app.aclose()

    _run(main())

    assert seen[0] == "pending"
    assert seen[-1] == "connected"


# ---- lifetime -----------------------------------------------------------


def test_closing_the_app_stops_the_servers(tmp_path: Path):
    log = tmp_path / "server.log"
    _write_config(tmp_path, {"fake": _fake("--log", str(log), "--spawn-child")})

    async def main():
        app = attach_sessions(await _open(_config(tmp_path)))
        await app.aclose()

    _run(main())

    grandchild = next(
        json.loads(line)["grandchild"]
        for line in log.read_text().splitlines()
        if "grandchild" in line
    )
    assert not pid_alive(grandchild)


def test_a_failed_assembly_does_not_leak_the_servers(tmp_path: Path):
    """``build_app`` raising after the servers started must still stop them."""
    log = tmp_path / "server.log"
    _write_config(tmp_path, {"fake": _fake("--log", str(log), "--spawn-child")})

    async def main():
        probe = await _open(_config(tmp_path))
        clash = [tool for tool in probe.registry.names() if tool.startswith("mcp__")]
        own = [probe.registry.get(clash[0])]
        await probe.aclose()
        log.unlink()
        with pytest.raises(ToolAlreadyRegistered):
            await _open(_config(tmp_path), tools=own)

    _run(main())

    grandchild = next(
        json.loads(line)["grandchild"]
        for line in log.read_text().splitlines()
        if "grandchild" in line
    )
    assert not pid_alive(grandchild)


# ---- through the main loop ----------------------------------------------


def test_the_react_loop_calls_an_mcp_tool_like_any_other(tmp_path: Path):
    """Model → Action (MCP tool) → approval → server → Observation → answer.

    The engine is unchanged; this is the proof that it did not need to be.
    """
    _write_config(tmp_path, {"fake": _fake()})
    provider = _RecordingProvider(
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(id="c1", name="mcp__fake__echo", arguments='{"gene": "TP53"}'),
            ),
        ),
        Message(role=Role.ASSISTANT, content="TP53 came back."),
    )
    asked: list[str] = []

    def human(request):
        asked.append(request.tool_name)
        return True

    async def main():
        app = await _open(_config(tmp_path), provider)
        try:
            with use_tool_context(approval=human):
                return await run_turn(app, (), "echo TP53 through MCP")
        finally:
            await app.aclose()

    outcome = _run(main())

    assert outcome.reply == "TP53 came back."
    assert asked == ["mcp__fake__echo"]
    observation = next(m for m in outcome.history if m.role is Role.TOOL)
    assert json.loads(observation.content) == {"gene": "TP53"}
    assert not observation.is_error
    assert "mcp__fake__echo" in provider.offered[0]
    assert provider.offered[0] == provider.offered[1]


def test_each_mcp_approval_card_shows_the_arguments_of_its_own_call(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The reported defect, end to end through the production assembly.

    Two calls to one MCP tool differ only in their arguments. Before, both
    cards read ``MCP server 'fake' via …, tool 'echo'`` and a person could
    not tell the ``harmless`` call from the ``rm-everything`` one. The
    arguments are now on the card: through the permission gate, which hands
    the question to the tool, through the approval broker, and through
    :class:`~omicsclaw.entry.render.TextRenderer`, whose approval line the
    Channel posts and the CLI prints.

    The same run checks the other half of the ruling: the arguments are on
    the card and nowhere else — not in any log record at DEBUG, and not in
    the audit trail, which records a digest.
    """
    _write_config(tmp_path, {"fake": _fake()})
    audit = tmp_path / "audit.jsonl"
    secret = "sk-live-7f3a"
    provider = _RecordingProvider(
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(
                    id="c1", name="mcp__fake__echo", arguments='{"text": "harmless"}'
                ),
                ToolCall(
                    id="c2",
                    name="mcp__fake__echo",
                    arguments=json.dumps({"text": "rm-everything", "api_key": secret}),
                ),
            ),
        ),
        Message(role=Role.ASSISTANT, content="done"),
    )

    async def main():
        app = await _open(_config(tmp_path, audit_log=audit), provider)
        stream = TurnStream("s1", "t1")
        broker = ApprovalBroker(stream)
        runner = TurnRunner(
            app, stream, session_id="s1", turn_id="t1", user_text="go",
            approval=broker,
        )
        channel, terminal = TextRenderer(batched=True), TextRenderer()
        cards: list[tuple[str, str]] = []

        async def answer():
            async with stream.observe() as observation:
                async for frame in observation:
                    if frame.type is TurnEventType.APPROVAL_REQUIRED:
                        cards.append((channel.feed(frame), terminal.feed(frame)))
                        broker.settle(frame.request_id, ApprovalDecision(True))

        try:
            consumer = asyncio.create_task(answer())
            outcome = await runner.run()
            await consumer
        finally:
            await app.aclose()
        return outcome, cards

    with caplog.at_level(logging.DEBUG):
        outcome, cards = _run(main())

    assert len(cards) == 2
    assert all(on_channel == on_terminal for on_channel, on_terminal in cards)
    harmless, dangerous = sorted((card for card, _ in cards), key=len)
    assert harmless != dangerous
    assert harmless.endswith(
        f'with arguments:\n{CONTINUATION_PREFIX}{{"text": "harmless"}}'
    )
    assert dangerous.endswith(
        f"with arguments:\n{CONTINUATION_PREFIX}"
        '{"api_key": "[redacted]", "text": "rm-everything"}'
    )
    assert secret not in dangerous
    observations = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert [m.is_error for m in observations] == [False, False]

    logged = [record.getMessage() for record in caplog.records]
    assert sum("approval requested: tool=mcp__fake__echo" in m for m in logged) == 2
    trail = audit.read_text(encoding="utf-8")
    assert len(trail.splitlines()) == 2
    for value in ("harmless", "rm-everything", secret):
        assert not [m for m in logged if value in m], value
        assert value not in trail, value

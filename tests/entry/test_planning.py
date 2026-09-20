"""Plan 0039's wiring: one switch, three effects, and a real exchange.

The three effects — ``plan_write`` in the registry, a planning section in
the prompt, and a block injected before every model call — have to move
together. Half of this feature is worse than none of it: a prompt telling
the model to call a tool nobody mounted spends turns on a capability the
deployment does not have.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app
from omicsclaw.entry.config import AppConfig, resolve_app_config
from omicsclaw.entry.planning import build_injector, build_plan_book
from omicsclaw.entry.turn import run_turn
from omicsclaw.planning import (
    PLAN_WRITE_TOOL_NAME,
    INJECTION_HEADER,
    PlanArchiveError,
    PlanItem,
    PlanStatus,
)
from omicsclaw.provider import Completion
from omicsclaw.tools.base import ApprovalMode, ToolPolicy
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
)

P, R, C = PlanStatus.PENDING, PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED


@dataclasses.dataclass
class _ScriptedProvider:
    """Replies from a script, and records what it was sent."""

    replies: list[Message] = dataclasses.field(default_factory=list)
    seen: list[tuple[Message, ...]] = dataclasses.field(default_factory=list)

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None) -> Completion:
        self.seen.append(tuple(messages))
        index = min(len(self.seen) - 1, len(self.replies) - 1)
        reply = (
            self.replies[index]
            if self.replies
            else Message(role=Role.ASSISTANT, content="done")
        )
        return Completion(message=reply, finish_reason="stop")

    async def _stream(self, messages, tools) -> AsyncIterator[StreamChunk]:
        completion = await self.generate(messages, tools)
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides: Any) -> "_ScriptedProvider":
        return self


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda provider, model: _ScriptedProvider()
    )


def _config(workspace: pathlib.Path, **overrides: object) -> AppConfig:
    return AppConfig(workspace=workspace, **overrides)


def _section_keys(app) -> tuple[str, ...]:
    return tuple(part.key for part in app.prompt.render().sections)


# ---- the switch ----------------------------------------------------------


def test_planning_is_on_by_default(tmp_path, offline):
    """A native capability that defaults to off is a mode with extra steps."""
    app = build_app(_config(tmp_path))

    assert app.plans is not None
    assert PLAN_WRITE_TOOL_NAME in app.registry.names()


def test_the_tool_and_the_section_arrive_together(tmp_path, offline):
    app = build_app(_config(tmp_path))

    assert PLAN_WRITE_TOOL_NAME in app.registry.names()
    assert "planning" in _section_keys(app)


def test_turning_planning_off_removes_all_three_halves(tmp_path, offline):
    app = build_app(_config(tmp_path, planning=False))

    assert app.plans is None
    assert PLAN_WRITE_TOOL_NAME not in app.registry.names()
    assert "planning" not in _section_keys(app)
    assert build_injector(app, session_id="s") is None


def test_a_caller_s_own_tools_without_plan_write_disable_planning(tmp_path, offline):
    """What is mounted decides, not what the configuration asked for."""

    class _Custom:
        @property
        def name(self) -> str:
            return "custom"

        def definition(self) -> ToolDefinition:
            return ToolDefinition(name="custom", description="does a thing")

        async def execute(self, arguments: str) -> str:
            return "ok"

    app = build_app(_config(tmp_path), tools=[_Custom()])

    assert app.plans is None
    assert "planning" not in _section_keys(app)
    assert build_injector(app, session_id="s") is None


def test_the_switch_is_readable_from_the_environment(tmp_path):
    config = resolve_app_config(
        argv=[],
        env={"OMICSCLAW_WORKSPACE": str(tmp_path), "OMICSCLAW_PLANNING": "false"},
    )

    assert config.planning is False


def test_the_gate_budget_is_readable_from_the_command_line(tmp_path):
    config = resolve_app_config(
        argv=["--planning-gate-turns", "3"],
        env={"OMICSCLAW_WORKSPACE": str(tmp_path)},
    )

    assert config.planning_gate_turns == 3


# ---- the section itself --------------------------------------------------


def test_the_section_names_the_tool_it_asks_for(tmp_path, offline):
    app = build_app(_config(tmp_path))

    body = app.prompt.render().system_prompt
    assert PLAN_WRITE_TOOL_NAME in body


def test_the_section_sits_between_guidance_and_the_volatile_blocks(tmp_path, offline):
    keys = _section_keys(build_app(_config(tmp_path)))

    assert keys.index("tools") < keys.index("planning")
    assert keys.index("planning") < keys.index("environment")


# ---- where plans are kept ------------------------------------------------


def test_plans_live_beside_the_other_per_session_state(tmp_path):
    config = _config(tmp_path)

    assert config.plans_root() == tmp_path / ".omicsclaw" / "plans"


def test_no_directory_is_made_until_a_plan_is_written(tmp_path, offline):
    build_app(_config(tmp_path))

    assert not (tmp_path / ".omicsclaw" / "plans").exists()


def test_a_written_plan_reaches_the_workspace(tmp_path, offline):
    app = build_app(_config(tmp_path))
    assert app.plans is not None

    app.plans.for_session("sess-1").write((PlanItem("1", "load data", R),))

    plans = tmp_path / ".omicsclaw" / "plans"
    assert (plans / "sess-1.json").is_file()
    assert "load data" in (plans / "sess-1.md").read_text(encoding="utf-8")


def test_a_storage_failure_is_reported_and_the_plan_survives(tmp_path, caplog):
    """Fail-open: the plan is in memory and correct, so losing the turn
    would trade a disk problem for a lost exchange."""
    book = build_plan_book(_config(tmp_path))
    assert book is not None
    unwritable = tmp_path / ".omicsclaw"
    unwritable.mkdir(parents=True)
    (unwritable / "plans").write_text("not a directory", encoding="utf-8")

    store = book.for_session("sess-1")
    store.write((PlanItem("1", "step", R),))

    assert [item.id for item in store.read()] == ["1"]
    assert any("could not store the plan" in r.message for r in caplog.records)


def test_a_corrupt_plan_file_does_not_stop_an_exchange(tmp_path, caplog):
    plans = tmp_path / ".omicsclaw" / "plans"
    plans.mkdir(parents=True)
    (plans / "sess-1.json").write_text("{ not json", encoding="utf-8")
    book = build_plan_book(_config(tmp_path))
    assert book is not None

    store = book.for_session("sess-1")

    assert store.read() == ()
    assert any("could not store the plan" in r.message for r in caplog.records)


# ---- the exchange --------------------------------------------------------


def _app_with(tmp_path, monkeypatch, provider: _ScriptedProvider, **overrides):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda p, m: provider
    )
    app = build_app(_config(tmp_path, **overrides))
    from omicsclaw.engine import AgentEngine

    return dataclasses.replace(
        app,
        engine=AgentEngine(provider, app.registry, app.config.engine_config()),
    )


def test_a_plan_written_in_one_turn_is_injected_into_the_next(
    tmp_path, monkeypatch
):
    """The whole point, end to end through the real loop and the real tool."""
    provider = _ScriptedProvider(
        replies=[
            Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name=PLAN_WRITE_TOOL_NAME,
                        arguments=json.dumps(
                            {
                                "steps": [
                                    {
                                        "id": "1",
                                        "content": "load the matrix",
                                        "status": "in_progress",
                                    }
                                ]
                            }
                        ),
                    ),
                ),
            ),
            Message(role=Role.ASSISTANT, content="matrix loaded"),
        ]
    )
    app = _app_with(tmp_path, monkeypatch, provider)

    asyncio.run(run_turn(app, [], "analyse this sample", session_id="sess-1"))

    assert len(provider.seen) == 2
    first, second = provider.seen
    assert not any(INJECTION_HEADER in (m.content or "") for m in first)
    assert second[-1].content.startswith(INJECTION_HEADER)
    assert "load the matrix" in second[-1].content


def test_the_injected_block_is_not_carried_into_the_next_exchange(
    tmp_path, monkeypatch
):
    """It is re-derived every call; storing it would let it accumulate."""
    provider = _ScriptedProvider(
        replies=[Message(role=Role.ASSISTANT, content="done")]
    )
    app = _app_with(tmp_path, monkeypatch, provider)
    assert app.plans is not None
    app.plans.for_session("sess-1").write((PlanItem("1", "step", R),))

    outcome = asyncio.run(run_turn(app, [], "go", session_id="sess-1"))

    assert not any(INJECTION_HEADER in (m.content or "") for m in outcome.history)


def test_a_plan_survives_a_restart(tmp_path, monkeypatch):
    """A second app over the same workspace resumes the session's plan."""
    provider = _ScriptedProvider(
        replies=[Message(role=Role.ASSISTANT, content="done")]
    )
    first = _app_with(tmp_path, monkeypatch, provider)
    assert first.plans is not None
    first.plans.for_session("sess-1").write((PlanItem("1", "carry on", R),))

    provider.seen.clear()
    second = _app_with(tmp_path, monkeypatch, provider)
    asyncio.run(run_turn(second, [], "continue", session_id="sess-1"))

    assert "carry on" in provider.seen[0][-1].content


def test_an_anonymous_exchange_leaves_no_plan_file(tmp_path, monkeypatch):
    provider = _ScriptedProvider(
        replies=[Message(role=Role.ASSISTANT, content="done")]
    )
    app = _app_with(tmp_path, monkeypatch, provider)
    assert app.plans is not None
    app.plans.for_session("").write((PlanItem("1", "step", R),))

    assert not (tmp_path / ".omicsclaw" / "plans").exists()


def test_two_sessions_do_not_see_each_other_s_plans(tmp_path, monkeypatch):
    provider = _ScriptedProvider(
        replies=[Message(role=Role.ASSISTANT, content="done")]
    )
    app = _app_with(tmp_path, monkeypatch, provider)
    assert app.plans is not None
    app.plans.for_session("alice").write((PlanItem("1", "alice's step", R),))
    app.plans.for_session("bob").write((PlanItem("2", "bob's step", R),))

    asyncio.run(run_turn(app, [], "go", session_id="bob"))

    sent = provider.seen[-1][-1].content
    assert "bob's step" in sent
    assert "alice's step" not in sent


def test_planning_off_injects_nothing_even_with_a_plan_on_disk(
    tmp_path, monkeypatch
):
    provider = _ScriptedProvider(
        replies=[Message(role=Role.ASSISTANT, content="done")]
    )
    seeded = _app_with(tmp_path, monkeypatch, provider)
    assert seeded.plans is not None
    seeded.plans.for_session("sess-1").write((PlanItem("1", "step", R),))

    provider.seen.clear()
    off = _app_with(tmp_path, monkeypatch, provider, planning=False)
    asyncio.run(run_turn(off, [], "go", session_id="sess-1"))

    assert not any(
        INJECTION_HEADER in (m.content or "") for m in provider.seen[0]
    )


def test_run_turn_tells_the_tools_which_session_they_are_in(tmp_path, monkeypatch):
    """The seam ``plan_write`` resolves its session through.

    Without it the tool writes to the anonymous store while the injector
    reads the session's, so a plan is written and gone by the next call
    with nothing raised anywhere. ``TurnRunner`` binds the same fact;
    these two functions did not.
    """
    seen: list[object] = []

    class _Nosy:
        policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, read_only=True)

        @property
        def name(self) -> str:
            return "nosy"

        def definition(self) -> ToolDefinition:
            return ToolDefinition(name="nosy", description="reads its context")

        async def execute(self, arguments: str) -> str:
            from omicsclaw.tools.context import context_value

            seen.append(context_value("session_id"))
            return "ok"

    provider = _ScriptedProvider(
        replies=[
            Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=(ToolCall(id="c1", name="nosy", arguments="{}"),),
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    monkeypatch.setattr(assembly, "provider_from_env", lambda p, m: provider)
    app = build_app(_config(tmp_path), tools=[_Nosy()])
    from omicsclaw.engine import AgentEngine

    app = dataclasses.replace(
        app, engine=AgentEngine(provider, app.registry, app.config.engine_config())
    )

    asyncio.run(run_turn(app, [], "go", session_id="sess-9"))

    assert seen == ["sess-9"]


def test_binding_the_session_keeps_an_outer_approval_channel(tmp_path, monkeypatch):
    """``use_tool_context`` replaces rather than merges.

    A bare ``values=`` bind would unbind a caller's approval channel, and
    every gated tool would start failing closed — a regression whose only
    symptom is tools refusing to run.
    """
    from omicsclaw.tools.context import (
        ApprovalDecision,
        current_context,
        use_tool_context,
    )

    seen: list[object] = []

    class _Nosy:
        policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, read_only=True)

        @property
        def name(self) -> str:
            return "nosy"

        def definition(self) -> ToolDefinition:
            return ToolDefinition(name="nosy", description="reads its context")

        async def execute(self, arguments: str) -> str:
            seen.append(current_context().approval)
            return "ok"

    async def approve(request: Any) -> ApprovalDecision:
        return ApprovalDecision.ALLOW

    provider = _ScriptedProvider(
        replies=[
            Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=(ToolCall(id="c1", name="nosy", arguments="{}"),),
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    monkeypatch.setattr(assembly, "provider_from_env", lambda p, m: provider)
    app = build_app(_config(tmp_path), tools=[_Nosy()])
    from omicsclaw.engine import AgentEngine

    app = dataclasses.replace(
        app, engine=AgentEngine(provider, app.registry, app.config.engine_config())
    )

    async def drive():
        with use_tool_context(approval=approve):
            await run_turn(app, [], "go", session_id="sess-9")

    asyncio.run(drive())

    assert seen == [approve]


# ---- the other two exchange paths ----------------------------------------


def _plan_write_reply(content: str) -> Message:
    return Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=(
            ToolCall(
                id="c1",
                name=PLAN_WRITE_TOOL_NAME,
                arguments=json.dumps(
                    {
                        "steps": [
                            {"id": "1", "content": content, "status": "in_progress"}
                        ]
                    }
                ),
            ),
        ),
    )


def test_stream_turn_writes_and_injects_under_the_right_session(
    tmp_path, monkeypatch
):
    """One of the three documented call sites, and it had no test.

    ``run_turn`` was covered and ``TurnRunner`` binds the session through
    its own ``turn_values``; this path had neither, so the fix that made
    ``plan_write`` resolve its session could have regressed here alone.
    """
    from omicsclaw.entry.turn import stream_turn

    provider = _ScriptedProvider(
        replies=[
            _plan_write_reply("stream the matrix"),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    app = _app_with(tmp_path, monkeypatch, provider)

    async def drive():
        async for _event in stream_turn(app, [], "go", session_id="sess-S"):
            pass

    asyncio.run(drive())

    assert app.plans is not None
    assert [i.id for i in app.plans.for_session("sess-S").read()] == ["1"]
    assert "stream the matrix" in provider.seen[1][-1].content


def test_the_session_registry_path_writes_and_injects(tmp_path, monkeypatch):
    """The path every live surface actually uses.

    Channel, Desktop and the CLI all go through ``SessionRegistry`` →
    ``TurnRunner``, not through ``run_turn``. A feature verified only on
    the library path is a feature verified on the path nobody runs.
    """
    from omicsclaw.entry import attach_sessions
    from omicsclaw.entry.ingress import InboundMessage

    provider = _ScriptedProvider(
        replies=[
            _plan_write_reply("load the matrix"),
            Message(role=Role.ASSISTANT, content="matrix loaded"),
        ]
    )
    app = attach_sessions(_app_with(tmp_path, monkeypatch, provider))

    async def drive():
        handle = await app.sessions.deliver(
            InboundMessage(
                text="analyse this", session_id="sess-T", source_request_id="r1"
            )
        )
        await handle.wait()
        await app.aclose()

    asyncio.run(drive())

    assert len(provider.seen) == 2
    assert provider.seen[1][-1].content.startswith(INJECTION_HEADER)
    assert "load the matrix" in provider.seen[1][-1].content
    assert (tmp_path / ".omicsclaw" / "plans" / "sess-T.json").is_file()

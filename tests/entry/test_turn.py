"""One exchange, from the composed prompt to the engine and back."""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib

import pytest

from omicsclaw.context import ContextBudget, Pressure
from omicsclaw.engine import AgentEngine, EngineEventType, StopReason
from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app
from omicsclaw.entry.config import AppConfig, SkillsIndex
from omicsclaw.entry.turn import (
    PRESSURE_ORDER,
    at_least,
    compose,
    prepare,
    run_turn,
    stream_turn,
)
from omicsclaw.provider import Completion
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
)


class _Scripted:
    """A provider that replays a fixed list of completions, in order.

    Records every conversation it was handed, which is what the tests
    about the system prompt actually assert on: what reached the model.
    """

    def __init__(self, *replies: Message) -> None:
        self.replies = list(replies) or [Message(role=Role.ASSISTANT, content="ok")]
        self.seen: list[tuple[Message, ...]] = []
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        self.seen.append(tuple(messages))
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return Completion(message=reply)

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        yield StreamChunk(
            type=StreamChunkType.TEXT_DELTA, delta=completion.message.content
        )
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides):
        return self


def write_skill(root: pathlib.Path, domain: str, name: str, description: str) -> None:
    """One minimal ``SKILL.md`` under ``root/skills/<domain>/<name>/``."""
    directory = root / "skills" / domain / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\nRun it with `python {name}.py`.\n",
        encoding="utf-8",
    )


def make_app(tmp_path: pathlib.Path, provider: _Scripted, **overrides) -> object:
    """A real app over a fake backend, built by the real composition root."""
    (tmp_path / "OMICSCLAW.md").write_text(
        "You are OmicsClaw.\n\nRoute to a skill, never guess.", encoding="utf-8"
    )
    config = AppConfig(workspace=tmp_path, **overrides)

    real = assembly.provider_from_env
    assembly.provider_from_env = lambda p, m: provider
    try:
        app = build_app(config)
    finally:
        assembly.provider_from_env = real

    return dataclasses.replace(
        app,
        engine=AgentEngine(provider, app.registry, config.engine_config()),
    )


# ---- the StrEnum trap ---------------------------------------------------


def test_the_pressure_tiers_do_not_compare_correctly_on_their_own():
    """Why :func:`at_least` exists at all, stated as an executable fact."""
    assert not (Pressure.EMERGENCY >= Pressure.FULL)


def test_at_least_ranks_the_tiers_by_severity():
    assert at_least(Pressure.EMERGENCY, Pressure.FULL)
    assert at_least(Pressure.FULL, Pressure.FULL)
    assert not at_least(Pressure.WARN, Pressure.FULL)
    assert not at_least(Pressure.NONE, Pressure.WARN)


def test_every_tier_has_a_rank():
    assert set(PRESSURE_ORDER) == set(Pressure)


# ---- composition --------------------------------------------------------


def test_compose_puts_one_system_message_first_and_the_user_last(tmp_path):
    app = make_app(tmp_path, _Scripted())

    messages, _prompt = compose(app, [], "分析这份 Visium 数据")

    assert messages[0].role is Role.SYSTEM
    assert sum(m.role is Role.SYSTEM for m in messages) == 1
    assert messages[-1].role is Role.USER
    assert messages[-1].content == "分析这份 Visium 数据"


def test_the_composed_prompt_carries_all_three_tiers(tmp_path):
    """Core identity, the contract, and the skill catalogue."""
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    app = make_app(tmp_path, _Scripted())

    system = compose(app, [], "hi")[0][0].content

    assert "You are OmicsClaw." in system
    assert "Route to a skill, never guess." in system
    assert "- spatial-de: Load when running DE." in system
    assert "## Safety rules" in system


def test_the_prompt_is_rendered_per_turn_not_frozen_at_start_up(tmp_path):
    app = make_app(tmp_path, _Scripted())
    assert "You are OmicsClaw." in compose(app, [], "hi")[0][0].content

    (tmp_path / "OMICSCLAW.md").write_text("You are somebody else.", encoding="utf-8")

    assert "You are somebody else." in compose(app, [], "hi")[0][0].content


def test_a_history_carried_forward_does_not_stack_system_messages(tmp_path):
    app = make_app(tmp_path, _Scripted())
    first, _ = compose(app, [], "one")

    second, _ = compose(app, first[1:], "two")

    assert sum(m.role is Role.SYSTEM for m in second) == 1


# ---- the engine actually receives it ------------------------------------


def test_the_engine_is_handed_the_composed_prompt(tmp_path):
    """The injection, asserted where it lands: at the provider."""
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider)

    outcome = asyncio.run(run_turn(app, [], "分析"))

    seen = provider.seen[0]
    assert seen[0].role is Role.SYSTEM
    assert "You are OmicsClaw." in seen[0].content
    assert "- spatial-de: Load when running DE." in seen[0].content
    assert outcome.reply == "done"
    assert outcome.result.stop_reason is StopReason.CONVERGED


def test_the_model_can_load_a_skill_through_the_loop(tmp_path):
    """The whole of progressive disclosure, end to end.

    The index in the system prompt names the skill; the model calls
    ``use_skill``; the body comes back as an Observation and the loop
    converges. If the section and the tool were built from two scans this
    is the test that would fail.
    """
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    provider = _Scripted(
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(
                    id="c1",
                    name="use_skill",
                    arguments='{"skill_name": "spatial-de"}',
                ),
            ),
        ),
        Message(role=Role.ASSISTANT, content="loaded"),
    )
    app = make_app(tmp_path, provider)

    outcome = asyncio.run(run_turn(app, [], "run spatial DE"))

    observation = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert len(observation) == 1
    assert not observation[0].is_error
    assert "Run it with `python spatial-de.py`." in observation[0].content
    assert "Skill directory:" in observation[0].content
    assert outcome.reply == "loaded"


def test_the_returned_history_is_free_of_the_system_message(tmp_path):
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider)

    outcome = asyncio.run(run_turn(app, [], "one"))

    assert not any(m.role is Role.SYSTEM for m in outcome.history)
    assert outcome.history[0].content == "one"


def test_two_turns_in_a_row_keep_exactly_one_system_message(tmp_path):
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider)

    first = asyncio.run(run_turn(app, [], "one"))
    asyncio.run(run_turn(app, first.history, "two"))

    assert sum(m.role is Role.SYSTEM for m in provider.seen[1]) == 1
    assert provider.seen[1][-1].content == "two"


def test_the_outcome_reports_which_section_cost_what(tmp_path):
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    app = make_app(tmp_path, _Scripted())

    outcome = asyncio.run(run_turn(app, [], "hi"))

    keys = [key for key, _ in outcome.prompt.section_stats]
    assert "skills" in keys
    assert all(tokens > 0 for _key, tokens in outcome.prompt.section_stats)


# ---- budget and compaction ---------------------------------------------


def test_a_conversation_that_fits_is_not_compacted(tmp_path):
    app = make_app(tmp_path, _Scripted())

    messages, _prompt, _state, record = asyncio.run(prepare(app, [], "hi"))

    assert record is None
    assert messages[0].role is Role.SYSTEM


def test_a_conversation_over_the_tier_is_compacted_before_the_engine(tmp_path):
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider)
    tiny = ContextBudget(
        context_tokens=2_000,
        reserve_output_tokens=200,
        reserve_tool_tokens=200,
    )
    app = dataclasses.replace(app, budget=tiny)
    history = []
    for index in range(40):
        history.append(Message.user(f"question {index} " + "q" * 400))
        history.append(Message.assistant("answer " + "a" * 400))

    outcome = asyncio.run(run_turn(app, history, "next"))

    assert outcome.compaction is not None
    assert outcome.compaction.msgs_after < outcome.compaction.msgs_before
    assert not any(m.role is Role.SYSTEM for m in outcome.history)

    # The pinned head survived as itself. Asserting only "exactly one
    # system message" would not notice ``pinned=0``: compaction would
    # summarize the prompt away and the count would still be one, or
    # zero, depending on where the cut landed.
    sent = provider.seen[0]
    assert sum(m.role is Role.SYSTEM for m in sent) == 1
    assert sent[0].role is Role.SYSTEM
    assert "You are OmicsClaw." in sent[0].content
    assert "## Safety rules" in sent[0].content


class _Canned:
    """A summarizer that returns a summary compaction can actually parse.

    The scripted provider's reply is not anchors-and-summary shaped, so
    a turn driven by it always takes the degraded path — and the degraded
    path preserves the head whether or not it was pinned, which makes it
    the wrong place to test pinning.
    """

    async def summarize(self, prompt, *, system):
        return (
            "## Anchors\n\n### User Intent\nship it\n\n"
            "## Summary\nthey discussed it at length"
        )


def test_the_system_message_survives_a_successful_summarization(tmp_path):
    """``pinned=1``, tested at the only tier where it changes anything.

    At ``emergency`` the fallback preserves the head regardless, so
    ``pinned=0`` is indistinguishable there. At ``full`` with a working
    summarizer it is not: the head is summarized, and without the pin
    the persona and the safety rules go into the summary and out of the
    conversation — message zero comes back as a user turn.

    ``memory=False`` and ``subagents=False`` because the tier is the
    subject and the tier moves with the size of the tool table:
    ``measure`` reserves what the declarations in ``tools_snapshot``
    actually cost, so mounting the two memory tools or the ``task`` tool
    tips this history from ``full`` into ``emergency`` and the test stops
    being about pinning.
    """
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider, memory=False, subagents=False)
    app = dataclasses.replace(
        app,
        summarizer=_Canned(),
        budget=ContextBudget(
            context_tokens=9_000,
            reserve_output_tokens=200,
            reserve_tool_tokens=200,
        ),
    )
    history = []
    for index in range(30):
        history.append(Message.user(f"question {index} " + "q" * 300))
        history.append(Message.assistant("answer " + "a" * 300))

    outcome = asyncio.run(run_turn(app, history, "next"))

    assert outcome.compaction is not None
    assert outcome.compaction.pressure is Pressure.FULL
    assert not outcome.compaction.degraded, "this must be the summarizing path"

    sent = provider.seen[0]
    assert sent[0].role is Role.SYSTEM
    assert "You are OmicsClaw." in sent[0].content
    assert "## Safety rules" in sent[0].content


def test_the_compaction_threshold_is_read_from_the_config(tmp_path):
    """``compact_at=none`` compacts every turn; the default does not."""
    app = make_app(tmp_path, _Scripted(), compact_at=Pressure.NONE)

    _messages, _prompt, _state, record = asyncio.run(prepare(app, [], "hi"))

    assert record is not None


# ---- deadlines and streaming -------------------------------------------


def test_a_turn_deadline_is_applied_when_one_is_configured(tmp_path):
    class Slow(_Scripted):
        async def generate(self, messages, tools=None):
            await asyncio.sleep(1.0)
            return await super().generate(messages, tools)

    app = make_app(tmp_path, Slow(), turn_timeout_s=0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(run_turn(app, [], "hi"))


def test_no_turn_deadline_means_the_turn_may_take_as_long_as_it_takes(tmp_path):
    app = make_app(tmp_path, _Scripted())

    assert app.config.turn_timeout_s is None
    assert asyncio.run(run_turn(app, [], "hi")).reply == "ok"


def test_streaming_a_turn_composes_the_same_prompt(tmp_path):
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    provider = _Scripted(Message(role=Role.ASSISTANT, content="streamed"))
    app = make_app(tmp_path, provider)

    async def drive():
        return [event async for event in stream_turn(app, [], "hi")]

    events = asyncio.run(drive())

    assert any(e.type is EngineEventType.DONE for e in events)
    assert "- spatial-de: Load when running DE." in provider.seen[0][0].content


# ---- the catalogue switch ----------------------------------------------


def test_switching_the_catalogue_off_removes_it_from_the_turn(tmp_path):
    write_skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    provider = _Scripted(Message(role=Role.ASSISTANT, content="done"))
    app = make_app(tmp_path, provider, skills_index=SkillsIndex.OFF)

    asyncio.run(run_turn(app, [], "hi"))

    assert "spatial-de" not in provider.seen[0][0].content
    assert app.registry.get("use_skill") is None
    assert app.skills.is_empty

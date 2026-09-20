"""Plan 0035: compaction across the model calls of one run.

Three questions are pinned here, each in the direction that would hurt if
it were answered wrongly:

* **Offload comes first and is re-graded.** A conversation that offloading
  alone brings under the trigger must not also pay for a summary.
* **The write-back gate.** A failed summary serves one call and is retried
  on the next; an emergency truncation is kept; a no-op is not kept.
* **Nothing is lost between compactions.** Offload references survive a
  second summary, the extractor sees the text as it was before offloading,
  and the incremental template is used once a summary exists.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.context import (
    COMPACTION_MARKER,
    OFFLOAD_MARKER,
    OFFLOAD_RULE,
    CompactionPlan,
    CompactionRecord,
    CompactionState,
    ContextBudget,
    Offloader,
    Pressure,
    ProgressiveCompactor,
    build_summary_prompt,
    compact,
    estimate_messages_tokens,
    should_write_back,
)
from omicsclaw.context.offload import parse_references
from omicsclaw.schema import Message, ToolCall

_GOOD = (
    "## Anchors\n\n### User Intent\nannotate the slide\n\n"
    "### Next Steps\n- run spatial-de\n\n## Summary\nthree steps in"
)


class Store:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    async def put(self, key: str, content: str) -> str:
        self.files[key] = content
        return f".omicsclaw/tool_results/s1/{key}.txt"


class Summarizer:
    def __init__(self, text: str = _GOOD, *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.prompts: list[str] = []

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.text


class Extractor:
    def __init__(self, *, fail: bool = False) -> None:
        self.seen: list[tuple[Message, ...]] = []
        self.fail = fail

    async def extract(self, messages):
        self.seen.append(tuple(messages))
        if self.fail:
            raise RuntimeError("store locked")
        return None


def _budget(tokens: int, ratio: float) -> ContextBudget:
    """A budget under which *tokens* sits at *ratio* of what is usable."""
    return ContextBudget(
        context_tokens=int(tokens / ratio),
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )


def _conversation(exchanges: int, *, output: int = 8_000, text: int = 0):
    """``[system, user, (call, result) * n, answer]``; results are large."""
    messages = [Message.system("sys"), Message.user("annotate the slide")]
    for index in range(exchanges):
        call = ToolCall(id=f"c{index}", name="bash", arguments="{}")
        messages.append(Message.assistant("t" * text, tool_calls=[call]))
        messages.append(
            Message.tool(
                tool_call_id=f"c{index}",
                name="bash",
                content=f"out {index}\n" + "y" * output,
            )
        )
    messages.append(Message.assistant("working on it"))
    return tuple(messages)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


# --- offload first, then re-grade ----------------------------------------


def test_the_warn_tier_offloads_and_asks_no_model():
    messages = _conversation(8)
    tokens = estimate_messages_tokens(messages)
    summarizer = Summarizer()

    result, record, _ = _run(
        compact(
            messages,
            _budget(tokens, 0.65),
            summarizer=summarizer,
            offloader=Offloader(Store()),
            pinned=1,
        )
    )

    assert record.trigger is Pressure.WARN
    assert record.offloaded
    assert summarizer.prompts == []
    assert len(result) == len(messages)
    assert result[-6:] == messages[-6:], "the tail is never offloaded"
    assert any(m.content.startswith(OFFLOAD_MARKER) for m in result[1:-6])
    assert record.tokens_after < record.tokens_before


def test_without_an_offloader_the_warn_tier_changes_nothing():
    messages = _conversation(8)
    tokens = estimate_messages_tokens(messages)

    result, record, _ = _run(compact(messages, _budget(tokens, 0.65), pinned=1))

    assert result == messages
    assert record.offloaded == ()


def test_offloading_that_is_enough_skips_the_summary():
    """Graded at SOFT, offloaded, re-graded below it: no model call."""
    messages = _conversation(8)
    tokens = estimate_messages_tokens(messages)
    summarizer = Summarizer()

    _, record, state = _run(
        compact(
            messages,
            _budget(tokens, 0.75),
            summarizer=summarizer,
            offloader=Offloader(Store()),
            pinned=1,
        )
    )

    assert record.trigger is Pressure.SOFT
    assert record.pressure is not Pressure.SOFT
    assert summarizer.prompts == []
    assert state == CompactionState()
    assert any("offloading lowered the pressure" in note for note in record.advisories)


def test_offloading_that_is_not_enough_still_summarizes():
    messages = _conversation(8, output=5_000, text=20_000)
    tokens = estimate_messages_tokens(messages)
    summarizer = Summarizer()

    result, record, _ = _run(
        compact(
            messages,
            _budget(tokens, 0.85),
            summarizer=summarizer,
            offloader=Offloader(Store()),
            pinned=1,
        )
    )

    assert record.offloaded
    assert record.pressure in (Pressure.SOFT, Pressure.FULL)
    assert record.summarized > 0
    assert result[1].content.startswith(COMPACTION_MARKER)
    assert OFFLOAD_RULE in summarizer.prompts[0]


# --- references survive ---------------------------------------------------


def test_the_compaction_message_lists_what_was_offloaded_and_summarized():
    messages = _conversation(8)
    tokens = estimate_messages_tokens(messages)

    result, record, _ = _run(
        compact(
            messages,
            _budget(tokens, 0.5),
            summarizer=Summarizer(),
            offloader=Offloader(Store()),
            pinned=1,
            floor=Pressure.FULL,
        )
    )

    listed = parse_references(result[1].content)
    offloaded_in_head = {
        entry.reference
        for entry in record.offloaded
        if entry.tool_call_id in {m.tool_call_id for m in messages[1:-6]}
    }
    assert offloaded_in_head
    assert {entry.reference for entry in listed} == offloaded_in_head
    assert record.forced


def test_references_are_carried_into_the_next_compaction():
    first = _conversation(8)
    tokens = estimate_messages_tokens(first)
    budget = _budget(tokens, 0.5)
    once, record, state = _run(
        compact(
            first,
            budget,
            summarizer=Summarizer(),
            offloader=Offloader(Store()),
            pinned=1,
            floor=Pressure.FULL,
        )
    )
    earlier = {entry.reference for entry in parse_references(once[1].content)}
    # Different content, so the second batch gets different keys and an
    # old reference can only survive by being carried, not by recurring.
    grown = (*once, *_conversation(8, output=8_001)[2:])

    twice, _, _ = _run(
        compact(
            grown,
            budget,
            summarizer=Summarizer(),
            state=state,
            offloader=Offloader(Store()),
            pinned=1,
            floor=Pressure.FULL,
        )
    )

    later = {entry.reference for entry in parse_references(twice[1].content)}
    assert earlier and earlier <= later
    assert later - earlier, "the second batch was listed too"
    assert sum(m.content.startswith(COMPACTION_MARKER) for m in twice) == 1


# --- the extractor -------------------------------------------------------


def test_the_extractor_reads_the_text_as_it_was_before_offloading():
    messages = _conversation(8)
    extractor = Extractor()

    _run(
        compact(
            messages,
            _budget(estimate_messages_tokens(messages), 0.5),
            summarizer=Summarizer(),
            offloader=Offloader(Store()),
            extractor=extractor,
            pinned=1,
            floor=Pressure.FULL,
        )
    )

    (seen,) = extractor.seen
    assert seen == messages[1 : 1 + len(seen)]
    assert not any(m.content.startswith(OFFLOAD_MARKER) for m in seen)


def test_an_extractor_that_fails_changes_nothing_but_a_note():
    messages = _conversation(8)

    _, record, _ = _run(
        compact(
            messages,
            _budget(estimate_messages_tokens(messages), 0.5),
            summarizer=Summarizer(),
            extractor=Extractor(fail=True),
            pinned=1,
            floor=Pressure.FULL,
        )
    )

    assert record.summarized > 0
    assert record.degraded == ""
    assert any("store locked" in note for note in record.advisories)


def test_the_extractor_runs_beside_the_summarizer_not_after_it():
    """Each waits for the other to start; run one after the other, they hang."""
    started = asyncio.Event()
    released = asyncio.Event()

    class Waiting(Summarizer):
        async def summarize(self, prompt, *, system):
            started.set()
            await released.wait()
            return _GOOD

    class Releasing(Extractor):
        async def extract(self, messages):
            await started.wait()
            released.set()

    messages = _conversation(8)
    _, record, _ = _run(
        compact(
            messages,
            _budget(estimate_messages_tokens(messages), 0.5),
            summarizer=Waiting(),
            extractor=Releasing(),
            pinned=1,
            floor=Pressure.FULL,
        )
    )

    assert record.summarized > 0


# --- the summary prompt --------------------------------------------------


def test_the_offload_rule_appears_only_when_there_is_a_placeholder():
    plain = CompactionPlan(
        Pressure.FULL, (), (Message.user("hello"),), (), needs_summary=True
    )

    _, prompt = build_summary_prompt(plain, CompactionState())

    assert OFFLOAD_RULE not in prompt


def test_an_incremental_prompt_does_not_repeat_the_previous_compaction():
    old = Message.user(f"{COMPACTION_MARKER}\n## Anchors\n\nsecret-old-body")
    plan = CompactionPlan(
        Pressure.FULL, (), (old, Message.user("new work")), (), needs_summary=True
    )

    _, prompt = build_summary_prompt(plan, CompactionState(summary="before"))

    assert "secret-old-body" not in prompt
    assert "new work" in prompt
    assert "<previous-compaction>" in prompt


# --- the write-back gate --------------------------------------------------


def _record(**changes) -> CompactionRecord:
    values = dict(
        pressure=Pressure.FULL,
        tokens_before=100,
        tokens_after=40,
        msgs_before=20,
        msgs_after=8,
        summarized=12,
        preserved_tail=6,
    )
    values.update(changes)
    return CompactionRecord(**values)


def test_a_summary_that_removed_something_is_kept():
    assert should_write_back(_record())


def test_a_degraded_summary_is_not_kept():
    assert not should_write_back(_record(degraded="the summarizer raised ..."))


def test_an_emergency_truncation_is_kept_despite_its_reason():
    assert should_write_back(
        _record(pressure=Pressure.EMERGENCY, degraded="emergency fallback")
    )


def test_a_compaction_that_removed_nothing_is_not_kept():
    assert not should_write_back(
        _record(tokens_after=100, msgs_after=20, summarized=0)
    )


def test_an_offload_alone_is_kept():
    from omicsclaw.context import OffloadEntry

    assert should_write_back(
        _record(
            pressure=Pressure.WARN,
            tokens_after=100,
            msgs_after=20,
            offloaded=(OffloadEntry(reference="r", lines=1, chars=1),),
        )
    )


# --- the compactor across calls ------------------------------------------


def test_below_the_trigger_it_measures_and_leaves_the_history_alone():
    messages = _conversation(2)
    reports = []
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.3),
        pinned=1,
        on_measure=reports.append,
    )

    assert _run(compactor.compact(messages, ())) is None
    assert len(reports) == 1
    assert compactor.records == ()


def test_a_successful_summary_is_kept_and_the_next_one_is_incremental():
    messages = _conversation(8, output=5_000, text=20_000)
    summarizer = Summarizer()
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.85),
        summarizer=summarizer,
        pinned=1,
    )

    sent, keep = _run(compactor.compact(messages, ()))
    assert keep
    assert compactor.state.summary == "three steps in"
    assert compactor.last_record.written_back

    grown = (*sent, *_conversation(5, output=5_000, text=20_000)[2:])
    _run(compactor.compact(grown, ()))

    assert len(summarizer.prompts) == 2
    assert "<previous-compaction>" in summarizer.prompts[-1]


def test_a_failed_summary_serves_one_call_and_is_retried_on_the_next():
    messages = _conversation(8, output=5_000, text=20_000)
    summarizer = Summarizer(fail=True)
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.85),
        summarizer=summarizer,
        pinned=1,
    )

    sent, keep = _run(compactor.compact(messages, ()))

    assert not keep
    assert len(sent) < len(messages), "the call itself still gets a view that fits"
    assert compactor.state == CompactionState()
    assert not compactor.last_record.written_back

    _run(compactor.compact(messages, ()))
    assert len(summarizer.prompts) == 2


def test_a_summary_that_grew_the_conversation_does_not_become_the_state():
    """One short message summarized into a longer one: nothing to keep.

    The summary state has to describe the history that was kept; carrying
    it forward while the history stays uncompacted would make the next
    incremental summary merge a compaction that never happened.
    """
    tail = [Message.assistant("x" * 4_000) for _ in range(6)]
    messages = (
        Message.system("sys"),
        Message.user("hi"),
        Message.assistant("ok"),
        *tail,
    )
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.75),
        summarizer=Summarizer(),
        pinned=1,
    )

    _, keep = _run(compactor.compact(messages, ()))

    record = compactor.last_record
    assert record.pressure is Pressure.SOFT and record.summarized == 1
    assert record.tokens_after > record.tokens_before
    assert not keep
    assert compactor.state == CompactionState()


def test_an_emergency_truncation_is_kept():
    """Over the budget outright: truncation is the only way it is sendable."""
    messages = _conversation(8, output=5_000, text=20_000)
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 1.5), pinned=1
    )

    sent, keep = _run(compactor.compact(messages, ()))

    assert keep
    assert len(sent) < len(messages)
    assert sent[1] == messages[1], "the task anchor survives"


def test_after_an_emergency_truncation_the_next_compaction_summarizes():
    """Many small messages pack tightly: a truncation aimed at the whole
    usable budget lands just under the EMERGENCY line and is graded
    EMERGENCY again on the next call, forever, and no summary ever runs."""
    messages = [Message.system("sys"), Message.user("the task")]
    for index in range(60):
        call = ToolCall(id=f"c{index}", name="bash", arguments="{}")
        messages.append(Message.assistant("t" * 600, tool_calls=[call]))
        messages.append(
            Message.tool(tool_call_id=f"c{index}", name="bash", content="o" * 600)
        )
    messages = tuple(messages)
    budget = _budget(estimate_messages_tokens(messages), 1.2)
    summarizer = Summarizer()
    compactor = ProgressiveCompactor(budget, summarizer=summarizer, pinned=1)

    sent, keep = _run(compactor.compact(messages, ()))
    assert keep and compactor.last_record.pressure is Pressure.EMERGENCY
    assert budget.pressure(estimate_messages_tokens(sent)) is not Pressure.EMERGENCY

    grown = (*sent, Message.assistant("next step"))
    _run(compactor.compact(grown, ()))

    assert compactor.last_record.pressure is not Pressure.EMERGENCY
    assert summarizer.prompts, "the call after the truncation summarized"


def test_an_emergency_offloads_a_large_recent_result_instead_of_dropping_it():
    """The tail is never offloaded below EMERGENCY; at EMERGENCY a result
    too large to keep would otherwise vanish behind a placeholder answer."""
    call = ToolCall(id="big", name="bash", arguments="{}")
    messages = (
        Message.system("sys"),
        Message.user("the task"),
        Message.assistant("", tool_calls=[call]),
        Message.tool(tool_call_id="big", name="bash", content="z" * 400_000),
    )
    store = Store()
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 2.0),
        offloader=Offloader(store),
        pinned=1,
    )

    sent, keep = _run(compactor.compact(messages, ()))

    assert keep
    assert list(store.files.values()) == ["z" * 400_000]
    assert sent[-1].tool_call_id == "big"
    assert sent[-1].content.startswith(OFFLOAD_MARKER)


def test_force_summarizes_a_quiet_conversation():
    messages = _conversation(8)
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.1),
        summarizer=Summarizer(),
        pinned=1,
    )

    sent, record = _run(compactor.force(messages))

    assert record.forced and record.pressure is Pressure.FULL
    assert record.written_back
    assert sent[1].content.startswith(COMPACTION_MARKER)


def test_a_forced_summary_that_fails_is_not_kept():
    messages = _conversation(8)
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.1),
        summarizer=Summarizer(fail=True),
        pinned=1,
    )

    _, record = _run(compactor.force(messages))

    assert not record.written_back
    assert record.degraded


def test_listeners_hear_compactions_and_cannot_break_them():
    messages = _conversation(8)
    heard: list[CompactionRecord] = []

    def broken_measure(report):
        raise RuntimeError("renderer crashed")

    async def on_compact(record):
        heard.append(record)
        raise RuntimeError("log disk full")

    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.65),
        offloader=Offloader(Store()),
        pinned=1,
        on_measure=broken_measure,
        on_compact=on_compact,
    )

    rewrite = _run(compactor.compact(messages, ()))

    assert rewrite is not None and rewrite[1]
    assert heard == [compactor.last_record]


def test_a_none_tier_compaction_is_recorded_but_not_announced():
    messages = _conversation(2)
    heard = []

    async def on_compact(record):
        heard.append(record)

    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.1),
        pinned=1,
        trigger=Pressure.NONE,
        on_compact=on_compact,
    )

    sent, keep = _run(compactor.compact(messages, ()))

    assert not keep and tuple(sent) == messages
    assert len(compactor.records) == 1
    assert heard == []


def test_a_warn_pass_with_nothing_to_offload_is_not_announced():
    """Every such pass would otherwise be one more chat message in a channel."""
    messages = _conversation(8, output=100, text=6_000)
    heard = []

    async def on_compact(record):
        heard.append(record)

    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.65),
        offloader=Offloader(Store()),
        pinned=1,
        on_compact=on_compact,
    )

    sent, keep = _run(compactor.compact(messages, ()))

    assert compactor.last_record.pressure is Pressure.WARN
    assert not keep and heard == []


@pytest.mark.parametrize("trigger", [Pressure.SOFT, Pressure.FULL])
def test_a_higher_trigger_skips_the_cheaper_tiers(trigger):
    messages = _conversation(8)
    compactor = ProgressiveCompactor(
        _budget(estimate_messages_tokens(messages), 0.65),
        offloader=Offloader(Store()),
        pinned=1,
        trigger=trigger,
    )

    assert _run(compactor.compact(messages, ())) is None

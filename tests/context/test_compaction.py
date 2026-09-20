"""Plan 0030 task C: the orchestration, and the seams either side of it.

Two things this file is arranged around.

**Every tier must do a different thing** (seam ③, pitfall 3). An
implementation that routed all five pressures to one treatment would
satisfy any test that only checked which
:class:`~omicsclaw.context.budget.Pressure` came back, so the tier tests
here assert on the *plan* — what was cut, what was kept, whether a model
is about to be asked anything.

**A no-op has to be a real no-op** (pitfall 6). It cannot be checked by
object identity, because every return value here is a freshly built
tuple on purpose (pitfall 5), and it cannot be checked by ``==``,
because an implementation that rebuilt every message would satisfy that.
What is left is element identity and byte identity of the assembled
prefix, which are the two things the prompt cache actually pays for.

``pytest-asyncio`` is not installed, so the coroutines are driven by
``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from omicsclaw.context.budget import ContextBudget, Pressure
from omicsclaw.context.compaction import (
    CompactionPlan,
    CompactionRecord,
    CompactionState,
    DEFAULT_MIN_TAIL,
    apply_compaction,
    build_summary_prompt,
    compact,
    plan_compaction,
)
from omicsclaw.context.prompt import PromptAssembler, assemble
from omicsclaw.context.sections import Section, static
from omicsclaw.context.summary import Anchors, COMPACTION_MARKER, is_summary_message
from omicsclaw.context.tokens import estimate_messages_tokens
from omicsclaw.context.transcript import MISSING_TOOL_RESULT
from omicsclaw.schema import Message, Role, ToolCall


class _Fixed:
    """A :class:`TokenCounter` answering one token per string.

    A probe rather than a tokenizer: under it every message costs a
    count of its populated fields, which is nothing like what the
    built-in estimate produces for these fixtures, so a grade computed
    with it cannot be mistaken for a grade computed without it.
    """

    def count_text(self, text: str) -> int:
        return 1

_GOOD_SUMMARY = (
    "## Anchors\n\n### User Intent\nannotate the slide\n\n"
    "### Next Steps\n- run spatial-de\n\n## Summary\nthree steps in"
)


class _Canned:
    """A summarizer that answers with a fixed string and counts calls."""

    def __init__(self, text: str = _GOOD_SUMMARY) -> None:
        self.text = text
        self.calls = 0
        self.prompts: list[tuple[str, str]] = []

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.calls += 1
        self.prompts.append((system, prompt))
        return self.text


def _history(turns: int = 24, *, size: int = 400) -> list[Message]:
    """A system prompt and ``turns`` messages of predictable weight."""
    messages = [Message.system("you are OmicsClaw")]
    for index in range(turns):
        messages.append(Message.user(f"q{index} " + "x" * size))
    return messages


def _budget_at(messages, ratio: float) -> ContextBudget:
    """A budget under which *messages* sits at roughly *ratio* of usable."""
    usable = max(1, int(estimate_messages_tokens(messages) / ratio))
    return ContextBudget(
        context_tokens=usable,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )


def _plan(messages, ratio: float, **kwargs) -> CompactionPlan:
    return plan_compaction(
        messages,
        _budget_at(messages, ratio),
        **{"pinned": 1, "min_tail": 6, **kwargs},
    )


# --- one tier, one treatment ---------------------------------------------


def test_the_quiet_tiers_plan_to_do_nothing():
    """``NONE`` and ``WARN`` leave the conversation alone.

    ``WARN`` is the harness's offload tier
    (``progressive_compactor.go:249-261``) with the offloading removed,
    since writing tool results to disk is step 6's. What is left of it
    is the signal, which is a real deliverable — a surface can show
    context pressure before anything has been thrown away — but it is
    not a reason to touch a message.
    """
    messages = _history()

    for ratio, expected in ((0.30, Pressure.NONE), (0.65, Pressure.WARN)):
        plan = _plan(messages, ratio)

        assert plan.pressure is expected
        assert plan.head == ()
        assert plan.needs_summary is False
        assert plan.pinned + plan.tail == tuple(messages)


def test_the_soft_tier_summarizes_half_the_head_and_keeps_the_rest_verbatim():
    """``progressive_compactor.go:266-301``: compression against continuity."""
    messages = _history()

    plan = _plan(messages, 0.75)

    assert plan.pressure is Pressure.SOFT
    assert plan.needs_summary is True
    assert plan.head == tuple(messages[1:10])
    assert plan.tail == tuple(messages[10:])


def test_the_full_tier_summarizes_the_whole_head():
    """``progressive_compactor.go:305-336``: only ``min_tail`` survives."""
    messages = _history()

    plan = _plan(messages, 0.85)

    assert plan.pressure is Pressure.FULL
    assert plan.needs_summary is True
    assert plan.head == tuple(messages[1:19])
    assert plan.tail == tuple(messages[19:])
    assert len(plan.tail) == 6


def test_soft_and_full_are_genuinely_different_cuts():
    """The mutation this rules out: one path wearing five tier labels.

    A compactor that graded correctly and then did the same thing every
    time would pass every assertion about ``Pressure`` in this suite.
    """
    messages = _history()

    soft = _plan(messages, 0.75)
    full = _plan(messages, 0.85)

    assert len(full.head) > len(soft.head)
    assert len(full.tail) < len(soft.tail)


def test_the_emergency_tier_truncates_without_planning_a_summary():
    """``progressive_compactor.go:341-352``: no model, no round trip.

    The tier exists because there is no room left to spend one in. The
    task anchor is still first, because an emergency that loses the task
    is the 143-turn spin of issue #117.
    """
    messages = _history()

    plan = _plan(messages, 1.8)

    assert plan.pressure is Pressure.EMERGENCY
    assert plan.needs_summary is False
    assert plan.head == ()
    assert len(plan.tail) < len(messages) - 1, "messages were dropped"
    assert plan.tail[0] is messages[1], "the task anchor survives"


def test_a_plan_with_nothing_compactible_falls_back_to_pass_through():
    """Pitfall 11 at the tier level: ``pinned + min_tail`` covers it all."""
    messages = _history(turns=4)

    plan = _plan(messages, 0.85, min_tail=6)

    assert plan.pressure is Pressure.FULL
    assert plan.head == ()
    assert plan.needs_summary is False


# --- pitfall 6: a no-op that is actually a no-op --------------------------


def test_a_quiet_turn_rebuilds_not_one_message():
    """Pitfall 6, assertion one: element identity.

    Not ``result is messages`` — the input is a ``Sequence`` and the
    output is a ``tuple``, so that can never hold and a test written
    that way would be testing nothing. Not ``==`` either, because an
    implementation that rebuilt every message with identical content
    satisfies it. The mutation this catches is
    ``dataclasses.replace(m, content=m.content)`` on the quiet path:
    same bytes, different objects.
    """
    messages = _history()
    budget = _budget_at(messages, 0.30)
    result, record, state = asyncio.run(compact(messages, budget, pinned=1))

    assert record.pressure is Pressure.NONE
    assert len(result) == len(messages)
    assert all(a is b for a, b in zip(result, messages))
    assert state is not None


def test_a_quiet_turn_leaves_the_assembled_prompt_byte_identical():
    """Pitfall 6, assertion two: the bytes the prefix cache pays for.

    Object identity is not what is billed. This is: the same sections
    and the same history render to the same string, before and after a
    compaction that decided to do nothing.
    """
    messages = _history()
    prompt = (
        PromptAssembler()
        .with_section(Section("persona", "", static("你是 OmicsClaw。")))
        .render()
    )
    budget = _budget_at(messages, 0.30)
    result, _, _ = asyncio.run(compact(messages, budget, pinned=1))

    before = assemble(prompt, messages, "next")
    after = assemble(prompt, result, "next")

    assert [m.content for m in before] == [m.content for m in after]
    assert [m.role for m in before] == [m.role for m in after]


def test_compaction_never_touches_the_callers_list():
    """Pitfall 5: the harness's issue #117 aliasing bug, in Python form."""
    messages = _history()
    budget = _budget_at(messages, 0.85)

    summarizer = _Canned()
    result, _, _ = asyncio.run(
        compact(messages, budget, summarizer=summarizer, pinned=1)
    )
    length = len(result)
    messages.append(Message.user("appended afterwards"))

    assert isinstance(result, tuple)
    assert len(result) == length


# --- the summary path -----------------------------------------------------


def test_a_successful_compaction_replaces_the_head_with_one_message():
    messages = _history()
    budget = _budget_at(messages, 0.85)
    summarizer = _Canned()

    result, record, state = asyncio.run(
        compact(messages, budget, summarizer=summarizer, pinned=1)
    )

    assert summarizer.calls == 1
    assert result[0] is messages[0]
    assert is_summary_message(result[1])
    assert result[2:] == tuple(messages[19:])
    assert record.degraded == ""
    assert state.summary == "three steps in"
    assert state.anchors.user_intent == "annotate the slide"


def test_a_compacted_conversation_fits_the_budget_it_was_compacted_for():
    """Task C acceptance 3, on the tier where it is load-bearing.

    Under ``EMERGENCY`` the conversation does *not* fit before the call,
    which is the only case where the input was over the line to begin
    with.

    The docstring here used to narrow the test to that tier with the
    argument that "at every lower tier the ratio is below one already
    and 'it fits afterwards' is free". It is free only if compaction
    cannot *increase* the token count, and it can — see
    :func:`test_a_summary_larger_than_what_it_replaced_is_a_failed_compaction`.
    Acceptance 3 is written without a tier condition, so the two tests
    below carry the other tiers.
    """
    messages = _history(turns=40)
    budget = _budget_at(messages, 1.8)

    assert estimate_messages_tokens(messages) > budget.usable_tokens

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1)
    )

    assert record.pressure is Pressure.EMERGENCY
    assert estimate_messages_tokens(result) <= budget.usable_tokens


def test_a_summary_larger_than_what_it_replaced_is_a_failed_compaction():
    """Task C acceptance 3 without its tier condition, which it never had.

    A summarization model handed a long conversation and a small budget
    has one classic degenerate output: it restates the input instead of
    compressing it. Nothing else in this function notices. The
    summarizer returned, the response parsed, anchors merged, the state
    advanced, ``summarized`` counted eighteen messages and ``degraded``
    was empty — while the conversation came back **twenty times larger**
    than it went in and the next request would be refused by the API.
    ``compression_ratio`` computed 20.89 and no line of code read it.

    The repair weighs the result against ``usable_tokens`` before
    returning. It is a *budget* check and not one of the six content
    gates decision 0 removed: it asks nothing about what the summary
    says, and the number it compares against is the one every tier in
    this package already divides by.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)
    bloated = _Canned(
        "## Anchors\n\n### User Intent\n" + "w" * 200_000 + "\n\n## Summary\nshort"
    )

    result, record, state = asyncio.run(
        compact(messages, budget, summarizer=bloated, pinned=1)
    )

    assert bloated.calls == 1, "the summarizer was asked, and answered"
    assert estimate_messages_tokens(result) <= budget.usable_tokens
    assert record.tokens_after <= budget.usable_tokens
    assert record.compression_ratio < 1.0
    assert "usable budget" in record.degraded
    assert record.summarized == 0
    assert record.summary_text == ""
    assert not any(is_summary_message(m) for m in result)
    assert state.summary == "", "an inflating round must not advance the state"


def test_an_emergency_that_still_does_not_fit_says_which_of_the_two_it_was():
    """Decision Q10 has a price and the record is where it is stated.

    The task anchor survives an emergency truncation unconditionally
    (``compaction.go:137-142``, and issue #117's 143 spinning turns are
    the reason), so a conversation whose *task message* is bigger than
    the whole budget comes back over the line however hard this tier
    truncates. That is the right trade. What is not right is recording
    it as an ordinary emergency: "I truncated" and "I truncated and it
    still does not fit" predict different things about the next request,
    and only the second one predicts a refusal.
    """
    budget = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )
    messages = [
        Message.system("sys"),
        Message.user("T" * 200_000),
        *[Message.user("x" * 400) for _ in range(8)],
    ]

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=None, pinned=1, min_tail=1)
    )

    assert record.pressure is Pressure.EMERGENCY
    assert estimate_messages_tokens(result) > budget.usable_tokens
    assert "emergency fallback: forced truncation" in record.degraded
    assert "still over usable_tokens" in record.degraded

    fitting = _history(turns=40)
    _, clean, _ = asyncio.run(
        compact(fitting, _budget_at(fitting, 1.8), summarizer=None, pinned=1)
    )
    assert clean.degraded == "emergency fallback: forced truncation", (
        "an emergency that did fit must not wear the extra reason"
    )


def test_the_anchors_of_an_earlier_compaction_are_carried_forward():
    """The incremental path, and why ``CompactionState`` is a return value.

    A summarizer that restates only one anchor must not erase the rest —
    that is :meth:`Anchors.merge`, exercised here through the public
    entry point rather than only in isolation.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)
    earlier = CompactionState(
        summary="the first round",
        anchors=Anchors(user_intent="original goal", next_steps="- keep going"),
    )
    summarizer = _Canned(
        "## Anchors\n\n### Next Steps\n- now do this\n\n## Summary\nround two"
    )

    _, record, state = asyncio.run(
        compact(messages, budget, summarizer=summarizer, state=earlier, pinned=1)
    )

    assert state.anchors.user_intent == "original goal"
    assert state.anchors.next_steps == "- now do this"
    assert record.anchors == state.anchors


def test_the_first_and_incremental_templates_are_chosen_by_the_state():
    """``progressive_compactor.go:406-415``."""
    messages = _history()
    plan = _plan(messages, 0.85)

    _, first = build_summary_prompt(plan, CompactionState())
    _, incremental = build_summary_prompt(
        plan,
        CompactionState(summary="earlier", anchors=Anchors(user_intent="goal")),
    )

    assert "<previous-compaction>" not in first
    assert "<previous-compaction>" in incremental
    assert "### User Intent\ngoal" in incremental
    assert "earlier" in incremental


def test_the_summary_prompt_carries_the_head_and_not_the_tail():
    """What the model is asked about is exactly what will disappear."""
    messages = _history()
    plan = _plan(messages, 0.85)

    _, user = build_summary_prompt(plan, CompactionState())

    assert "q0 " in user
    assert "q17 " in user
    assert "q18 " not in user, "the tail stays in the conversation verbatim"


def test_applying_a_plan_is_a_pure_function_of_the_plan():
    """``apply_compaction`` takes no budget, no state and no model.

    Which is what makes the interesting 90% of this module testable
    without an event loop anywhere in sight.
    """
    messages = _history()
    plan = _plan(messages, 0.85)

    once = apply_compaction(plan, summary="s", anchors=Anchors())
    twice = apply_compaction(plan, summary="s", anchors=Anchors())

    assert [m.content for m in once] == [m.content for m in twice]
    assert once[1].content.startswith(COMPACTION_MARKER)


def test_a_pass_through_does_not_repair_a_history_it_did_not_break():
    """The claim ``apply_compaction``'s docstring spends a paragraph on.

    A pass-through that ran the repair would not be a pass-through: it
    would rebuild a malformed history into a *different* one, and the
    quiet tiers have to be byte-identical or every calm turn costs a
    prompt-cache re-warm. Pitfall 6's element-identity test cannot see
    this — over a well-formed history the repair hands back the very
    same objects — so the input here is deliberately malformed: a tool
    result whose call is nowhere. A repair on this path would delete it.
    """
    messages = [
        Message.system("sys"),
        Message.tool(tool_call_id="never-called", content="stale"),
        *[Message.user(f"q{i}") for i in range(6)],
    ]
    budget = _budget_at(messages, 0.30)

    result, record, _ = asyncio.run(compact(messages, budget, pinned=1))

    assert record.pressure is Pressure.NONE
    assert len(result) == len(messages)
    assert all(a is b for a, b in zip(result, messages))
    assert any(m.tool_call_id == "never-called" for m in result), (
        "the quiet tiers hand the conversation back as it arrived, "
        "orphans and all"
    )


def test_an_emergency_repairs_the_tool_pairs_its_truncation_broke():
    """The tier that discards the most is the one most likely to cut a pair.

    ``EMERGENCY`` keeps the task anchor and then takes whatever else
    fits, newest first, skipping anything too large — which is exactly
    how an assistant turn keeps its ``tool_use`` while the oversized
    result answering it is dropped. Its repair pass
    (``apply_compaction``'s second branch) was the only one no test
    exercised: removing it left all 186 green.
    """
    budget = ContextBudget(
        context_tokens=400,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )
    messages = [
        Message.system("sys"),
        Message.user("the task"),
        Message.assistant("call", tool_calls=(ToolCall(id="c0", name="bash"),)),
        Message.tool(tool_call_id="c0", content="o" * 8_000),
        Message.user("after"),
    ]

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=None, pinned=1, min_tail=1)
    )

    assert record.pressure is Pressure.EMERGENCY
    assert not any(m.tool_call_id == "c0" and "o" * 100 in m.content for m in result)
    called = {c.id for m in result for c in m.tool_calls}
    answered = {m.tool_call_id for m in result if m.role is Role.TOOL}
    assert called == answered == {"c0"}, "the stranded call was answered"
    stand_in = next(m for m in result if m.role is Role.TOOL)
    assert stand_in.content == MISSING_TOOL_RESULT


def test_a_summary_never_lands_between_a_tool_call_and_its_answer():
    """Where ``apply_compaction`` puts the message it inserts.

    The pinned prefix may end mid-exchange — "system + one bootstrap
    assistant turn" is an ordinary way to pin, ``pinned`` is a public
    parameter with no upper bound, and decision Q8's whole ruling is
    that the caller declares it. When that last assistant turn asked for
    tools in parallel, the answers are the first thing in the tail, and
    dropping the compaction message in front of them produces
    ``assistant[tool_use c0, tool_use c1]`` / ``user[tool_result c0]`` /
    ``user[text]`` / ``user[tool_result c1]``: ``c1`` unanswered where
    the API insists it be answered.

    Both halves of the repair are checked here — the message goes behind
    the answers it would have split, and the encoded conversation is
    one the adapter would send.
    """
    from omicsclaw.provider.anthropic_provider import encode_conversation

    messages = [
        Message.system("sys"),
        Message.assistant(
            "two at once",
            tool_calls=(
                ToolCall(id="c0", name="bash"),
                ToolCall(id="c1", name="read_file"),
            ),
        ),
        Message.tool(tool_call_id="c0", content="o" * 300),
        Message.tool(tool_call_id="c1", content="p" * 300),
        *[Message.user(f"q{i} " + "x" * 300) for i in range(6)],
    ]
    budget = _budget_at(messages, 0.75)

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=2, min_tail=6)
    )

    assert record.pressure is Pressure.SOFT
    assert record.summarized > 0
    assert any("p" * 300 in m.content for m in result), (
        "the pinned prefix's own tool result was kept, not replaced by "
        "a placeholder"
    )

    def assert_answerable(conversation) -> None:
        _, turns = encode_conversation(conversation)
        for index, turn in enumerate(turns):
            asked = [b["id"] for b in turn["content"] if b.get("type") == "tool_use"]
            if not asked:
                continue
            following = turns[index + 1] if index + 1 < len(turns) else {"content": []}
            answered = [
                b["tool_use_id"]
                for b in following["content"]
                if b.get("type") == "tool_result"
            ]
            assert sorted(asked) == sorted(answered), (
                f"turn {index} asked for {asked}; the next turn answered "
                f"{answered}"
            )

    assert_answerable(result)

    # And again with the whole history read back as plain strings, which
    # is what a session row deserializes into. The seam this function
    # guards is decided by two role tests, and under ``is`` both stop
    # seeing anything.
    stored = [dataclasses.replace(m, role=str(m.role)) for m in messages]
    from_storage, record, _ = asyncio.run(
        compact(stored, budget, summarizer=_Canned(), pinned=2, min_tail=6)
    )

    assert record.summarized > 0
    assert any("p" * 300 in m.content for m in from_storage)
    assert_answerable(from_storage)


def test_the_summary_goes_behind_a_half_answered_prefix_too():
    """The other shape of the same seam, on ``apply_compaction`` directly.

    A pinned prefix can end *inside* an exchange as well as at the end
    of one: ``[system, assistant(c0, c1), tool(c0)]`` is a prefix that
    is still owed ``c1``. Finding that out means walking back over the
    answers already there and looking at the turn in front of them —
    the same adjacency reasoning ``repair_tool_pairs`` uses — and the
    two role tests that walk are the mutation surface. ``plan_compaction``
    cannot currently hand this shape over, because its head is
    contiguous with the prefix; ``apply_compaction`` is public, takes a
    plan from anyone, and documents itself as a pure function of one.
    """

    def plan_for(messages):
        return CompactionPlan(
            pressure=Pressure.FULL,
            pinned=tuple(messages[:3]),
            head=(Message.user("summarized away"),),
            tail=tuple(messages[3:]),
            needs_summary=True,
        )

    messages = [
        Message.system("sys"),
        Message.assistant(
            "two at once",
            tool_calls=(
                ToolCall(id="c0", name="bash"),
                ToolCall(id="c1", name="read_file"),
            ),
        ),
        Message.tool(tool_call_id="c0", content="first"),
        Message.tool(tool_call_id="c1", content="second"),
        Message.user("later"),
    ]

    for label, history in (
        ("as built", messages),
        (
            "read back from storage",
            [dataclasses.replace(m, role=str(m.role)) for m in messages],
        ),
    ):
        result = apply_compaction(plan_for(history), summary="s", anchors=Anchors())

        assert [str(m.role) for m in result] == [
            "system",
            "assistant",
            "tool",
            "tool",
            "user",
            "user",
        ], label
        assert [m.content for m in result[2:4]] == ["first", "second"], (
            f"{label}: the prefix's own answers were replaced by placeholders"
        )
        assert result[4].content.startswith(COMPACTION_MARKER), label


def test_a_compaction_repairs_the_tool_pairs_it_broke():
    """The head that vanished may have contained half of a pair.

    Whole-message compaction and the Anthropic pairing rule meet here,
    and the meeting has to happen *after* the cut rather than before it.
    """
    messages = [Message.system("sys"), Message.user("task")]
    for index in range(12):
        messages.append(
            Message.assistant(
                "calling", tool_calls=(ToolCall(id=f"c{index}", name="bash"),)
            )
        )
        messages.append(Message.tool(tool_call_id=f"c{index}", content="o" * 300))
    budget = _budget_at(messages, 0.85)

    summarizer = _Canned()
    result, _, _ = asyncio.run(
        compact(messages, budget, summarizer=summarizer, pinned=1)
    )

    called = {c.id for m in result for c in m.tool_calls}
    answered = {m.tool_call_id for m in result if m.role is Role.TOOL}
    assert called == answered


# --- decision Q8 ----------------------------------------------------------


def test_a_conversation_without_a_system_message_is_compacted_all_the_same():
    """Pitfall 8, through the public entry point.

    The harness returns the input untouched when message zero is not a
    system prompt. Copying that here would make the compactor a silent
    no-op for anything this repository's engine did not assemble — and
    the engine assembles nothing.
    """
    messages = [Message.user(f"q{i} " + "x" * 400) for i in range(24)]
    budget = _budget_at(messages, 0.85)

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=0)
    )

    assert record.summarized > 0
    assert len(result) < len(messages)


def test_pinning_nothing_in_front_of_a_system_prompt_is_reported():
    """Decision Q8's second mitigation: state the fact, change nothing.

    ``pinned=0`` is the only default that asserts nothing about the
    input, and the price is that a caller who forgets ``pinned=1`` finds
    its system prompt in the compactible head. This layer cannot correct
    that — guessing is the one thing Q8 forbids — so it says so.

    **Where it says so moved**, and this test moved with it. The note
    used to be joined into ``degraded`` beside the genuine failure
    reasons; the assertion below used to read ``"pinned=0" in
    said.degraded``. See
    :func:`test_an_advisory_is_not_a_failure_and_does_not_look_like_one`
    for what that cost.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)

    _, said, _ = asyncio.run(compact(messages, budget, summarizer=_Canned(), pinned=0))
    _, silent, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1)
    )

    assert any("pinned=0" in note for note in said.advisories)
    assert silent.advisories == ()
    assert silent.degraded == ""


def test_an_advisory_is_not_a_failure_and_does_not_look_like_one():
    """Plan 0030 §11.A's seam table, read forward into step 6.

    ``internal/engine/history.go:120-122`` is the write-back gate step 6
    has to port: *a record with an error is not written back unless the
    tier was* ``EMERGENCY``, so that a transient summarization failure
    is retried next turn instead of being frozen into the session. Port
    that against a ``degraded`` field that also carried advisories and
    it refuses to write back a compaction that did **exactly** what it
    was asked to — 11 messages to 7, 470 tokens to 108, a parsed
    summary, a clean anchors merge — because the caller forgot
    ``pinned=1``. The conversation is then re-compacted every single
    turn, at the price of one summarization each time, which is issue
    #117's failure with a different cause.

    So: ``degraded`` is failures, ``advisories`` is facts, and the
    mutation this rules out is putting them back in one string.
    """
    messages = _history(turns=10, size=200)
    budget = _budget_at(messages, 0.85)

    result, record, state = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=0)
    )

    assert record.summarized > 0, "this compaction succeeded on every measure"
    assert record.summary_text == "three steps in"
    assert record.tokens_after < record.tokens_before
    assert len(result) < len(messages)
    assert state.anchors.user_intent == "annotate the slide"
    assert record.advisories, "the pinned=0 fact is still reported"
    assert record.degraded == "", (
        "an advisory in `degraded` makes the step 6 write-back gate "
        "reject a compaction that worked"
    )


def test_an_advisory_survives_a_history_read_back_as_plain_strings():
    """The same ``==``-not-``is`` rule, on the one role test outside
    ``transcript.py``.

    Step 6 reads a history back out of a session row, and
    :class:`~omicsclaw.schema.Role` is a ``StrEnum`` so that survives.
    The ``pinned=0`` advisory exists for a caller who forgot
    ``pinned=1``, and a caller resuming a stored session is exactly that
    caller — so the one path where the note is most needed is the one
    where an identity test stops seeing the system prompt.
    """
    messages = [
        dataclasses.replace(Message.system("you are OmicsClaw"), role="system"),
        *[Message.user(f"q{i} " + "x" * 400) for i in range(24)],
    ]
    budget = _budget_at(messages, 0.85)

    _, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=0)
    )

    assert any("pinned=0" in note for note in record.advisories)


def test_nothing_compactible_is_reported_too():
    """Pitfall 11: the plan did nothing, and the record says why.

    Without this the caller sees a ``FULL`` pressure, an unchanged
    conversation and no explanation, and concludes the compactor is
    broken.
    """
    messages = _history(turns=4)
    budget = _budget_at(messages, 0.85)

    _, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1, min_tail=6)
    )

    assert record.advisories == (
        "nothing to compact: the pinned prefix and min_tail cover "
        "the whole conversation",
    )
    assert record.degraded == ""
    assert record.msgs_after == record.msgs_before


def test_the_nothing_to_compact_advisory_is_not_written_when_it_is_false():
    """An advisory nobody checks for truth is worse than no advisory.

    The condition used to be ``not plan.head``, and under ``SOFT`` the
    plan's head is *half* the compactible head. A conversation with
    exactly one compactible message therefore halved to nothing and the
    record announced that "the pinned prefix and min_tail cover the
    whole conversation" — with ``pinned + min_tail == 7`` against eight
    messages, and a compactible message sitting right there. The
    existing mutation that deleted the advisory outright was killed;
    nothing looked at whether the sentence was *true*.
    """
    messages = _history(turns=7, size=300)
    budget = _budget_at(messages, 0.75)

    _, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1, min_tail=6)
    )

    assert record.pressure is Pressure.SOFT
    assert len(messages) - 1 > 6, "there is a compactible message"
    assert not any("cover the whole conversation" in n for n in record.advisories)
    assert record.advisories == (
        "nothing to summarize: the soft tier compacts the older half of "
        "the head, and the head is a single message",
    )


# --- the record -----------------------------------------------------------


def test_every_field_of_the_record_says_something_true():
    """Task C acceptance 4: an audit field nobody reads is dead weight.

    ``FRAMEWORK-REBUILD.md``'s "stored, never read" category, caught
    here by reading all of them once in a case where each has a value
    that can be checked against something else.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1)
    )

    assert record.pressure is Pressure.FULL
    assert record.tokens_before == estimate_messages_tokens(messages)
    assert record.tokens_after == estimate_messages_tokens(result)
    assert record.tokens_after < record.tokens_before
    assert record.msgs_before == len(messages)
    assert record.msgs_after == len(result)
    assert record.summarized == 18
    assert record.preserved_tail == 6
    assert record.anchors.user_intent == "annotate the slide"
    assert record.summary_text == "three steps in"
    assert record.degraded == ""
    assert record.duration_s >= 0.0
    assert 0.0 < record.compression_ratio < 1.0


def test_the_duration_is_measured_rather_than_reported_as_zero():
    """Task C acceptance 4, on the one field a constant satisfies.

    ``assert record.duration_s >= 0.0`` is true of a stopwatch and true
    of ``0.0``, so it does not read the field at all. Almost all of a
    compaction's wall time is the summarizer's ``await``, which makes
    this measurable without a clock injection: a summarizer that sleeps
    puts a floor under the number that a constant cannot clear.
    """
    delay = 0.05

    class _Slow(_Canned):
        async def summarize(self, prompt: str, *, system: str) -> str:
            await asyncio.sleep(delay)
            return await super().summarize(prompt, system=system)

    messages = _history()
    budget = _budget_at(messages, 0.85)

    _, record, _ = asyncio.run(compact(messages, budget, summarizer=_Slow(), pinned=1))

    assert record.duration_s >= delay, (
        "the field is a stopwatch reading, and a constant cannot clear "
        "a summarizer that slept"
    )


def test_preserved_tail_counts_messages_that_arrived_and_nothing_else():
    """The one record field whose non-summary branch nothing ever read.

    Two mutations lived here. ``preserved_tail = len(plan.tail)``
    unconditionally passed, because the branch for degraded and quiet
    runs was never exercised. And the claim in the field's docstring —
    "original messages carried through verbatim" — was false on the
    repair paths, where the count included the placeholders
    :func:`repair_tool_pairs` had just invented.
    """
    messages = [
        Message.system("sys"),
        Message.user("the task"),
        Message.assistant("call", tool_calls=(ToolCall(id="c0", name="bash"),)),
        Message.tool(tool_call_id="c0", content="o" * 4_000),
        *[Message.user("x" * 300) for _ in range(4)],
    ]
    budget = ContextBudget(
        context_tokens=500,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=None, pinned=1, min_tail=2)
    )

    invented = [m for m in result if m.content == MISSING_TOOL_RESULT]
    assert invented, "this fixture strands a tool call on purpose"
    assert record.preserved_tail == len(result) - 1 - len(invented)
    assert record.preserved_tail == sum(
        1 for m in result[1:] if any(m is original for original in messages)
    )

    quiet = _history()
    _, calm, _ = asyncio.run(compact(quiet, _budget_at(quiet, 0.30), pinned=1))
    assert calm.preserved_tail == len(quiet) - 1


def test_the_whole_compaction_honours_an_injected_counter():
    """Task A acceptance 3, at the public entry points that spend it.

    :class:`~omicsclaw.context.tokens.TokenCounter` is the only seam
    through which this package accepts a number better than its own, so
    a deployment with a real tokenizer passes one in and believes the
    tier grading, the cut and the record are all computed from it.
    ``plan_compaction`` and ``compact`` each take ``counter=`` and each
    ignored it silently: under ``_Fixed`` this conversation costs 100
    tokens against a 1,000-token window and is quiet, while the built-in
    estimate makes the same conversation an emergency.
    """
    messages = _history()
    budget = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )

    assert plan_compaction(
        messages, budget, pinned=1, min_tail=6
    ).pressure is Pressure.EMERGENCY

    plan = plan_compaction(
        messages, budget, pinned=1, min_tail=6, counter=_Fixed()
    )
    assert plan.pressure is Pressure.NONE
    assert plan.head == ()

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Canned(), pinned=1, counter=_Fixed())
    )

    assert record.pressure is Pressure.NONE
    assert record.tokens_before == estimate_messages_tokens(
        messages, counter=_Fixed()
    )
    assert record.tokens_after == estimate_messages_tokens(result, counter=_Fixed())
    assert record.tokens_before < estimate_messages_tokens(messages)
    assert all(a is b for a, b in zip(result, messages))


def test_the_compression_ratio_of_an_empty_conversation_is_zero():
    """``:195-197`` guards the division; so does this, reachably."""
    empty = CompactionRecord(
        pressure=Pressure.NONE,
        tokens_before=0,
        tokens_after=0,
        msgs_before=0,
        msgs_after=0,
        summarized=0,
        preserved_tail=0,
    )

    assert empty.compression_ratio == 0.0


def test_the_record_is_a_frozen_value_anybody_may_keep():
    """Step 6 persists it; a mutable audit record is not evidence."""
    messages = _history()
    budget = _budget_at(messages, 0.30)
    _, record, _ = asyncio.run(compact(messages, budget, pinned=1))

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.degraded = "rewritten"  # type: ignore[misc]


def test_the_default_min_tail_is_the_harness_figure_and_is_declared():
    """Plan 0030 §9-8: a borrowed literal, named rather than inlined.

    The same author used 6 in ``compaction.go:87-92`` and 8 in his own
    benchmark (``runner.go:293-299``). Neither has been calibrated
    against this repository, where one tool result can be a whole
    analysis report, so the figure lives in one named place where a
    calibration can replace it.
    """
    assert DEFAULT_MIN_TAIL == 6

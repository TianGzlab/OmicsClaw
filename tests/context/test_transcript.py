"""Plan 0030 task C: the pure transforms, and the two Go lines that lie.

``repair_tool_pairs`` is where a literal port stops being merely
inelegant and becomes a *silent functional failure*: the repaired
history would look repaired, pass every assertion written about this
package, and still be refused by the API for the exact reason the
function exists. So the test that matters here reaches into
``omicsclaw.provider`` and asks the adapter — the exception pitfall 10
opens, for the one assertion that cannot be made from inside.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from omicsclaw.context.budget import ContextBudget
from omicsclaw.context.tokens import estimate_message_tokens, estimate_messages_tokens
from omicsclaw.context.transcript import (
    MISSING_TOOL_RESULT,
    _emergency_survivors,
    emergency_fit,
    fit_to_budget,
    render_for_summary,
    repair_tool_pairs,
    split_head_tail,
)
from omicsclaw.schema import Message, Role, ToolCall


class _Fixed:
    """A :class:`TokenCounter` answering one token per string.

    Useless as a tokenizer and perfect as a probe: under it a message
    costs a *count of fields*, which no built-in estimate of these
    fixtures ever produces, so any function that quietly dropped
    ``counter=`` on the floor grades the conversation differently.
    """

    def __init__(self) -> None:
        self.calls = 0

    def count_text(self, text: str) -> int:
        self.calls += 1
        return 1

_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "omicsclaw" / "context"


def _budget(usable: int) -> ContextBudget:
    return ContextBudget(
        context_tokens=usable,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )


def _turn(index: int, *, size: int = 400) -> list[Message]:
    """One assistant/tool round trip, correctly paired."""
    return [
        Message.assistant(
            "working", tool_calls=(ToolCall(id=f"c{index}", name="bash"),)
        ),
        Message.tool(tool_call_id=f"c{index}", content="o" * size),
    ]


# --- repair_tool_pairs ----------------------------------------------------


def test_a_tool_result_whose_call_was_compacted_away_is_dropped():
    """``compaction.go:221-223``, direction one."""
    messages = [
        Message.user("task"),
        Message.tool(tool_call_id="vanished", content="stale output"),
    ]

    repaired = repair_tool_pairs(messages)

    assert [m.role for m in repaired] == [Role.USER]


def test_a_tool_call_left_unanswered_gets_a_placeholder_result():
    """``compaction.go:226-236``, direction two.

    The placeholder goes directly after the call it answers, one per
    unanswered call, because a turn that requested three tools has to
    answer all three.
    """
    messages = [
        Message.assistant(
            "two at once",
            tool_calls=(
                ToolCall(id="a", name="bash"),
                ToolCall(id="b", name="read_file"),
            ),
        ),
        Message.user("and then"),
    ]

    repaired = repair_tool_pairs(messages)

    assert [m.role for m in repaired] == [
        Role.ASSISTANT,
        Role.TOOL,
        Role.TOOL,
        Role.USER,
    ]
    assert [m.tool_call_id for m in repaired[1:3]] == ["a", "b"]
    assert repaired[1].content == MISSING_TOOL_RESULT


def test_placeholders_appear_in_the_order_the_calls_were_requested():
    """Pitfall 7, the ``set`` source, in the one place this layer has one.

    ``repair_tool_pairs`` builds sets of ids to test membership against
    — and membership is all it does with them. Emitting placeholders by
    iterating one of those sets would order them by string hash, which
    varies between processes: the same compaction would produce
    different bytes on different runs and the prompt prefix would never
    cache. Six calls, because two could agree by luck.
    """
    ids = [f"c{index}" for index in range(6)]
    messages = [
        Message.assistant(
            "six at once",
            tool_calls=tuple(ToolCall(id=i, name="bash") for i in ids),
        )
    ]

    repaired = repair_tool_pairs(messages)

    assert [m.tool_call_id for m in repaired[1:]] == ids


def test_a_placeholder_is_a_tool_message_not_a_user_message():
    """Decision Q11, and the assertion is about **behaviour**.

    The harness builds ``Message{Role: RoleUser, ToolCallID: tc.ID}``
    because its schema has three roles. Translated literally that is
    ``Message(role=USER, tool_call_id=...)``, and
    ``anthropic_provider.py:271-290`` dispatches on role alone: the
    message encodes as an ordinary text turn, ``tool_call_id`` is
    dropped, and the unanswered ``tool_use`` block is still unanswered.
    A test asserting on the *role field* would be satisfied by a
    placeholder the adapter throws away, so this one asks the adapter
    what it made — which is why it imports from ``omicsclaw.provider``,
    under the exception pitfall 10 opens for exactly this.
    """
    from omicsclaw.provider.anthropic_provider import encode_conversation

    repaired = repair_tool_pairs(
        [Message.assistant("go", tool_calls=(ToolCall(id="a", name="bash"),))]
    )

    _, turns = encode_conversation(repaired)
    blocks = [block for turn in turns for block in turn["content"]]
    results = [b for b in blocks if b.get("type") == "tool_result"]

    assert len(results) == 1
    assert results[0]["tool_use_id"] == "a"
    assert results[0]["is_error"] is False, (
        "nothing failed — the history was compacted. Marking it an error "
        "teaches the model to retry a call that already succeeded"
    )


def test_a_well_formed_history_comes_back_message_for_message():
    """Repair is identity when there is nothing to repair.

    Which is what lets the low-pressure tiers stay byte-identical: a
    repair that rebuilt every message would churn the prompt prefix on
    every quiet turn.
    """
    messages = [Message.user("task"), *_turn(0)]

    repaired = repair_tool_pairs(messages)

    assert len(repaired) == len(messages)
    assert all(a is b for a, b in zip(repaired, messages))


def test_repair_hands_back_a_tuple_that_is_not_the_callers_list():
    """Pitfall 5: the harness's issue #117 was an aliasing bug."""
    messages = [Message.user("task")]

    repaired = repair_tool_pairs(messages)
    messages.append(Message.user("added later"))

    assert isinstance(repaired, tuple)
    assert len(repaired) == 1


def test_an_answer_that_is_not_adjacent_to_its_call_is_not_an_answer():
    """The repair's real rule, which a membership test cannot express.

    Anthropic requires every ``tool_use`` of an assistant turn to be
    answered in the **immediately following** user turn, and
    ``anthropic_provider.py:271-291`` flushes its batch of pending
    results the instant any other message interrupts them. A version of
    this function that built a set of answered ids and asked "is it
    somewhere in the list" calls the conversation below repaired, and
    the API calls it a 400.

    The shape is the one a compaction actually produces: an assistant
    turn asking for two tools in parallel, whose second answer ended up
    behind the message the compactor inserted.
    """
    call = Message.assistant(
        "two at once",
        tool_calls=(ToolCall(id="a", name="bash"), ToolCall(id="b", name="read_file")),
    )
    messages = [
        call,
        Message.tool(tool_call_id="a", content="first"),
        Message.user("[Context Compaction] ..."),
        Message.tool(tool_call_id="b", content="second"),
    ]

    repaired = repair_tool_pairs(messages)

    assert [m.role for m in repaired] == [
        Role.ASSISTANT,
        Role.TOOL,
        Role.TOOL,
        Role.USER,
    ]
    assert [m.tool_call_id for m in repaired[1:3]] == ["a", "b"]
    assert repaired[1].content == "first", "the adjacent answer is kept as it was"
    assert repaired[2].content == MISSING_TOOL_RESULT
    assert repaired[3].content.startswith("[Context Compaction]")


def test_the_adapter_agrees_that_the_repaired_conversation_is_answerable():
    """The same assertion made where it cannot be argued with (pitfall 10).

    ``repair_tool_pairs`` exists for one reason and this is it, so the
    check is the API's own rule read off the encoded turns: every
    ``tool_use`` id in an assistant turn appears as a ``tool_result`` in
    the turn straight after it, and no id is left over.
    """
    from omicsclaw.provider.anthropic_provider import encode_conversation

    messages = [
        Message.system("sys"),
        Message.assistant(
            "two at once",
            tool_calls=(
                ToolCall(id="a", name="bash"),
                ToolCall(id="b", name="read_file"),
            ),
        ),
        Message.tool(tool_call_id="a", content="first"),
        Message.user("something in between"),
        Message.tool(tool_call_id="b", content="second"),
    ]

    _, turns = encode_conversation(repair_tool_pairs(messages))

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
            f"turn {index} asked for {asked} and the next turn answered "
            f"{answered}; Anthropic refuses the request"
        )


def test_a_role_that_arrives_as_a_plain_string_is_still_a_role():
    """Decision Q11 spells the test ``==``, and it has to stay ``==``.

    :class:`~omicsclaw.schema.Message` is an unvalidated dataclass whose
    ``role`` is only annotated, and :class:`~omicsclaw.schema.Role` is a
    ``StrEnum`` so that a history deserialized out of a session row —
    step 6's whole job — keeps working. Both provider adapters are
    written that way deliberately
    (``anthropic_provider.py:272,276,281``, and
    ``openai_provider.py:140`` converts with ``str()`` first), and so is
    the Go this was ported from, which asks ``m.ToolCallID != ""`` and
    never looks at a role object's identity at all.

    Under ``is`` the failures are silent and there are three of them, so
    all three are here. A conversation whose roles are strings gets **no
    repair whatever**: a stranded call keeps no placeholder and an
    orphaned result is not dropped, which is this function returning its
    input and reporting success. And a conversation with *mixed* roles —
    a pinned prefix built in-process in front of a history read back
    from storage — gets one ``tool_use`` answered twice.
    """
    call = Message.assistant("go", tool_calls=(ToolCall(id="c0", name="bash"),))
    answer = Message.tool(tool_call_id="c0", content="output")
    orphan = Message.tool(tool_call_id="long gone", content="stale")

    def as_text(message: Message) -> Message:
        return dataclasses.replace(message, role=str(message.role))

    stranded = repair_tool_pairs([as_text(call), Message.user("and then")])
    assert [m.tool_call_id for m in stranded] == ["", "c0", ""], (
        "the stranded call went unanswered, which is the API 400"
    )
    assert stranded[1].content == MISSING_TOOL_RESULT

    cleaned = repair_tool_pairs([Message.user("task"), as_text(orphan)])
    assert len(cleaned) == 1, "the orphan was carried through, which is the other 400"

    mixed = repair_tool_pairs([call, as_text(answer)])
    assert len(mixed) == 2, "one tool_use answered twice is the mixed-role form"
    assert mixed[1].content == "output"

    assert render_for_summary([as_text(call), as_text(answer)]).split("\n") == [
        "[assistant]: go",
        "[tool_call bash(c0)]: {}",
        "[tool_result c0]: output",
    ]


def test_a_stale_tool_result_is_dropped_whatever_its_id_matches():
    """Direction one, restated for the adjacency rule.

    An id that matches *some* call in the conversation is not a licence
    to keep the message where it is: the call it answers is three turns
    back and the API looks in one place only.
    """
    messages = [
        Message.assistant("go", tool_calls=(ToolCall(id="c0", name="bash"),)),
        Message.tool(tool_call_id="c0", content="the real answer"),
        Message.user("later"),
        Message.tool(tool_call_id="c0", content="a duplicate, out of place"),
    ]

    repaired = repair_tool_pairs(messages)

    assert [m.role for m in repaired] == [Role.ASSISTANT, Role.TOOL, Role.USER]
    assert repaired[1].content == "the real answer"


def test_the_placeholder_says_what_happened_rather_than_nothing():
    """Pitfall 18's neighbour: the placeholder's *content* is the point.

    Every other assertion about it compares against
    :data:`MISSING_TOOL_RESULT` itself, so emptying the constant leaves
    them all green while the model is handed a blank tool result and no
    explanation — and a blank result reads as "the tool returned
    nothing", which is a different and wrong thing to believe.
    """
    assert MISSING_TOOL_RESULT
    assert "compact" in MISSING_TOOL_RESULT.lower()

    repaired = repair_tool_pairs(
        [Message.assistant("go", tool_calls=(ToolCall(id="a", name="bash"),))]
    )

    assert repaired[1].content == MISSING_TOOL_RESULT
    assert repaired[1].content.strip(), "a silent placeholder explains nothing"
    assert repaired[1].is_error is False


# --- split_head_tail ------------------------------------------------------


def test_the_pinned_prefix_and_the_tail_are_both_untouchable():
    messages = [Message.user(f"m{i}") for i in range(10)]

    pinned, head, tail = split_head_tail(messages, pinned=1, min_tail=3)

    assert pinned == (messages[0],)
    assert head == tuple(messages[1:7])
    assert tail == tuple(messages[7:])


def test_nothing_is_compactible_when_pinned_and_min_tail_cover_everything():
    """Pitfall 11: a state the harness cannot reach and this one can.

    It hardcodes a pinned prefix of one, so ``1 + min_tail >
    len(msgs)`` is its only overflow. With ``pinned`` a parameter the
    sum can exceed the conversation from either side, and the defined
    behaviour is the harness's: no head, so the caller skips the tier
    rather than compacting something already minimal
    (``progressive_compactor.go:240-242``).
    """
    messages = [Message.user(f"m{i}") for i in range(4)]

    pinned, head, tail = split_head_tail(messages, pinned=2, min_tail=6)

    assert head == ()
    assert pinned + tail == tuple(messages)

    over, over_head, over_tail = split_head_tail(messages, pinned=99, min_tail=1)

    assert over_head == ()
    assert over == tuple(messages)
    assert over_tail == ()


def test_a_min_tail_of_zero_means_zero_and_not_the_default():
    """Pitfall 15: Go's zero-value fallbacks are not logic to port.

    ``compaction.go:181-193`` has ``maxTokens()`` and ``minTail()``
    getters that substitute a default whenever the field is ``<= 0``,
    because in Go an unset field *is* zero and the two cannot be told
    apart. Python has keyword defaults, so a caller who passes ``0``
    means zero — and a getter re-reading the default would be an
    unreachable branch the day it was written, which is precisely the
    "dead code ported from Go" category.
    """
    messages = [Message.user(f"m{i}") for i in range(10)]

    _, head, tail = split_head_tail(messages, pinned=0, min_tail=0)

    assert tail == ()
    assert head == tuple(messages)


def test_the_min_tail_boundary_is_checked_on_both_sides():
    """Pitfall 2 on ``split_head_tail``'s one structural guard.

    ``len(rest) <= min_tail`` means "already minimal, there is nothing
    to compact" (``progressive_compactor.go:240-242``). One below the
    boundary is where writing it ``<`` shows: ``head_end`` goes negative
    and ``rest[:head_end]`` silently becomes "all but the last few",
    handing the caller a head to summarize out of a conversation the
    guard exists to leave alone.

    Exactly *on* the boundary the two spellings agree — ``head_end`` is
    zero and both slices come out empty — so this test names the value
    below it as well, and that is the one that kills the mutation.
    """
    messages = [Message.user(f"m{i}") for i in range(10)]

    _, at_boundary, tail_at = split_head_tail(messages[:6], pinned=0, min_tail=6)
    assert at_boundary == ()
    assert tail_at == tuple(messages[:6])

    _, below, tail_below = split_head_tail(messages[:4], pinned=0, min_tail=6)
    assert below == (), "a shorter conversation has no compactible head at all"
    assert tail_below == tuple(messages[:4])

    _, above, tail_above = split_head_tail(messages[:7], pinned=0, min_tail=6)
    assert above == (messages[0],), "one over the boundary is one compactible message"
    assert tail_above == tuple(messages[1:7])

    # And the record of what the boundary is *not*: writing the guard
    # ``<`` rather than ``<=`` changes nothing at all. At ``len(rest) ==
    # min_tail`` the arithmetic path computes ``head_end = 0`` and hands
    # back the same empty head and the same whole tail the early return
    # does, and below the boundary the negative ``head_end`` slices
    # ``rest[:negative]`` and ``rest[negative:]`` back into the identical
    # pair. Checked exhaustively for every ``(len, pinned, min_tail)``
    # under 30: no input separates them. It is an equivalent mutant, and
    # saying so is worth more than a test that pretends to kill it.


def test_a_conversation_with_no_system_message_is_split_all_the_same():
    """Decision Q8 and pitfall 8, at the level where the choice is made.

    Every compactor in the harness returns the input untouched when
    message zero is not a system prompt, which is safe there because its
    engine injects one on every load. This project's engine injects
    nothing, so the same precondition would make the compactor a silent
    no-op — something that resolves, is never read, and never goes red.
    """
    messages = [Message.user(f"m{i}") for i in range(10)]

    _, head, tail = split_head_tail(messages, pinned=0, min_tail=2)

    assert head == tuple(messages[:8])
    assert tail == tuple(messages[8:])


# --- fit_to_budget --------------------------------------------------------


def test_a_history_that_already_fits_is_returned_unchanged():
    messages = [Message.user("short"), *_turn(0, size=4)]

    result = fit_to_budget(messages, _budget(10_000), pinned=1, min_tail=2)

    assert all(a is b for a, b in zip(result, messages))
    assert len(result) == len(messages)


def test_a_history_that_fits_exactly_is_still_a_history_that_fits():
    """Pitfall 2 on the other comparison: ``<=`` written ``<``.

    A conversation whose estimate lands exactly on ``usable_tokens``
    fits — the budget already holds back an output reserve, a tool
    reserve and a safety fraction, so the boundary is not a cliff edge
    to back away from. Spelled ``<``, this call peels the oldest message
    off a conversation that was inside its budget and pays a prompt
    prefix re-warm for nothing, and no mid-range value moves.

    The conversation carries an orphaned tool result on purpose. Over a
    well-formed history the repaired candidate is object-for-object the
    input, so "returned early" and "rebuilt and found it already fits"
    are indistinguishable and the mutation hides. The orphan is the
    difference: the early return keeps it, the rebuild deletes it.
    """
    messages = [
        Message.system("sys"),
        Message.tool(tool_call_id="never-called", content="x" * 400),
        *[Message.user("x" * 400) for _ in range(5)],
    ]
    exact = estimate_messages_tokens(messages)

    on_the_line = fit_to_budget(messages, _budget(exact), pinned=1, min_tail=2)
    one_short = fit_to_budget(messages, _budget(exact - 1), pinned=1, min_tail=2)

    assert len(on_the_line) == len(messages)
    assert all(a is b for a, b in zip(on_the_line, messages))
    assert any(m.tool_call_id == "never-called" for m in on_the_line), (
        "a conversation that fits is handed back, not rebuilt"
    )
    assert len(one_short) < len(messages), "one token over and it must trim"


def test_fit_to_budget_trims_against_an_explicit_target_when_given_one():
    """The parameter that makes the degradation path a degradation.

    ``compact`` hands a target one declared tier below the tier that
    fired, because a fallback aimed at the same ``usable_tokens`` the
    tier was graded against provably removes nothing — see
    ``test_summary_gates.py``. Here it is on its own: the same
    conversation, the same budget, two targets, two answers.
    """
    messages = [Message.system("sys"), *[Message.user("x" * 400) for _ in range(9)]]
    budget = _budget(estimate_messages_tokens(messages))

    untouched = fit_to_budget(messages, budget, pinned=1, min_tail=2)
    trimmed = fit_to_budget(
        messages,
        budget,
        pinned=1,
        min_tail=2,
        target_tokens=int(budget.usable_tokens * budget.soft_at),
    )

    assert len(untouched) == len(messages)
    assert len(trimmed) < len(messages)
    assert estimate_messages_tokens(trimmed) <= int(
        budget.usable_tokens * budget.soft_at
    )
    assert trimmed[0] is messages[0]


def test_the_oldest_compactible_message_goes_first_and_one_at_a_time():
    """``compaction.go:117-125``: peel, do not jump to a fixed window.

    The result keeps as much history as the budget allows, so the test
    asserts both halves — it fits, *and* it did not throw away more than
    it had to.
    """
    messages = [Message.system("sys")]
    for index in range(8):
        messages.extend(_turn(index))
    budget = _budget(900)

    result = fit_to_budget(messages, budget, pinned=1, min_tail=4)

    assert estimate_messages_tokens(result) <= budget.usable_tokens
    assert result[0] is messages[0]
    assert len(result) > 5, "peeling one at a time keeps more than the tail"


def test_a_conversation_with_no_system_message_is_still_compacted():
    """Pitfall 8, at the level where the damage would show.

    The mutation this rules out is the harness's precondition: "message
    zero must be a system prompt, otherwise return the input". Under it
    this assertion fails and nothing else in the suite moves.
    """
    messages = [Message.user("the task"), *[Message.user("x" * 400)] * 12]
    budget = _budget(500)

    result = fit_to_budget(messages, budget, pinned=0, min_tail=2)

    assert len(result) < len(messages)
    assert estimate_messages_tokens(result) <= budget.usable_tokens


def test_peeling_the_head_strands_a_tool_call_and_the_repair_papers_over_it():
    """The cost of dropping block-aware trimming, made visible.

    The replaced layer never separated an assistant turn from the tool
    results answering it. The harness peels first and repairs after, and
    that is what this layer does: here the 2,000-character tool result
    is peeled off while the call that asked for it survives, so the
    output the model had is **gone** and what it sees instead is a
    placeholder saying so. The old cut would have kept it. This is the
    accepted price, not an accident.
    """
    messages = [
        Message.system("sys"),
        Message.assistant("call", tool_calls=(ToolCall(id="c0", name="bash"),)),
        Message.tool(tool_call_id="c0", content="o" * 2_000),
        *[Message.user("x" * 200) for _ in range(6)],
    ]
    budget = _budget(400)

    result = fit_to_budget(messages, budget, pinned=1, min_tail=3)

    assert estimate_messages_tokens(result) <= budget.usable_tokens
    assert not any("o" * 100 in m.content for m in result), "the output is lost"
    stand_ins = [m for m in result if m.role is Role.TOOL]
    assert [m.content for m in stand_ins] == [MISSING_TOOL_RESULT]
    assert [c.id for m in result for c in m.tool_calls] == ["c0"]


# --- emergency_fit --------------------------------------------------------


def test_the_task_survives_an_emergency_and_a_giant_message_does_not():
    """Decision Q10 and pitfall 9, both halves of ``compaction.go:
    137-142``.

    The comment there is a measurement, not an argument: dropping the
    task left the model with no goal and it span for 143 consecutive
    emergency turns before the task failed. The second half is why a
    message that does not fit is *skipped* rather than shortened — one
    enormous tool result would otherwise fill the emergency view by
    itself and push the task back out of it.

    **The giant is a plain user turn**, and that is the repair to this
    test rather than a detail of it. It used to be a tool result, and a
    truncating implementation passed: it emitted a shortened 748-character
    ``G`` message, which :func:`repair_tool_pairs` then deleted as an
    orphan, so the assertion below went green for a reason that had
    nothing to do with truncation. A message that takes no part in tool
    pairing has no second line of defence, so a truncation survives to
    be seen.
    """
    task = Message.user("annotate the Visium slide")
    giant = Message.user("G" * 20_000)
    messages = [
        Message.system("sys"),
        task,
        giant,
        Message.user("small one"),
        Message.user("smaller"),
    ]
    budget = _budget(200)

    result = emergency_fit(messages, budget, pinned=1)

    assert result[0] is messages[0]
    assert task in result, "the task anchor is unconditional"
    assert giant not in result
    assert Message.user("smaller") in result, (
        "a message that does not fit is skipped, so later smaller ones "
        "still get their chance"
    )
    assert not any("G" * 100 in m.content for m in result), (
        "skipped whole, never truncated"
    )
    assert all(m in messages for m in result), (
        "every survivor is a message that went in, not an edited copy"
    )


def test_the_survivors_of_an_emergency_are_the_input_messages_themselves():
    """The same property asserted where the repair cannot mask it.

    :func:`_emergency_survivors` is what
    ``plan_compaction`` puts into a plan, so this reads it directly:
    element identity against the input, which no shortening
    implementation can produce.
    """
    kept = (Message.system("sys"),)
    rest = (
        Message.user("the task"),
        Message.user("G" * 20_000),
        Message.user("small"),
    )

    survivors = _emergency_survivors(kept, rest, _budget(200), None)

    assert survivors[0] is rest[0]
    assert all(any(s is m for m in rest) for s in survivors)
    assert rest[1] not in survivors


def test_an_emergency_with_no_pinned_prefix_keeps_the_first_message():
    """``pinned=0`` still has a task anchor — it is just message zero."""
    task = Message.user("the task")
    messages = [task, *[Message.user("y" * 4_000) for _ in range(4)]]

    result = emergency_fit(messages, _budget(100), pinned=0)

    assert result[0] is task


def test_an_emergency_protects_the_prefix_it_was_told_to_protect():
    """``pinned`` is on this function, and ignoring it is invisible.

    Plan 0030 §3.2 left the parameter off and the docstring says why it
    came back: without it :func:`~omicsclaw.context.compaction.compact`
    could not honour its own ``pinned`` on the one path that discards
    the most. An implementation that accepted the argument and treated
    everything as compactible still returns a plausible conversation —
    it just returns one where the protected prefix competed for room
    against the recent messages and lost.

    Which is why the pinned prefix here is **expensive** and the recent
    messages are cheap and numerous. With a small prefix every
    arrangement keeps everything and the parameter cannot be seen to
    matter; with this one, greedy newest-first spends the budget before
    it reaches the prefix and drops it.
    """
    messages = [
        Message.system("s" * 1_600),
        Message.user("p" * 1_600),
        Message.user("the task"),
        *[Message.user(f"recent {i} " + "z" * 180) for i in range(10)],
    ]

    result = emergency_fit(messages, _budget(1_000), pinned=2)

    assert result[0] is messages[0]
    assert result[1] is messages[1], "the pinned prefix does not compete for room"
    assert result[2] is messages[2], "the anchor is the first *unpinned* message"
    assert len(result) > 3, "and the newest messages still get what is left"


def test_every_transform_honours_an_injected_counter():
    """Task A acceptance 3, on the functions that decide what to drop.

    :class:`~omicsclaw.context.tokens.TokenCounter` is the one seam
    through which this package accepts a better number than it can
    compute, and a deployment that installs a real tokenizer and passes
    it in believes the whole layer is working from exact figures. A
    function that takes ``counter=`` and never forwards it keeps
    grading, cutting and truncating by the uncalibrated estimate, and
    the only visible symptom is a budget that behaves differently from
    the one the caller measured.

    Under ``_Fixed`` every string is worth one token, so a message of
    400 characters costs four instead of a hundred and these budgets
    hold several of them — while under the built-in estimate they hold
    the system prompt and nothing else. Every assertion below is
    therefore a claim the estimate cannot also satisfy.

    ``fit_to_budget`` reads the count in two places — the "does it
    already fit" shortcut and the peeling loop — and they are checked
    separately, because each one alone falls through to an answer the
    other produces anyway.
    """
    messages = [Message.system("sys"), *[Message.user("x" * 400) for _ in range(9)]]

    # The shortcut, and it needs an orphan to be visible: over a
    # well-formed history "returned early" and "rebuilt and found it
    # already fits" produce the same objects, so the repair pass at the
    # end of the loop is what tells them apart.
    shortcut = [
        Message.system("sys"),
        Message.tool(tool_call_id="never-called", content="x" * 400),
        Message.user("x" * 400),
        Message.user("x" * 400),
    ]
    counter = _Fixed()
    whole = fit_to_budget(shortcut, _budget(16), pinned=1, min_tail=1, counter=counter)
    assert counter.calls, "the counter was never consulted"
    assert len(whole) == len(shortcut), (
        "16 tokens by the injected count and 401 by the estimate: the "
        "shortcut has to read the injected one"
    )
    assert all(a is b for a, b in zip(whole, shortcut))
    assert len(fit_to_budget(shortcut, _budget(16), pinned=1, min_tail=1)) == 2

    partial = fit_to_budget(
        messages, _budget(20), pinned=1, min_tail=1, counter=_Fixed()
    )
    assert len(partial) == 5, (
        "the peeling loop keeps as much as the injected count allows; "
        "under the estimate nothing fits and only the tail survives"
    )
    assert len(fit_to_budget(messages, _budget(20), pinned=1, min_tail=1)) == 2

    fitted = fit_to_budget(messages, _budget(8), pinned=1, min_tail=1, counter=_Fixed())
    assert estimate_messages_tokens(fitted, counter=_Fixed()) <= 8
    assert estimate_messages_tokens(fitted) > 8, (
        "under the built-in estimate this result does not fit, which is "
        "what proves the injected counter did the deciding"
    )

    roomier = _budget(16)
    survivors = _emergency_survivors(
        (messages[0],), tuple(messages[1:]), roomier, _Fixed()
    )
    assert len(survivors) == 3, "the built-in estimate would keep the anchor alone"
    assert (
        sum(estimate_message_tokens(m, counter=_Fixed()) for m in survivors)
        <= roomier.usable_tokens
    )
    assert (
        len(_emergency_survivors((messages[0],), tuple(messages[1:]), roomier, None))
        == 1
    )

    truncated = emergency_fit(messages, roomier, pinned=1, counter=_Fixed())
    assert len(truncated) == 1 + len(survivors)


# --- render_for_summary ---------------------------------------------------


def test_the_summary_material_is_rendered_line_for_line_as_the_harness_does():
    """``progressive_compactor.go:391-404``, ported literally.

    The three shapes and their order matter: a tool result contributes
    its one line and nothing else, any other message contributes its
    content when it has some and then one line per tool call. The
    mutation this rules out is the replaced layer's prose form,
    ``[called tools: a, b]``.
    """
    messages = [
        Message.user("please read it"),
        Message.assistant(
            "on it",
            tool_calls=(
                ToolCall(id="c1", name="read_file", arguments='{"path":"a.h5ad"}'),
            ),
        ),
        Message.tool(tool_call_id="c1", content="200 lines"),
        Message.assistant("", tool_calls=(ToolCall(id="c2", name="bash"),)),
    ]

    assert render_for_summary(messages).split("\n") == [
        "[user]: please read it",
        "[assistant]: on it",
        '[tool_call read_file(c1)]: {"path":"a.h5ad"}',
        "[tool_result c1]: 200 lines",
        "[tool_call bash(c2)]: {}",
    ]


def test_the_renderer_never_truncates_anything():
    """Pitfall 18. Size is solved by dropping whole messages, not by
    a renderer deciding how much of a tool result matters.

    The harness does not truncate here either, and the 70/30 split the
    replaced layer used had all three of its call sites deleted along
    with the paths that used them.

    All three of the renderer's branches are checked, because a
    truncation added to one of them is a truncation: a test that only
    looked at tool results would miss a ``[:2000]`` on the line that
    renders what the user said.
    """
    enormous = "z" * 50_000
    payload = '{"text": "' + "a" * 50_000 + '"}'

    result = render_for_summary([Message.tool(tool_call_id="c", content=enormous)])
    spoken = render_for_summary([Message.user(enormous)])
    called = render_for_summary(
        [
            Message.assistant(
                enormous,
                tool_calls=(ToolCall(id="c", name="edit_file", arguments=payload),),
            )
        ]
    )

    assert result == f"[tool_result c]: {enormous}"
    assert spoken == f"[user]: {enormous}"
    assert called == f"[assistant]: {enormous}\n[tool_call edit_file(c)]: {payload}"


def test_tool_call_arguments_are_rendered_whole_and_unparsed():
    """Pitfall 17: ``arguments`` is byte-exact everywhere, including here.

    ADR 0077 keeps it as the unparsed JSON text the model emitted
    because prompt-prefix caching and replay evidence both read those
    bytes. A ``[:200]`` anywhere in this package is the mutation.
    """
    payload = '{"path": "' + "p" * 5_000 + '", "spaced" :   1}'
    message = Message.assistant(
        "", tool_calls=(ToolCall(id="c", name="edit_file", arguments=payload),)
    )

    assert render_for_summary([message]) == f"[tool_call edit_file(c)]: {payload}"


def test_compaction_never_rewrites_a_surviving_tool_call():
    """Pitfall 17, on the messages rather than on the rendering.

    A truncated argument payload is an *invalid* one, so the model is
    handed something it cannot use and retries it forever; if a
    compaction were persisted in the same turn, it would be invalid
    permanently.
    """
    payload = '{"path": "' + "p" * 400 + '"}'
    call = ToolCall(id="c0", name="edit_file", arguments=payload)
    messages = [
        Message.system("sys"),
        *[Message.user("x" * 400) for _ in range(6)],
        Message.assistant("last", tool_calls=(call,)),
        Message.tool(tool_call_id="c0", content="ok"),
    ]

    result = fit_to_budget(messages, _budget(400), pinned=1, min_tail=2)

    survivors = [c for m in result for c in m.tool_calls]
    assert survivors == [call]
    assert survivors[0].arguments == payload


def test_this_package_has_exactly_one_renderer_of_messages_to_text():
    """Pitfall 20, as a structural rule the source has to keep obeying.

    One renderer, and its output goes to the summarizer and never back
    into the model's own view. That is the whole reason it can be plain
    prose: prose the model reads triggers few-shot imitation — it starts
    narrating tool calls instead of making them — which is why the
    replaced layer rendered them as ``<prior-tool-calls/>``. A second
    renderer would be somebody quietly restoring the template-summary
    path, and this test is what notices.

    **The predicate is deliberately loose about spelling**, because the
    first version was not and could be stepped around without trying:
    it asked for ``Sequence`` *and* ``Message`` in an argument
    annotation and for a return annotated exactly ``str``, so
    ``list[Message] -> str`` and ``Sequence[Message] -> str | None``
    were both invisible to it. A structural guard that a rename defeats
    is a guard that will be defeated by accident. It also walks the
    whole tree rather than the module body, so a renderer parked inside
    a class or a factory is not a hiding place.
    """
    renderers: list[str] = []

    for path in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            returns = ast.unparse(node.returns) if node.returns else ""
            arguments = (
                node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            )
            takes_messages = any(
                arg.annotation is not None
                and "Message" in ast.unparse(arg.annotation)
                for arg in arguments
            )
            if "str" in returns and takes_messages:
                renderers.append(f"{path.name}:{node.name}")

    assert renderers == ["transcript.py:render_for_summary"]


def test_every_returned_sequence_is_a_tuple():
    """Pitfall 5, swept across the module rather than function by function."""
    messages = [Message.user("task"), *_turn(0)]
    budget = _budget(10_000)

    assert isinstance(repair_tool_pairs(messages), tuple)
    assert isinstance(fit_to_budget(messages, budget, min_tail=1), tuple)
    assert isinstance(emergency_fit(messages, budget), tuple)
    parts = split_head_tail(messages, pinned=0, min_tail=1)
    assert all(isinstance(part, tuple) for part in parts)


@pytest.mark.parametrize(
    "call",
    [
        lambda b: repair_tool_pairs([]),
        lambda b: fit_to_budget([], b, min_tail=1),
        lambda b: emergency_fit([], b),
    ],
    ids=["repair", "fit", "emergency"],
)
def test_an_empty_conversation_is_not_a_crash(call):
    assert call(_budget(100)) == ()

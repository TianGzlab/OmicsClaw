"""Plan 0030 task B: one system prompt, and the bytes of it.

Two properties carry this file. **Exactly one system message** (decision
Q5), because the two adapters disagree about several and a prompt that
means different things on different backends is not one prompt. And
**byte stability** (pitfall 7), because the prefix cache pays by the
byte: this package can no longer promise that the prompt rarely changes
— the owner's 2026-09-18 ruling put the volatile blocks into it — but it
can still promise that identical input renders identically.

``test_the_cache_breakpoint_lands_on_message_zero`` reaches across into
``omicsclaw.provider``. That is deliberate and is the exception pitfall
10 opens: the assertion is about what an adapter *does* with this
layer's output, so it cannot be made without naming the adapter, and a
test naming it is not a module naming it — the layering guard reads
``omicsclaw/context/``, not ``tests/``.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from omicsclaw.context.prompt import AssembledPrompt, PromptAssembler, assemble
from omicsclaw.context.sections import Section, static
from omicsclaw.context.tokens import estimate_text_tokens
from omicsclaw.schema import Message, Role, ToolCall

_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "omicsclaw" / "context"


def _counting_source(text: str) -> tuple[object, list[int]]:
    calls: list[int] = []

    def source() -> str:
        calls.append(1)
        return text

    return source, calls


def _three_sections() -> PromptAssembler:
    return (
        PromptAssembler()
        .with_section(Section("persona", "", static("你是 OmicsClaw。")))
        .with_section(Section("project", "## Project", static("Keep it short.")))
        .with_section(Section("skills", "## Skills", static("- spatial-de")))
    )


def test_assemble_emits_exactly_one_system_message_and_puts_it_first():
    """Decision Q5, and it is a property of :func:`assemble`, not of render.

    ``anthropic_provider.py:262-290`` joins every system message into
    one block; ``openai_provider.py:123-169`` passes each through
    separately. A prompt built one-message-per-section would therefore
    reach Claude as one block and OpenAI as three entries — two
    different prompts from one assembler.
    """
    history = [Message.user("earlier"), Message.assistant("answer")]

    conversation = assemble(_three_sections().render(), history, "现在呢")

    systems = [m for m in conversation if m.role is Role.SYSTEM]
    assert len(systems) == 1
    assert conversation[0] is systems[0]
    assert "你是 OmicsClaw。" in systems[0].content
    assert "## Skills" in systems[0].content


def test_an_empty_section_takes_its_heading_with_it():
    """``builder.go:113,179``; ``builder_test.go:105-111``.

    A bare ``## Long-term memory`` over nothing does not read as "there
    is none" — it reads as an instruction to the model about a section
    that exists and is empty.
    """
    prompt = (
        PromptAssembler()
        .with_section(Section("kept", "## Kept", static("body")))
        .with_section(Section("blank", "## Long-term memory", static("")))
        .render()
    )

    assert [key for key, _ in prompt.section_stats] == ["kept"]
    assert "Long-term memory" not in prompt.system_prompt


def test_a_disabled_section_is_skipped_without_being_removed():
    prompt = (
        PromptAssembler()
        .with_section(Section("a", "", static("kept")))
        .with_section(Section("b", "", static("hidden"), enabled=False))
        .render()
    )

    assert prompt.system_prompt == "kept"


def test_without_drops_a_section_by_key_and_leaves_the_rest_in_order():
    assembler = _three_sections().without("project")

    assert [s.key for s in assembler.sections] == ["persona", "skills"]
    untouched = _three_sections().without("absent")
    assert [s.key for s in untouched.sections] == ["persona", "project", "skills"]


def test_rendering_twice_produces_identical_bytes():
    """Pitfall 7. The prefix cache pays by the byte, not by the object."""
    assembler = _three_sections()

    assert assembler.render().system_prompt == assembler.render().system_prompt


def test_changing_one_section_leaves_every_other_byte_alone():
    """Pitfall 7 again, and the shape Q5b left behind.

    The replaced layer kept volatile text out of the system prompt
    entirely; that split is gone, so what is still defensible is that a
    change is *local* — one block's bytes move and the separators and
    neighbours do not. An implementation whose separator varied with the
    number of sections, or which re-wrapped the whole prompt on every
    render, would fail here and pass everything else in this file.
    """
    before = _three_sections().render().system_prompt
    after = (
        PromptAssembler()
        .with_section(Section("persona", "", static("你是 OmicsClaw。")))
        .with_section(Section("project", "## Project", static("Keep it short.")))
        .with_section(Section("skills", "## Skills", static("- spatial-deconv")))
        .render()
        .system_prompt
    )

    head_before, _, tail_before = before.rpartition("- spatial-de")
    head_after, _, tail_after = after.rpartition("- spatial-deconv")

    assert head_before == head_after
    assert tail_before == tail_after == ""
    assert before.count("\n\n") == after.count("\n\n")


def test_arrival_order_is_render_order():
    """The ``(order, key)`` sort is gone; ``with_section`` appends.

    Determinism does not suffer — arrival order is as determined as a
    sort key — but the responsibility moved to the composition root,
    which now has no way to correct a mistake after the fact.
    """
    forwards = (
        PromptAssembler()
        .with_section(Section("a", "", static("first")))
        .with_section(Section("b", "", static("second")))
        .render()
    )
    backwards = (
        PromptAssembler()
        .with_section(Section("b", "", static("second")))
        .with_section(Section("a", "", static("first")))
        .render()
    )

    assert forwards.system_prompt == "first\n\nsecond"
    assert backwards.system_prompt == "second\n\nfirst"


def test_every_source_is_called_on_every_render():
    """``builder.go:56-59``, generalised to every section.

    A snapshot taken when the assembler was built would mean a
    ``memory_write`` from this turn is invisible until the process
    restarts.
    """
    source, calls = _counting_source("content")
    assembler = PromptAssembler().with_section(Section("m", "", source))

    assembler.render()
    assembler.render()

    assert len(calls) == 2


def test_whatever_a_source_returns_is_placed_verbatim():
    """Task B acceptance 5: this layer does not edit text it cannot read.

    Rendering lives outside — a skills index, a persona file, a memory
    précis all arrive already formatted — so truncating, stripping or
    re-wrapping here would be second-guessing a decision made by
    somebody with more information. A ``[:2000]`` in ``render`` is the
    mutation this rules out.
    """
    body = "line one\n\n  indented   \n" + "x" * 5_000 + "\ntrailing   "
    prompt = (
        PromptAssembler()
        .with_section(Section("raw", "## Raw", static(body)))
        .render()
    )

    assert prompt.system_prompt == f"## Raw\n\n{body}"


def test_section_stats_agree_with_the_token_estimator():
    """Task B seam ②: one counting rule, not a second ``ceil(len/4)``.

    The layer being replaced had three estimators living in three files
    and disagreeing.
    """
    prompt = _three_sections().render()

    assert prompt.section_stats == tuple(
        (s.key, estimate_text_tokens(s.content)) for s in prompt.sections
    )
    assert prompt.total_estimated_tokens == sum(
        tokens for _, tokens in prompt.section_stats
    )


def test_render_does_not_read_a_clock():
    """Decision Q2-d, as a negative property rather than a parameter.

    Today's date is outside knowledge like everything else, so a
    composition root passes a closure and this layer never asks. Stated
    the other way round: a date read inside ``render`` would make the
    prompt change at midnight, for no reason a reader of the section
    list could see.
    """
    import datetime
    import time

    class _Explodes:
        @staticmethod
        def today():
            raise AssertionError("render() read the calendar")

        @staticmethod
        def now(*args, **kwargs):
            raise AssertionError("render() read the clock")

    original = (datetime.date, datetime.datetime, time.time)
    datetime.date, datetime.datetime = _Explodes, _Explodes
    def _tick():
        raise AssertionError("render() read the clock")

    time.time = _tick
    try:
        assert _three_sections().render().system_prompt
    finally:
        datetime.date, datetime.datetime, time.time = original


def test_no_module_in_the_layer_names_a_wall_clock():
    """The same property, checked where a monkeypatch cannot reach.

    ``from datetime import date`` at module scope binds the name before
    any test can replace it, so the runtime probe above has a spelling
    it cannot see. This one reads the source instead: nothing in the
    package imports ``datetime``, the only name taken from ``time`` is
    ``monotonic``, and no attribute called ``today``/``now``/``utcnow``
    is touched anywhere.

    ``monotonic`` is the single exception and it is not a wall clock: it
    measures how long a compaction took, which is a duration in an audit
    record and never a byte of any prompt.
    """
    forbidden_attributes = {"today", "now", "utcnow"}
    offenders: list[str] = []

    for path in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden_attributes:
                    offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"datetime", "time"}:
                        offenders.append(f"{path.name}:{node.lineno} {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "datetime":
                    offenders.append(f"{path.name}:{node.lineno} datetime")
                if node.module == "time":
                    offenders.extend(
                        f"{path.name}:{node.lineno} time.{alias.name}"
                        for alias in node.names
                        if alias.name != "monotonic"
                    )

    assert not offenders, f"the layer reads a clock at {offenders}"


def test_an_empty_user_text_appends_nothing():
    """Task B acceptance 8, boundary one.

    History very often already ends with the user's turn — a caller that
    compacted and is re-running is the ordinary case — and an extra
    blank turn on top of it is a turn the model has to interpret.
    """
    history = [Message.user("the only thing I said")]

    conversation = assemble(_three_sections().render(), history)

    assert len(conversation) == 2
    assert conversation[-1] is history[0]


def test_a_user_turn_is_appended_byte_for_byte():
    """Task B acceptance 8, boundary two — no prefix, no heading.

    The replaced layer put ``"## User Request"`` in front of it. That
    heading existed to separate the user's words from the volatile
    context riding on the same turn, and with the context now in the
    system prompt it separates nothing. The mutation this rules out is
    putting it back.
    """
    prompt = _three_sections().render()

    conversation = assemble(prompt, [], "分析这份 Visium 数据")

    assert len(conversation) == 2
    assert conversation[1].role is Role.USER
    assert conversation[1].content == "分析这份 Visium 数据"


def test_assemble_hands_back_a_tuple_that_is_not_the_callers_list():
    history = [Message.user("one")]

    conversation = assemble(_three_sections().render(), history)
    history.append(Message.user("two"))

    assert isinstance(conversation, tuple)
    assert len(conversation) == 2


def test_the_history_arrives_whole_in_order_and_between_the_two_ends():
    """``[system, *history, user?]`` read as three separate claims.

    This is the layer's main public exit and every test of it used a
    history of zero or one message, which is a length at which reversing
    the list, keeping only the last three, or putting the new user turn
    *before* the history are all indistinguishable from doing it right.
    All three of those mutations passed the whole suite.

    So: four messages including a tool round trip, asserted by element
    identity — ``==`` would be satisfied by an implementation that
    rebuilt each message and churned the prompt prefix — with the
    system message pinned at index 0 and the new user turn pinned last.
    """
    history = [
        Message.user("earlier"),
        Message.assistant("on it", tool_calls=(ToolCall(id="c0", name="bash"),)),
        Message.tool(tool_call_id="c0", content="done"),
        Message.assistant("finished"),
    ]

    conversation = assemble(_three_sections().render(), history, "现在呢")

    assert len(conversation) == len(history) + 2
    assert conversation[0].role is Role.SYSTEM
    assert all(a is b for a, b in zip(conversation[1 : 1 + len(history)], history)), (
        "the history is handed through in arrival order, object for object"
    )
    assert conversation[-1].role is Role.USER
    assert conversation[-1].content == "现在呢"
    assert conversation[-1] not in history


def test_a_second_system_message_can_only_come_from_the_history():
    """The honest version of "exactly one system message", and its loop.

    :func:`assemble` contributes one system message and puts it first.
    It does not inspect the history, so the sentence "exactly one
    message carries ``Role.SYSTEM``" is a claim about what this function
    *adds* — and this package's own documented round trip breaks it:
    ``compact(..., pinned=1)`` keeps the system message it was given and
    returns it inside the compacted history, so feeding that straight
    back produces two.

    The consequence is not abstract. ``apply_cache_breakpoints`` marks
    the **last** system message, so the breakpoint lands on index 1, and
    the model reads a stale persona beside the current one. The remedy
    is the caller's and it is one slice — the second half of this test —
    because dropping a system message out of *history* here would be
    this layer silently discarding something a caller kept on purpose.
    """
    from omicsclaw.provider.openai_provider import (
        apply_cache_breakpoints,
        encode_messages,
    )

    prompt = _three_sections().render()
    compacted = (
        Message.system("an older prompt"),
        Message.user("[Context Compaction] ..."),
        Message.user("recent"),
    )

    def marked_index(conversation) -> int:
        encoded, _ = apply_cache_breakpoints(
            encode_messages(conversation),
            None,
            provider="anthropic",
            model="claude-sonnet-4.6",
            base_url="https://api.anthropic.com",
        )
        marked = [
            index
            for index, message in enumerate(encoded)
            if isinstance(message.get("content"), list)
            and any("cache_control" in block for block in message["content"])
        ]
        assert len(marked) == 1, encoded
        return marked[0]

    naive = assemble(prompt, compacted, "下一步")
    assert [m.role for m in naive].count(Role.SYSTEM) == 2
    assert marked_index(naive) == 1

    sliced = assemble(prompt, compacted[1:], "下一步")
    assert [m.role for m in sliced].count(Role.SYSTEM) == 1
    assert marked_index(sliced) == 0


def test_the_cache_breakpoint_lands_on_message_zero():
    """Task B seam ③, and it crosses packages on purpose (pitfall 10).

    ``apply_cache_breakpoints`` marks the **last** system message
    (``openai_provider.py:212-252``). With exactly one, "last" and
    "first" are the same message and the mark cannot drift because
    somebody added a section — which is the incidental benefit decision
    Q5 claims and the only place it can actually be checked.
    """
    from omicsclaw.provider.openai_provider import (
        apply_cache_breakpoints,
        encode_messages,
    )

    def marked_index(prompt: AssembledPrompt) -> int:
        conversation = assemble(prompt, [Message.user("hi")], "again")
        encoded, _ = apply_cache_breakpoints(
            encode_messages(conversation),
            None,
            provider="anthropic",
            model="claude-sonnet-4.6",
            base_url="https://api.anthropic.com",
        )
        marked = [
            index
            for index, message in enumerate(encoded)
            if isinstance(message.get("content"), list)
            and any("cache_control" in block for block in message["content"])
        ]
        assert len(marked) == 1, encoded
        return marked[0]

    one_section = PromptAssembler().with_section(
        Section("persona", "", static("你是 OmicsClaw。"))
    )

    assert marked_index(one_section.render()) == 0
    assert marked_index(_three_sections().render()) == 0


def test_a_prompt_with_no_sections_still_produces_the_system_message():
    """Degenerate but reachable: an assembler nobody added anything to.

    Emitting the message regardless keeps "exactly one system message,
    at index 0" true without a caveat.

    **Only one adapter drops it.** This docstring used to claim "both
    adapters drop an empty system string on the way out", and that was
    the sole defence offered for emitting a message with no content.
    Anthropic does drop it — ``anthropic_provider.py:273`` guards on
    ``if message.content`` — but OpenAI passes it straight through as
    ``{"role": "system", "content": ""}``, and
    ``_mark_last_system_message`` then turns it into a cache-controlled
    empty text block. Whether that is worth changing is a question for
    whoever owns the adapters; what this test does is stop the claim
    being repeated.
    """
    from omicsclaw.provider.anthropic_provider import encode_conversation
    from omicsclaw.provider.openai_provider import apply_cache_breakpoints

    conversation = assemble(PromptAssembler().render(), [])

    assert len(conversation) == 1
    assert conversation[0].role is Role.SYSTEM
    assert conversation[0].content == ""

    system_text, turns = encode_conversation(conversation)
    assert system_text == "", "Anthropic drops it"
    assert turns == []

    encoded, _ = apply_cache_breakpoints(
        [{"role": "system", "content": ""}],
        None,
        provider="anthropic",
        model="claude-sonnet-4.6",
        base_url="https://api.anthropic.com",
    )
    assert encoded[0]["role"] == "system", "OpenAI keeps it"
    assert encoded[0]["content"] != "", (
        "and turns it into a cache-controlled empty block — the opposite "
        "of dropping it"
    )

"""Plan 0030 task A: the counting rule everything else divides by.

Pitfall 1 lives here in its purest form. Two of this layer's three
first-class "literal borrowed from Go" targets are counted by these
functions, and both of them fail *silently* if the port is literal: a
``charsPerToken`` applied to code points instead of bytes, and a field
list copied from a schema that has no ``reasoning_content``.
"""

from __future__ import annotations

import pytest

from omicsclaw.context.tokens import (
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_text_tokens,
    estimate_tool_tokens,
    format_token_count,
)
from omicsclaw.schema import Message, Role, ToolCall, ToolDefinition

_CHINESE = "这是一个中文句子，用于测试 token 估算。"
_ENGLISH = "This is an English sentence, written to exercise the estimator."


class _Fixed:
    """A :class:`TokenCounter` that answers ``1`` to everything.

    Useless as a tokenizer and perfect as a probe: any figure that comes
    back as a count of *calls* proves the injected counter was the thing
    doing the counting.
    """

    def count_text(self, text: str) -> int:
        return 1


class _Recording:
    """Remembers every string it was handed, then estimates normally."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def count_text(self, text: str) -> int:
        self.seen.append(text)
        return estimate_text_tokens(text)


def test_chinese_is_not_undercounted_the_way_a_literal_port_would():
    """Pitfall 1, target one: ``charsPerToken = 4`` is bytes in Go.

    The measurement, for the record — and note what it is a measurement
    *of*. There was no tokenizer on this machine, so these are three
    estimators compared against each other, **not** against ground
    truth. Accuracy remains **uncalibrated** (plan 0030 §11.A-8), which
    is why no error figure appears here or in any docstring:

    ===================================  =======  =======
    estimator                            Chinese  English
    ===================================  =======  =======
    this module                               18       17
    ``len(text) // 4``  (naive port)           5       15
    ``len(text.encode()) // 4`` (the Go)      13       15
    ===================================  =======  =======

    The naive port is the dangerous one and the reason this test names
    a floor rather than a value: it believes a Chinese prompt costs a
    third of what the reference implementation thinks it costs, and
    every prompt in this repository that matters is Chinese.
    """
    assert len(_CHINESE) == 23
    assert len(_CHINESE.encode()) == 55

    estimate = estimate_text_tokens(_CHINESE)

    assert estimate >= len(_CHINESE.encode()) // 4, (
        "the estimate must not fall below what the reference harness "
        "would have counted for the same string"
    )
    assert estimate > len(_CHINESE) // 4 * 2, (
        "a literal port counts code points and undercounts Chinese "
        "two to three fold"
    )


def test_pure_ascii_agrees_with_the_harness():
    """The other half of the same rule: nothing was made up for ASCII.

    "Agrees" means *to within the rounding, and never below*, which is
    what the ``+ 1`` on the second line is. ``token.go:29`` divides one
    running total at the end and so floors; this module rounds each
    field up separately, so the two coincide only when the ASCII length
    is a multiple of four — ``"hello"`` is one token there and two here.
    The module docstring used to claim exact agreement; the assertions
    below never did, and they are the honest version.
    """
    assert estimate_text_tokens("a" * 400) == 100
    assert estimate_text_tokens(_ENGLISH) == len(_ENGLISH.encode()) // 4 + 1


def test_the_empty_string_is_free():
    assert estimate_text_tokens("") == 0
    assert estimate_messages_tokens([]) == 0
    assert estimate_tool_tokens([]) == 0


def test_nothing_special_happens_to_text_that_looks_like_base64():
    """Pitfall 21: the image blind spot must not be papered over.

    ``Message.content`` is a ``str``, so an image has no representation
    here and is billed nothing. The temptation is a heuristic — "looks
    like base64, add 1300" — and it is refused, because the heuristic
    misfires on ordinary text, which is the worse failure. This test is
    what makes the refusal enforceable rather than a note.

    The assertion is that the estimate is a function of the *character
    mix* and of nothing else: a blob, a run of one letter, and English
    prose of the same length all cost the same. Any sniffing at the
    shape of the text — alphanumeric runs, length thresholds, a base64
    alphabet — separates one of these three from the others.
    """
    base64_ish = "iVBORw0KGgoAAAANSUhEUg" * 40
    ordinary = "x" * len(base64_ish)
    prose = ("the slide was annotated, and then it was not. " * 20)[
        : len(base64_ish)
    ]

    assert len(prose) == len(base64_ish)
    assert estimate_text_tokens(base64_ish) == estimate_text_tokens(ordinary)
    assert estimate_text_tokens(base64_ish) == estimate_text_tokens(prose)
    assert estimate_text_tokens(base64_ish) == -(-len(base64_ish) // 4)


@pytest.mark.parametrize(
    "field",
    ["content", "reasoning_content", "tool_call_id", "name"],
)
def test_every_billable_field_makes_the_estimate_strictly_larger(field: str):
    """Pitfall 1, target two: the harness's field list is incomplete here.

    ``token.go:19-29`` counts content, tool-call ids, names and
    arguments, and ``tool_call_id``. It does not count
    ``reasoning_content`` — because its schema has no such field. This
    one does, ADR 0077 added it deliberately (thinking endpoints reject
    a history that lost it), and a copied field list would therefore
    under-count precisely the field this repository went out of its way
    to persist.

    The assertion is on the **number**, not on the source: a test that
    read the function's source for a field name would pass over an
    implementation that named the field and then did nothing with it.
    """
    bare = Message(role=Role.ASSISTANT)
    filled = bare.replace(**{field: "z" * 200})

    assert estimate_message_tokens(filled) > estimate_message_tokens(bare)


def test_a_tool_call_costs_its_id_its_name_and_its_arguments():
    """The three parts ``token.go:24`` counts, each checked separately."""
    empty = Message.assistant("hello")
    calls = [
        ToolCall(id="c" * 100, name="n", arguments="{}"),
        ToolCall(id="c", name="n" * 100, arguments="{}"),
        ToolCall(id="c", name="n", arguments='{"path": "' + "p" * 100 + '"}'),
    ]

    for call in calls:
        with_call = empty.replace(tool_calls=(call,))
        assert estimate_message_tokens(with_call) > estimate_message_tokens(empty)


def test_a_conversation_costs_the_sum_of_its_messages():
    messages = [
        Message.system("system"),
        Message.user(_CHINESE),
        Message.assistant("answer", reasoning_content="thought"),
    ]

    assert estimate_messages_tokens(messages) == sum(
        estimate_message_tokens(m) for m in messages
    )


def test_a_prompt_costs_its_system_text_plus_its_messages():
    """The replaced layer's ``estimate_prompt_tokens``, as an addition.

    Plan 0030 §5.2 asks for this to be written down rather than merely
    true, because a capability that is an addition of two other things
    looks exactly like a capability that was dropped.
    """
    system = "你是 OmicsClaw。" + _ENGLISH
    messages = [Message.user("hi"), Message.assistant("hello")]

    whole = estimate_messages_tokens([Message.system(system), *messages])

    assert whole == estimate_text_tokens(system) + estimate_messages_tokens(messages)


def test_an_injected_counter_replaces_the_estimate_everywhere():
    """Task A acceptance 3: every estimator honours ``counter=``.

    ``_Fixed`` answers ``1`` per string, so the totals below are counts
    of *calls*, and a function that quietly fell back to the built-in
    estimate would produce something else entirely.
    """
    counter = _Fixed()
    message = Message.assistant(
        "content",
        reasoning_content="thought",
        tool_calls=(ToolCall(id="c1", name="bash", arguments="{}"),),
    )

    # content + reasoning + tool_call_id + name + (id + name + arguments)
    assert estimate_message_tokens(message, counter=counter) == 7
    assert estimate_messages_tokens([message, message], counter=counter) == 14

    tool = ToolDefinition("bash", "run a command", {"type": "object"})
    # name + description + schema
    assert estimate_tool_tokens([tool], counter=counter) == 3


def test_tool_definitions_are_counted_schema_and_all():
    """``token.go:33-45``: tool schemas are 20-30K tokens, not a rounding.

    The whole reason ``ContextBudget`` demands a tool reserve. A
    preflight that counted names and descriptions and skipped the
    schemas would be optimistic by most of the figure.
    """
    named_only = ToolDefinition("spatial_de", "differential expression")
    with_schema = ToolDefinition(
        "spatial_de",
        "differential expression",
        {"type": "object", "properties": {"groupby": {"type": "string"}}},
    )

    assert estimate_tool_tokens([with_schema]) > estimate_tool_tokens([named_only])


def test_a_schema_serializes_the_same_way_whatever_order_it_was_built_in():
    """Pitfall 7, the ``json.dumps`` source: ``sort_keys`` defaults to False.

    Two registries that assembled the same schema by different routes
    would otherwise hand the estimator different bytes, and an estimate
    that moves with dictionary insertion order is an estimate nobody can
    reproduce. The check reads the *string the counter was handed*
    rather than the total, because two orderings of the same keys have
    the same length and would agree on the number while disagreeing on
    everything that matters.
    """
    forwards = ToolDefinition("t", "d", {"alpha": 1, "beta": 2, "gamma": 3})
    backwards = ToolDefinition("t", "d", {"gamma": 3, "beta": 2, "alpha": 1})

    first, second = _Recording(), _Recording()
    estimate_tool_tokens([forwards], counter=first)
    estimate_tool_tokens([backwards], counter=second)

    assert first.seen == second.seen
    assert first.seen[-1] == '{"alpha":1,"beta":2,"gamma":3}'


def test_a_schema_that_json_cannot_encode_is_still_counted():
    """The harness drops such a schema (``token.go:41``); this does not.

    Its comment says "rather under-count than interrupt", and
    under-counting is the one direction this layer refuses: the whole
    point of counting tool schemas is that forgetting them costs 20-30K
    tokens of imaginary headroom.
    """
    exotic = ToolDefinition("t", "d", {"callback": object()})

    assert estimate_tool_tokens([exotic]) > estimate_tool_tokens(
        [ToolDefinition("t", "d", {})]
    )


def test_a_chinese_description_is_counted_rather_than_escaped():
    """``ensure_ascii`` is off, so CJK is billed by the rule at the top.

    With the default, every Chinese character in a schema would become
    six ASCII characters of ``\\uXXXX`` escape and be billed 1.5 tokens
    instead of 1 — a number that describes the serializer rather than
    the prompt.
    """
    recorder = _Recording()
    tool = ToolDefinition("t", "d", {"desc": "差异表达"})
    estimate_tool_tokens([tool], counter=recorder)

    assert "差异表达" in recorder.seen[-1]


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "0"),
        (500, "500"),
        (999, "999"),
        (1_000, "1.0K"),
        (45_200, "45.2K"),
        (999_999, "1000.0K"),
        (1_000_000, "1.0M"),
        (1_200_000, "1.2M"),
    ],
)
def test_token_counts_format_the_way_the_harness_prints_them(count: int, expected: str):
    """``token.go:49-58``, behaviour ported and its ``switch`` not.

    Both boundaries are here because both are off-by-one candidates:
    999 is not ``1.0K`` and 1000 is.
    """
    assert format_token_count(count) == expected

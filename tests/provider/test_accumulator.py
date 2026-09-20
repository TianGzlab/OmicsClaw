"""Streaming tool-call reassembly (plan 0026 §5, trap 1).

The regression this file exists for is trap 1: vendor stream indices are
not guaranteed to start at 0, and a positional loop silently drops tool
calls. Everything else here guards the reassembly around it.
"""

from __future__ import annotations

from omicsclaw.provider._accumulator import ToolCallAccumulators
from omicsclaw.schema import ToolCall


def test_a_single_call_is_reassembled_from_fragments():
    accumulators = ToolCallAccumulators()
    accumulators.start(0, "call_1", "run_skill")
    accumulators.append_arguments(0, '{"skill":')
    accumulators.append_arguments(0, ' "spatial-de"}')

    assert accumulators.finalize() == (
        ToolCall(id="call_1", name="run_skill", arguments='{"skill": "spatial-de"}'),
    )


def test_indices_starting_above_zero_are_not_dropped():
    """Trap 1. Anthropic's index is the content-block position, so with
    extended thinking the tool_use blocks begin at 1. A ``range(len())``
    loop finds nothing at 0 and loses every call."""
    accumulators = ToolCallAccumulators()
    accumulators.start(1, "call_a", "first")
    accumulators.append_arguments(1, "{}")
    accumulators.start(2, "call_b", "second")
    accumulators.append_arguments(2, "{}")

    assert [c.id for c in accumulators.finalize()] == ["call_a", "call_b"]


def test_non_contiguous_indices_are_all_kept():
    accumulators = ToolCallAccumulators()
    for index, call_id in ((3, "c"), (7, "d"), (11, "e")):
        accumulators.start(index, call_id, "t")

    assert [c.id for c in accumulators.finalize()] == ["c", "d", "e"]


def test_calls_are_ordered_by_index_not_arrival():
    """Parallel tool calls interleave in the stream; the model correlates
    them positionally, so emission order must follow the index."""
    accumulators = ToolCallAccumulators()
    accumulators.start(2, "second", "t")
    accumulators.start(0, "first", "t")
    accumulators.start(1, "middle", "t")

    assert [c.id for c in accumulators.finalize()] == ["first", "middle", "second"]


def test_interleaved_fragments_stay_with_their_own_call():
    accumulators = ToolCallAccumulators()
    accumulators.start(0, "a", "t")
    accumulators.start(1, "b", "t")
    accumulators.append_arguments(0, '{"x":')
    accumulators.append_arguments(1, '{"y":')
    accumulators.append_arguments(0, "1}")
    accumulators.append_arguments(1, "2}")

    calls = accumulators.finalize()
    assert calls[0].arguments == '{"x":1}'
    assert calls[1].arguments == '{"y":2}'


def test_a_call_with_no_arguments_still_yields_parseable_json():
    """The schema guarantees ``arguments`` is always valid JSON text."""
    accumulators = ToolCallAccumulators()
    accumulators.start(0, "call_1", "no_args_tool")

    call = accumulators.finalize()[0]
    assert call.arguments == "{}"
    assert call.parsed_arguments() == {}


def test_a_repeated_start_does_not_blank_the_identity():
    """Some backends repeat the index on continuation chunks with the id
    and name omitted; that must not erase what the opening chunk set."""
    accumulators = ToolCallAccumulators()
    accumulators.start(0, "call_1", "run_skill")
    accumulators.start(0, "", "")

    call = accumulators.finalize()[0]
    assert call.id == "call_1"
    assert call.name == "run_skill"


def test_an_empty_stream_yields_no_calls():
    """No tool call is the normal terminating turn, not an error."""
    accumulators = ToolCallAccumulators()
    assert accumulators.finalize() == ()
    assert not accumulators


def test_empty_fragments_are_ignored():
    accumulators = ToolCallAccumulators()
    accumulators.start(0, "c", "t")
    accumulators.append_arguments(0, "")
    accumulators.append_arguments(0, '{"a":1}')
    accumulators.append_arguments(0, "")

    assert accumulators.finalize()[0].arguments == '{"a":1}'

"""Contract tests for ``omicsclaw.schema`` message types (ADR 0077).

The load-bearing property is vendor-neutrality: nothing here may know
what an OpenAI or Anthropic payload looks like. Translation belongs to
the model adapter layer, which is a later step.
"""

from __future__ import annotations

import pytest

from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)


# --- Role -----------------------------------------------------------------


def test_role_compares_equal_to_its_literal():
    """Migration guard: un-migrated code compares against bare strings."""
    assert Role.ASSISTANT == "assistant"
    assert Role.TOOL == "tool"
    assert str(Role.SYSTEM) == "system"


def test_role_round_trips_through_str():
    assert Role(str(Role.USER)) is Role.USER


def test_tool_is_a_distinct_role():
    """Observations stay structurally distinguishable from human input."""
    assert Role.TOOL is not Role.USER


# --- ToolCall -------------------------------------------------------------


def test_tool_call_keeps_arguments_unparsed():
    """Byte-exactness, not equivalence: key order must not be normalized."""
    raw = '{"skill": "spatial-de", "demo": true}'
    call = ToolCall(id="call_1", name="execute_omicsclaw", arguments=raw)
    assert call.arguments == raw


def test_tool_call_parses_arguments_on_demand():
    call = ToolCall(id="c", name="t", arguments='{"a": 1, "b": [2]}')
    assert call.parsed_arguments() == {"a": 1, "b": [2]}


@pytest.mark.parametrize("raw", ["", "{", "null", "[1,2]", '"text"'])
def test_tool_call_parse_never_raises_on_unusable_payloads(raw):
    """A truncated stream must cost one turn, not crash the loop."""
    assert ToolCall(id="c", name="t", arguments=raw).parsed_arguments() == {}


# --- Message --------------------------------------------------------------


def test_message_is_frozen():
    message = Message.user("hi")
    with pytest.raises(Exception):
        message.content = "changed"  # type: ignore[misc]


def test_replace_returns_a_new_message():
    original = Message.assistant("a", reasoning_content="thought")
    updated = original.replace(content="b")

    assert updated.content == "b"
    assert updated.reasoning_content == "thought"
    assert original.content == "a"


def test_replace_carries_every_field():
    original = Message.tool(
        tool_call_id="c1", content="boom", name="t", is_error=True
    )
    updated = original.replace(content="fixed")

    assert updated.tool_call_id == "c1"
    assert updated.name == "t"
    assert updated.is_error is True
    assert updated.content == "fixed"


def test_is_action_distinguishes_acting_from_answering():
    acting = Message.assistant(tool_calls=[ToolCall(id="c", name="t")])
    answering = Message.assistant("here is the result")

    assert acting.is_action is True
    assert answering.is_action is False


def test_assistant_carries_thought_and_action_together():
    """One turn may reason and act; the schema must not force a choice."""
    message = Message.assistant(
        "running it",
        reasoning_content="the user asked for a demo",
        tool_calls=[ToolCall(id="c1", name="run")],
    )
    assert message.reasoning_content == "the user asked for a demo"
    assert message.content == "running it"
    assert message.is_action is True


# --- ToolResult -----------------------------------------------------------


def test_tool_result_projects_into_a_tool_message():
    result = ToolResult(tool_call_id="c1", name="run", output="ok")
    message = result.to_message()

    assert message.role is Role.TOOL
    assert message.tool_call_id == "c1"
    assert message.name == "run"
    assert message.content == "ok"
    assert message.is_error is False


def test_error_state_survives_the_projection():
    """Anthropic has a native ``is_error``; the schema must be able to
    feed it rather than relying on the model parsing an error prefix."""
    result = ToolResult(tool_call_id="c1", name="t", output="boom", is_error=True)
    assert result.to_message().is_error is True


def test_metadata_is_carried_but_never_projected():
    """Execution facts are for the loop, not the model."""
    result = ToolResult(
        tool_call_id="c1", name="t", output="ok", metadata={"timed_out": True}
    )
    assert result.metadata["timed_out"] is True
    assert result.to_message().content == "ok"


def test_metadata_defaults_are_not_shared():
    first = ToolResult(tool_call_id="a", name="t")
    second = ToolResult(tool_call_id="b", name="t")
    assert first.metadata == second.metadata == {}


# --- ToolDefinition -------------------------------------------------------


def test_tool_definition_holds_only_what_a_model_is_told():
    """Local policy must be structurally absent, not merely unused."""
    fields = set(ToolDefinition.__dataclass_fields__)
    assert fields == {"name", "description", "input_schema"}


# --- Usage ----------------------------------------------------------------


def test_usage_accumulates():
    total = Usage(input_tokens=10, output_tokens=2, cache_read_tokens=8) + Usage(
        input_tokens=5, output_tokens=3, cache_write_tokens=4
    )
    assert total == Usage(
        input_tokens=15, output_tokens=5, cache_read_tokens=8, cache_write_tokens=4
    )
    assert total.total_tokens == 20


def test_uncached_input_is_the_billable_remainder():
    usage = Usage(input_tokens=1000, cache_read_tokens=900)
    assert usage.uncached_input_tokens == 100


def test_uncached_input_never_goes_negative():
    """A vendor reporting more cached than total must not produce a
    negative charge."""
    assert Usage(input_tokens=10, cache_read_tokens=99).uncached_input_tokens == 0


def test_usage_carries_no_vendor_field_names():
    fields = set(Usage.__dataclass_fields__)
    assert fields == {
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    }


# --- StreamChunk ----------------------------------------------------------


def test_stream_chunk_constructors_set_the_matching_field():
    assert StreamChunk.text("a").delta == "a"
    assert StreamChunk.reasoning("t").type is StreamChunkType.REASONING_DELTA
    assert StreamChunk.failed("boom").error == "boom"


def test_done_chunk_carries_the_assembled_message_and_usage():
    message = Message.assistant("done")
    chunk = StreamChunk.done(message, Usage(input_tokens=5, output_tokens=1))

    assert chunk.type is StreamChunkType.DONE
    assert chunk.message is message
    assert chunk.usage == Usage(input_tokens=5, output_tokens=1)


def test_deltas_carry_no_partial_tool_calls():
    """Half-decoded arguments must never be observable mid-stream."""
    assert StreamChunk.text("partial").message is None
    assert StreamChunk.reasoning("partial").message is None


def test_a_done_chunk_can_say_why_the_model_stopped():
    """The amendment plan 0027 §5 takes.

    Without this the Main Loop cannot tell a stream cut off by the output
    ceiling from a model that finished: both end in a ``DONE`` chunk whose
    message requests no tools.
    """
    truncated = StreamChunk.done(Message.assistant("half a sen"), None, "length")
    converged = StreamChunk.done(Message.assistant("all done"), None, "stop")

    assert truncated.finish_reason == "length"
    assert converged.finish_reason == "stop"
    assert truncated.message.is_action is converged.message.is_action


def test_finish_reason_defaults_to_empty_so_existing_callers_keep_working():
    """Additive with a default: a two-argument ``done()`` stays valid."""
    assert StreamChunk.done(Message.assistant("ok")).finish_reason == ""
    assert StreamChunk.done(Message.assistant("ok"), Usage()).finish_reason == ""
    assert StreamChunk.text("d").finish_reason == ""

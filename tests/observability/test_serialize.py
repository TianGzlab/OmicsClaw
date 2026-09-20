"""A span attribute is a protobuf string going over a network."""

from __future__ import annotations

from omicsclaw.observability.serialize import (
    MAX_ATTRIBUTE_BYTES,
    TRUNCATION_MARK,
    serialize_messages,
    serialize_output,
    truncate_attr,
)
from omicsclaw.schema import Message, Role, ToolCall


def test_a_short_string_is_returned_unchanged():
    assert truncate_attr("hello") == "hello"
    assert truncate_attr("") == ""


def test_the_bound_is_bytes_not_characters():
    """4096 characters of Chinese would be 12 KiB on the wire."""
    text = "基" * 4000

    cut = truncate_attr(text)

    assert cut.endswith(TRUNCATION_MARK)
    assert len(cut.removesuffix(TRUNCATION_MARK).encode("utf-8")) <= (
        MAX_ATTRIBUTE_BYTES
    )


def test_truncation_never_splits_a_character():
    """A half character is the corruption a reader blames on their pipeline."""
    for filler in range(3):
        text = "a" * filler + "→" * 4000
        cut = truncate_attr(text).removesuffix(TRUNCATION_MARK)

        cut.encode("utf-8").decode("utf-8")
        assert "�" not in cut


def test_a_string_exactly_at_the_bound_is_not_marked():
    text = "a" * MAX_ATTRIBUTE_BYTES

    assert truncate_attr(text) == text


def test_a_surrogate_from_binary_tool_output_does_not_raise():
    """``errors="surrogateescape"`` is how the stdlib hands bytes back as str."""
    text = b"\xff\xfe binary".decode("utf-8", "surrogateescape")

    cleaned = truncate_attr(text)

    cleaned.encode("utf-8")
    assert "binary" in cleaned


def test_messages_serialize_to_parseable_json_with_the_fields_that_matter():
    import json

    payload = serialize_messages(
        [
            Message(role=Role.USER, content="hi"),
            Message(
                role=Role.ASSISTANT,
                content="acting",
                tool_calls=(ToolCall(id="c1", name="bash", arguments='{"command":"ls"}'),),
            ),
            Message.tool(tool_call_id="c1", content="out", name="bash"),
        ]
    )

    views = json.loads(payload)
    assert [v["role"] for v in views] == ["user", "assistant", "tool"]
    assert views[1]["tool_calls"][0]["name"] == "bash"
    assert views[2]["tool_call_id"] == "c1"


def test_tool_call_arguments_stay_the_text_they_are():
    """Re-encoding reorders keys and breaks prompt-prefix caching evidence."""
    import json

    raw = '{"b":1,"a":2}'
    payload = serialize_messages(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="c", name="t", arguments=raw),),
            )
        ]
    )

    assert json.loads(payload)[0]["tool_calls"][0]["arguments"] == raw


def test_reasoning_content_is_not_serialized():
    """A thought is the model's working, not the request."""
    payload = serialize_messages(
        [Message(role=Role.ASSISTANT, content="said", reasoning_content="thought")]
    )

    assert "thought" not in payload
    assert "said" in payload


def test_an_oversized_conversation_stays_parseable_up_to_the_cut():
    payload = serialize_messages(
        [Message(role=Role.USER, content="x" * 9000)] * 3
    )

    assert payload.endswith(TRUNCATION_MARK)
    assert payload.startswith('[{"role":"user"')


def test_output_prefers_tool_calls_over_prose():
    """A turn that requested an action is about the action."""
    message = Message(
        role=Role.ASSISTANT,
        content="let me look",
        tool_calls=(ToolCall(id="c", name="read_file", arguments="{}"),),
    )

    rendered = serialize_output(message)

    assert "read_file" in rendered
    assert "let me look" not in rendered


def test_output_of_nothing_is_the_empty_string():
    assert serialize_output(None) == ""
    assert serialize_output(Message(role=Role.ASSISTANT)) == ""


def test_output_is_bounded_too():
    message = Message(role=Role.ASSISTANT, content="y" * 9000)

    assert serialize_output(message).endswith(TRUNCATION_MARK)


def test_non_ascii_is_not_escaped():
    """``ensure_ascii`` triples the byte cost and spends it on backslashes."""
    payload = serialize_messages([Message(role=Role.USER, content="空间转录组")])

    assert "空间转录组" in payload
    assert "\\u" not in payload

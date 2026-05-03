"""Tests for the compaction summary's prior-tool-call rendering.

Bare prose like ``"Read, Edit"`` in the summary triggers few-shot mimicry —
after compaction the model writes plain-text tool descriptions instead of
emitting real tool_use blocks. XML self-closing tags are treated as
structural metadata and not reproduced. (Same lesson as CodePilot's fix.)
"""
from __future__ import annotations

from omicsclaw.runtime.context_compaction import (
    ContextCompactionConfig,
    compact_history,
)


def _build_history_with_tool_call_assistant(turns: int = 12) -> list[dict]:
    history: list[dict] = []
    for i in range(turns):
        history.append({"role": "user", "content": f"user query {i} " + "x" * 200})
        # Every other assistant turn carries tool_calls
        if i % 2 == 0:
            history.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call-{i}",
                            "type": "function",
                            "function": {"name": "Read", "arguments": "{}"},
                        }
                    ],
                }
            )
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call-{i}",
                    "content": "tool output " + "y" * 200,
                }
            )
        else:
            history.append(
                {
                    "role": "assistant",
                    "content": f"assistant reply {i} " + "y" * 200,
                }
            )
    return history


def test_tool_call_highlights_use_xml_tags_not_prose():
    history = _build_history_with_tool_call_assistant(turns=12)
    result = compact_history(
        history,
        preserve_messages=4,
        preserve_chars=2000,
        config=ContextCompactionConfig(),
    )
    summary = result.summary
    # Highlights for assistant-with-tool_calls must be wrapped in XML tags
    # so the model treats them as metadata rather than narrative.
    assert "<prior-tool-calls" in summary
    # And must NOT contain the historical prose form.
    assert "(used " not in summary


def test_tool_call_xml_tag_is_self_closing_and_lists_tool_names():
    history = [
        {"role": "user", "content": "q1 " + "a" * 300},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "Read", "arguments": "{}"},
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "Edit", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "out"},
        {"role": "tool", "tool_call_id": "c2", "content": "out"},
        # Tail to preserve
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "tail"},
    ]
    result = compact_history(
        history,
        preserve_messages=2,
        preserve_chars=1000,
        config=ContextCompactionConfig(),
    )
    assert result.omitted_count > 0
    # The tag must include both tool names.
    assert "Read" in result.summary
    assert "Edit" in result.summary
    # Self-closing form: ends with /> on the prior-tool-calls tag.
    assert "<prior-tool-calls" in result.summary
    assert "/>" in result.summary


def test_assistant_with_text_content_renders_as_text():
    """Highlights for assistant messages with prose content stay as prose
    (XML wrapping is only for the tool-call narration risk)."""
    history = [
        {"role": "user", "content": "q " + "a" * 400},
        {"role": "assistant", "content": "I think the answer is 42 because..." + "b" * 300},
        # Tail
        {"role": "user", "content": "tail-q"},
        {"role": "assistant", "content": "tail-a"},
    ]
    result = compact_history(
        history,
        preserve_messages=2,
        preserve_chars=600,
        config=ContextCompactionConfig(),
    )
    assert result.omitted_count > 0
    assert "<prior-tool-calls" not in result.summary

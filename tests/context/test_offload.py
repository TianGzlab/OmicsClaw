"""Plan 0035: which tool results leave the conversation, and what stays behind.

The placeholder is read by two parties — the model, which needs a path it
can hand to ``read_file``, and this package, which parses it back to carry
the reference into the next compaction message. Both directions are
pinned here, together with the key rule that keeps two different results
from sharing one file.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.context.offload import (
    MAX_REFERENCES,
    OFFLOAD_MARKER,
    OffloadEntry,
    Offloader,
    is_offloaded,
    offload_key,
    offload_messages,
    parse_placeholder,
    parse_references,
    render_placeholder,
    render_references,
)
from omicsclaw.schema import Message


class MemoryStore:
    """An :class:`OffloadStore` that keeps files in a dict."""

    def __init__(self, *, fail: bool = False) -> None:
        self.files: dict[str, str] = {}
        self.puts = 0
        self.fail = fail

    async def put(self, key: str, content: str) -> str:
        self.puts += 1
        if self.fail:
            raise OSError("disk full")
        self.files[key] = content
        return f".omicsclaw/tool_results/s1/{key}.txt"


def _result(call_id: str, content: str, name: str = "bash") -> Message:
    return Message.tool(tool_call_id=call_id, content=content, name=name)


# --- keys -----------------------------------------------------------------


def test_the_key_follows_the_content_not_only_the_call_id():
    """Some presets reuse or omit call ids; the file must not be shared."""
    first = offload_key("call_0", "a" * 5000)
    second = offload_key("call_0", "b" * 5000)

    assert first != second
    assert first.startswith("call_0-")
    assert offload_key("call_0", "a" * 5000) == first


def test_a_result_without_a_call_id_still_gets_a_key():
    assert offload_key("", "x" * 5000)


def test_the_key_is_a_single_safe_file_name():
    key = offload_key("../../etc/passwd", "x")

    assert "/" not in key
    assert not key.startswith(".")


# --- placeholders ---------------------------------------------------------


def test_a_placeholder_parses_back_into_its_entry():
    entry = OffloadEntry(reference="r/a.txt", lines=3, chars=12)
    text = render_placeholder(
        entry, "one\ntwo\nthree", preview_lines=2, preview_chars=100
    )
    message = _result("c1", text, name="read_file")

    parsed = parse_placeholder(message)

    assert is_offloaded(message)
    assert parsed == OffloadEntry(
        reference="r/a.txt",
        lines=3,
        chars=12,
        tool_call_id="c1",
        tool_name="read_file",
    )
    assert "one\ntwo" in text and "three" not in text
    assert "read_file" in text


def test_a_single_enormous_line_does_not_become_its_own_preview():
    """A line-count preview alone keeps a minified JSON blob whole."""
    content = "x" * 50_000
    entry = OffloadEntry(reference="r", lines=1, chars=len(content))

    text = render_placeholder(entry, content, preview_lines=10, preview_chars=800)

    assert len(text) < 1_200
    assert "clipped" in text


def test_ordinary_text_is_not_a_placeholder():
    assert parse_placeholder(_result("c1", "[offloaded: but no header")) is None
    assert parse_placeholder(Message.user("hello")) is None


# --- moving messages ------------------------------------------------------


def test_only_large_tool_results_move():
    messages = (
        Message.user("u" * 8_000),
        _result("c1", "small"),
        _result("c2", "big\n" * 2_000),
        Message.assistant("a" * 8_000),
    )
    store = MemoryStore()

    outcome = asyncio.run(offload_messages(messages, Offloader(store)))

    assert outcome.messages[0] is messages[0]
    assert outcome.messages[1] is messages[1]
    assert outcome.messages[3] is messages[3]
    assert outcome.messages[2].content.startswith(OFFLOAD_MARKER)
    assert outcome.messages[2].tool_call_id == "c2"
    assert [entry.tool_call_id for entry in outcome.entries] == ["c2"]
    assert list(store.files.values()) == [messages[2].content]


def test_a_placeholder_is_never_offloaded_again():
    store = MemoryStore()
    first = (_result("c1", "y" * 9_000),)
    once = asyncio.run(offload_messages(first, Offloader(store)))

    twice = asyncio.run(offload_messages(once.messages, Offloader(store, min_tokens=0)))

    assert store.puts == 1
    assert twice.entries == ()
    assert twice.messages == once.messages


def test_a_store_that_fails_leaves_the_message_and_says_why():
    message = _result("c1", "y" * 9_000)

    outcome = asyncio.run(
        offload_messages((message,), Offloader(MemoryStore(fail=True)))
    )

    assert outcome.messages == (message,)
    assert outcome.entries == ()
    assert "disk full" in outcome.failures[0]


def test_the_threshold_is_in_tokens():
    exactly = _result("c1", "y" * 4_000)  # 1,000 estimated tokens

    outcome = asyncio.run(offload_messages((exactly,), Offloader(MemoryStore())))

    assert outcome.entries == (), "at the threshold is not above it"


def test_negative_limits_are_refused():
    with pytest.raises(ValueError):
        Offloader(MemoryStore(), min_tokens=-1)


# --- references -----------------------------------------------------------


def test_references_round_trip_through_their_block():
    entries = (
        OffloadEntry(reference="a.txt", lines=10, chars=400, tool_name="bash"),
        OffloadEntry(reference="b.txt", lines=1, chars=9),
    )

    text = "## Summary\nsomething\n\n" + render_references(entries)

    assert parse_references(text) == entries


def test_the_reference_block_keeps_only_the_newest():
    entries = tuple(
        OffloadEntry(reference=f"{index}.txt", lines=1, chars=1)
        for index in range(MAX_REFERENCES + 5)
    )

    parsed = parse_references(render_references(entries))

    assert len(parsed) == MAX_REFERENCES
    assert parsed[-1].reference == f"{MAX_REFERENCES + 4}.txt"
    assert parsed[0].reference == "5.txt"


def test_no_entries_render_no_block():
    assert render_references(()) == ""

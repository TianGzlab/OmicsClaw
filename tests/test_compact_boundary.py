"""Tests for boundary-aware /compact (CodePilot bug #7).

Repeated /compact must not feed the previous summary back into the summarizer
— it would either re-summarize the meta-text or silently duplicate it.
The previous summary is carried forward verbatim; only messages after it are
fed to _collapse_history. Detection is via the ``<compaction-summary>...</...>``
content marker on system-role messages.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types

import pytest

from omicsclaw.runtime.context_compaction import (
    is_compaction_summary_message,
    unwrap_compaction_summary,
    wrap_compaction_summary,
)
from omicsclaw.runtime.transcript_store import TranscriptStore, sanitize_tool_history


# ---------------------------------------------------------------------------
# Wrap / unwrap / detect primitives
# ---------------------------------------------------------------------------


class TestWrapAndDetect:
    def test_wrap_round_trip(self):
        body = "- 7 earlier message(s)...\n- preserved tail starts at..."
        wrapped = wrap_compaction_summary(body)
        assert wrapped.startswith("<compaction-summary>")
        assert wrapped.rstrip().endswith("</compaction-summary>")
        assert unwrap_compaction_summary(wrapped) == body

    def test_unwrap_passes_through_when_unwrapped(self):
        assert unwrap_compaction_summary("plain text") == "plain text"

    def test_detect_only_on_system_role(self):
        assert is_compaction_summary_message(
            {"role": "system", "content": wrap_compaction_summary("body")}
        )
        # Same content but wrong role must NOT be detected.
        assert not is_compaction_summary_message(
            {"role": "user", "content": wrap_compaction_summary("body")}
        )
        assert not is_compaction_summary_message(
            {"role": "system", "content": "plain system note"}
        )


# ---------------------------------------------------------------------------
# /compact slash, second call must respect boundary
# ---------------------------------------------------------------------------


@pytest.fixture
def bot_core():
    if "httpx" not in sys.modules:
        httpx_stub = types.ModuleType("httpx")

        class _StubHTTPError(Exception):
            pass

        httpx_stub.HTTPError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.ConnectError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.TimeoutException = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.get = lambda *_, **__: None  # type: ignore[attr-defined]
        sys.modules["httpx"] = httpx_stub
    for stub_name in ("openai", "tiktoken"):
        if stub_name not in sys.modules:
            sys.modules[stub_name] = types.ModuleType(stub_name)
    if "openai" in sys.modules and not hasattr(sys.modules["openai"], "AsyncOpenAI"):
        class _FakeAsyncOpenAI:
            def __init__(self, *_, **__):
                pass

        class _FakeAPIError(Exception):
            pass

        sys.modules["openai"].AsyncOpenAI = _FakeAsyncOpenAI  # type: ignore[attr-defined]
        sys.modules["openai"].APIError = _FakeAPIError  # type: ignore[attr-defined]
    try:
        return importlib.import_module("bot.core")
    except ImportError as exc:
        pytest.skip(f"bot.core unavailable: {exc}")


def _seed_long_history(store: TranscriptStore, chat_id: str, *, turns: int = 10) -> None:
    for i in range(turns):
        store.append_user_message(chat_id, f"user {i} " + "x" * 200)
        store.append_assistant_message(chat_id, content=f"assistant {i} " + "y" * 200)


def test_second_compact_with_no_new_messages_is_a_no_op(bot_core):
    chat_id = "boundary-1"
    bot_core.transcript_store.clear(chat_id)
    _seed_long_history(bot_core.transcript_store, chat_id, turns=12)

    first = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))
    assert first.startswith("✓")

    # No new turns added between calls.
    second = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))
    second_lower = second.lower()
    assert (
        "already compacted" in second_lower
        or "no new messages" in second_lower
        or "nothing new" in second_lower
    )

    history = bot_core.transcript_store.get_history(chat_id)
    # Exactly one summary message at the head — not nested into another.
    summary_messages = [m for m in history if is_compaction_summary_message(m)]
    assert len(summary_messages) == 1


def test_second_compact_carries_previous_summary_forward(bot_core):
    chat_id = "boundary-2"
    bot_core.transcript_store.clear(chat_id)
    _seed_long_history(bot_core.transcript_store, chat_id, turns=12)

    first = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))
    assert first.startswith("✓")

    history_after_first = bot_core.transcript_store.get_history(chat_id)
    first_summary = next(
        m for m in history_after_first if is_compaction_summary_message(m)
    )
    first_body = unwrap_compaction_summary(first_summary["content"])
    # Capture a fingerprint of the first summary.
    first_fingerprint = first_body[:80]
    assert first_fingerprint  # non-empty

    # Simulate enough new conversation to require another compaction.
    for i in range(8):
        bot_core.transcript_store.append_user_message(
            chat_id, f"new user {i} " + "u" * 250
        )
        bot_core.transcript_store.append_assistant_message(
            chat_id, content=f"new assistant {i} " + "v" * 250
        )

    second = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))
    assert second.startswith("✓")

    history_after_second = bot_core.transcript_store.get_history(chat_id)
    summary_messages = [
        m for m in history_after_second if is_compaction_summary_message(m)
    ]
    # Still exactly one summary message (combined) — not a summary of summaries.
    assert len(summary_messages) == 1
    combined_body = unwrap_compaction_summary(summary_messages[0]["content"])
    # The previous summary's text must appear verbatim — not re-summarized.
    assert first_fingerprint in combined_body
    # And new content must be reflected (mention of new compacted messages).
    assert "earlier message" in combined_body.lower()


def test_compact_branch_is_not_persisted_as_assistant_message(bot_core):
    """CodePilot bug #3: the user-facing notification must NOT land in
    the transcript as an assistant message."""
    chat_id = "boundary-3"
    bot_core.transcript_store.clear(chat_id)
    _seed_long_history(bot_core.transcript_store, chat_id, turns=12)

    asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))

    history = bot_core.transcript_store.get_history(chat_id)
    for m in history:
        content = m.get("content") or ""
        # The status string starts with ✓ — none of those text fragments
        # may appear in the persisted transcript.
        assert "✓ Compacted" not in content
        assert "Nothing to compact" not in content
        assert "Already compacted" not in content

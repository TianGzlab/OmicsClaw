"""Tests for the deterministic /compact slash command and its primitives.

The /compact command rebuilds the persisted transcript using the existing
template-based collapse logic (no LLM call). This avoids the DeepSeek
thinking-mode failure mode entirely for /compact and gives users a way to
shrink long histories on demand.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types

import pytest

from omicsclaw.runtime.context_compaction import (
    ContextCompactionConfig,
    compact_history,
)
from omicsclaw.runtime.transcript_store import TranscriptStore, sanitize_tool_history


def _seed_long_history(store: TranscriptStore, chat_id: str, *, turns: int = 10) -> None:
    for i in range(turns):
        store.append_user_message(chat_id, f"user turn {i} " + "x" * 200)
        store.append_assistant_message(chat_id, content=f"assistant reply {i} " + "y" * 200)


# ---------------------------------------------------------------------------
# Public compact_history primitive
# ---------------------------------------------------------------------------


class TestCompactHistoryHelper:
    def test_returns_summary_and_trimmed_messages(self):
        store = TranscriptStore(sanitizer=sanitize_tool_history)
        _seed_long_history(store, "chat-helper", turns=10)
        history = store.get_history("chat-helper")

        result = compact_history(
            history,
            preserve_messages=4,
            preserve_chars=2000,
            config=ContextCompactionConfig(),
        )

        assert result.omitted_count > 0
        assert len(result.messages) <= len(history)
        assert "compacted" in result.summary.lower()
        assert result.messages[-1]["content"].startswith("assistant reply 9")

    def test_returns_no_op_when_history_already_short(self):
        result = compact_history(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            preserve_messages=10,
            preserve_chars=10000,
            config=ContextCompactionConfig(),
        )
        assert result.omitted_count == 0
        assert result.summary == ""


# ---------------------------------------------------------------------------
# TranscriptStore.replace_history
# ---------------------------------------------------------------------------


class TestReplaceHistory:
    def test_replaces_existing_history(self):
        store = TranscriptStore(sanitizer=sanitize_tool_history)
        _seed_long_history(store, "chat-replace", turns=5)
        new_history = [
            {"role": "system", "content": "compacted summary"},
            {"role": "user", "content": "current question"},
        ]
        store.replace_history("chat-replace", new_history)
        assert store.get_history("chat-replace") == new_history

    def test_creates_chat_if_missing(self):
        store = TranscriptStore(sanitizer=sanitize_tool_history)
        store.replace_history(
            "fresh-chat",
            [{"role": "user", "content": "q"}],
        )
        assert store.get_history("fresh-chat") == [{"role": "user", "content": "q"}]


# ---------------------------------------------------------------------------
# /compact slash command
# ---------------------------------------------------------------------------


@pytest.fixture
def bot_core(monkeypatch):
    """Import bot.core with stubs for optional heavy deps so the slash branch
    can run without LLM clients or external libraries."""
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
        pytest.skip(f"bot.core unavailable in this environment: {exc}")


def test_compact_slash_replaces_history_with_summary_and_tail(bot_core):
    chat_id = "compact-chat"
    bot_core.transcript_store.clear(chat_id)
    _seed_long_history(bot_core.transcript_store, chat_id, turns=10)
    starting_len = len(bot_core.transcript_store.get_history(chat_id))

    result = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))

    new_history = bot_core.transcript_store.get_history(chat_id)
    # Should be strictly smaller than what we started with
    assert len(new_history) < starting_len
    # Status string flags success and shows omitted-count
    assert result.startswith("✓")
    assert "compact" in result.lower()
    # Head of new history carries the summary message
    assert new_history[0]["role"] in {"system", "user"}
    assert "compacted" in new_history[0]["content"].lower()


def test_compact_slash_no_op_message_when_already_short(bot_core):
    chat_id = "compact-empty"
    bot_core.transcript_store.clear(chat_id)
    bot_core.transcript_store.append_user_message(chat_id, "hi")
    bot_core.transcript_store.append_assistant_message(chat_id, content="hello")

    result = asyncio.run(bot_core.llm_tool_loop(chat_id, "/compact"))

    assert "nothing to compact" in result.lower() or "already" in result.lower()
    history = bot_core.transcript_store.get_history(chat_id)
    assert len(history) == 2

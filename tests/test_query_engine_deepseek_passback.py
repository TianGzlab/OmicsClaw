"""Regression tests for DeepSeek reasoning_content passback in run_query_engine.

DeepSeek thinking-mode endpoints reject requests where any historical assistant
message lacks ``reasoning_content``. The chat path
(bot/core.py:llm_tool_loop -> runtime/query_engine.py:run_query_engine)
must inject the field for DeepSeek, mirroring the autoagent path.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.tool_registry import ToolRegistry
from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.transcript_store import TranscriptStore, sanitize_tool_history


class _FakeLLM:
    def __init__(self, message_content: str = "ok"):
        self._content = message_content
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content, tool_calls=None)
                )
            ],
        )


def _seed_history(store: TranscriptStore, chat_id: str) -> None:
    store.append_user_message(chat_id, "first turn")
    store.append_assistant_message(chat_id, content="first reply")
    store.append_user_message(chat_id, "second turn")
    store.append_assistant_message(chat_id, content="second reply")


def test_passback_injects_reasoning_content_for_deepseek(tmp_path):
    llm = _FakeLLM()
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    _seed_history(transcript_store, "chat-deepseek")
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-deepseek",
                session_id=None,
                system_prompt="SYSTEM",
                user_message_content="/compact",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(
                model="deepseek-v4-pro",
                deepseek_reasoning_passback=True,
            ),
        )
    )

    sent_messages = llm.calls[0]["messages"]
    assistant_messages = [m for m in sent_messages if m.get("role") == "assistant"]
    assert assistant_messages, "history should include prior assistant messages"
    for m in assistant_messages:
        assert "reasoning_content" in m, (
            "assistant message must carry reasoning_content under DeepSeek passback"
        )
        assert m["reasoning_content"] == ""


def test_passback_disabled_by_default(tmp_path):
    llm = _FakeLLM()
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    _seed_history(transcript_store, "chat-default")
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-default",
                session_id=None,
                system_prompt="SYSTEM",
                user_message_content="hello",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="gpt-5.5"),
        )
    )

    sent_messages = llm.calls[0]["messages"]
    for m in sent_messages:
        if m.get("role") == "assistant":
            assert "reasoning_content" not in m


def test_passback_preserves_existing_reasoning_content(tmp_path):
    llm = _FakeLLM()
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    transcript_store.append_user_message("chat-preserved", "q1")
    history = transcript_store.get_or_create("chat-preserved")
    history.append(
        {
            "role": "assistant",
            "content": "a1",
            "reasoning_content": "thought through it",
        }
    )
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-preserved",
                session_id=None,
                system_prompt="SYSTEM",
                user_message_content="/plan",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(
                model="deepseek-v4-pro",
                deepseek_reasoning_passback=True,
            ),
        )
    )

    sent_messages = llm.calls[0]["messages"]
    assistant_messages = [m for m in sent_messages if m.get("role") == "assistant"]
    assert assistant_messages
    assert assistant_messages[0]["reasoning_content"] == "thought through it"

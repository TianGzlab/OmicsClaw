"""Tests for capturing and persisting DeepSeek reasoning_content.

Real reasoning_content from the API must round-trip into the transcript so
that subsequent requests echo back the actual values (not just an empty
placeholder injected by the passback shim). This is the forward-compatible
form of the DeepSeek thinking-mode contract.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from omicsclaw.runtime.context_budget import estimate_message_size
from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.tool_registry import ToolRegistry
from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.transcript_store import TranscriptStore, sanitize_tool_history


class _FakeNonStreamingLLM:
    def __init__(self, *, content: str, reasoning_content: str | None = None):
        self._content = content
        self._reasoning = reasoning_content
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self._content, tool_calls=None)
        if self._reasoning is not None:
            message.reasoning_content = self._reasoning
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=message)],
        )


class _FakeStreamResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeStreamingLLM:
    def __init__(self, *, content_chunks, reasoning_chunks):
        chunks = []
        for r in reasoning_chunks:
            chunks.append(
                SimpleNamespace(
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                reasoning_content=r,
                                tool_calls=None,
                            )
                        )
                    ],
                )
            )
        for c in content_chunks:
            chunks.append(
                SimpleNamespace(
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=c, tool_calls=None)
                        )
                    ],
                )
            )
        self._response = _FakeStreamResponse(chunks)
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_non_streaming_response_persists_reasoning_content(tmp_path):
    llm = _FakeNonStreamingLLM(content="hi back", reasoning_content="thought it through")
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-A",
                session_id=None,
                system_prompt="SYS",
                user_message_content="hi",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="deepseek-v4-pro"),
        )
    )

    history = transcript_store.get_history("chat-A")
    assistant = next(m for m in history if m.get("role") == "assistant")
    assert assistant["content"] == "hi back"
    assert assistant["reasoning_content"] == "thought it through"


def test_streaming_response_accumulates_reasoning_content(tmp_path):
    captured_reasoning: list[str] = []

    async def on_reasoning(chunk: str) -> None:
        captured_reasoning.append(chunk)

    async def on_content(chunk: str) -> None:
        pass

    llm = _FakeStreamingLLM(
        content_chunks=["Hello ", "world"],
        reasoning_chunks=["plan ", "first"],
    )
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-stream",
                session_id=None,
                system_prompt="SYS",
                user_message_content="hi",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="deepseek-v4-pro"),
            callbacks=QueryEngineCallbacks(
                on_stream_content=on_content,
                on_stream_reasoning=on_reasoning,
            ),
        )
    )

    # Streaming callback still sees per-chunk reasoning (existing behavior)
    assert "".join(captured_reasoning) == "plan first"

    # And the final assistant transcript message persists the joined value
    history = transcript_store.get_history("chat-stream")
    assistant = next(m for m in history if m.get("role") == "assistant")
    assert assistant["reasoning_content"] == "plan first"
    assert assistant["content"] == "Hello world"


def test_passback_preserves_real_reasoning_content_on_next_turn(tmp_path):
    """If reasoning_content is captured on turn 1, turn 2 should send it back."""
    llm = _FakeNonStreamingLLM(content="r1", reasoning_content="r1-thought")
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    # Turn 1
    asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-multi",
                session_id=None,
                system_prompt="SYS",
                user_message_content="q1",
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

    # Turn 2
    llm2 = _FakeNonStreamingLLM(content="r2")
    asyncio.run(
        run_query_engine(
            llm=llm2,
            context=QueryEngineContext(
                chat_id="chat-multi",
                session_id=None,
                system_prompt="SYS",
                user_message_content="q2",
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

    sent_messages = llm2.calls[0]["messages"]
    assistant_in_request = next(m for m in sent_messages if m.get("role") == "assistant")
    # Real reasoning is preserved (NOT replaced by the empty-string shim)
    assert assistant_in_request["reasoning_content"] == "r1-thought"


def test_message_size_estimator_counts_reasoning_content():
    msg = {
        "role": "assistant",
        "content": "hi",
        "reasoning_content": "x" * 500,
    }
    base = {"role": "assistant", "content": "hi"}
    assert estimate_message_size(msg) - estimate_message_size(base) >= 500

"""Tests for run_query_engine's on_context_compacted callback wiring."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from omicsclaw.runtime.context_compaction import (
    CompactionEvent,
    ContextCompactionConfig,
)
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
    def __init__(self):
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=None)
                )
            ],
        )


def _seed_long_history(store: TranscriptStore, chat_id: str, *, turns: int = 30) -> None:
    for i in range(turns):
        store.append_user_message(chat_id, f"user {i} " + "x" * 800)
        store.append_assistant_message(chat_id, content=f"assistant {i} " + "y" * 800)


def test_callback_fires_when_compaction_applied(tmp_path):
    captured: list[CompactionEvent] = []

    def on_compacted(event: CompactionEvent) -> None:
        captured.append(event)

    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    _seed_long_history(transcript_store, "chat-A")
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=_FakeLLM(),
            context=QueryEngineContext(
                chat_id="chat-A",
                session_id=None,
                system_prompt="SYS",
                user_message_content="hi",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(
                model="fake",
                # Tight budget to force compaction.
                context_compaction=ContextCompactionConfig(max_prompt_chars=8000),
            ),
            callbacks=QueryEngineCallbacks(on_context_compacted=on_compacted),
        )
    )

    assert len(captured) == 1
    event = captured[0]
    assert event.applied_stages
    assert event.messages_compressed >= 0
    assert event.tokens_saved_estimate >= 0


def test_callback_not_fired_when_no_compaction(tmp_path):
    captured: list[CompactionEvent] = []

    def on_compacted(event: CompactionEvent) -> None:
        captured.append(event)

    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    transcript_store.append_user_message("chat-B", "tiny first turn")
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    asyncio.run(
        run_query_engine(
            llm=_FakeLLM(),
            context=QueryEngineContext(
                chat_id="chat-B",
                session_id=None,
                system_prompt="SYS",
                user_message_content="hi",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake"),
            callbacks=QueryEngineCallbacks(on_context_compacted=on_compacted),
        )
    )

    assert captured == []


def test_callback_failure_does_not_abort_turn(tmp_path):
    """A raising callback must be swallowed; the turn must complete."""

    def on_compacted(event: CompactionEvent) -> None:
        raise RuntimeError("simulated callback failure")

    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    _seed_long_history(transcript_store, "chat-C")
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    final = asyncio.run(
        run_query_engine(
            llm=_FakeLLM(),
            context=QueryEngineContext(
                chat_id="chat-C",
                session_id=None,
                system_prompt="SYS",
                user_message_content="hi",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(
                model="fake",
                context_compaction=ContextCompactionConfig(max_prompt_chars=8000),
            ),
            callbacks=QueryEngineCallbacks(on_context_compacted=on_compacted),
        )
    )

    assert final == "ok"

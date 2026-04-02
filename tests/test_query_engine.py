"""Tests for the shared query engine runtime."""

import asyncio

from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.events import EVENT_SESSION_START, EVENT_TOOL_AFTER
from omicsclaw.runtime.hooks import (
    HOOK_MODE_CONTEXT,
    HOOK_MODE_NOTICE,
    LifecycleHookRuntime,
    LifecycleHookSpec,
)
from omicsclaw.runtime.policy import TOOL_POLICY_REQUIRE_APPROVAL
from omicsclaw.runtime.tool_registry import ToolRegistry
from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.tool_spec import APPROVAL_MODE_ASK, ToolSpec
from omicsclaw.runtime.transcript_store import TranscriptStore, sanitize_tool_history


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.usage = None
        self.choices = [_FakeChoice(message)]


class _FakeLLM:
    def __init__(self, responses=None, error=None):
        self._responses = list(responses or [])
        self._error = error
        self.calls = []
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._responses.pop(0)


class _FakeAPIError(Exception):
    pass


def test_run_query_engine_executes_tools_and_records_transcript(tmp_path):
    async def alpha_executor(args):
        return "alpha-result"

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            )
        ]
    ).build_runtime({"alpha": alpha_executor})

    llm = _FakeLLM(
        [
            _FakeResponse(
                _FakeMessage(
                    content="",
                    tool_calls=[_FakeToolCall("call-alpha", "alpha", "{}")],
                )
            ),
            _FakeResponse(_FakeMessage(content="done", tool_calls=None)),
        ]
    )
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    observed = {"before": [], "after": []}

    async def before_tool(request):
        observed["before"].append((request.call_id, request.name, request.arguments))
        return {"seen": True}

    async def after_tool(result, record, tool_state):
        observed["after"].append(
            (result.request.call_id, record.content, tool_state["seen"])
        )

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-1",
                session_id="session-1",
                system_prompt="SYSTEM",
                user_message_content="hello",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
            callbacks=QueryEngineCallbacks(before_tool=before_tool, after_tool=after_tool),
        )
    )

    assert result == "done"
    assert observed["before"] == [("call-alpha", "alpha", {})]
    assert observed["after"] == [("call-alpha", "alpha-result", True)]
    history = transcript_store.get_history("chat-1")
    assert history == [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-alpha",
                    "type": "function",
                    "function": {"name": "alpha", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-alpha", "content": "alpha-result"},
        {"role": "assistant", "content": "done"},
    ]


def test_run_query_engine_uses_llm_error_callback(tmp_path):
    llm = _FakeLLM(error=_FakeAPIError("boom"))
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    runtime = ToolRegistry([]).build_runtime({})

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-err",
                session_id=None,
                system_prompt="SYSTEM",
                user_message_content="hello",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
            callbacks=QueryEngineCallbacks(
                on_llm_error=lambda exc: f"handled: {exc}"
            ),
        )
    )

    assert result == "handled: boom"


def test_run_query_engine_records_policy_blocked_tool_results(tmp_path):
    observed = {"calls": 0}

    async def writer_executor(args):
        observed["calls"] += 1
        return "written"

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="writer",
                description="Writer tool",
                parameters={"type": "object", "properties": {}},
                approval_mode=APPROVAL_MODE_ASK,
                writes_workspace=True,
            )
        ]
    ).build_runtime({"writer": writer_executor})

    llm = _FakeLLM(
        [
            _FakeResponse(
                _FakeMessage(
                    content="",
                    tool_calls=[_FakeToolCall("call-writer", "writer", "{}")],
                )
            ),
            _FakeResponse(_FakeMessage(content="needs approval", tool_calls=None)),
        ]
    )
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-policy",
                session_id="session-policy",
                system_prompt="SYSTEM",
                user_message_content="please write a file",
                surface="cli",
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
        )
    )

    assert result == "needs approval"
    assert observed["calls"] == 0
    records = result_store.get_records("chat-policy")
    assert len(records) == 1
    assert records[0].policy_action == TOOL_POLICY_REQUIRE_APPROVAL
    assert "explicit approval" in records[0].policy_reason

    history = transcript_store.get_history("chat-policy")
    assert history[2]["role"] == "tool"
    assert history[2]["tool_call_id"] == "call-writer"
    assert "[tool policy blocked]" in history[2]["content"]


def test_run_query_engine_applies_session_context_hooks_and_tool_notices(tmp_path):
    async def alpha_executor(args):
        return "alpha-result"

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            )
        ]
    ).build_runtime({"alpha": alpha_executor})

    hook_runtime = LifecycleHookRuntime(
        [
            LifecycleHookSpec(
                name="session-sop",
                event=EVENT_SESSION_START,
                message="Follow lab SOP for {surface}.",
                mode=HOOK_MODE_CONTEXT,
            ),
            LifecycleHookSpec(
                name="tool-summary",
                event=EVENT_TOOL_AFTER,
                message="Hook summary for {tool_name}: {status}.",
                mode=HOOK_MODE_NOTICE,
            ),
        ]
    )

    llm = _FakeLLM(
        [
            _FakeResponse(
                _FakeMessage(
                    content="",
                    tool_calls=[_FakeToolCall("call-alpha", "alpha", "{}")],
                )
            ),
            _FakeResponse(_FakeMessage(content="done", tool_calls=None)),
        ]
    )
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-hook",
                session_id="session-hook",
                system_prompt="SYSTEM",
                user_message_content="hello",
                surface="cli",
                hook_runtime=hook_runtime,
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
            callbacks=QueryEngineCallbacks(),
        )
    )

    assert result == "done"
    assert "## Active Session Hooks" in llm.calls[0]["messages"][0]["content"]
    assert "Follow lab SOP for cli." in llm.calls[0]["messages"][0]["content"]

    history = transcript_store.get_history("chat-hook")
    assert "Hook summary for alpha: completed." in history[2]["content"]
    assert history[2]["content"].endswith("alpha-result")

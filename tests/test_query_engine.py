"""Tests for the shared query engine runtime."""

import asyncio
import json

from omicsclaw.extensions import (
    ExtensionManifest,
    extension_store_dir,
    write_extension_state,
    write_install_record,
)

from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.events import (
    EVENT_SESSION_START,
    EVENT_TOOL_AFTER,
    EVENT_TOOL_FAILURE,
)
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


def test_run_query_engine_merges_tool_runtime_context(tmp_path):
    observed = {}

    async def alpha_executor(args, workspace=None):
        observed["workspace"] = workspace
        return workspace or "<missing>"

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                context_params=("workspace",),
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

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-runtime",
                session_id="session-runtime",
                system_prompt="SYSTEM",
                user_message_content="hello",
                tool_runtime_context={"workspace": "/tmp/omics-workspace"},
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
        )
    )

    assert result == "done"
    assert observed["workspace"] == "/tmp/omics-workspace"


def test_run_query_engine_emits_failure_hooks_and_persists_execution_trace(tmp_path):
    async def broken_executor(args):
        raise RuntimeError("boom")

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="broken",
                description="Broken tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
    ).build_runtime({"broken": broken_executor})

    hook_runtime = LifecycleHookRuntime(
        [
            LifecycleHookSpec(
                name="tool-failure",
                event=EVENT_TOOL_FAILURE,
                message="Failure hook for {tool_name}: {status}.",
                mode=HOOK_MODE_NOTICE,
            ),
        ]
    )

    llm = _FakeLLM(
        [
            _FakeResponse(
                _FakeMessage(
                    content="",
                    tool_calls=[_FakeToolCall("call-broken", "broken", "{}")],
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
                chat_id="chat-failure",
                session_id="session-failure",
                system_prompt="SYSTEM",
                user_message_content="hello",
                surface="cli",
                hook_runtime=hook_runtime,
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
        )
    )

    assert result == "done"
    records = result_store.get_records("chat-failure")
    assert len(records) == 1
    assert records[0].execution_trace is not None
    assert records[0].execution_trace["tool_name"] == "broken"
    assert "execution" in records[0].execution_trace["phase_timings_ms"]

    history = transcript_store.get_history("chat-failure")
    assert "Failure hook for broken: failed." in history[2]["content"]


def test_run_query_engine_auto_loads_extension_tool_execution_hooks(tmp_path):
    observed = {}

    pack_dir = extension_store_dir(tmp_path, "prompt-pack") / "runtime-rules"
    pack_dir.mkdir(parents=True)
    (pack_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (pack_dir / "tool-hooks.json").write_text(
        json.dumps(
            {
                "tool_execution_hooks": [
                    {
                        "name": "rewrite-alpha",
                        "tools": ["alpha"],
                        "surfaces": ["cli"],
                        "pre": {
                            "set_arguments": {"path": "{workspace}/rewritten.txt"},
                        },
                        "post": {
                            "output_template": "{output}\npost:{workspace}",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = ExtensionManifest(
        name="runtime-rules",
        version="1.0.0",
        type="prompt-pack",
        entrypoints=["rules.md"],
        tool_execution_hooks=["tool-hooks.json"],
        trusted_capabilities=["runtime-policy"],
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
                "tool_execution_hooks": manifest.tool_execution_hooks,
                "trusted_capabilities": manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        pack_dir,
        extension_name="runtime-rules",
        source_kind="local",
        source="/tmp/runtime-rules",
        manifest=manifest,
        extension_type="prompt-pack",
        relative_install_path="installed_extensions/prompt-packs/runtime-rules",
    )
    write_extension_state(pack_dir, enabled=True)

    async def alpha_executor(args):
        observed["args"] = dict(args)
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

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-runtime-hooks",
                session_id="session-runtime-hooks",
                system_prompt="SYSTEM",
                user_message_content="hello",
                surface="cli",
                tool_runtime_context={
                    "omicsclaw_dir": str(tmp_path),
                    "workspace": "/tmp/omics-workspace",
                },
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
        )
    )

    assert result == "done"
    assert observed["args"] == {"path": "/tmp/omics-workspace/rewritten.txt"}
    records = result_store.get_records("chat-runtime-hooks")
    assert len(records) == 1
    assert records[0].execution_trace is not None
    assert (
        records[0].execution_trace["pre_hook_records"][0]["metadata"]["extension_name"]
        == "runtime-rules"
    )
    assert (
        records[0].execution_trace["post_hook_records"][0]["metadata"]["extension_name"]
        == "runtime-rules"
    )

    history = transcript_store.get_history("chat-runtime-hooks")
    assert history[2]["content"] == "alpha-result\npost:/tmp/omics-workspace"


def test_run_query_engine_extension_tool_execution_hook_can_require_approval(tmp_path):
    observed = {"calls": 0}

    pack_dir = extension_store_dir(tmp_path, "prompt-pack") / "runtime-gates"
    pack_dir.mkdir(parents=True)
    (pack_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (pack_dir / "tool-hooks.json").write_text(
        json.dumps(
            {
                "tool_execution_hooks": [
                    {
                        "name": "confirm-writer",
                        "tools": ["writer"],
                        "surfaces": ["cli"],
                        "pre": {
                            "action": "ask",
                            "message": "Confirm writer access for {surface}.",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = ExtensionManifest(
        name="runtime-gates",
        version="1.0.0",
        type="prompt-pack",
        entrypoints=["rules.md"],
        tool_execution_hooks=["tool-hooks.json"],
        trusted_capabilities=["runtime-policy"],
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
                "tool_execution_hooks": manifest.tool_execution_hooks,
                "trusted_capabilities": manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        pack_dir,
        extension_name="runtime-gates",
        source_kind="local",
        source="/tmp/runtime-gates",
        manifest=manifest,
        extension_type="prompt-pack",
        relative_install_path="installed_extensions/prompt-packs/runtime-gates",
    )
    write_extension_state(pack_dir, enabled=True)

    async def writer_executor(args):
        observed["calls"] += 1
        return "written"

    runtime = ToolRegistry(
        [
            ToolSpec(
                name="writer",
                description="Writer tool",
                parameters={"type": "object", "properties": {}},
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
            _FakeResponse(_FakeMessage(content="needs confirmation", tool_calls=None)),
        ]
    )
    transcript_store = TranscriptStore(sanitizer=sanitize_tool_history)
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")

    result = asyncio.run(
        run_query_engine(
            llm=llm,
            context=QueryEngineContext(
                chat_id="chat-runtime-gates",
                session_id="session-runtime-gates",
                system_prompt="SYSTEM",
                user_message_content="write something",
                surface="cli",
                tool_runtime_context={
                    "omicsclaw_dir": str(tmp_path),
                },
            ),
            tool_runtime=runtime,
            transcript_store=transcript_store,
            tool_result_store=result_store,
            config=QueryEngineConfig(model="fake-model", llm_error_types=(_FakeAPIError,)),
        )
    )

    assert result == "needs confirmation"
    assert observed["calls"] == 0
    records = result_store.get_records("chat-runtime-gates")
    assert len(records) == 1
    assert records[0].policy_action == TOOL_POLICY_REQUIRE_APPROVAL
    assert "Confirm writer access for cli." in (records[0].policy_reason or "")

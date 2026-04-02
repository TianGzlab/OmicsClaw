"""Tests for the shared tool runtime primitives."""

import asyncio

import pytest

from omicsclaw.runtime.policy import (
    TOOL_POLICY_DENY,
    TOOL_POLICY_REQUIRE_APPROVAL,
    evaluate_tool_policy,
)
from omicsclaw.runtime.tool_executor import build_executor_kwargs, invoke_tool
from omicsclaw.runtime.tool_orchestration import (
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_HOOK_BLOCKED,
    EXECUTION_STATUS_INPUT_SCHEMA_INVALID,
    EXECUTION_STATUS_INPUT_VALIDATION_FAILED,
    EXECUTION_STATUS_POLICY_BLOCKED,
    ToolExecutionHook,
    ToolExecutionHookResult,
    ToolExecutionRequest,
    execute_tool_requests,
)
from omicsclaw.runtime.tool_registry import ToolRegistry
from omicsclaw.runtime.tool_spec import (
    APPROVAL_MODE_ASK,
    APPROVAL_MODE_DENY_UNLESS_TRUSTED,
    RISK_LEVEL_HIGH,
    ToolSpec,
)
from omicsclaw.runtime.tool_validation import ToolInputValidationResult


def test_tool_registry_builds_openai_tools_and_executors_from_same_specs():
    def alpha_executor(args):
        return args

    def beta_executor(args):
        return args

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
            ToolSpec(
                name="beta",
                description="Beta tool",
                parameters={"type": "object", "properties": {}},
            ),
        ]
    )

    runtime = registry.build_runtime(
        {
            "alpha": alpha_executor,
            "beta": beta_executor,
        }
    )

    assert [tool["function"]["name"] for tool in runtime.openai_tools] == ["alpha", "beta"]
    assert runtime.executors["alpha"] is alpha_executor
    assert runtime.executors["beta"] is beta_executor
    assert runtime.specs_by_name["alpha"].name == "alpha"


def test_tool_registry_rejects_missing_executor():
    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )

    with pytest.raises(KeyError, match="Missing tool executors"):
        registry.build_runtime({})


def test_tool_registry_rejects_duplicate_names():
    with pytest.raises(ValueError, match="Duplicate tool name"):
        ToolRegistry(
            [
                ToolSpec(
                    name="alpha",
                    description="Alpha tool",
                    parameters={"type": "object", "properties": {}},
                ),
                ToolSpec(
                    name="alpha",
                    description="Duplicate alpha tool",
                    parameters={"type": "object", "properties": {}},
                ),
            ]
        )


def test_build_executor_kwargs_uses_declared_context_only():
    spec = ToolSpec(
        name="alpha",
        description="Alpha tool",
        parameters={"type": "object", "properties": {}},
        context_params=("session_id", "chat_id"),
    )

    kwargs = build_executor_kwargs(
        spec,
        {
            "session_id": "sess-1",
            "chat_id": "chat-1",
            "ignored": "value",
        },
    )

    assert kwargs == {
        "session_id": "sess-1",
        "chat_id": "chat-1",
    }


def test_invoke_tool_passes_runtime_context_kwargs():
    calls = {}

    async def alpha_executor(args, session_id=None, chat_id=None):
        calls["args"] = args
        calls["session_id"] = session_id
        calls["chat_id"] = chat_id
        return "ok"

    spec = ToolSpec(
        name="alpha",
        description="Alpha tool",
        parameters={"type": "object", "properties": {}},
        context_params=("session_id", "chat_id"),
    )

    result = asyncio.run(
        invoke_tool(
            spec,
            alpha_executor,
            {"hello": "world"},
            runtime_context={
                "session_id": "sess-1",
                "chat_id": "chat-1",
            },
        )
    )

    assert result == "ok"
    assert calls == {
        "args": {"hello": "world"},
        "session_id": "sess-1",
        "chat_id": "chat-1",
    }


def test_execute_tool_requests_runs_safe_reads_concurrently():
    both_started = asyncio.Event()
    started: list[str] = []

    async def alpha_executor(args):
        started.append("alpha")
        if len(started) == 2:
            both_started.set()
        await both_started.wait()
        return "alpha"

    async def beta_executor(args):
        started.append("beta")
        if len(started) == 2:
            both_started.set()
        await both_started.wait()
        return "beta"

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
            ToolSpec(
                name="beta",
                description="Beta tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor, "beta": beta_executor})
    requests = [
        ToolExecutionRequest(
            call_id="call-alpha",
            name="alpha",
            arguments={},
            spec=runtime.specs_by_name["alpha"],
            executor=runtime.executors["alpha"],
        ),
        ToolExecutionRequest(
            call_id="call-beta",
            name="beta",
            arguments={},
            spec=runtime.specs_by_name["beta"],
            executor=runtime.executors["beta"],
        ),
    ]

    results = asyncio.run(asyncio.wait_for(execute_tool_requests(requests), timeout=0.2))

    assert [result.output for result in results] == ["alpha", "beta"]
    assert started == ["alpha", "beta"]


def test_execute_tool_requests_preserves_write_barriers_and_order():
    write_completed = asyncio.Event()
    observed: list[tuple[str, bool]] = []

    async def alpha_executor(args):
        observed.append(("alpha", write_completed.is_set()))
        return "alpha"

    async def writer_executor(args):
        observed.append(("writer", write_completed.is_set()))
        write_completed.set()
        return "writer"

    async def beta_executor(args):
        observed.append(("beta", write_completed.is_set()))
        return "beta"

    async def gamma_executor(args):
        observed.append(("gamma", write_completed.is_set()))
        return "gamma"

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
            ToolSpec(
                name="writer",
                description="Writer tool",
                parameters={"type": "object", "properties": {}},
            ),
            ToolSpec(
                name="beta",
                description="Beta tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
            ToolSpec(
                name="gamma",
                description="Gamma tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
        ]
    )
    runtime = registry.build_runtime(
        {
            "alpha": alpha_executor,
            "writer": writer_executor,
            "beta": beta_executor,
            "gamma": gamma_executor,
        }
    )
    requests = [
        ToolExecutionRequest(
            call_id="call-alpha",
            name="alpha",
            arguments={},
            spec=runtime.specs_by_name["alpha"],
            executor=runtime.executors["alpha"],
        ),
        ToolExecutionRequest(
            call_id="call-writer",
            name="writer",
            arguments={},
            spec=runtime.specs_by_name["writer"],
            executor=runtime.executors["writer"],
        ),
        ToolExecutionRequest(
            call_id="call-beta",
            name="beta",
            arguments={},
            spec=runtime.specs_by_name["beta"],
            executor=runtime.executors["beta"],
        ),
        ToolExecutionRequest(
            call_id="call-gamma",
            name="gamma",
            arguments={},
            spec=runtime.specs_by_name["gamma"],
            executor=runtime.executors["gamma"],
        ),
    ]

    results = asyncio.run(execute_tool_requests(requests))

    assert [result.output for result in results] == ["alpha", "writer", "beta", "gamma"]
    assert observed == [
        ("alpha", False),
        ("writer", False),
        ("beta", True),
        ("gamma", True),
    ]


def test_execute_tool_requests_wraps_errors_and_unknown_tools_without_aborting_bundle():
    async def broken_executor(args):
        raise RuntimeError("boom")

    async def ok_executor(args):
        return "ok"

    registry = ToolRegistry(
        [
            ToolSpec(
                name="broken",
                description="Broken tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
            ToolSpec(
                name="ok",
                description="OK tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
        ]
    )
    runtime = registry.build_runtime({"broken": broken_executor, "ok": ok_executor})
    requests = [
        ToolExecutionRequest(
            call_id="call-broken",
            name="broken",
            arguments={},
            spec=runtime.specs_by_name["broken"],
            executor=runtime.executors["broken"],
        ),
        ToolExecutionRequest(
            call_id="call-ok",
            name="ok",
            arguments={},
            spec=runtime.specs_by_name["ok"],
            executor=runtime.executors["ok"],
        ),
        ToolExecutionRequest(
            call_id="call-unknown",
            name="unknown",
            arguments={},
            spec=None,
            executor=None,
        ),
    ]

    results = asyncio.run(execute_tool_requests(requests))

    assert [result.output for result in results] == [
        "Error executing broken: RuntimeError: boom",
        "ok",
        "Unknown tool: unknown",
    ]
    assert results[0].success is False
    assert isinstance(results[0].error, RuntimeError)
    assert results[1].success is True
    assert results[2].success is False
    assert results[2].error is None


def test_evaluate_tool_policy_enforces_approval_and_trust_modes():
    approval_spec = ToolSpec(
        name="writer",
        description="Writer tool",
        parameters={"type": "object", "properties": {}},
        approval_mode=APPROVAL_MODE_ASK,
        risk_level=RISK_LEVEL_HIGH,
        writes_workspace=True,
    )
    approval_decision = evaluate_tool_policy(
        "writer",
        approval_spec,
        runtime_context={"surface": "bot"},
    )

    assert approval_decision is not None
    assert approval_decision.action == TOOL_POLICY_REQUIRE_APPROVAL
    assert approval_decision.surface == "bot"
    assert "explicit approval" in approval_decision.reason

    trusted_spec = ToolSpec(
        name="trusted-only",
        description="Trusted-only tool",
        parameters={"type": "object", "properties": {}},
        approval_mode=APPROVAL_MODE_DENY_UNLESS_TRUSTED,
        writes_config=True,
    )
    trusted_decision = evaluate_tool_policy(
        "trusted-only",
        trusted_spec,
        runtime_context={"surface": "bot"},
    )

    assert trusted_decision is not None
    assert trusted_decision.action == TOOL_POLICY_DENY
    assert "trusted runtime contexts" in trusted_decision.reason


def test_execute_tool_requests_blocks_policy_gated_tool_without_running_executor():
    calls = {"writer": 0, "reader": 0}

    async def writer_executor(args):
        calls["writer"] += 1
        return "writer"

    async def reader_executor(args):
        calls["reader"] += 1
        return "reader"

    registry = ToolRegistry(
        [
            ToolSpec(
                name="writer",
                description="Writer tool",
                parameters={"type": "object", "properties": {}},
                approval_mode=APPROVAL_MODE_ASK,
                risk_level=RISK_LEVEL_HIGH,
                writes_workspace=True,
            ),
            ToolSpec(
                name="reader",
                description="Reader tool",
                parameters={"type": "object", "properties": {}},
                read_only=True,
                concurrency_safe=True,
            ),
        ]
    )
    runtime = registry.build_runtime(
        {
            "writer": writer_executor,
            "reader": reader_executor,
        }
    )
    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-writer",
                    name="writer",
                    arguments={},
                    spec=runtime.specs_by_name["writer"],
                    executor=runtime.executors["writer"],
                    runtime_context={"surface": "bot"},
                ),
                ToolExecutionRequest(
                    call_id="call-reader",
                    name="reader",
                    arguments={},
                    spec=runtime.specs_by_name["reader"],
                    executor=runtime.executors["reader"],
                    runtime_context={"surface": "bot"},
                ),
            ]
        )
    )

    assert calls == {"writer": 0, "reader": 1}
    assert results[0].success is False
    assert results[0].status == EXECUTION_STATUS_POLICY_BLOCKED
    assert results[0].policy_decision is not None
    assert results[0].policy_decision.action == TOOL_POLICY_REQUIRE_APPROVAL
    assert "[tool policy blocked]" in str(results[0].output)
    assert results[1].output == "reader"


def test_execute_tool_requests_rejects_invalid_schema_without_running_executor():
    calls = {"alpha": 0}

    async def alpha_executor(args):
        calls["alpha"] += 1
        return "ok"

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "lines": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            )
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={"path": 123, "lines": "ten"},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                )
            ]
        )
    )

    assert calls["alpha"] == 0
    assert results[0].success is False
    assert results[0].status == EXECUTION_STATUS_INPUT_SCHEMA_INVALID
    assert "input.path must be a string" in str(results[0].output)
    assert results[0].trace is not None
    assert results[0].trace.schema_errors


def test_execute_tool_requests_runs_tool_level_input_validator():
    calls = {"alpha": 0}

    async def alpha_executor(args):
        calls["alpha"] += 1
        return "ok"

    def validate_alpha(args, runtime_context=None):
        if int(args.get("end", 0)) < int(args.get("start", 0)):
            return ToolInputValidationResult(
                valid=False,
                message="end must be >= start",
            )
        return ToolInputValidationResult(valid=True)

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    "required": ["start", "end"],
                },
                input_validator=validate_alpha,
            )
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={"start": 9, "end": 3},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                )
            ]
        )
    )

    assert calls["alpha"] == 0
    assert results[0].status == EXECUTION_STATUS_INPUT_VALIDATION_FAILED
    assert results[0].trace is not None
    assert results[0].trace.input_validation.message == "end must be >= start"


def test_execute_tool_requests_applies_pre_hook_argument_updates_and_post_hook_output_updates():
    observed = {}

    async def alpha_executor(args):
        observed["args"] = dict(args)
        return "alpha"

    hook = ToolExecutionHook(
        name="rewrite-hook",
        pre_tool=lambda request, arguments, runtime_context: ToolExecutionHookResult(
            updated_arguments={**arguments, "path": "rewritten.txt"}
        ),
        post_tool=lambda request, output, trace, runtime_context: ToolExecutionHookResult(
            updated_output=f"{output}-post"
        ),
    )

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={"path": "original.txt"},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                    runtime_context={"tool_execution_hooks": [hook]},
                )
            ]
        )
    )

    assert observed["args"] == {"path": "rewritten.txt"}
    assert results[0].output == "alpha-post"
    assert results[0].trace is not None
    assert results[0].trace.effective_arguments == {"path": "rewritten.txt"}
    assert results[0].trace.pre_hook_records[0].updated_arguments is True
    assert results[0].trace.post_hook_records[0].updated_output is True


def test_execute_tool_requests_blocks_when_pre_hook_denies():
    calls = {"alpha": 0}

    async def alpha_executor(args):
        calls["alpha"] += 1
        return "alpha"

    hook = ToolExecutionHook(
        name="deny-hook",
        pre_tool=lambda request, arguments, runtime_context: ToolExecutionHookResult(
            action=TOOL_POLICY_DENY,
            message="blocked by hook",
        ),
    )

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                    runtime_context={"tool_execution_hooks": [hook]},
                )
            ]
        )
    )

    assert calls["alpha"] == 0
    assert results[0].status == EXECUTION_STATUS_HOOK_BLOCKED
    assert results[0].policy_decision is not None
    assert results[0].policy_decision.action == TOOL_POLICY_DENY
    assert "blocked by hook" in str(results[0].output)


def test_execute_tool_requests_runs_failure_hooks_and_records_trace():
    async def broken_executor(args):
        raise RuntimeError("boom")

    hook = ToolExecutionHook(
        name="failure-hook",
        on_failure=lambda request, error, output, trace, runtime_context: ToolExecutionHookResult(
            updated_output=f"{output}\nhandled-by-hook"
        ),
    )

    registry = ToolRegistry(
        [
            ToolSpec(
                name="broken",
                description="Broken tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    runtime = registry.build_runtime({"broken": broken_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-broken",
                    name="broken",
                    arguments={},
                    spec=runtime.specs_by_name["broken"],
                    executor=runtime.executors["broken"],
                    runtime_context={"tool_execution_hooks": [hook]},
                )
            ]
        )
    )

    assert results[0].success is False
    assert results[0].status == EXECUTION_STATUS_FAILED
    assert results[0].trace is not None
    assert results[0].trace.failure_hook_records[0].updated_output is True
    assert "handled-by-hook" in str(results[0].output)


def test_execute_tool_requests_records_speculative_classifier_trace():
    async def alpha_executor(args):
        return "ok"

    async def classify_alpha(args, runtime_context=None):
        await asyncio.sleep(0)
        return {"label": "workspace_mutation", "risk": "medium"}

    registry = ToolRegistry(
        [
            ToolSpec(
                name="alpha",
                description="Alpha tool",
                parameters={"type": "object", "properties": {}},
                speculative_classifier=classify_alpha,
            )
        ]
    )
    runtime = registry.build_runtime({"alpha": alpha_executor})

    results = asyncio.run(
        execute_tool_requests(
            [
                ToolExecutionRequest(
                    call_id="call-alpha",
                    name="alpha",
                    arguments={},
                    spec=runtime.specs_by_name["alpha"],
                    executor=runtime.executors["alpha"],
                )
            ]
        )
    )

    assert results[0].success is True
    assert results[0].trace is not None
    assert results[0].trace.classifier_result == {
        "label": "workspace_mutation",
        "risk": "medium",
    }

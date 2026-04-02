from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .policy import (
    TOOL_POLICY_ALLOW,
    TOOL_POLICY_DENY,
    TOOL_POLICY_REQUIRE_APPROVAL,
    ToolPolicyDecision,
    evaluate_tool_policy,
    format_policy_block_message,
)
from .tool_executor import ToolCallable, invoke_tool
from .tool_spec import ToolSpec
from .tool_validation import (
    ToolInputValidationResult,
    normalize_input_validation_result,
    validate_arguments_against_schema,
)

EXECUTION_STATUS_COMPLETED = "completed"
EXECUTION_STATUS_FAILED = "failed"
EXECUTION_STATUS_HOOK_BLOCKED = "hook_blocked"
EXECUTION_STATUS_INPUT_SCHEMA_INVALID = "input_schema_invalid"
EXECUTION_STATUS_INPUT_VALIDATION_FAILED = "input_validation_failed"
EXECUTION_STATUS_POLICY_BLOCKED = "policy_blocked"
EXECUTION_STATUS_UNKNOWN_TOOL = "unknown_tool"

_HOOK_OUTPUT_UNSET = object()


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    call_id: str
    name: str
    arguments: dict[str, Any]
    spec: ToolSpec | None
    executor: ToolCallable | None
    runtime_context: dict[str, Any] | None = None
    policy_decision: ToolPolicyDecision | None = None

    @property
    def can_run_concurrently(self) -> bool:
        policy_decision = _resolve_policy_decision(self)
        return bool(
            policy_decision
            and policy_decision.allows_execution
            and self.spec
            and self.executor
            and self.spec.read_only
            and self.spec.concurrency_safe
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionHookResult:
    action: str = TOOL_POLICY_ALLOW
    message: str = ""
    updated_arguments: dict[str, Any] | None = None
    updated_output: Any = _HOOK_OUTPUT_UNSET
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolExecutionHook:
    name: str
    pre_tool: ToolCallable | None = None
    post_tool: ToolCallable | None = None
    on_failure: ToolCallable | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionHookRecord:
    hook_name: str
    stage: str
    action: str
    success: bool
    duration_ms: float
    message: str = ""
    error: str = ""
    updated_arguments: bool = False
    updated_output: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_name": self.hook_name,
            "stage": self.stage,
            "action": self.action,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 3),
            "message": self.message,
            "error": self.error,
            "updated_arguments": self.updated_arguments,
            "updated_output": self.updated_output,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ToolExecutionTrace:
    tool_name: str
    requested_arguments: dict[str, Any] = field(default_factory=dict)
    effective_arguments: dict[str, Any] = field(default_factory=dict)
    mcp_metadata: dict[str, Any] = field(default_factory=dict)
    classifier_result: dict[str, Any] = field(default_factory=dict)
    schema_errors: tuple[str, ...] = ()
    input_validation: ToolInputValidationResult = field(
        default_factory=lambda: ToolInputValidationResult(valid=True)
    )
    pre_hook_records: list[ToolExecutionHookRecord] = field(default_factory=list)
    post_hook_records: list[ToolExecutionHookRecord] = field(default_factory=list)
    failure_hook_records: list[ToolExecutionHookRecord] = field(default_factory=list)
    phase_timings_ms: dict[str, float] = field(default_factory=dict)
    blocked_by: str = ""
    block_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "requested_arguments": dict(self.requested_arguments),
            "effective_arguments": dict(self.effective_arguments),
            "mcp_metadata": dict(self.mcp_metadata),
            "classifier_result": dict(self.classifier_result),
            "schema_errors": list(self.schema_errors),
            "input_validation": {
                "valid": self.input_validation.valid,
                "message": self.input_validation.message,
                "normalized_arguments": (
                    dict(self.input_validation.normalized_arguments)
                    if self.input_validation.normalized_arguments is not None
                    else None
                ),
                "metadata": dict(self.input_validation.metadata or {}),
            },
            "pre_hook_records": [record.to_dict() for record in self.pre_hook_records],
            "post_hook_records": [record.to_dict() for record in self.post_hook_records],
            "failure_hook_records": [
                record.to_dict() for record in self.failure_hook_records
            ],
            "phase_timings_ms": {
                key: round(value, 3)
                for key, value in self.phase_timings_ms.items()
            },
            "blocked_by": self.blocked_by,
            "block_message": self.block_message,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    request: ToolExecutionRequest
    output: Any
    success: bool
    error: Exception | None = None
    status: str = EXECUTION_STATUS_COMPLETED
    policy_decision: ToolPolicyDecision | None = None
    trace: ToolExecutionTrace | None = None


def _resolve_policy_decision(
    request: ToolExecutionRequest,
) -> ToolPolicyDecision | None:
    if request.policy_decision is not None:
        return request.policy_decision
    return evaluate_tool_policy(
        request.name,
        request.spec,
        runtime_context=request.runtime_context,
    )


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _mark_timing(trace: ToolExecutionTrace, phase: str, started_at: float) -> None:
    trace.phase_timings_ms[phase] = (time.perf_counter() - started_at) * 1000.0


def _extract_mcp_metadata(request: ToolExecutionRequest) -> dict[str, Any]:
    if request.name.startswith("mcp__"):
        parts = request.name.split("__", 2)
        payload = {"is_mcp": True}
        if len(parts) >= 2:
            payload["server"] = parts[1]
        if len(parts) >= 3:
            payload["tool"] = parts[2]
        return payload
    if request.spec is not None and "mcp" in request.spec.policy_tags:
        return {"is_mcp": True, "tool": request.name}
    return {}


def _resolve_hooks(
    runtime_context: Mapping[str, Any] | None,
) -> tuple[ToolExecutionHook, ...]:
    if not runtime_context:
        return ()
    hooks = runtime_context.get("tool_execution_hooks")
    if not isinstance(hooks, (list, tuple)):
        return ()
    return tuple(hook for hook in hooks if isinstance(hook, ToolExecutionHook))


def _normalize_hook_result(value: Any) -> ToolExecutionHookResult:
    if value is None:
        return ToolExecutionHookResult()
    if isinstance(value, ToolExecutionHookResult):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ToolExecutionHookResult()
        return ToolExecutionHookResult(message=text)
    if isinstance(value, Mapping):
        updated_arguments = value.get("updated_arguments")
        if updated_arguments is not None and not isinstance(updated_arguments, Mapping):
            raise TypeError("updated_arguments must be a mapping when provided")
        return ToolExecutionHookResult(
            action=str(value.get("action", TOOL_POLICY_ALLOW) or TOOL_POLICY_ALLOW),
            message=str(value.get("message", "") or "").strip(),
            updated_arguments=dict(updated_arguments) if updated_arguments is not None else None,
            updated_output=value.get("updated_output", _HOOK_OUTPUT_UNSET),
            metadata=dict(value.get("metadata", {}) or {}),
        )
    raise TypeError(f"Unsupported tool hook result: {type(value)!r}")


def _synthetic_policy_decision(
    request: ToolExecutionRequest,
    *,
    action: str,
    reason: str,
) -> ToolPolicyDecision:
    spec = request.spec
    return ToolPolicyDecision(
        action=action,
        reason=reason,
        risk_level=str((spec.risk_level if spec else "low") or "low"),
        approval_mode=str((spec.approval_mode if spec else "auto") or "auto"),
        writes_workspace=bool(spec.writes_workspace if spec else False),
        writes_config=bool(spec.writes_config if spec else False),
        touches_network=bool(spec.touches_network if spec else False),
        allowed_in_background=bool(spec.allowed_in_background if spec else True),
        policy_tags=tuple(spec.policy_tags if spec else ()),
        surface=str((request.runtime_context or {}).get("surface", "") or ""),
        background=bool((request.runtime_context or {}).get("background", False)),
        trusted=bool((request.runtime_context or {}).get("trusted", False)),
        hint=(
            "Ask the user to confirm this action, then retry the request."
            if action == TOOL_POLICY_REQUIRE_APPROVAL
            else "Choose a safer alternative or run from a trusted context."
            if action == TOOL_POLICY_DENY
            else ""
        ),
    )


def _classifier_policy_decision(
    request: ToolExecutionRequest,
    classifier_result: Mapping[str, Any] | None,
) -> ToolPolicyDecision | None:
    if not isinstance(classifier_result, Mapping):
        return None
    action = str(
        classifier_result.get("policy_action")
        or classifier_result.get("action")
        or ""
    ).strip()
    if action not in {TOOL_POLICY_DENY, TOOL_POLICY_REQUIRE_APPROVAL}:
        return None
    reason = str(
        classifier_result.get("reason")
        or classifier_result.get("message")
        or f"classifier requested {action}"
    ).strip()
    return _synthetic_policy_decision(
        request,
        action=action,
        reason=reason,
    )


def _more_restrictive_policy(
    primary: ToolPolicyDecision | None,
    secondary: ToolPolicyDecision | None,
) -> ToolPolicyDecision | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    rank = {
        TOOL_POLICY_ALLOW: 0,
        TOOL_POLICY_REQUIRE_APPROVAL: 1,
        TOOL_POLICY_DENY: 2,
    }
    if rank.get(secondary.action, 0) > rank.get(primary.action, 0):
        return secondary
    return primary


async def _run_pre_hooks(
    request: ToolExecutionRequest,
    *,
    arguments: dict[str, Any],
    hooks: tuple[ToolExecutionHook, ...],
    trace: ToolExecutionTrace,
) -> tuple[dict[str, Any], ToolExecutionHookResult | None]:
    current_arguments = dict(arguments)
    for hook in hooks:
        if hook.pre_tool is None:
            continue
        started_at = time.perf_counter()
        try:
            raw_result = await _maybe_await(
                hook.pre_tool(request, dict(current_arguments), request.runtime_context)
            )
            result = _normalize_hook_result(raw_result)
            if result.updated_arguments is not None:
                current_arguments = dict(result.updated_arguments)
            trace.pre_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="pre",
                    action=result.action,
                    success=True,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    message=result.message,
                    updated_arguments=result.updated_arguments is not None,
                    metadata=dict(result.metadata),
                )
            )
            if result.action in {TOOL_POLICY_DENY, TOOL_POLICY_REQUIRE_APPROVAL}:
                return current_arguments, result
        except Exception as exc:
            trace.pre_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="pre",
                    action="error",
                    success=False,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return current_arguments, None


async def _run_post_hooks(
    request: ToolExecutionRequest,
    *,
    output: Any,
    hooks: tuple[ToolExecutionHook, ...],
    trace: ToolExecutionTrace,
) -> Any:
    current_output = output
    for hook in hooks:
        if hook.post_tool is None:
            continue
        started_at = time.perf_counter()
        try:
            raw_result = await _maybe_await(
                hook.post_tool(request, current_output, trace, request.runtime_context)
            )
            result = _normalize_hook_result(raw_result)
            if result.updated_output is not _HOOK_OUTPUT_UNSET:
                current_output = result.updated_output
            trace.post_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="post",
                    action=result.action,
                    success=True,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    message=result.message,
                    updated_output=result.updated_output is not _HOOK_OUTPUT_UNSET,
                    metadata=dict(result.metadata),
                )
            )
        except Exception as exc:
            trace.post_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="post",
                    action="error",
                    success=False,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return current_output


async def _run_failure_hooks(
    request: ToolExecutionRequest,
    *,
    error: Exception | None,
    output: Any,
    hooks: tuple[ToolExecutionHook, ...],
    trace: ToolExecutionTrace,
) -> Any:
    current_output = output
    for hook in hooks:
        if hook.on_failure is None:
            continue
        started_at = time.perf_counter()
        try:
            raw_result = await _maybe_await(
                hook.on_failure(
                    request,
                    error,
                    current_output,
                    trace,
                    request.runtime_context,
                )
            )
            result = _normalize_hook_result(raw_result)
            if result.updated_output is not _HOOK_OUTPUT_UNSET:
                current_output = result.updated_output
            trace.failure_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="failure",
                    action=result.action,
                    success=True,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    message=result.message,
                    updated_output=result.updated_output is not _HOOK_OUTPUT_UNSET,
                    metadata=dict(result.metadata),
                )
            )
        except Exception as exc:
            trace.failure_hook_records.append(
                ToolExecutionHookRecord(
                    hook_name=hook.name,
                    stage="failure",
                    action="error",
                    success=False,
                    duration_ms=(time.perf_counter() - started_at) * 1000.0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return current_output


async def _run_speculative_classifier(
    request: ToolExecutionRequest,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if request.spec is None or request.spec.speculative_classifier is None:
        return {}
    try:
        result = await _maybe_await(
            request.spec.speculative_classifier(arguments, request.runtime_context)
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    if result is None:
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    return {"label": str(result)}


async def _execute_single_request(request: ToolExecutionRequest) -> ToolExecutionResult:
    trace = ToolExecutionTrace(
        tool_name=request.name,
        requested_arguments=dict(request.arguments or {}),
        effective_arguments=dict(request.arguments or {}),
        mcp_metadata=_extract_mcp_metadata(request),
    )

    if request.spec is None or request.executor is None:
        return ToolExecutionResult(
            request=request,
            output=f"Unknown tool: {request.name}",
            success=False,
            status=EXECUTION_STATUS_UNKNOWN_TOOL,
            trace=trace,
        )

    schema_started_at = time.perf_counter()
    schema_errors = validate_arguments_against_schema(request.arguments, request.spec.parameters)
    _mark_timing(trace, "schema_validation", schema_started_at)
    trace.schema_errors = tuple(schema_errors)
    if schema_errors:
        return ToolExecutionResult(
            request=request,
            output=(
                f"Input schema validation failed for {request.name}: "
                + "; ".join(schema_errors)
            ),
            success=False,
            status=EXECUTION_STATUS_INPUT_SCHEMA_INVALID,
            trace=trace,
        )

    effective_arguments = dict(request.arguments or {})

    validation_started_at = time.perf_counter()
    if request.spec.input_validator is not None:
        try:
            raw_validation = await _maybe_await(
                request.spec.input_validator(effective_arguments, request.runtime_context)
            )
            trace.input_validation = normalize_input_validation_result(raw_validation)
            if trace.input_validation.normalized_arguments is not None:
                effective_arguments = dict(trace.input_validation.normalized_arguments)
        except Exception as exc:
            trace.input_validation = ToolInputValidationResult(
                valid=False,
                message=f"Input validator crashed for {request.name}: {type(exc).__name__}: {exc}",
            )
    _mark_timing(trace, "input_validation", validation_started_at)
    if not trace.input_validation.valid:
        trace.effective_arguments = dict(effective_arguments)
        return ToolExecutionResult(
            request=request,
            output=(
                trace.input_validation.message
                or f"Input validation failed for {request.name}"
            ),
            success=False,
            status=EXECUTION_STATUS_INPUT_VALIDATION_FAILED,
            trace=trace,
        )

    classifier_task = asyncio.create_task(
        _run_speculative_classifier(request, dict(effective_arguments))
    )

    hooks = _resolve_hooks(request.runtime_context)
    pre_hooks_started_at = time.perf_counter()
    effective_arguments, hook_block = await _run_pre_hooks(
        request,
        arguments=effective_arguments,
        hooks=hooks,
        trace=trace,
    )
    _mark_timing(trace, "pre_hooks", pre_hooks_started_at)

    classifier_started_at = time.perf_counter()
    trace.classifier_result = await classifier_task
    _mark_timing(trace, "classifier", classifier_started_at)

    trace.effective_arguments = dict(effective_arguments)

    if hook_block is not None:
        trace.blocked_by = "pre_hook"
        trace.block_message = hook_block.message
        hook_policy = _synthetic_policy_decision(
            request,
            action=(
                hook_block.action
                if hook_block.action in {TOOL_POLICY_DENY, TOOL_POLICY_REQUIRE_APPROVAL}
                else TOOL_POLICY_DENY
            ),
            reason=hook_block.message or f"Blocked by pre-hook for {request.name}",
        )
        return ToolExecutionResult(
            request=request,
            output=format_policy_block_message(request.name, hook_policy),
            success=False,
            status=EXECUTION_STATUS_HOOK_BLOCKED,
            policy_decision=hook_policy,
            trace=trace,
        )

    policy_started_at = time.perf_counter()
    policy_decision = _resolve_policy_decision(request)
    policy_decision = _more_restrictive_policy(
        policy_decision,
        _classifier_policy_decision(request, trace.classifier_result),
    )
    _mark_timing(trace, "policy", policy_started_at)
    if policy_decision is not None and not policy_decision.allows_execution:
        trace.blocked_by = "policy"
        trace.block_message = policy_decision.reason
        return ToolExecutionResult(
            request=request,
            output=format_policy_block_message(request.name, policy_decision),
            success=False,
            status=EXECUTION_STATUS_POLICY_BLOCKED,
            policy_decision=policy_decision,
            trace=trace,
        )

    execution_started_at = time.perf_counter()
    try:
        output = await invoke_tool(
            request.spec,
            request.executor,
            effective_arguments,
            runtime_context=request.runtime_context,
        )
        _mark_timing(trace, "execution", execution_started_at)

        post_hooks_started_at = time.perf_counter()
        output = await _run_post_hooks(
            request,
            output=output,
            hooks=hooks,
            trace=trace,
        )
        _mark_timing(trace, "post_hooks", post_hooks_started_at)
        return ToolExecutionResult(
            request=request,
            output=output,
            success=True,
            status=EXECUTION_STATUS_COMPLETED,
            policy_decision=policy_decision,
            trace=trace,
        )
    except Exception as exc:
        _mark_timing(trace, "execution", execution_started_at)
        output = f"Error executing {request.name}: {type(exc).__name__}: {exc}"
        failure_hooks_started_at = time.perf_counter()
        output = await _run_failure_hooks(
            request,
            error=exc,
            output=output,
            hooks=hooks,
            trace=trace,
        )
        _mark_timing(trace, "failure_hooks", failure_hooks_started_at)
        return ToolExecutionResult(
            request=request,
            output=output,
            success=False,
            error=exc,
            status=EXECUTION_STATUS_FAILED,
            policy_decision=policy_decision,
            trace=trace,
        )


async def _execute_concurrent_batch(
    requests: list[ToolExecutionRequest],
) -> list[ToolExecutionResult]:
    return list(await asyncio.gather(*(_execute_single_request(request) for request in requests)))


async def execute_tool_requests(
    requests: list[ToolExecutionRequest],
) -> list[ToolExecutionResult]:
    """Execute tool requests with write barriers and stable output ordering.

    Each request runs through a shared pipeline:
    schema validation, optional tool-level input validation, speculative
    classification, pre-hooks, policy resolution, executor invocation, trace
    capture, and post/failure hooks.

    Consecutive read-only, concurrency-safe tools still run concurrently.
    Any other tool acts as a barrier and is executed serially.
    """

    results: list[ToolExecutionResult] = []
    concurrent_batch: list[ToolExecutionRequest] = []

    async def flush_concurrent_batch() -> None:
        nonlocal concurrent_batch
        if not concurrent_batch:
            return
        results.extend(await _execute_concurrent_batch(concurrent_batch))
        concurrent_batch = []

    for request in requests:
        if request.can_run_concurrently:
            concurrent_batch.append(request)
            continue

        await flush_concurrent_batch()
        results.append(await _execute_single_request(request))

    await flush_concurrent_batch()
    return results


__all__ = [
    "EXECUTION_STATUS_COMPLETED",
    "EXECUTION_STATUS_FAILED",
    "EXECUTION_STATUS_HOOK_BLOCKED",
    "EXECUTION_STATUS_INPUT_SCHEMA_INVALID",
    "EXECUTION_STATUS_INPUT_VALIDATION_FAILED",
    "EXECUTION_STATUS_POLICY_BLOCKED",
    "EXECUTION_STATUS_UNKNOWN_TOOL",
    "ToolExecutionHook",
    "ToolExecutionHookRecord",
    "ToolExecutionHookResult",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolExecutionTrace",
    "execute_tool_requests",
]

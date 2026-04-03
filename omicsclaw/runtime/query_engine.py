from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from omicsclaw.common.user_guidance import (
    extract_user_guidance_payloads,
    render_guidance_block,
)

from .context_compaction import ContextCompactionConfig, prepare_model_messages
from .events import (
    EVENT_SESSION_RESUME,
    EVENT_SESSION_START,
    EVENT_TOOL_AFTER,
    EVENT_TOOL_BEFORE,
    EVENT_TOOL_FAILURE,
)
from .hook_payloads import SessionHookPayload, ToolHookPayload
from .hooks import HOOK_MODE_CONTEXT, HOOK_MODE_NOTICE
from .policy import evaluate_tool_policy
from .hooks import LifecycleHookRuntime
from .policy_state import ToolPolicyState
from .tool_execution_hooks import (
    build_default_tool_execution_hooks,
    merge_tool_execution_hooks,
)
from .tool_orchestration import ToolExecutionRequest, ToolExecutionResult, execute_tool_requests
from .tool_registry import ToolRuntime
from .tool_result_store import ToolResultRecord, ToolResultStore
from .transcript_store import TranscriptStore
from .token_budget import (
    check_token_budget,
    create_token_budget_tracker,
    record_completion_tokens,
)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _prepare_tool_runtime_context(
    runtime_context: dict[str, Any] | None,
) -> dict[str, Any]:
    prepared = dict(runtime_context or {})
    omicsclaw_dir = str(prepared.get("omicsclaw_dir", "") or "").strip()
    if not omicsclaw_dir:
        return prepared
    return merge_tool_execution_hooks(
        prepared,
        build_default_tool_execution_hooks(omicsclaw_dir),
    )


@dataclass(frozen=True, slots=True)
class MaterializedToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class MaterializedMessage:
    content: str | None
    tool_calls: list[MaterializedToolCall] | None


@dataclass(frozen=True, slots=True)
class QueryEngineContext:
    chat_id: int | str
    session_id: str | None
    system_prompt: str
    user_message_content: Any
    surface: str = "bot"
    policy_state: ToolPolicyState | None = None
    hook_runtime: LifecycleHookRuntime | None = None
    tool_runtime_context: dict[str, Any] | None = None
    token_budget: int | str | None = None


@dataclass(slots=True)
class QueryEngineCallbacks:
    accumulate_usage: Callable[[Any], Any] | None = None
    on_stream_content: Callable[[str], Any] | None = None
    before_tool: Callable[[ToolExecutionRequest], Any] | None = None
    after_tool: Callable[[ToolExecutionResult, ToolResultRecord, Any], Any] | None = None
    on_llm_error: Callable[[Exception], Any] | None = None


@dataclass(frozen=True, slots=True)
class QueryEngineConfig:
    model: str
    max_iterations: int = 20
    max_tokens: int = 8192
    llm_error_types: tuple[type[BaseException], ...] = (Exception,)
    context_compaction: ContextCompactionConfig = field(
        default_factory=ContextCompactionConfig
    )


def _extract_completion_tokens(response_usage, delta) -> int:
    if isinstance(delta, dict):
        try:
            value = int(delta.get("completion_tokens", 0) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value

    try:
        return int(getattr(response_usage, "completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _record_usage(
    response_usage,
    callbacks: QueryEngineCallbacks,
    *,
    on_usage_delta: Callable[[Any, Any], None] | None = None,
) -> None:
    delta = None
    if callbacks.accumulate_usage:
        delta = callbacks.accumulate_usage(response_usage)
    if on_usage_delta is not None:
        on_usage_delta(response_usage, delta)


def _is_prompt_too_long_error(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 413:
        return True
    http_status = getattr(exc, "http_status", None)
    if http_status == 413:
        return True

    message = str(exc).lower()
    patterns = (
        "prompt too long",
        "context length",
        "maximum context",
        "too many tokens",
        "request too large",
        "request entity too large",
        "413",
    )
    return any(pattern in message for pattern in patterns)


def _merge_response_segments(segments: list[str], current: str) -> str:
    merged = [segment.strip() for segment in [*segments, current] if segment and segment.strip()]
    if not merged:
        return "(no response)"
    return "\n\n".join(merged)


def _build_preflight_interruption_message(text: str | None) -> str:
    payloads = extract_user_guidance_payloads(text)
    if not payloads:
        return ""
    relevant = [
        payload
        for payload in payloads
        if payload.get("kind") == "preflight"
        and payload.get("status") in {"needs_user_input", "blocked"}
    ]
    if not relevant:
        return ""
    return render_guidance_block([], payloads=relevant, title="Important follow-up")


def _materialize_message_from_choice_message(message) -> MaterializedMessage:
    tool_calls = None
    if getattr(message, "tool_calls", None):
        tool_calls = [
            MaterializedToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments,
            )
            for tc in message.tool_calls
        ]
    return MaterializedMessage(
        content=getattr(message, "content", None),
        tool_calls=tool_calls,
    )


async def _materialize_message_from_stream(
    response,
    callbacks: QueryEngineCallbacks,
    *,
    on_usage_delta: Callable[[Any, Any], None] | None = None,
) -> MaterializedMessage:
    final_content = ""
    tool_calls_dict: dict[int, MaterializedToolCall] = {}

    async for chunk in response:
        if not chunk.choices:
            if chunk.usage:
                _record_usage(
                    chunk.usage,
                    callbacks,
                    on_usage_delta=on_usage_delta,
                )
            continue

        delta = chunk.choices[0].delta
        if delta.content:
            final_content += delta.content
            if callbacks.on_stream_content:
                await _maybe_await(callbacks.on_stream_content(delta.content))

        if delta.tool_calls:
            for tc_chunk in delta.tool_calls:
                tc_index = tc_chunk.index
                if tc_index not in tool_calls_dict:
                    tool_calls_dict[tc_index] = MaterializedToolCall(
                        id=tc_chunk.id or "",
                        name=tc_chunk.function.name or "",
                        arguments=tc_chunk.function.arguments or "",
                    )
                else:
                    existing = tool_calls_dict[tc_index]
                    tool_calls_dict[tc_index] = MaterializedToolCall(
                        id=existing.id or tc_chunk.id or "",
                        name=existing.name + (tc_chunk.function.name or ""),
                        arguments=existing.arguments + (tc_chunk.function.arguments or ""),
                    )

    tool_calls = [tool_calls_dict[idx] for idx in sorted(tool_calls_dict)] or None
    return MaterializedMessage(
        content=final_content or None,
        tool_calls=tool_calls,
    )


async def _materialize_message(
    response,
    callbacks: QueryEngineCallbacks,
    *,
    on_usage_delta: Callable[[Any, Any], None] | None = None,
) -> MaterializedMessage:
    if callbacks.on_stream_content is not None:
        return await _materialize_message_from_stream(
            response,
            callbacks,
            on_usage_delta=on_usage_delta,
        )

    if getattr(response, "usage", None):
        _record_usage(
            response.usage,
            callbacks,
            on_usage_delta=on_usage_delta,
        )
    return _materialize_message_from_choice_message(response.choices[0].message)


async def run_query_engine(
    *,
    llm,
    context: QueryEngineContext,
    tool_runtime: ToolRuntime,
    transcript_store: TranscriptStore,
    tool_result_store: ToolResultStore,
    config: QueryEngineConfig,
    callbacks: QueryEngineCallbacks | None = None,
) -> str:
    callbacks = callbacks or QueryEngineCallbacks()
    hook_runtime = context.hook_runtime
    tool_runtime_context = _prepare_tool_runtime_context(context.tool_runtime_context)
    history_before = list(transcript_store.get_history(context.chat_id))
    system_prompt = context.system_prompt

    if hook_runtime is not None:
        session_event_name = (
            EVENT_SESSION_RESUME if history_before else EVENT_SESSION_START
        )
        hook_runtime.emit(
            session_event_name,
            SessionHookPayload(
                chat_id=str(context.chat_id),
                session_id=str(context.session_id or ""),
                surface=context.surface,
                resumed=bool(history_before),
                message_count=len(history_before),
            ),
            context={
                "chat_id": str(context.chat_id),
                "session_id": str(context.session_id or ""),
                "surface": context.surface,
            },
        )
        context_fragments = hook_runtime.consume_pending_messages(
            mode=HOOK_MODE_CONTEXT,
            event_names=(session_event_name,),
        )
        if context_fragments:
            system_prompt = (
                f"{system_prompt.rstrip()}\n\n## Active Session Hooks\n\n"
                + "\n\n".join(fragment for fragment in context_fragments if fragment.strip())
            ).strip()

    transcript_store.touch(context.chat_id)
    transcript_store.evict_lru_conversations()
    transcript_store.append_user_message(context.chat_id, context.user_message_content)
    transcript_store.prepare_history(context.chat_id)

    budget_tracker = create_token_budget_tracker(context.token_budget)
    accumulated_response_segments: list[str] = []
    has_attempted_reactive_compact = False
    pipeline_workspace = str(
        (tool_runtime_context or {}).get("pipeline_workspace", "") or ""
    ).strip()
    workspace = str((tool_runtime_context or {}).get("workspace", "") or "").strip()
    compaction_metadata = (
        {"pipeline_workspace": pipeline_workspace}
        if pipeline_workspace
        else None
    )
    compaction_workspace = pipeline_workspace or workspace or None

    def _observe_usage_delta(response_usage, delta) -> None:
        completion_tokens = _extract_completion_tokens(response_usage, delta)
        if completion_tokens > 0:
            record_completion_tokens(budget_tracker, completion_tokens)

    last_message: MaterializedMessage | None = None
    for _ in range(config.max_iterations):
        history = transcript_store.prepare_history(context.chat_id)
        prepared_messages = prepare_model_messages(
            system_prompt=system_prompt,
            history=history,
            chat_id=context.chat_id,
            tool_result_store=tool_result_store,
            config=config.context_compaction,
            metadata=compaction_metadata,
            workspace=compaction_workspace,
        )
        request_system_prompt = prepared_messages.system_prompt
        request_messages = prepared_messages.messages
        try:
            while True:
                kwargs = {}
                if callbacks.on_stream_content is not None:
                    kwargs = {"stream": True, "stream_options": {"include_usage": True}}

                try:
                    response = await llm.chat.completions.create(
                        model=config.model,
                        max_tokens=config.max_tokens,
                        messages=[{"role": "system", "content": request_system_prompt}]
                        + request_messages,
                        tools=list(tool_runtime.openai_tools),
                        **kwargs,
                    )
                    last_message = await _materialize_message(
                        response,
                        callbacks,
                        on_usage_delta=_observe_usage_delta,
                    )
                    break
                except config.llm_error_types as exc:
                    if not (
                        not has_attempted_reactive_compact
                        and config.context_compaction.enabled
                        and _is_prompt_too_long_error(exc)
                    ):
                        raise

                    reactive_messages = prepare_model_messages(
                        system_prompt=system_prompt,
                        history=history,
                        chat_id=context.chat_id,
                        tool_result_store=tool_result_store,
                        config=config.context_compaction,
                        metadata=compaction_metadata,
                        workspace=compaction_workspace,
                        force_reactive_compact=True,
                    )
                    has_attempted_reactive_compact = True
                    if (
                        reactive_messages.applied_stages
                        and (
                            reactive_messages.system_prompt != request_system_prompt
                            or reactive_messages.messages != request_messages
                        )
                    ):
                        request_system_prompt = reactive_messages.system_prompt
                        request_messages = reactive_messages.messages
                        continue
                    raise
        except config.llm_error_types as exc:
            if callbacks.on_llm_error is not None:
                return await _maybe_await(callbacks.on_llm_error(exc))
            raise

        assistant_tool_calls = None
        if last_message.tool_calls:
            assistant_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in last_message.tool_calls
            ]
        transcript_store.append_assistant_message(
            context.chat_id,
            content=last_message.content or "",
            tool_calls=assistant_tool_calls,
        )

        if not last_message.tool_calls:
            current_response = last_message.content or ""
            budget_decision = check_token_budget(budget_tracker)
            if budget_decision.action == "continue":
                if current_response.strip():
                    accumulated_response_segments.append(current_response)
                transcript_store.append_user_message(
                    context.chat_id,
                    budget_decision.nudge_message,
                )
                continue
            return _merge_response_segments(accumulated_response_segments, current_response)

        execution_requests: list[ToolExecutionRequest] = []
        tool_states: dict[str, Any] = {}
        for tc in last_message.tool_calls:
            executor = tool_runtime.executors.get(tc.name)
            tool_spec = tool_runtime.specs_by_name.get(tc.name)
            try:
                func_args = json.loads(tc.arguments) if executor else {}
            except json.JSONDecodeError:
                func_args = {}

            runtime_context = {
                "session_id": context.session_id,
                "chat_id": context.chat_id,
                "surface": context.surface,
                "policy_state": context.policy_state,
            }
            if tool_runtime_context:
                runtime_context.update(tool_runtime_context)
            request = ToolExecutionRequest(
                call_id=tc.id,
                name=tc.name,
                arguments=func_args,
                spec=tool_spec,
                executor=executor,
                runtime_context=runtime_context,
                policy_decision=evaluate_tool_policy(
                    tc.name,
                    tool_spec,
                    runtime_context=runtime_context,
                ),
            )
            if hook_runtime is not None:
                hook_runtime.emit(
                    EVENT_TOOL_BEFORE,
                    ToolHookPayload(
                        tool_name=tc.name,
                        call_id=tc.id,
                        status="pending",
                        success=False,
                        surface=context.surface,
                        session_id=str(context.session_id or ""),
                        chat_id=str(context.chat_id),
                        policy_action=(
                            request.policy_decision.action
                            if request.policy_decision is not None
                            else ""
                        ),
                    ),
                    context=runtime_context,
                )
            if executor and callbacks.before_tool is not None:
                tool_states[tc.id] = await _maybe_await(callbacks.before_tool(request))
            execution_requests.append(request)

        execution_results = await execute_tool_requests(execution_requests)
        interruption_message = ""
        for execution_result in execution_results:
            request = execution_result.request
            record_output = execution_result.output
            if hook_runtime is not None:
                event_name = EVENT_TOOL_AFTER
                if not execution_result.success:
                    event_name = EVENT_TOOL_FAILURE
                hook_runtime.emit(
                    event_name,
                    ToolHookPayload(
                        tool_name=request.name,
                        call_id=request.call_id,
                        status=execution_result.status,
                        success=execution_result.success,
                        surface=context.surface,
                        session_id=str(context.session_id or ""),
                        chat_id=str(context.chat_id),
                        policy_action=(
                            execution_result.policy_decision.action
                            if execution_result.policy_decision is not None
                            else ""
                        ),
                    ),
                    context={
                        "session_id": context.session_id,
                        "chat_id": context.chat_id,
                        "surface": context.surface,
                        "workspace": str(
                            (request.runtime_context or {}).get("pipeline_workspace")
                            or (request.runtime_context or {}).get("workspace")
                            or ""
                        ).strip(),
                    },
                )
                notices = hook_runtime.consume_pending_messages(
                    mode=HOOK_MODE_NOTICE,
                    event_names=(EVENT_TOOL_BEFORE, EVENT_TOOL_AFTER, EVENT_TOOL_FAILURE),
                    call_id=request.call_id,
                )
                if notices:
                    record_output = "\n".join(
                        [*notices, str(record_output)]
                    ).strip()
            result_record = tool_result_store.record(
                chat_id=context.chat_id,
                tool_call_id=request.call_id,
                tool_name=request.name,
                output=record_output,
                success=execution_result.success,
                error=execution_result.error,
                spec=request.spec,
                policy_decision=execution_result.policy_decision,
                execution_trace=(
                    execution_result.trace.to_dict()
                    if execution_result.trace is not None
                    else None
                ),
            )

            if callbacks.after_tool is not None:
                await _maybe_await(
                    callbacks.after_tool(
                        execution_result,
                        result_record,
                        tool_states.get(request.call_id),
                    )
                )

            transcript_store.append_tool_message(
                context.chat_id,
                tool_call_id=request.call_id,
                content=result_record.content,
            )

            if not interruption_message:
                interruption_message = _build_preflight_interruption_message(
                    result_record.content
                )

        if interruption_message:
            transcript_store.append_assistant_message(
                context.chat_id,
                content=interruption_message,
            )
            return interruption_message

    if last_message and last_message.content:
        return _merge_response_segments(accumulated_response_segments, last_message.content)
    return "(max tool iterations reached)"

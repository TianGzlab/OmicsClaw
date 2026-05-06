from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from omicsclaw.common.user_guidance import (
    extract_user_guidance_payloads,
    render_guidance_block,
)
from omicsclaw.core.llm_patches import apply_deepseek_reasoning_passback

from .context_budget import estimate_message_size
from .context_compaction import (
    CompactionEvent,
    ContextCompactionConfig,
    PreparedModelMessages,
    prepare_model_messages,
    wrap_compaction_summary,
)
from .events import (
    EVENT_SESSION_RESUME,
    EVENT_SESSION_START,
    EVENT_TOOL_AFTER,
    EVENT_TOOL_BEFORE,
    EVENT_TOOL_FAILURE,
)
from .hook_payloads import SessionHookPayload, ToolHookPayload
from .hooks import HOOK_MODE_CONTEXT, HOOK_MODE_NOTICE
from .policy import TOOL_POLICY_REQUIRE_APPROVAL, evaluate_tool_policy
from .hooks import LifecycleHookRuntime
from .policy_state import ToolPolicyState
from .tool_execution_hooks import (
    build_default_tool_execution_hooks,
    merge_tool_execution_hooks,
)
from .tool_orchestration import (
    EXECUTION_STATUS_POLICY_BLOCKED,
    ToolExecutionRequest,
    ToolExecutionResult,
    execute_tool_requests,
)
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
    reasoning_content: str | None = None


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
    on_stream_reasoning: Callable[[str], Any] | None = None
    before_tool: Callable[[ToolExecutionRequest], Any] | None = None
    after_tool: Callable[[ToolExecutionResult, ToolResultRecord, Any], Any] | None = (
        None
    )
    request_tool_approval: (
        Callable[[ToolExecutionRequest, ToolExecutionResult], Any] | None
    ) = None
    on_llm_error: Callable[[Exception], Any] | None = None
    on_context_compacted: Callable[["CompactionEvent"], Any] | None = None


@dataclass(frozen=True, slots=True)
class QueryEngineConfig:
    model: str
    max_iterations: int = 20
    max_tokens: int = 8192
    llm_error_types: tuple[type[BaseException], ...] = (Exception,)
    context_compaction: ContextCompactionConfig = field(
        default_factory=ContextCompactionConfig
    )
    extra_api_params: dict[str, Any] = field(default_factory=dict)
    # DeepSeek thinking-mode endpoints reject requests where any historical
    # assistant message lacks ``reasoning_content``. Set to True for the
    # ``deepseek`` provider so the chat path mirrors the autoagent passback.
    deepseek_reasoning_passback: bool = False


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
    merged = [
        segment.strip()
        for segment in [*segments, current]
        if segment and segment.strip()
    ]
    if not merged:
        return "(no response)"
    return "\n\n".join(merged)


def _normalize_permission_resolution(
    raw: Any,
    *,
    request: ToolExecutionRequest,
    fallback_surface: str,
) -> tuple[str, dict[str, Any] | None, ToolPolicyState | None, str, bool]:
    if raw is None:
        return ("deny", None, None, "", False)

    if isinstance(raw, str):
        behavior = raw.strip().lower()
        if behavior in {"allow", "deny"}:
            return (behavior, None, None, "", False)
        return ("deny", None, None, raw.strip(), False)

    if not isinstance(raw, Mapping):
        return ("deny", None, None, "", False)

    behavior = str(raw.get("behavior") or raw.get("decision") or "").strip().lower()
    if behavior not in {"allow", "deny"}:
        behavior = "deny"

    updated_arguments_raw = raw.get("updated_arguments")
    if updated_arguments_raw is None:
        updated_arguments_raw = raw.get("updated_input")
    updated_arguments = (
        dict(updated_arguments_raw)
        if isinstance(updated_arguments_raw, Mapping)
        else None
    )

    policy_state_raw = raw.get("policy_state")
    policy_state = (
        ToolPolicyState.from_mapping(
            policy_state_raw,
            surface=str(
                (
                    (request.runtime_context or {}).get("surface")
                    or fallback_surface
                    or ""
                )
            ).strip(),
        )
        if policy_state_raw is not None
        else None
    )

    message = str(raw.get("message", "") or "").strip()
    persist = bool(raw.get("persist", False))
    return (behavior, updated_arguments, policy_state, message, persist)


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


def _extract_text_fragments(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        for key in ("text", "content", "summary", "reasoning"):
            fragment = value.get(key)
            if isinstance(fragment, str) and fragment:
                return [fragment]
        return []
    if isinstance(value, (list, tuple)):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_extract_text_fragments(item))
        return fragments
    for attr in ("text", "content", "summary", "reasoning"):
        fragment = getattr(value, attr, None)
        if isinstance(fragment, str) and fragment:
            return [fragment]
    return []


def _extract_stream_delta_chunks(delta: Any) -> tuple[list[str], list[str]]:
    text_chunks: list[str] = []
    reasoning_chunks: list[str] = []

    content = getattr(delta, "content", None)
    if isinstance(content, str):
        text_chunks.append(content)
    elif content is not None:
        parts = content if isinstance(content, (list, tuple)) else [content]
        for part in parts:
            part_type = ""
            if isinstance(part, Mapping):
                part_type = str(part.get("type", "") or "").strip().lower()
            else:
                part_type = str(getattr(part, "type", "") or "").strip().lower()
            fragments = _extract_text_fragments(part)
            if part_type in {"reasoning", "thinking", "summary"}:
                reasoning_chunks.extend(fragments)
            else:
                text_chunks.extend(fragments)

    for attr in ("reasoning", "reasoning_content", "thinking"):
        reasoning_chunks.extend(_extract_text_fragments(getattr(delta, attr, None)))

    return text_chunks, reasoning_chunks


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
    reasoning_content: str | None = None
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value:
            reasoning_content = value
            break
    return MaterializedMessage(
        content=getattr(message, "content", None),
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )


async def _materialize_message_from_stream(
    response,
    callbacks: QueryEngineCallbacks,
    *,
    on_usage_delta: Callable[[Any, Any], None] | None = None,
) -> MaterializedMessage:
    final_content = ""
    final_reasoning = ""
    tool_calls_dict: dict[int, MaterializedToolCall] = {}
    # Some OpenAI-compatible proxies (ccproxy, LiteLLM, some Gemini transports)
    # emit cumulative `chunk.usage` on every chunk, not just the terminal one.
    # Record the last snapshot once, after the stream ends, to avoid inflating
    # accumulated totals for those providers.
    last_usage: Any = None

    async for chunk in response:
        if chunk.usage:
            last_usage = chunk.usage
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta
        text_chunks, reasoning_chunks = _extract_stream_delta_chunks(delta)
        for reasoning_chunk in reasoning_chunks:
            final_reasoning += reasoning_chunk
            if callbacks.on_stream_reasoning:
                await _maybe_await(callbacks.on_stream_reasoning(reasoning_chunk))
        for text_chunk in text_chunks:
            final_content += text_chunk
            if callbacks.on_stream_content:
                await _maybe_await(callbacks.on_stream_content(text_chunk))

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
                        arguments=existing.arguments
                        + (tc_chunk.function.arguments or ""),
                    )

    if last_usage is not None:
        _record_usage(last_usage, callbacks, on_usage_delta=on_usage_delta)

    tool_calls = [tool_calls_dict[idx] for idx in sorted(tool_calls_dict)] or None
    return MaterializedMessage(
        content=final_content or None,
        tool_calls=tool_calls,
        reasoning_content=final_reasoning or None,
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


async def _emit_compaction_event(
    *,
    callbacks: QueryEngineCallbacks,
    pre_chars: int,
    post_chars: int,
    history_len: int,
    kept_len: int,
    applied_stages: tuple[str, ...],
) -> None:
    """Build a CompactionEvent and dispatch via the callback.

    Failures in the user-supplied callback are logged at WARNING and
    swallowed — compaction itself succeeded; failing to notify must
    not abort the turn.
    """
    saved_chars = max(0, pre_chars - post_chars)
    omitted = max(0, history_len - kept_len)
    event = CompactionEvent(
        messages_compressed=omitted,
        tokens_saved_estimate=int(saved_chars / 3.5),
        applied_stages=applied_stages,
    )
    try:
        await _maybe_await(callbacks.on_context_compacted(event))
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "on_context_compacted callback raised; ignoring.",
            exc_info=True,
        )


def _persist_prepared_compaction(
    *,
    transcript_store: TranscriptStore,
    chat_id: int | str,
    prepared_messages: PreparedModelMessages,
) -> None:
    if not prepared_messages.persisted_summary.strip():
        return
    compacted_history = [
        {
            "role": "system",
            "content": wrap_compaction_summary(prepared_messages.persisted_summary),
        },
        *prepared_messages.messages,
    ]
    transcript_store.replace_history(chat_id, compacted_history)


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
                + "\n\n".join(
                    fragment for fragment in context_fragments if fragment.strip()
                )
            ).strip()

    transcript_store.touch(context.chat_id)
    transcript_store.evict_lru_conversations()
    transcript_store.append_user_message(context.chat_id, context.user_message_content)
    transcript_store.prepare_history(context.chat_id)

    budget_tracker = create_token_budget_tracker(context.token_budget)
    accumulated_response_segments: list[str] = []
    has_attempted_reactive_compact = False
    current_policy_state = context.policy_state
    pipeline_workspace = str(
        (tool_runtime_context or {}).get("pipeline_workspace", "") or ""
    ).strip()
    workspace = str((tool_runtime_context or {}).get("workspace", "") or "").strip()
    compaction_metadata = (
        {"pipeline_workspace": pipeline_workspace} if pipeline_workspace else None
    )
    compaction_workspace = pipeline_workspace or workspace or None

    def _observe_usage_delta(response_usage, delta) -> None:
        completion_tokens = _extract_completion_tokens(response_usage, delta)
        if completion_tokens > 0:
            record_completion_tokens(budget_tracker, completion_tokens)

    last_message: MaterializedMessage | None = None
    for _ in range(config.max_iterations):
        history = transcript_store.prepare_history(context.chat_id)
        pre_chars = sum(estimate_message_size(m) for m in history)
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
        if config.deepseek_reasoning_passback:
            request_messages = apply_deepseek_reasoning_passback(request_messages)
        _persist_prepared_compaction(
            transcript_store=transcript_store,
            chat_id=context.chat_id,
            prepared_messages=prepared_messages,
        )
        if prepared_messages.applied_stages and callbacks.on_context_compacted:
            await _emit_compaction_event(
                callbacks=callbacks,
                pre_chars=pre_chars,
                post_chars=prepared_messages.estimated_chars,
                history_len=len(history),
                kept_len=len(prepared_messages.messages),
                applied_stages=prepared_messages.applied_stages,
            )
        try:
            while True:
                kwargs = {}
                if callbacks.on_stream_content is not None:
                    kwargs = {"stream": True, "stream_options": {"include_usage": True}}
                if config.extra_api_params:
                    kwargs.update(config.extra_api_params)

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

                    reactive_pre_chars = sum(estimate_message_size(m) for m in history)
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
                    if reactive_messages.applied_stages and (
                        reactive_messages.system_prompt != request_system_prompt
                        or reactive_messages.messages != request_messages
                    ):
                        request_system_prompt = reactive_messages.system_prompt
                        request_messages = reactive_messages.messages
                        if config.deepseek_reasoning_passback:
                            request_messages = apply_deepseek_reasoning_passback(
                                request_messages
                            )
                        _persist_prepared_compaction(
                            transcript_store=transcript_store,
                            chat_id=context.chat_id,
                            prepared_messages=reactive_messages,
                        )
                        if callbacks.on_context_compacted:
                            await _emit_compaction_event(
                                callbacks=callbacks,
                                pre_chars=reactive_pre_chars,
                                post_chars=reactive_messages.estimated_chars,
                                history_len=len(history),
                                kept_len=len(reactive_messages.messages),
                                applied_stages=reactive_messages.applied_stages,
                            )
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
            reasoning_content=last_message.reasoning_content,
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
            return _merge_response_segments(
                accumulated_response_segments, current_response
            )

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
                "policy_state": current_policy_state,
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
        if callbacks.request_tool_approval is not None:
            resolved_execution_results: list[ToolExecutionResult] = []
            for execution_result in execution_results:
                request = execution_result.request
                if (
                    execution_result.status == EXECUTION_STATUS_POLICY_BLOCKED
                    and execution_result.policy_decision is not None
                    and execution_result.policy_decision.action
                    == TOOL_POLICY_REQUIRE_APPROVAL
                ):
                    resolution = await _maybe_await(
                        callbacks.request_tool_approval(request, execution_result)
                    )
                    (
                        approval_behavior,
                        updated_arguments,
                        updated_policy_state,
                        deny_message,
                        approval_persist,
                    ) = _normalize_permission_resolution(
                        resolution,
                        request=request,
                        fallback_surface=context.surface,
                    )
                    if approval_behavior == "allow":
                        base_policy_state = ToolPolicyState.from_mapping(
                            (request.runtime_context or {}).get("policy_state"),
                            surface=context.surface,
                        )
                        effective_policy_state = updated_policy_state
                        if effective_policy_state is None:
                            effective_policy_state = ToolPolicyState(
                                surface=base_policy_state.surface or context.surface,
                                trusted=base_policy_state.trusted,
                                background=base_policy_state.background,
                                auto_approve_ask=base_policy_state.auto_approve_ask,
                                approved_tool_names=(
                                    base_policy_state.approved_tool_names
                                    | frozenset({request.name})
                                ),
                            )
                        approved_runtime_context = dict(request.runtime_context or {})
                        approved_runtime_context["policy_state"] = (
                            effective_policy_state
                        )
                        approved_request = ToolExecutionRequest(
                            call_id=request.call_id,
                            name=request.name,
                            arguments=(
                                updated_arguments
                                if updated_arguments is not None
                                else request.arguments
                            ),
                            spec=request.spec,
                            executor=request.executor,
                            runtime_context=approved_runtime_context,
                            policy_decision=evaluate_tool_policy(
                                request.name,
                                request.spec,
                                runtime_context=approved_runtime_context,
                            ),
                        )
                        execution_result = (
                            await execute_tool_requests([approved_request])
                        )[0]
                        if updated_policy_state is not None and approval_persist:
                            current_policy_state = updated_policy_state
                    elif deny_message:
                        execution_result = ToolExecutionResult(
                            request=request,
                            output=deny_message,
                            success=False,
                            error=execution_result.error,
                            status=execution_result.status,
                            policy_decision=execution_result.policy_decision,
                            trace=execution_result.trace,
                        )
                resolved_execution_results.append(execution_result)
            execution_results = resolved_execution_results

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
                    event_names=(
                        EVENT_TOOL_BEFORE,
                        EVENT_TOOL_AFTER,
                        EVENT_TOOL_FAILURE,
                    ),
                    call_id=request.call_id,
                )
                if notices:
                    record_output = "\n".join([*notices, str(record_output)]).strip()
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
        return _merge_response_segments(
            accumulated_response_segments, last_message.content
        )
    return "(max tool iterations reached)"

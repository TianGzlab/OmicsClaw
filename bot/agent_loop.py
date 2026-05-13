"""Multi-round LLM dispatch loop — the agent's central control flow.

Carved out of ``bot/core.py`` per ADR 0001 (#121, the final bot/core
slice). Every User-facing entry (bot channels, ``omicsclaw/app/server.py``,
``omicsclaw/interactive/interactive.py``) walks through ``llm_tool_loop``
to interleave LLM completions with tool execution until the model emits
a final user-facing message.

Cross-module access:

* Stable bot.core symbols (``OUTPUT_DIR``, ``OMICSCLAW_DIR``,
  ``transcript_store``, ``tool_result_store``,
  ``pending_preflight_requests``, ``audit``, ``MAX_HISTORY``,
  ``MAX_CONVERSATIONS``, ...) imported at module top.
* Runtime-reassigned globals (``llm``, ``OMICSCLAW_MODEL``,
  ``LLM_PROVIDER_NAME``, ``memory_store``, ``session_manager``)
  accessed via ``_core.<name>`` at call time. ``bot.session.init()``
  sets them after modules finish loading.
* Sibling helpers (``bot.skill_orchestration``,
  ``bot.tool_executors``) imported from canonical homes.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import APIError, AsyncOpenAI, OpenAIError

# Late-binding handle for runtime-mutated bot.core globals.
import bot.core as _core

# Stable bot.core symbols.
from bot.core import (
    BOT_START_TIME,
    DATA_DIR,
    DEEP_LEARNING_METHODS,
    EXAMPLES_DIR,
    MAX_CONVERSATIONS,
    MAX_HISTORY,
    MAX_HISTORY_CHARS,
    OMICSCLAW_DIR,
    OUTPUT_DIR,
    _primary_skill_count,
    _skill_registry,
    audit,
    format_skills_table,
    pending_preflight_requests,
    tool_result_store,
    transcript_store,
)
from bot.billing import accumulate_usage as _accumulate_usage
from bot.commands import SlashCommandContext
from bot.commands import dispatch as _dispatch_slash_command
from bot.preflight import (
    _apply_preflight_answers,
    _build_pending_preflight_message,
    _extract_pending_preflight_payload,
    _is_affirmative_preflight_confirmation,
    _parse_preflight_reply,
    _preflight_payload_needs_reply,
    _remember_pending_preflight_request,
)
from bot.tool_executors import (
    _build_tool_runtime,
    execute_omicsclaw,
    get_tool_executors,
    get_tool_runtime,
)

from omicsclaw.common.user_guidance import strip_user_guidance_lines
from omicsclaw.core.llm_timeout import build_llm_timeout_policy
from omicsclaw.engine import (
    EngineDependencies,
    apply_model_identity_anchor,
    resolve_effective_model_provider,
    run_engine_loop,
)
from omicsclaw.runtime.bot_tools import (
    BotToolContext,
    build_bot_tool_registry,
)
from omicsclaw.runtime.context_assembler import (
    assemble_chat_context as _assemble_chat_context,
)
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.policy import TOOL_POLICY_ALLOW
from omicsclaw.runtime.policy_state import ToolPolicyState
from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.system_prompt import build_system_prompt
from omicsclaw.runtime.tool_orchestration import (
    EXECUTION_STATUS_POLICY_BLOCKED,
    ToolExecutionRequest,
)
from omicsclaw.runtime.tool_spec import PROGRESS_POLICY_ANALYSIS
from omicsclaw.runtime.transcript_store import (
    build_selective_replay_context,
    sanitize_tool_history as _runtime_sanitize_tool_history,
)

logger = logging.getLogger("omicsclaw.bot.agent_loop")


# ---------------------------------------------------------------------------
# System prompt + tool-registry hooks
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = ""

def _ensure_system_prompt():
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = build_system_prompt(omicsclaw_dir=str(OMICSCLAW_DIR))

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

def get_tools() -> list[dict]:
    return list(get_tool_runtime().openai_tools)


def _build_bot_tool_context() -> BotToolContext:
    """Thin alias around the canonical ``build_default_bot_tool_context``
    in ``omicsclaw/runtime/bot_tools.py``. Kept as a module-private hook
    so other bot/core.py callers can monkeypatch in tests if needed —
    do not inline this call site away."""
    from omicsclaw.runtime.bot_tools import build_default_bot_tool_context

    return build_default_bot_tool_context()


def get_tool_registry():
    return build_bot_tool_registry(_build_bot_tool_context())


def _build_llm_timeout():
    """Build the shared timeout policy for the AsyncOpenAI client."""
    return build_llm_timeout_policy(log=logger).as_httpx_timeout()


MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))  # Increased from 10, configurable


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


def _format_llm_api_error_message(exc: Exception) -> str:
    detail = str(exc).strip() or type(exc).__name__
    provider = (_core.LLM_PROVIDER_NAME or "").strip().lower()
    base_url = ""
    try:
        from omicsclaw.core.provider_runtime import get_active_provider_runtime

        runtime = get_active_provider_runtime()
        base_url = str(getattr(runtime, "base_url", "") or "").strip()
    except Exception:
        base_url = ""
    if not base_url:
        base_url = str(
            os.getenv("LLM_BASE_URL", "") or os.getenv("OMICSCLAW_BASE_URL", "") or ""
        ).strip()

    if provider == "custom":
        endpoint_hint = (
            f" Custom endpoint base_url is `{base_url}`."
            if base_url
            else " Custom endpoint base_url is empty."
        )
        return (
            "LLM provider request failed for the custom endpoint:"
            f" {detail}.{endpoint_hint} Ensure the base URL is the "
            "OpenAI-compatible API root, commonly ending in `/v1`, not the "
            "provider dashboard or homepage."
        )

    return f"Sorry, I'm having trouble thinking right now -- API error: {detail}"


def _sanitize_tool_history(history: list[dict], warn: bool = True) -> list[dict]:
    return _runtime_sanitize_tool_history(history, warn=warn)


def _normalize_tool_callback_args(callback, args: tuple) -> tuple:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return args

    positional_capacity = 0
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            return args
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional_capacity += 1
    return args[:positional_capacity]


async def _emit_tool_callback(callback, *args) -> None:
    if not callback:
        return
    callback_args = _normalize_tool_callback_args(callback, args)
    if asyncio.iscoroutinefunction(callback):
        await callback(*callback_args)
    else:
        callback(*callback_args)


def _coerce_timeout_seconds(value) -> int | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return max(1, round(seconds))


def _extract_timeout_seconds_from_text(text: str) -> int | None:
    if not text:
        return None

    patterns = (
        r"timed out after (?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
        r"timeout after (?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        seconds = _coerce_timeout_seconds(match.group("seconds"))
        if seconds is not None:
            return seconds
    return None


def _extract_tool_timeout_seconds(execution_result, display_output) -> int | None:
    error = getattr(execution_result, "error", None)
    if error is not None:
        for attr_name in (
            "timeout",
            "timeout_seconds",
            "elapsed_seconds",
            "elapsed_time_seconds",
            "seconds",
        ):
            seconds = _coerce_timeout_seconds(getattr(error, attr_name, None))
            if seconds is not None:
                return seconds

        seconds = _extract_timeout_seconds_from_text(str(error))
        if seconds is not None:
            return seconds

    display_text = str(display_output or "")
    if "timed out" in display_text.lower() or "timeout" in display_text.lower():
        return _extract_timeout_seconds_from_text(display_text)

    return None


def _build_tool_result_callback_metadata(execution_result, display_output) -> dict[str, object]:
    timeout_seconds = _extract_tool_timeout_seconds(execution_result, display_output)
    metadata: dict[str, object] = {
        "status": getattr(execution_result, "status", ""),
        "success": bool(getattr(execution_result, "success", False)),
        "is_error": bool(not getattr(execution_result, "success", False) or timeout_seconds),
    }

    error = getattr(execution_result, "error", None)
    if error is not None:
        metadata["error_type"] = type(error).__name__
    if timeout_seconds is not None:
        metadata["timed_out"] = True
        metadata["elapsed_seconds"] = timeout_seconds
    return metadata


def _build_bot_query_engine_callbacks(
    *,
    chat_id: int | str,
    progress_fn,
    progress_update_fn,
    on_tool_call,
    on_tool_result,
    on_stream_content,
    on_stream_reasoning,
    request_tool_approval,
    logger_obj,
    audit_fn,
    deep_learning_methods: set[str],
    usage_accumulator,
    on_context_compacted=None,
):
    notified_methods: set[str] = set()

    async def before_tool(request: ToolExecutionRequest):
        func_name = request.name
        func_args = request.arguments
        spec = request.spec
        policy_decision = request.policy_decision
        logger_obj.info(f"Tool call: {func_name}({json.dumps(func_args)[:200]})")
        audit_fn(
            "tool_call",
            chat_id=str(chat_id),
            tool=func_name,
            args_preview=json.dumps(func_args, default=str)[:300],
            policy_action=(
                policy_decision.action if policy_decision is not None else TOOL_POLICY_ALLOW
            ),
        )
        await _emit_tool_callback(on_tool_call, func_name, func_args)

        progress_handle = None
        if (
            policy_decision is not None
            and not policy_decision.allows_execution
        ):
            return {"progress_handle": None}

        if spec is not None and spec.progress_policy == PROGRESS_POLICY_ANALYSIS and progress_fn:
            dl_method = (func_args.get("method") or "").lower()
            if dl_method in deep_learning_methods and dl_method not in notified_methods:
                notified_methods.add(dl_method)
                method_display = func_args.get("method", dl_method)
                progress_handle = await progress_fn(
                    f"⏳ **{method_display}** is a deep learning method and may take "
                    f"10-60 minutes depending on data size. Please be patient...\n\n"
                    f"💡 The analysis is running on the server, you can leave this "
                    f"chat open and come back later."
                )
        return {"progress_handle": progress_handle}

    async def after_tool(execution_result, result_record, tool_state):
        request = execution_result.request
        func_name = request.name
        func_args = request.arguments
        progress_handle = (tool_state or {}).get("progress_handle")
        policy_decision = execution_result.policy_decision

        if progress_handle and progress_update_fn:
            method_display = func_args.get("method") or "analysis"
            if execution_result.success:
                await progress_update_fn(
                    progress_handle,
                    f"✅ **{method_display}** analysis complete!"
                )
            else:
                error_name = type(execution_result.error).__name__ if execution_result.error else "Error"
                await progress_update_fn(
                    progress_handle,
                    f"❌ **{method_display}** failed: {error_name}"
                )

        if (
            execution_result.status == EXECUTION_STATUS_POLICY_BLOCKED
            and policy_decision is not None
        ):
            audit_fn(
                "tool_policy_blocked",
                chat_id=str(chat_id),
                tool=func_name,
                action=policy_decision.action,
                reason=policy_decision.reason[:300],
                risk=policy_decision.risk_level,
            )

        if execution_result.error:
            logger_obj.error(
                "Tool %s raised: %s",
                func_name,
                execution_result.error,
                exc_info=(
                    type(execution_result.error),
                    execution_result.error,
                    execution_result.error.__traceback__,
                ),
            )
            audit_fn(
                "tool_error",
                chat_id=str(chat_id),
                tool=func_name,
                error=str(execution_result.error)[:300],
            )

        if request.executor:
            display_output = result_record.content
            if func_name == "omicsclaw":
                pending_payload = _extract_pending_preflight_payload(display_output)
                if _preflight_payload_needs_reply(pending_payload):
                    _remember_pending_preflight_request(
                        chat_id,
                        args=func_args,
                        payload=pending_payload,
                    )
                else:
                    pending_preflight_requests.pop(chat_id, None)
            if func_name == "consult_knowledge":
                try:
                    from omicsclaw.knowledge.retriever import consume_runtime_notice

                    notice = consume_runtime_notice()
                    if notice:
                        display_output = f"{notice}\n{display_output}"
                except Exception:
                    pass
            await _emit_tool_callback(
                on_tool_result,
                func_name,
                display_output,
                _build_tool_result_callback_metadata(execution_result, display_output),
            )

    def on_llm_error(exc: Exception) -> str:
        logger_obj.debug("LLM API error: %s", exc)
        return _format_llm_api_error_message(exc)

    return QueryEngineCallbacks(
        accumulate_usage=usage_accumulator,
        on_stream_content=on_stream_content,
        on_stream_reasoning=on_stream_reasoning,
        before_tool=before_tool,
        after_tool=after_tool,
        request_tool_approval=request_tool_approval,
        on_llm_error=on_llm_error,
        on_context_compacted=on_context_compacted,
    )


async def _maybe_resume_pending_preflight_request(
    *,
    chat_id: int | str,
    user_content: str | list,
    session_id: str | None,
) -> str | None:
    state = pending_preflight_requests.get(chat_id)
    if not state or not isinstance(user_content, str):
        return None

    user_text = user_content.strip()
    if not user_text or user_text.startswith("/"):
        return None

    if (
        state.get("payload", {}).get("confirmations")
        and not state.get("pending_fields")
        and not _is_affirmative_preflight_confirmation(user_text)
    ):
        pending_preflight_requests.pop(chat_id, None)
        return None

    resolved, remaining = _parse_preflight_reply(state, user_text)
    state["answers"] = resolved
    if remaining:
        pending_preflight_requests[chat_id] = state
        return _build_pending_preflight_message(state, answered=resolved, remaining_fields=remaining)

    updated_args = _apply_preflight_answers(
        state.get("original_args", {}),
        state.get("pending_fields", []),
        resolved,
    )
    if state.get("payload", {}).get("confirmations"):
        updated_args["confirmed_preflight"] = True
    pending_preflight_requests.pop(chat_id, None)
    result = await execute_omicsclaw(updated_args, session_id=session_id, chat_id=chat_id)

    pending_payload = _extract_pending_preflight_payload(result)
    if _preflight_payload_needs_reply(pending_payload):
        _remember_pending_preflight_request(
            chat_id,
            args=updated_args,
            payload=pending_payload,
        )
    return strip_user_guidance_lines(result) or result


async def llm_tool_loop(
    chat_id: int | str,
    user_content: str | list,
    user_id: str = None,
    platform: str = None,
    plan_context: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    scoped_memory_scope: str = "",
    mcp_servers: tuple[str, ...] | None = None,
    output_style: str = "",
    progress_fn=None,
    progress_update_fn=None,
    on_tool_call=None,
    on_tool_result=None,
    on_stream_content=None,
    on_stream_reasoning=None,
    on_context_compacted=None,
    # Per-request runtime overrides (desktop app frontend)
    model_override: str = "",
    extra_api_params: dict | None = None,
    max_tokens_override: int = 0,
    system_prompt_append: str = "",
    mode: str = "",
    usage_accumulator=None,
    request_tool_approval=None,
    policy_state=None,
) -> str:
    """
    Run the LLM tool-use loop:
    1. Append user message to history
    2. Call LLM with system prompt + history + tools
    3. If tool_calls -> execute -> append results -> call again
    4. Return final text

    progress_fn: async callable(msg) -> handle. Sends a progress message, returns a handle.
    progress_update_fn: async callable(handle, msg). Updates a previously sent progress message.
    on_tool_call: async callable(tool.name, arguments: dict). Called before a tool executes.
    on_tool_result: async callable(tool.name, result: Any). Called after a tool completes.
    on_stream_content: async callable(chunk: str). Called as final text streams in.
    """
    # Slash-command dispatch — registry lives in bot.commands.
    # Unknown / commands return None and fall through to the LLM,
    # preserving the original if-elif behaviour.
    if isinstance(user_content, str) and user_content.strip().startswith("/"):
        slash_result = await _dispatch_slash_command(
            SlashCommandContext(
                chat_id=chat_id,
                user_id=user_id,
                platform=platform,
                user_text=user_content,
                workspace=workspace,
                pipeline_workspace=pipeline_workspace,
            )
        )
        if slash_result is not None:
            return slash_result

    resumed_result = await _maybe_resume_pending_preflight_request(
        chat_id=chat_id,
        user_content=user_content,
        session_id=f"{platform}:{user_id}:{chat_id}" if user_id and platform else None,
    )
    if resumed_result is not None:
        transcript_store.append_user_message(chat_id, user_content)
        transcript_store.append_assistant_message(chat_id, content=resumed_result)
        return resumed_result

    _ensure_system_prompt()

    def _bind_callbacks_builder(**engine_kwargs):
        # Engine doesn't carry the bot's logger; bind it here so the
        # callback builder still gets the right ``logger_obj`` arg.
        return _build_bot_query_engine_callbacks(logger_obj=logger, **engine_kwargs)

    deps = EngineDependencies(
        transcript_store=transcript_store,
        tool_result_store=tool_result_store,
        llm=_core.llm,
        omicsclaw_model=_core.OMICSCLAW_MODEL or "",
        llm_provider_name=_core.LLM_PROVIDER_NAME or "",
        session_manager=_core.session_manager,
        omicsclaw_dir=str(OMICSCLAW_DIR),
        max_history=MAX_HISTORY,
        max_history_chars=MAX_HISTORY_CHARS or None,
        max_conversations=MAX_CONVERSATIONS,
        audit_fn=audit,
        usage_accumulator=usage_accumulator or _accumulate_usage,
        skill_aliases=tuple(_skill_registry().skills.keys()),
        deep_learning_methods=DEEP_LEARNING_METHODS,
        tool_runtime=_build_tool_runtime(),
        tool_registry=get_tool_registry(),
        callbacks_builder=_bind_callbacks_builder,
    )

    return await run_engine_loop(
        deps=deps,
        chat_id=chat_id,
        user_content=user_content,
        user_id=user_id,
        platform=platform,
        plan_context=plan_context,
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
        scoped_memory_scope=scoped_memory_scope,
        mcp_servers=mcp_servers,
        output_style=output_style,
        progress_fn=progress_fn,
        progress_update_fn=progress_update_fn,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
        on_stream_content=on_stream_content,
        on_stream_reasoning=on_stream_reasoning,
        on_context_compacted=on_context_compacted,
        model_override=model_override,
        extra_api_params=extra_api_params,
        max_tokens_override=max_tokens_override,
        system_prompt_append=system_prompt_append,
        mode=mode,
        request_tool_approval=request_tool_approval,
        policy_state=policy_state,
    )


# ---------------------------------------------------------------------------

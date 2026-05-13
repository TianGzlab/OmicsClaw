"""Surface-agnostic LLM tool-loop body.

``run_engine_loop`` is the post-slash-command, post-preflight-resume
half of the chat request: build the chat context, apply the
identity anchor, wire tool plumbing, and dispatch to
``run_query_engine``. It receives every bot-side dependency through
``EngineDependencies`` so this module never imports from ``bot/``
(enforced by ``tests/test_no_reverse_imports.py``).

Carved out of ``bot/agent_loop.py:llm_tool_loop`` per ADR-0001.
The bot side keeps ownership of slash-command dispatch (Task #8 will
extract it to a registry) and preflight-resume; everything that
follows lives here.
"""

from __future__ import annotations

import os
from typing import Any

from openai import APIError

from omicsclaw.runtime.context_assembler import (
    assemble_chat_context as _assemble_chat_context,
)
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.policy_state import ToolPolicyState
from omicsclaw.runtime.query_engine import (
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.system_prompt import build_system_prompt
from omicsclaw.runtime.transcript_store import (
    build_selective_replay_context,
)

from ._dependencies import EngineDependencies
from ._identity_anchor import (
    apply_model_identity_anchor,
    resolve_effective_model_provider,
)


# Mirrors the constant previously inlined in bot/agent_loop.py.
# Lives here because the engine is the only consumer.
MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))
DEFAULT_MAX_TOKENS = 8192

LLM_NOT_CONFIGURED_MESSAGE = (
    "⚠ LLM is not configured.\n"
    "\n"
    "Set LLM_API_KEY (or OPENAI_API_KEY) in your environment or "
    ".env file, then restart `oc chat`. To configure interactively, "
    "run `oc onboard`."
)

_MODE_HINTS: dict[str, str] = {
    "code": (
        "You are in code mode. Prefer writing and editing code to "
        "accomplish the user's goals."
    ),
    "plan": (
        "You are in plan mode. Create detailed plans and explain "
        "your reasoning before taking action."
    ),
}


def _maybe_append_mode_hint(system_prompt: str, mode: str) -> str:
    if not mode or mode == "ask":
        return system_prompt
    hint = _MODE_HINTS.get(mode, "")
    if not hint:
        return system_prompt
    return system_prompt.rstrip() + "\n\n## Mode\n" + hint


def _maybe_append_caller_addition(system_prompt: str, addition: str) -> str:
    if not addition:
        return system_prompt
    return system_prompt.rstrip() + "\n\n" + addition.strip()


async def run_engine_loop(
    *,
    deps: EngineDependencies,
    chat_id: int | str,
    user_content: str | list,
    user_id: str | None = None,
    platform: str | None = None,
    plan_context: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    scoped_memory_scope: str = "",
    mcp_servers: tuple[str, ...] | None = None,
    output_style: str = "",
    progress_fn: Any = None,
    progress_update_fn: Any = None,
    on_tool_call: Any = None,
    on_tool_result: Any = None,
    on_stream_content: Any = None,
    on_stream_reasoning: Any = None,
    on_context_compacted: Any = None,
    model_override: str = "",
    extra_api_params: dict | None = None,
    max_tokens_override: int = 0,
    system_prompt_append: str = "",
    mode: str = "",
    request_tool_approval: Any = None,
    policy_state: Any = None,
) -> str:
    """Drive the LLM-plus-tools loop for a single chat turn.

    Returns the assistant's final user-facing reply.
    """
    if deps.llm is None:
        return LLM_NOT_CONFIGURED_MESSAGE

    transcript_store = deps.transcript_store
    transcript_store.max_history = deps.max_history
    transcript_store.max_history_chars = deps.max_history_chars
    transcript_store.max_conversations = deps.max_conversations

    transcript_context = build_selective_replay_context(
        transcript_store.get_history(chat_id),
        metadata=(
            {"pipeline_workspace": pipeline_workspace} if pipeline_workspace else None
        ),
        workspace=workspace,
        max_messages=transcript_store.max_history,
        max_chars=transcript_store.max_history_chars,
        sanitizer=transcript_store.sanitizer,
    )

    chat_context = await _assemble_chat_context(
        chat_id=chat_id,
        user_content=user_content,
        user_id=user_id,
        platform=platform,
        session_manager=deps.session_manager,
        system_prompt_builder=build_system_prompt,
        skill_aliases=deps.skill_aliases,
        plan_context=plan_context,
        transcript_context=transcript_context,
        omicsclaw_dir=deps.omicsclaw_dir,
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
        scoped_memory_scope=scoped_memory_scope,
        mcp_servers=tuple(mcp_servers or ()),
        output_style=output_style,
    )

    effective_model, effective_provider = resolve_effective_model_provider(
        model_override, deps.omicsclaw_model, deps.llm_provider_name
    )
    system_prompt = apply_model_identity_anchor(
        chat_context.system_prompt, effective_model, effective_provider
    )
    system_prompt = _maybe_append_caller_addition(system_prompt, system_prompt_append)
    system_prompt = _maybe_append_mode_hint(system_prompt, mode)

    request_tools = tuple(
        deps.tool_registry.to_openai_tools_for_request(
            chat_context.prompt_context.request
        )
    )
    hook_runtime = build_default_lifecycle_hook_runtime(deps.omicsclaw_dir)

    callbacks = deps.callbacks_builder(
        chat_id=chat_id,
        progress_fn=progress_fn,
        progress_update_fn=progress_update_fn,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
        on_stream_content=on_stream_content,
        on_stream_reasoning=on_stream_reasoning,
        request_tool_approval=request_tool_approval,
        audit_fn=deps.audit_fn,
        deep_learning_methods=deps.deep_learning_methods,
        usage_accumulator=deps.usage_accumulator,
        on_context_compacted=on_context_compacted,
    )

    # Surface flows into audit/metrics; an absent platform is caller misuse,
    # not bot traffic — keep it visible as "unknown" instead of masquerading.
    surface = platform or "unknown"
    resolved_policy_state = ToolPolicyState.from_mapping(policy_state, surface=surface)

    return await run_query_engine(
        llm=deps.llm,
        context=QueryEngineContext(
            chat_id=chat_id,
            session_id=chat_context.session_id,
            system_prompt=system_prompt,
            user_message_content=chat_context.user_message_content,
            surface=surface,
            policy_state=resolved_policy_state,
            hook_runtime=hook_runtime,
            tool_runtime_context={
                "omicsclaw_dir": deps.omicsclaw_dir,
                "workspace": workspace,
                "pipeline_workspace": pipeline_workspace,
            },
            request_tools=request_tools,
        ),
        tool_runtime=deps.tool_runtime,
        transcript_store=transcript_store,
        tool_result_store=deps.tool_result_store,
        config=QueryEngineConfig(
            model=model_override or deps.omicsclaw_model,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=(
                max_tokens_override if max_tokens_override > 0 else DEFAULT_MAX_TOKENS
            ),
            llm_error_types=(APIError,),
            extra_api_params=extra_api_params or {},
            deepseek_reasoning_passback=(
                (deps.llm_provider_name or "").strip().lower() == "deepseek"
            ),
        ),
        callbacks=callbacks,
    )

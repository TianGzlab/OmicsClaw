"""Surface-agnostic DI surface for ``omicsclaw/engine/loop.py``.

The engine loop must not import from ``bot/`` (enforced by
``tests/test_no_reverse_imports.py``). Every bot-side singleton,
constant, and callback the engine needs is therefore funnelled
through ``EngineDependencies`` — built by the bot once per request
and passed in. The shape doubles as documentation: every entry in
this dataclass is a coupling point that future refactors must keep
visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EngineDependencies:
    """All bot-side state + functions ``run_engine_loop`` reads.

    Frozen so the engine cannot mutate caller state by accident, and
    construction is per-request so late-bound runtime values
    (``llm``, ``session_manager``) reach the engine via an explicit
    snapshot rather than through module globals.
    """

    # ── State stores ──────────────────────────────────────────────
    transcript_store: Any
    """Conversation history: ``get_history``, ``append_user_message``,
    ``append_assistant_message``, plus ``max_history`` / ``sanitizer``
    config the engine sets per request."""

    tool_result_store: Any
    """Tool-call result history; passed straight to
    ``run_query_engine``."""

    # ── LLM runtime (late-bound at request time) ──────────────────
    llm: Any | None
    """``AsyncOpenAI`` client. The engine returns a user-facing
    setup prompt and skips the loop when this is ``None``."""

    omicsclaw_model: str
    """Default model id, used when no per-request override is given.
    Surfaced via the identity anchor and ``QueryEngineConfig.model``."""

    llm_provider_name: str
    """Provider name (``deepseek``, ``openai``, ...). Surfaced via
    the identity anchor and gates the deepseek reasoning passback."""

    session_manager: Any | None
    """Session lookup for memory scoping; passed to
    ``_assemble_chat_context``."""

    # ── Path + size constants ─────────────────────────────────────
    omicsclaw_dir: str
    """Repository root path. Forwarded to ``build_system_prompt`` and
    the tool runtime context."""

    max_history: int
    max_history_chars: int | None
    max_conversations: int
    """Transcript-store sizing limits applied at the start of each
    request. ``max_history_chars=None`` means unlimited."""

    # ── Callbacks / functions ─────────────────────────────────────
    audit_fn: Callable[..., None]
    """Emits ``tool_call`` / ``tool_error`` / ``tool_policy_blocked``
    audit events from inside the per-request callbacks."""

    usage_accumulator: Callable[..., Any]
    """Wired into ``QueryEngineCallbacks.accumulate_usage`` to track
    per-request token costs."""

    # ── Skill metadata ────────────────────────────────────────────
    skill_aliases: tuple[str, ...]
    """Canonical skill names; passed to ``_assemble_chat_context``
    so the LLM sees the routing surface in its system prompt."""

    deep_learning_methods: Any
    """Set/frozenset of method names that trigger the deep-learning
    slow-warning in the ``before_tool`` callback."""

    # ── Tool plumbing (built once per request by bot) ─────────────
    tool_runtime: Any
    """Pre-built ``ToolRuntime``; passed straight to
    ``run_query_engine``."""

    tool_registry: Any
    """Pre-built ``ToolRegistry`` whose ``to_openai_tools_for_request``
    filters tools per request."""

    callbacks_builder: Callable[..., Any]
    """Constructs ``QueryEngineCallbacks`` per request. Receives the
    request-specific callback functions (``progress_fn``,
    ``on_tool_call``, ...) and returns a fully-bound
    ``QueryEngineCallbacks`` instance."""

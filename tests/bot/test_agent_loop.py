"""Unit tests for ``bot.agent_loop`` — the multi-round LLM dispatch loop.

The agent loop is the central path every User-facing entry walks through:
``bot/`` channels, ``omicsclaw/app/server.py``, and ``omicsclaw/interactive
/interactive.py`` all delegate to ``llm_tool_loop``. These tests pin its
observable contract:

* The function lives at ``bot.agent_loop`` (canonical home) and is also
  re-exported through ``bot.core`` for backward-compat.
* Its signature accepts the call sites that production uses (`chat_id`
  / `user_content` plus the keyword-only override knobs).

Behaviour tests against a fake ``AsyncOpenAI`` client (single-round /
multi-round tool dispatch / streaming / error paths) are written
incrementally as the extraction lands.
"""

from __future__ import annotations

import inspect


def test_llm_tool_loop_lives_in_bot_agent_loop():
    """Tracer bullet: the canonical home is ``bot.agent_loop``."""
    import bot.agent_loop  # noqa: F401

    assert hasattr(bot.agent_loop, "llm_tool_loop")
    assert inspect.iscoroutinefunction(bot.agent_loop.llm_tool_loop)


def test_bot_core_re_exports_llm_tool_loop_with_identity():
    """Backward-compat: ``omicsclaw/app/server.py`` and
    ``omicsclaw/interactive/interactive.py`` invoke ``core.llm_tool_loop``;
    the symbol must resolve to the same coroutine on both modules."""
    import bot.agent_loop
    import bot.core

    assert bot.core.llm_tool_loop is bot.agent_loop.llm_tool_loop


def test_llm_tool_loop_signature_matches_production_call_sites():
    """Pin the kwargs that ``omicsclaw/app/server.py:1740`` and
    ``omicsclaw/interactive/interactive.py:1505`` actually pass —
    a renamed kwarg would break those entries silently."""
    import bot.agent_loop

    sig = inspect.signature(bot.agent_loop.llm_tool_loop)
    params = sig.parameters
    # Required positional arg
    assert "chat_id" in params
    assert "user_content" in params
    # Keyword-only knobs the desktop-app entry passes
    expected_kwargs = {
        "user_id",
        "platform",
        "workspace",
        "pipeline_workspace",
        "output_style",
        "mcp_servers",
        "on_tool_call",
        "on_tool_result",
        "on_stream_content",
        "on_stream_reasoning",
        "on_context_compacted",
        "usage_accumulator",
        "request_tool_approval",
        "policy_state",
        "model_override",
        "extra_api_params",
        "max_tokens_override",
        "system_prompt_append",
        "mode",
    }
    missing = expected_kwargs - set(params)
    assert not missing, f"Missing kwargs: {missing}"


# --- Pure-helper behavior tests --------------------------------------------


def test_coerce_timeout_seconds_accepts_int_and_numeric_strings():
    """``_coerce_timeout_seconds`` is the input normaliser for tool-result
    timeout overrides. It accepts int, float, and numeric strings; returns
    ``None`` for unparseable inputs so the caller knows to skip the
    override. Float values round to the nearest second (``round`` not
    truncate) — so ``45.7`` → 46."""
    from bot.agent_loop import _coerce_timeout_seconds

    assert _coerce_timeout_seconds(60) == 60
    assert _coerce_timeout_seconds("120") == 120
    assert _coerce_timeout_seconds(45.7) == 46  # round to nearest int
    assert _coerce_timeout_seconds(0.3) == 1   # min clamp at 1 second
    assert _coerce_timeout_seconds(0) is None  # zero / negative → None
    assert _coerce_timeout_seconds(-5) is None
    assert _coerce_timeout_seconds("not-a-number") is None
    assert _coerce_timeout_seconds(None) is None


def test_extract_timeout_seconds_from_text_recognises_timeout_phrases():
    """When a tool emits a stderr line like ``"timed out after 60 seconds"``
    or ``"timeout after 90s"``, the loop extracts the seconds for the
    next-iteration override. The matcher is intentionally narrow — only
    explicit timeout phrases trigger, so unrelated numeric stderr text
    doesn't trip the override."""
    from bot.agent_loop import _extract_timeout_seconds_from_text

    assert _extract_timeout_seconds_from_text("timed out after 60 seconds") == 60
    assert _extract_timeout_seconds_from_text("Job timeout after 90s") == 90
    # Unrelated numeric text — no match (the matcher is deliberately strict)
    assert _extract_timeout_seconds_from_text("there were 42 records") is None
    assert _extract_timeout_seconds_from_text("regular log line") is None
    # Empty / None handled gracefully
    assert _extract_timeout_seconds_from_text("") is None
    assert _extract_timeout_seconds_from_text(None) is None


def test_llm_tool_loop_returns_actionable_message_when_llm_uninitialised():
    """If ``bot.core.llm`` is ``None`` (e.g. ``oc chat`` started without an
    API key), sending a message must return an actionable hint — naming
    the env var to set and the onboard command — rather than the cryptic
    ``Error: LLM client not initialised. Call core.init() first.`` that
    blames the user for not running a function they cannot reach.
    """
    import asyncio
    import bot.agent_loop as agent_loop
    import bot.core as core

    saved = core.llm
    core.llm = None
    try:
        result = asyncio.run(
            agent_loop.llm_tool_loop(
                chat_id="__test_uninitialised__",
                user_content="hi",
            )
        )
    finally:
        core.llm = saved

    lower = result.lower()
    assert "call core.init" not in lower, (
        f"message still tells the user to call a private function: {result!r}"
    )
    assert "llm_api_key" in lower or "openai_api_key" in lower, (
        f"message must name the env var to set: {result!r}"
    )
    assert "onboard" in lower, (
        f"message must point at the onboard remediation: {result!r}"
    )


def test_format_llm_api_error_message_provides_actionable_text_for_common_errors():
    """When the OpenAI SDK raises, this formatter turns the exception into
    a user-facing message with hints (rate limit, auth, network). The
    chat surface displays the formatted string verbatim — must be
    non-empty and reference the exception class name."""
    from bot.agent_loop import _format_llm_api_error_message

    # Plain Exception fallback
    msg = _format_llm_api_error_message(RuntimeError("kaboom"))
    assert msg
    assert "kaboom" in msg or "RuntimeError" in msg

    # Empty exception still produces a message (no crash)
    msg2 = _format_llm_api_error_message(Exception())
    assert msg2  # non-empty string

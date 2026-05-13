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


class _FakeExecutionResult:
    """Minimal stand-in for an ExecutionResult — only attributes the
    metadata builder reads."""

    def __init__(self, *, success: bool, status: str = "", error: Exception | None = None):
        self.success = success
        self.status = status
        self.error = error


def test_build_tool_result_callback_metadata_marks_failure_as_error():
    """Baseline: a non-success tool result without a preflight payload
    is reported as ``is_error=True`` so UIs can collapse it as a
    failure tile."""
    from bot.agent_loop import _build_tool_result_callback_metadata

    metadata = _build_tool_result_callback_metadata(
        _FakeExecutionResult(success=False), display_output="boom"
    )

    assert metadata["is_error"] is True
    assert metadata.get("preflight_pending") is None


def test_build_tool_result_callback_metadata_demotes_preflight_pending_from_error():
    """A preflight that needs user input is the structured ``needs_user_input``
    path — the subprocess exits non-zero by design so callers can stash
    state and prompt. UIs that gate on ``is_error`` would otherwise hide
    the confirmation text. With ``pending_preflight`` passed in, the
    metadata must:

      - report ``is_error=False`` (so the desktop frontend renders the
        guidance instead of collapsing it as an error)
      - carry ``preflight_pending=True`` and the original payload so
        surfaces can light up dedicated confirmation UI
      - preserve ``success`` and ``status`` from the underlying result —
        the run did fail at the process level; only the UX classification
        changes
    """
    from bot.agent_loop import _build_tool_result_callback_metadata

    payload = {
        "kind": "preflight",
        "status": "needs_user_input",
        "skill_name": "sc-preprocessing",
        "confirmations": ["confirm defaults are acceptable"],
        "pending_fields": [],
    }
    metadata = _build_tool_result_callback_metadata(
        _FakeExecutionResult(success=False, status="error"),
        display_output="preflight check failed",
        pending_preflight=payload,
    )

    assert metadata["is_error"] is False
    assert metadata["preflight_pending"] is True
    assert metadata["preflight_payload"] == payload
    assert metadata["success"] is False
    assert metadata["status"] == "error"


def test_after_tool_forwards_pending_preflight_payload_to_on_tool_result(monkeypatch):
    """Integration: the ``after_tool`` callback constructed by
    ``_build_bot_query_engine_callbacks`` must detect a preflight
    ``needs_user_input`` payload in an ``omicsclaw`` tool result, stash
    it, AND forward the payload to ``on_tool_result`` so a surface
    (desktop / TUI / bot) can surface a confirmation UI instead of
    rendering the run as a generic error.

    This is the regression test for the desktop app failing silently on
    sc-preprocessing preflight blocks (no confirmation surfaced).
    """
    import asyncio
    import json
    from types import SimpleNamespace

    import bot.agent_loop as agent_loop
    import bot.core as core

    # Isolate the global stash so we don't leak across tests.
    monkeypatch.setattr(core, "pending_preflight_requests", {}, raising=False)

    captured: list[tuple[str, object, dict]] = []

    async def fake_on_tool_result(name, output, metadata):
        captured.append((name, output, metadata))

    async def noop(*args, **kwargs):
        return None

    callbacks = agent_loop._build_bot_query_engine_callbacks(
        chat_id="chat-preflight",
        progress_fn=None,
        progress_update_fn=None,
        on_tool_call=noop,
        on_tool_result=fake_on_tool_result,
        on_stream_content=noop,
        on_stream_reasoning=noop,
        request_tool_approval=noop,
        logger_obj=SimpleNamespace(
            info=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        audit_fn=lambda *a, **k: None,
        deep_learning_methods=set(),
        usage_accumulator=lambda *_a, **_k: {},
    )

    payload = {
        "kind": "preflight",
        "status": "needs_user_input",
        "skill_name": "sc-preprocessing",
        "confirmations": ["Confirm defaults are acceptable"],
        "pending_fields": [],
        "missing_requirements": [],
    }
    tool_content = (
        "Important follow-up\n\n"
        f"USER_GUIDANCE_JSON: {json.dumps(payload)}\n"
        "preflight check failed\n"
    )

    request = SimpleNamespace(
        name="omicsclaw",
        arguments={"skill": "preprocess", "file_path": "/tmp/x.h5ad"},
        spec=None,
        policy_decision=None,
        executor=lambda *_a, **_k: None,
    )
    execution_result = SimpleNamespace(
        request=request,
        success=False,
        status="error",
        error=None,
        policy_decision=None,
    )
    result_record = SimpleNamespace(content=tool_content)

    asyncio.run(callbacks.after_tool(execution_result, result_record, {}))

    assert len(captured) == 1
    name, output, metadata = captured[0]
    assert name == "omicsclaw"
    assert metadata["is_error"] is False, (
        "preflight needs_user_input must not be classified as an error — "
        "the desktop frontend hides error tile content"
    )
    assert metadata["preflight_pending"] is True
    assert metadata["preflight_payload"]["status"] == "needs_user_input"
    assert metadata["preflight_payload"]["skill_name"] == "sc-preprocessing"
    # State is also stashed for the resume path on the next user message.
    assert "chat-preflight" in core.pending_preflight_requests


def test_after_tool_does_not_mark_preflight_pending_for_normal_failure(monkeypatch):
    """Sanity inverse: an ordinary tool failure (no preflight payload in
    the result) must NOT carry ``preflight_pending`` — otherwise every
    failed run would leak the marker and confuse downstream UIs."""
    import asyncio
    from types import SimpleNamespace

    import bot.agent_loop as agent_loop
    import bot.core as core

    monkeypatch.setattr(core, "pending_preflight_requests", {}, raising=False)

    captured: list[dict] = []

    async def fake_on_tool_result(name, output, metadata):
        captured.append(metadata)

    async def noop(*args, **kwargs):
        return None

    callbacks = agent_loop._build_bot_query_engine_callbacks(
        chat_id="chat-normal-fail",
        progress_fn=None,
        progress_update_fn=None,
        on_tool_call=noop,
        on_tool_result=fake_on_tool_result,
        on_stream_content=noop,
        on_stream_reasoning=noop,
        request_tool_approval=noop,
        logger_obj=SimpleNamespace(
            info=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        audit_fn=lambda *a, **k: None,
        deep_learning_methods=set(),
        usage_accumulator=lambda *_a, **_k: {},
    )

    request = SimpleNamespace(
        name="omicsclaw",
        arguments={"skill": "qc"},
        spec=None,
        policy_decision=None,
        executor=lambda *_a, **_k: None,
    )
    execution_result = SimpleNamespace(
        request=request,
        success=False,
        status="error",
        error=None,
        policy_decision=None,
    )
    result_record = SimpleNamespace(content="skill crashed with KeyError 'foo'")

    asyncio.run(callbacks.after_tool(execution_result, result_record, {}))

    assert len(captured) == 1
    metadata = captured[0]
    assert metadata["is_error"] is True
    assert metadata.get("preflight_pending") is None


def test_build_tool_result_callback_metadata_timeout_overrides_preflight_demotion():
    """If the tool genuinely timed out, that is an error regardless of
    any preflight payload — don't let a stale payload mask a hung run.
    """
    from bot.agent_loop import _build_tool_result_callback_metadata

    metadata = _build_tool_result_callback_metadata(
        _FakeExecutionResult(success=False),
        display_output="timed out after 120 seconds",
        pending_preflight={"kind": "preflight", "status": "needs_user_input"},
    )

    assert metadata["is_error"] is True
    assert metadata.get("timed_out") is True
    # The marker is still emitted so callers can choose to react, but
    # is_error wins on a real timeout.
    assert metadata["preflight_pending"] is True

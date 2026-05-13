"""Contract for the slash-command registry that replaced the
~250-line if-elif chain in bot/agent_loop.py:llm_tool_loop.

Phase 1 P0-E (Task #8). The registry lives in ``bot/commands/``
because the handlers read bot-side state (transcript_store,
DATA_DIR, format_skills_table, …) heavily — moving them to
``omicsclaw/engine/`` would require an even larger DI surface
than EngineDependencies and re-introduce reverse-import temptation.
"""

from __future__ import annotations

import asyncio

from bot.commands import (
    SlashCommandContext,
    dispatch,
    registered_commands,
)


def _make_ctx(text: str = "/help") -> SlashCommandContext:
    return SlashCommandContext(
        chat_id="__test_chat__",
        user_id=None,
        platform=None,
        user_text=text,
        workspace="",
        pipeline_workspace="",
    )


def test_dispatch_returns_none_for_unknown_slash_command() -> None:
    """Unknown ``/`` commands fall through to the LLM. The dispatcher
    must signal this with ``None`` so the wirer can keep walking."""
    assert asyncio.run(dispatch(_make_ctx("/no-such-command"))) is None


def test_dispatch_returns_none_for_non_slash_text() -> None:
    """Plain user text — even if it contains a slash mid-sentence —
    must not be dispatched as a command."""
    assert asyncio.run(dispatch(_make_ctx("hello / world"))) is None


def test_dispatch_normalises_case_and_whitespace() -> None:
    """Mirrors the legacy behaviour of ``user_content.strip().lower()``
    that the if-elif chain used as its dispatch key."""
    bare = asyncio.run(dispatch(_make_ctx("/help")))
    padded_upper = asyncio.run(dispatch(_make_ctx("  /HELP  ")))
    assert bare == padded_upper
    assert bare is not None


def test_help_returns_command_reference_text() -> None:
    result = asyncio.run(dispatch(_make_ctx("/help")))
    assert result is not None
    # The /help reply enumerates the major commands so users discover
    # them. If anyone changes the format, at least these three names
    # must remain.
    assert "/clear" in result
    assert "/forget" in result
    assert "/help" in result


def test_all_legacy_commands_registered() -> None:
    """All 14 commands that the pre-refactor if-elif handled must
    survive the move into the registry, by name. Add new commands by
    extending this set + implementing the handler."""
    expected = {
        "/clear",
        "/new",
        "/forget",
        "/plan",
        "/compact",
        "/files",
        "/outputs",
        "/recent",
        "/skills",
        "/demo",
        "/examples",
        "/help",
        "/status",
        "/version",
    }
    actual = set(registered_commands())
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"slash commands lost in registry refactor: {missing}"
    # Extras are not a hard error (someone may have added a command
    # without updating this test) but warn loud.
    assert not extra, (
        f"slash commands added without updating this test's expected set: "
        f"{extra}"
    )


def test_static_text_commands_round_trip_without_state() -> None:
    """``/demo`` and ``/examples`` are pure-text replies — no
    transcript_store, no LLM. They should return the same text in any
    context, providing a smoke test that the dispatcher hooks them up."""
    demo = asyncio.run(dispatch(_make_ctx("/demo")))
    examples = asyncio.run(dispatch(_make_ctx("/examples")))
    assert demo is not None and "Demo Options" in demo
    assert examples is not None and "Usage Examples" in examples

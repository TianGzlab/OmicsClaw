"""Phase 3 (Task 3.1) RED tests for the new ``surface_voice_rules`` injector.

The injector replaces the per-surface voice subsections that used to live
inside SOUL.md (Bot Mode / CLI Mode). It emits a small block (≤600 chars)
that adapts the agent's tone to the active surface:

- bot         — emoji OK sparingly, markdown formatting allowed
- interactive — plain text only, UPPERCASE for emphasis
- pipeline    — same plain-text rule as interactive
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.context_assembler import assemble_prompt_context
from omicsclaw.runtime.context_layers import (
    DEFAULT_CONTEXT_LAYER_INJECTORS,
    ContextAssemblyRequest,
)


def _layer_for(surface: str) -> str:
    asm = assemble_prompt_context(request=ContextAssemblyRequest(surface=surface))
    for layer in asm.layers:
        if layer.name == "surface_voice_rules":
            return layer.content
    return ""


def test_surface_voice_rules_injector_is_registered() -> None:
    names = [inj.name for inj in DEFAULT_CONTEXT_LAYER_INJECTORS]
    assert "surface_voice_rules" in names


def test_surface_voice_rules_for_bot_allows_emoji() -> None:
    text = _layer_for("bot")
    assert text, "bot voice rules layer empty"
    lower = text.lower()
    # Bot mode lets the agent use emoji sparingly.
    assert "emoji" in lower
    assert "no emoji" not in lower, "bot must not get the no-emoji rule"


def test_surface_voice_rules_for_interactive_forbids_emoji_and_markdown_bold() -> None:
    text = _layer_for("interactive")
    assert text, "interactive voice rules layer empty"
    lower = text.lower()
    assert "no emoji" in lower or "plain text" in lower
    # CLI mode prefers UPPERCASE over markdown bold.
    assert "uppercase" in lower or "**bold**" not in text


def test_surface_voice_rules_for_pipeline_uses_plain_text() -> None:
    text = _layer_for("pipeline")
    assert text, "pipeline voice rules layer empty"
    lower = text.lower()
    assert "no emoji" in lower or "plain text" in lower


def test_surface_voice_rules_size_under_600_chars_per_surface() -> None:
    for surface in ("bot", "interactive", "pipeline"):
        text = _layer_for(surface)
        assert 0 < len(text) <= 600, (
            f"surface_voice_rules for {surface}: {len(text)} chars (budget 600)"
        )


def test_surface_voice_rules_bot_emoji_replaces_old_role_guardrails_emoji_rule() -> None:
    """Phase 1 had ``role_guardrails`` carry "emojis unless the user
    explicitly requests them" for every surface. After Phase 3, only
    interactive/pipeline get an explicit no-emoji rule; bot gets the
    permissive variant. This test pins that contract change."""
    bot = _layer_for("bot")
    interactive = _layer_for("interactive")
    assert "no emoji" not in bot.lower()
    assert "no emoji" in interactive.lower() or "plain text" in interactive.lower()

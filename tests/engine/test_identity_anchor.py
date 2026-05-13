"""Pure-function contracts for the model-identity helpers.

These functions live in ``omicsclaw/engine/`` so every user-facing
surface (``bot/agent_loop.py``, ``omicsclaw/app/server.py``,
``omicsclaw/interactive/``) can apply the same identity disclosure
without each one re-implementing the prompt block.
"""

from __future__ import annotations

from omicsclaw.engine import (
    apply_model_identity_anchor,
    resolve_effective_model_provider,
)


class TestResolveEffectiveModelProvider:
    def test_override_wins_over_default_model(self) -> None:
        assert resolve_effective_model_provider("override-m", "default-m", "p") == (
            "override-m",
            "p",
        )

    def test_falls_back_to_default_model_when_no_override(self) -> None:
        assert resolve_effective_model_provider(None, "default-m", "p") == (
            "default-m",
            "p",
        )
        assert resolve_effective_model_provider("", "default-m", "p") == (
            "default-m",
            "p",
        )

    def test_strips_whitespace(self) -> None:
        assert resolve_effective_model_provider(
            "  override-m  ", "x", "  p  "
        ) == ("override-m", "p")

    def test_all_empty_returns_empty_strings(self) -> None:
        assert resolve_effective_model_provider(None, None, None) == ("", "")
        assert resolve_effective_model_provider("", "", "") == ("", "")


class TestApplyModelIdentityAnchor:
    def test_appends_when_both_present(self) -> None:
        result = apply_model_identity_anchor("base prompt", "m1", "p1")
        assert result.startswith("base prompt")
        assert "## Underlying model identity" in result
        assert "`m1`" in result
        assert "`p1`" in result

    def test_unchanged_when_model_empty(self) -> None:
        assert apply_model_identity_anchor("base", "", "p1") == "base"

    def test_unchanged_when_provider_empty(self) -> None:
        assert apply_model_identity_anchor("base", "m1", "") == "base"

    def test_unchanged_when_both_empty(self) -> None:
        assert apply_model_identity_anchor("base", "", "") == "base"

    def test_strips_trailing_whitespace_before_anchor(self) -> None:
        result = apply_model_identity_anchor("base   \n\n", "m1", "p1")
        assert "base\n\n## Underlying model identity" in result

    def test_warns_against_impersonation(self) -> None:
        """The whole point of the anchor is to stop distilled / fine-tuned
        models from claiming to be Claude / GPT / etc."""
        result = apply_model_identity_anchor("base", "m1", "p1")
        assert "Claude" in result
        assert "GPT" in result
        assert "Anthropic" in result
        assert "OpenAI" in result

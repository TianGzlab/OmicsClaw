"""Tests for ``omicsclaw.provider._model_limits``.

The table is maintained by hand and will always be behind; what has to
hold is that a miss degrades usefully and that a gateway-prefixed name
finds the vendor's own entry instead of falling through.
"""

from __future__ import annotations

import pytest

from omicsclaw.provider import DEFAULT_MODEL_LIMITS, ModelLimits, get_model_limits
from omicsclaw.provider._model_limits import KNOWN_MODEL_LIMITS, bare_model_name


# --- Lookup behaviour -----------------------------------------------------


def test_a_known_model_returns_both_of_its_windows():
    limits = get_model_limits("claude-sonnet-4-6")
    assert limits == ModelLimits(context_tokens=1_000_000, output_tokens=64_000)


@pytest.mark.parametrize(
    ("qualified", "bare"),
    [
        ("openai/gpt-4o", "gpt-4o"),
        ("anthropic/claude-opus-4.7", "claude-opus-4.7"),
        ("deepseek-ai/deepseek-v3.2", "deepseek-v3.2"),
        ("Pro/zai-org/GLM-5", "glm-5"),
        ("nvidia/nemotron-3-super-120b-a12b", "nemotron-3-super-120b-a12b"),
    ],
)
def test_a_gateway_prefix_resolves_to_the_vendor_entry(qualified, bare):
    """Otherwise every model needs one entry per reseller."""
    assert get_model_limits(qualified) == get_model_limits(bare)
    assert get_model_limits(qualified) is not DEFAULT_MODEL_LIMITS


def test_only_the_last_slash_segment_survives():
    assert bare_model_name("Pro/MiniMaxAI/MiniMax-M2.5") == "minimax-m2.5"


def test_lookup_is_case_insensitive():
    """The same model arrives capitalized differently from each reseller."""
    assert get_model_limits("GPT-4o") == get_model_limits("gpt-4o")


def test_an_ollama_tag_keeps_its_suffix():
    """Only ``/`` is a prefix separator; ``:`` is part of the model name."""
    assert get_model_limits("gemma4:12b").context_tokens == 262_144
    assert get_model_limits("gemma4:e2b").context_tokens == 131_072


# --- The fallback ---------------------------------------------------------


def test_an_unknown_model_falls_back_conservatively():
    """A table miss is routine — local tags and new releases — and must
    degrade, not fail."""
    assert get_model_limits("some-model-released-tomorrow") is DEFAULT_MODEL_LIMITS
    assert DEFAULT_MODEL_LIMITS.context_tokens == 256_000


@pytest.mark.parametrize("model", ["", "   ", "vendor/"])
def test_an_empty_model_name_does_not_raise(model):
    assert get_model_limits(model) is DEFAULT_MODEL_LIMITS


# --- The table itself -----------------------------------------------------


def test_every_hosted_preset_default_model_is_known():
    """The out-of-the-box choice for a hosted backend must not land on the
    fallback. Local backends are exempt: an Ollama tag's window depends on
    what the user pulled, so guessing it here would be worse than falling
    back."""
    from omicsclaw.provider import PRESETS, ProviderTier

    for name, preset in PRESETS.items():
        if not preset.default_model or preset.tier is ProviderTier.LOCAL:
            continue
        assert get_model_limits(preset.default_model) is not DEFAULT_MODEL_LIMITS, name


def test_every_entry_declares_positive_windows():
    for model, limits in KNOWN_MODEL_LIMITS.items():
        assert limits.context_tokens > 0, model
        assert limits.output_tokens > 0, model


def test_no_entry_carries_a_gateway_prefix():
    """A key with a ``/`` past the first segment could never be reached by
    the bare-name lookup, so it would be silently dead."""
    assert not [model for model in KNOWN_MODEL_LIMITS if "/" in model]


def test_the_table_is_read_only():
    with pytest.raises(TypeError):
        KNOWN_MODEL_LIMITS["gpt-4o"] = ModelLimits(1, 1)  # type: ignore[index]

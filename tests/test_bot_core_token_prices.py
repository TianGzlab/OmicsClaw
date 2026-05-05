"""Regression tests for `_get_token_price` coverage.

The chat-billing UI only renders a dollar amount when the backend emits a
non-zero ``cost_usd``. The previous price table only covered DeepSeek plus
legacy OpenAI / Anthropic / Gemini / Qwen models, so current-generation model
identifiers (claude-sonnet-4-5, gpt-5, gemini-2.5-pro, …) silently mapped to
``(0.0, 0.0)`` and no cost was shown.

These tests pin the minimum coverage we expect from the pricing table.
"""

from __future__ import annotations

import pytest

from bot.core import _TOKEN_PRICES, _get_token_price  # noqa: F401


CURRENT_GENERATION_MODELS = [
    # Anthropic Claude 4.x family (current UI defaults)
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-haiku-4-5",
    # OpenAI GPT-5.x family (current UI defaults)
    "gpt-5",
    "gpt-5-mini",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "o4-mini",
    # Google Gemini 2.5 / 3 family
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3.1-pro",
    "gemini-3-flash",
    # Qwen / DashScope current tiers
    "qwen3-coder-plus",
    "qwen-max",
]


@pytest.mark.parametrize("model", CURRENT_GENERATION_MODELS)
def test_price_table_covers_current_generation_models(model):
    inp, out = _get_token_price(model)
    assert inp > 0, f"input price missing for {model!r}"
    assert out > 0, f"output price missing for {model!r}"


def test_deepseek_pricing_unchanged():
    # Baseline: DeepSeek has always been covered — fix must not regress this.
    assert _get_token_price("deepseek-v4-flash") == pytest.approx((0.27, 1.10))
    assert _get_token_price("deepseek-v4-pro") == pytest.approx((0.55, 2.19))
    assert _get_token_price("deepseek-chat") == pytest.approx((0.27, 1.10))
    assert _get_token_price("deepseek-reasoner") == pytest.approx((0.55, 2.19))


def test_unknown_model_still_returns_zero():
    # Unknown identifiers must explicitly signal "no estimate" so callers can
    # omit the cost line instead of inventing a number.
    assert _get_token_price("some-unheard-of-model-xyz") == (0.0, 0.0)


def test_more_specific_key_wins_over_family_prefix():
    # Matching must be longest-first so a sub-tier id (e.g. "gpt-5-mini")
    # doesn't silently inherit pricing from its family prefix ("gpt-5").
    # Otherwise mini / flash / lite variants would be billed at flagship rates.
    mini_in, mini_out = _get_token_price("gpt-5-mini")
    flag_in, flag_out = _get_token_price("gpt-5")
    assert (mini_in, mini_out) != (flag_in, flag_out)
    assert mini_in < flag_in
    assert mini_out < flag_out

    # Same guarantee inside the OpenRouter-style "openai/gpt-5.4-mini" id.
    assert _get_token_price("openai/gpt-5.4-mini") == _get_token_price("gpt-5.4-mini")


def test_env_override_wins_over_table():
    import os

    orig_in = os.environ.pop("LLM_INPUT_PRICE", None)
    orig_out = os.environ.pop("LLM_OUTPUT_PRICE", None)
    try:
        os.environ["LLM_INPUT_PRICE"] = "7"
        os.environ["LLM_OUTPUT_PRICE"] = "11"
        assert _get_token_price("deepseek-chat") == (7.0, 11.0)
    finally:
        os.environ.pop("LLM_INPUT_PRICE", None)
        os.environ.pop("LLM_OUTPUT_PRICE", None)
        if orig_in is not None:
            os.environ["LLM_INPUT_PRICE"] = orig_in
        if orig_out is not None:
            os.environ["LLM_OUTPUT_PRICE"] = orig_out

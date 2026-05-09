"""Unit tests for ``bot.billing`` — token pricing + usage accumulator.

The billing module owns the per-process token counters and the price table.
These tests drive each piece in isolation, using synthetic ``response.usage``
shapes so we never touch a real LLM client.

The existing ``tests/test_bot_core_token_prices.py`` covers the price table's
content (current-generation models, longest-key matching, env override) at the
``bot.core`` import path; this file covers the accumulator + snapshot
behavior at the canonical ``bot.billing`` path.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_billing_state():
    """Each test starts with zeroed counters."""
    from bot.billing import reset_usage
    reset_usage()
    yield
    reset_usage()


class _Usage:
    """Stand-in for an OpenAI ``response.usage`` object."""

    def __init__(self, prompt: int, completion: int, total: int | None = None):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total if total is not None else prompt + completion


def test_accumulate_usage_returns_delta_and_increments_running_totals():
    from bot.billing import accumulate_usage, get_usage_snapshot

    delta = accumulate_usage(_Usage(prompt=100, completion=50))

    assert delta == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    snap = get_usage_snapshot(model="deepseek-v4-flash")
    assert snap["prompt_tokens"] == 100
    assert snap["completion_tokens"] == 50
    assert snap["total_tokens"] == 150


def test_accumulate_usage_none_is_noop_and_returns_empty_dict():
    """Some provider responses arrive without a ``usage`` block (streaming
    edge cases, retries). Treat that as a no-op rather than crashing."""
    from bot.billing import accumulate_usage, get_usage_snapshot

    delta = accumulate_usage(None)

    assert delta == {}
    snap = get_usage_snapshot()
    assert snap["prompt_tokens"] == 0
    assert snap["completion_tokens"] == 0
    assert snap["total_tokens"] == 0


def test_bot_core_re_exports_share_billing_state():
    """Backward-compat contract: legacy callers and existing tests
    (``tests/test_bot_core_token_prices.py`` etc.) import ``_TOKEN_PRICES``,
    ``_get_token_price``, ``_accumulate_usage``, ``get_usage_snapshot``,
    ``reset_usage`` from ``bot.core``. After the extraction those names
    must resolve to the **same** objects as in ``bot.billing`` — not
    parallel copies — so accumulation through either path lands in a
    single shared counter."""
    import bot.core
    import bot.billing

    assert bot.core._TOKEN_PRICES is bot.billing._TOKEN_PRICES
    assert bot.core._get_token_price is bot.billing._get_token_price
    assert bot.core._accumulate_usage is bot.billing.accumulate_usage
    assert bot.core.reset_usage is bot.billing.reset_usage
    # Mutating through one path is observable through the other.
    bot.billing.reset_usage()
    bot.core._accumulate_usage(_Usage(prompt=42, completion=7))
    assert bot.billing.get_usage_snapshot()["prompt_tokens"] == 42


def test_reset_usage_zeros_every_counter_including_api_calls():
    """``reset_usage`` is the hook a new session uses to clear the previous
    chat's counters. It must zero every key — not just the token counts.
    Pre-extraction, ``api_calls`` was a frequent source of stale-count bugs
    when callers reset only the token-bearing fields."""
    from bot.billing import accumulate_usage, get_usage_snapshot, reset_usage

    accumulate_usage(_Usage(prompt=10, completion=5))
    accumulate_usage(_Usage(prompt=20, completion=10))

    snap_before = get_usage_snapshot()
    assert snap_before["prompt_tokens"] == 30
    assert snap_before["api_calls"] == 2

    reset_usage()
    snap_after = get_usage_snapshot()

    assert snap_after["prompt_tokens"] == 0
    assert snap_after["completion_tokens"] == 0
    assert snap_after["total_tokens"] == 0
    assert snap_after["api_calls"] == 0


def test_get_usage_snapshot_includes_model_provider_and_cost_estimate():
    """The snapshot is what the chat UI billing display reads — so it must
    carry the active model + provider context plus the cost computed from
    the current model's price tuple."""
    from bot.billing import accumulate_usage, get_usage_snapshot

    accumulate_usage(_Usage(prompt=1_000_000, completion=500_000))

    snap = get_usage_snapshot(model="deepseek-v4-flash", provider="deepseek")

    assert snap["model"] == "deepseek-v4-flash"
    assert snap["provider"] == "deepseek"
    # deepseek-v4-flash is (input=$0.27, output=$1.10) per 1M tokens
    assert snap["input_price_per_1m"] == pytest.approx(0.27)
    assert snap["output_price_per_1m"] == pytest.approx(1.10)
    # 1M input * $0.27 + 0.5M output * $1.10 = $0.27 + $0.55 = $0.82
    assert snap["estimated_cost_usd"] == pytest.approx(0.82)

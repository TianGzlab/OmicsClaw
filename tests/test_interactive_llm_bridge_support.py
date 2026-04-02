from types import SimpleNamespace

import pytest

from omicsclaw.interactive._llm_bridge_support import (
    append_interruption_notice,
    build_usage_delta,
    seed_core_conversation,
    sync_core_conversation,
)


def _build_core() -> SimpleNamespace:
    return SimpleNamespace(conversations={}, _conversation_access={})


def test_seed_core_conversation_sanitizes_history_and_extracts_text_blocks():
    core = _build_core()
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "please"},
                {"type": "text", "text": "retry"},
            ],
        },
    ]

    user_text = seed_core_conversation(core, "chat-1", messages, touched_at=123.0)

    assert user_text == "please retry"
    assert core.conversations["chat-1"] == [{"role": "user", "content": "hello"}]
    assert core._conversation_access["chat-1"] == 123.0


def test_sync_core_conversation_sanitizes_and_mutates_message_list():
    core = _build_core()
    core.conversations["chat-2"] = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {"role": "assistant", "content": "final answer"},
    ]
    messages = [{"role": "user", "content": "stale"}]

    updated = sync_core_conversation(core, "chat-2", messages)

    assert updated == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final answer"},
    ]
    assert messages == updated
    assert core.conversations["chat-2"] == updated


def test_append_interruption_notice_syncs_first_and_updates_messages():
    core = _build_core()
    core.conversations["chat-3"] = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
    ]
    messages = []

    updated = append_interruption_notice(
        core,
        "chat-3",
        text="Conversation interrupted",
        messages=messages,
    )

    assert updated == [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "Conversation interrupted"},
    ]
    assert messages == updated
    assert core.conversations["chat-3"] == updated


def test_build_usage_delta_prefers_snapshot_cost_delta():
    delta = build_usage_delta(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "api_calls": 1,
            "estimated_cost_usd": 0.01,
        },
        {
            "prompt_tokens": 160,
            "completion_tokens": 90,
            "total_tokens": 250,
            "api_calls": 3,
            "estimated_cost_usd": 0.015,
            "model": "gpt-test",
            "provider": "test-provider",
            "input_price_per_1m": 1.0,
            "output_price_per_1m": 2.0,
        },
    )

    assert delta.prompt_tokens == 60
    assert delta.completion_tokens == 40
    assert delta.total_tokens == 100
    assert delta.api_calls == 2
    assert delta.estimated_cost_usd == pytest.approx(0.005)
    assert delta.model == "gpt-test"
    assert delta.provider == "test-provider"
    assert delta.has_usage is True


def test_build_usage_delta_falls_back_to_token_pricing_when_cost_missing():
    delta = build_usage_delta(
        {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "api_calls": 2,
            "estimated_cost_usd": 0.0,
        },
        {
            "prompt_tokens": 1010,
            "completion_tokens": 520,
            "total_tokens": 1530,
            "api_calls": 2,
            "estimated_cost_usd": 0.0,
            "input_price_per_1m": 2.0,
            "output_price_per_1m": 4.0,
        },
    )

    assert delta.prompt_tokens == 1000
    assert delta.completion_tokens == 500
    assert delta.total_tokens == 1500
    assert delta.api_calls == 0
    assert delta.estimated_cost_usd == pytest.approx(0.004)
    assert delta.has_usage is True


def test_build_usage_delta_clamps_negative_values_to_zero():
    delta = build_usage_delta(
        {
            "prompt_tokens": 100,
            "completion_tokens": 100,
            "total_tokens": 200,
            "api_calls": 5,
            "estimated_cost_usd": 1.0,
        },
        {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "api_calls": 1,
            "estimated_cost_usd": 0.5,
        },
    )

    assert delta.prompt_tokens == 0
    assert delta.completion_tokens == 0
    assert delta.total_tokens == 0
    assert delta.api_calls == 0
    assert delta.estimated_cost_usd == 0.0
    assert delta.has_usage is False

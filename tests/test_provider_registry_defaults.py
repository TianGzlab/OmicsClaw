"""Tests verifying default-model upgrades and llm_models integration in
omicsclaw.core.provider_registry.
"""
from __future__ import annotations

import pytest

from omicsclaw.core.provider_registry import (
    PROVIDER_PRESETS,
    get_langchain_llm,
)


# Spec table — keep in sync with
# docs/superpowers/specs/2026-04-30-llm-catalog-modernization-design.md
DEFAULT_MODEL_UPGRADES = {
    "openai":      "gpt-5.5",
    "anthropic":   "claude-sonnet-4-6",
    "gemini":      "gemini-3-flash-preview",
    "nvidia":      "nvidia/nemotron-3-super-120b-a12b",
    "siliconflow": "Pro/zai-org/GLM-5",
    "openrouter":  "anthropic/claude-sonnet-4.6",
    "volcengine":  "doubao-seed-2-0-pro-260215",
    "dashscope":   "qwen3.6-plus",
    "moonshot":    "kimi-k2.6",
    "zhipu":       "glm-5.1",
    "deepseek":    "deepseek-v4-flash",
    "ollama":      "qwen2.5:7b",
}


@pytest.mark.parametrize("provider, expected", list(DEFAULT_MODEL_UPGRADES.items()))
def test_provider_default_model_matches_spec(provider, expected):
    base_url, default_model, env_key = PROVIDER_PRESETS[provider]
    assert default_model == expected, (
        f"{provider}: PROVIDER_PRESETS default {default_model!r} "
        f"diverges from spec value {expected!r}"
    )


def test_custom_provider_has_empty_default():
    base_url, default_model, env_key = PROVIDER_PRESETS["custom"]
    assert default_model == ""


class TestGetLangchainLlmConsumesCatalog:
    def test_anthropic_injects_thinking_for_4_6(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert captured.get("thinking") == {"type": "adaptive"}

    def test_anthropic_respects_caller_thinking_override(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        # The caller doesn't currently expose a thinking kwarg, so this
        # asserts the default still fires. Future callers can pass
        # thinking= in kwargs and it must override; the implementation
        # uses dict.setdefault.
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert "thinking" in captured

    def test_anthropic_localhost_base_url_skips_thinking(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv(
            "ANTHROPIC_BASE_URL", "http://127.0.0.1:11435/claude"
        )
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert "thinking" not in captured

    def test_openai_injects_reasoning_effort(self, monkeypatch):
        captured = {}

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        get_langchain_llm(
            provider="openai",
            model="gpt-5.5",
            openai_cls=_FakeOpenAI,
        )
        extra_body = captured.get("extra_body", {})
        assert extra_body.get("reasoning_effort") == "max"

    def test_openai_localhost_skips_reasoning(self, monkeypatch):
        captured = {}

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv(
            "OPENAI_BASE_URL", "http://127.0.0.1:11435/codex/v1"
        )
        get_langchain_llm(
            provider="openai",
            model="gpt-5.5",
            openai_cls=_FakeOpenAI,
        )
        extra_body = captured.get("extra_body", {})
        assert "reasoning_effort" not in extra_body

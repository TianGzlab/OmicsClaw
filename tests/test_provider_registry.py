from __future__ import annotations

from omicsclaw.core.provider_registry import (
    PROVIDER_CHOICES,
    PROVIDER_DETECT_ORDER,
    PROVIDER_PRESETS,
    detect_provider_from_env,
    resolve_provider,
)


def test_provider_choices_match_registry_keys():
    assert PROVIDER_CHOICES == tuple(PROVIDER_PRESETS.keys())
    assert "nvidia" in PROVIDER_CHOICES
    assert PROVIDER_CHOICES[-2:] == ("ollama", "custom")


def test_detect_provider_from_env_prefers_explicit_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    assert detect_provider_from_env() == "custom"


def test_detect_provider_from_env_uses_detection_order(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    assert detect_provider_from_env() == PROVIDER_DETECT_ORDER[0]


def test_resolve_provider_uses_provider_specific_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://internal.deepseek.example/v1")

    resolved_url, resolved_model, resolved_key = resolve_provider(provider="deepseek")

    assert resolved_url == "https://internal.deepseek.example/v1"
    assert resolved_model == "deepseek-chat"
    assert resolved_key == "deepseek-key"


def test_resolve_provider_auto_detects_specific_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    resolved_url, resolved_model, resolved_key = resolve_provider()

    assert resolved_url is None
    assert resolved_model == "gpt-4o"
    assert resolved_key == "openai-key"


def test_resolve_provider_custom_preserves_explicit_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "generic-key")

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider="custom",
        base_url="https://custom.example.com/v1",
        model="custom-model",
    )

    assert resolved_url == "https://custom.example.com/v1"
    assert resolved_model == "custom-model"
    assert resolved_key == "generic-key"

from __future__ import annotations

from omicsclaw.core.provider_registry import (
    MODEL_NORMALIZATION_EXEMPT_PROVIDERS,
    PROVIDER_CHOICES,
    PROVIDER_DETECT_ORDER,
    PROVIDER_PRESETS,
    build_provider_registry_entries,
    detect_provider_from_env,
    get_langchain_llm,
    normalize_model_for_provider,
    resolve_provider,
)


def test_provider_choices_match_registry_keys():
    assert PROVIDER_CHOICES == tuple(PROVIDER_PRESETS.keys())
    assert "nvidia" in PROVIDER_CHOICES
    assert PROVIDER_CHOICES[-2:] == ("ollama", "custom")


def test_build_provider_registry_entries_exposes_display_metadata():
    entries = build_provider_registry_entries()

    assert [entry["name"] for entry in entries] == list(PROVIDER_PRESETS.keys())

    deepseek = next(entry for entry in entries if entry["name"] == "deepseek")
    assert deepseek["display_name"] == "DeepSeek"
    assert deepseek["tier"] == "primary"
    assert deepseek["models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]

    custom = next(entry for entry in entries if entry["name"] == "custom")
    assert custom["display_name"] == "Custom Endpoint"
    assert custom["models"] == []


def test_detect_provider_from_env_prefers_explicit_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    assert detect_provider_from_env() == "custom"


def test_detect_provider_from_env_uses_detection_order(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    assert detect_provider_from_env() == PROVIDER_DETECT_ORDER[0]


def test_dashscope_preset_exposes_latest_qwen_models():
    entries = build_provider_registry_entries()
    dashscope = next(entry for entry in entries if entry["name"] == "dashscope")

    assert dashscope["default_model"] == "qwen3.6-plus"
    assert dashscope["models"][0] == "qwen3.6-plus"
    assert "qwen3.6-plus" in dashscope["models"]
    assert "qwen3-coder-plus" in dashscope["models"]
    assert "qwen3-235b-a22b" in dashscope["models"]


def test_resolve_provider_uses_provider_specific_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://internal.deepseek.example/v1")

    resolved_url, resolved_model, resolved_key = resolve_provider(provider="deepseek")

    assert resolved_url == "https://internal.deepseek.example/v1"
    assert resolved_model == "deepseek-v4-flash"
    assert resolved_key == "deepseek-key"


def test_resolve_provider_auto_detects_specific_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    resolved_url, resolved_model, resolved_key = resolve_provider()

    assert resolved_url is None
    assert resolved_model == "gpt-5.5"
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


def test_normalize_model_for_provider_rewrites_foreign_default_model():
    normalized, foreign_provider = normalize_model_for_provider(
        provider="anthropic",
        model="deepseek-v4-flash",
    )

    assert normalized == PROVIDER_PRESETS["anthropic"][1]
    assert foreign_provider == "deepseek"


def test_normalize_model_for_provider_skips_gateway_and_local_providers():
    for provider in MODEL_NORMALIZATION_EXEMPT_PROVIDERS:
        normalized, foreign_provider = normalize_model_for_provider(
            provider=provider,
            model="deepseek-chat",
        )
        assert normalized == "deepseek-chat"
        assert foreign_provider == ""


def test_normalize_model_for_provider_skips_explicit_custom_base_url():
    normalized, foreign_provider = normalize_model_for_provider(
        provider="anthropic",
        model="deepseek-chat",
        base_url="https://proxy.example.test/v1",
    )

    assert normalized == "deepseek-chat"
    assert foreign_provider == ""


def test_resolve_provider_normalizes_stale_foreign_default_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider="anthropic",
        model="deepseek-v4-flash",
    )

    assert resolved_url == PROVIDER_PRESETS["anthropic"][0]
    assert resolved_model == PROVIDER_PRESETS["anthropic"][1]
    assert resolved_key == "sk-ant-test"


def test_resolve_provider_keeps_gateway_model_names(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider="openrouter",
        model="deepseek-chat",
    )

    assert resolved_url == PROVIDER_PRESETS["openrouter"][0]
    assert resolved_model == "deepseek-chat"
    assert resolved_key == "sk-or-test"


def test_get_langchain_llm_uses_openai_compatible_kwargs(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")

    llm = get_langchain_llm(
        provider="openrouter",
        timeout="timeout-token",
        openai_cls=_FakeOpenAI,
    )

    assert isinstance(llm, _FakeOpenAI)
    assert captured["openai_api_key"] == "openrouter-key"
    assert captured["openai_api_base"] == PROVIDER_PRESETS["openrouter"][0]
    assert captured["model"] == PROVIDER_PRESETS["openrouter"][1]
    assert captured["timeout"] == "timeout-token"
    assert captured["temperature"] == 0.3


def test_get_langchain_llm_uses_anthropic_kwargs(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic.example.test/v1")

    llm = get_langchain_llm(
        provider="anthropic",
        anthropic_timeout=42.0,
        anthropic_cls=_FakeAnthropic,
    )

    assert isinstance(llm, _FakeAnthropic)
    assert captured["anthropic_api_key"] == "anthropic-key"
    assert captured["anthropic_api_url"] == "https://anthropic.example.test/v1"
    assert captured["model"] == PROVIDER_PRESETS["anthropic"][1]
    assert captured["timeout"] == 42.0
    assert captured["temperature"] == 0.3

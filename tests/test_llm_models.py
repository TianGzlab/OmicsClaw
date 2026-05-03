"""Tests for omicsclaw.core.llm_models — the LLM model catalog."""
from __future__ import annotations

import pytest

from omicsclaw.core.llm_models import (
    MODEL_CATALOG,
    ModelInfo,
    all_short_names,
    get_context_window,
    get_default_features,
    list_models_for_provider,
    resolve_model,
)


class TestResolveModel:
    def test_known_short_name(self):
        info = resolve_model("anthropic", "claude-opus-4-7")
        assert info.short_name == "claude-opus-4-7"
        assert info.model_id == "claude-opus-4-7"
        assert info.provider == "anthropic"
        assert info.context_window == 1_000_000
        assert info.default_features.get("thinking") == {"type": "adaptive"}

    def test_unknown_falls_back_to_empty_info(self):
        info = resolve_model("anthropic", "claude-fictional-9-9")
        # Unknown short_name → empty info but model_id preserved
        assert info.model_id == "claude-fictional-9-9"
        assert info.provider == "anthropic"
        # Unknown models should not inherit guessed family-level windows.
        assert info.context_window is None

    def test_unknown_provider_returns_empty(self):
        info = resolve_model("nonexistent", "some-model")
        assert info.model_id == "some-model"
        assert info.provider == "nonexistent"
        assert info.context_window is None
        assert info.default_features == {}

    def test_provider_disambiguation(self):
        # kimi-k2.5 exists in moonshot, siliconflow, nvidia — provider
        # selects the right entry
        moonshot = resolve_model("moonshot", "kimi-k2.5")
        siliconflow = resolve_model("siliconflow", "kimi-k2.5")
        assert moonshot.model_id == "kimi-k2.5"
        assert siliconflow.model_id == "Pro/moonshotai/Kimi-K2.5"


class TestContextWindow:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("deepseek-v4-flash", 1_000_000),
            ("deepseek-v4-pro", 1_000_000),
            ("gpt-5.5-pro", 1_050_000),
            ("gpt-5.5", 1_050_000),
            ("gpt-5.4", 1_050_000),
            ("gpt-5.4-mini", 400_000),
            ("gpt-5.3-codex", 400_000),
            ("gpt-5", 400_000),
            ("gpt-5-mini", 400_000),
            ("claude-opus-4-7", 1_000_000),
            ("claude-opus-4-6", 1_000_000),
            ("claude-sonnet-4-6", 1_000_000),
            ("claude-sonnet-4-5", 200_000),
            ("claude-haiku-4-5", 200_000),
            ("gemini-3.1-pro-preview", 1_048_576),
            ("gemini-3-flash-preview", 1_048_576),
            ("gemini-2.5-pro", 1_048_576),
            ("gemini-2.5-flash", 1_048_576),
            ("nvidia/nemotron-3-super-120b-a12b", 1_000_000),
            ("deepseek-ai/deepseek-v3.2", 131_072),
            ("moonshotai/kimi-k2.5", 262_144),
            ("qwen/qwen3.5-397b-a17b", 262_144),
            ("Pro/zai-org/GLM-5", 202_752),
            ("Pro/MiniMaxAI/MiniMax-M2.5", 196_608),
            ("Pro/moonshotai/Kimi-K2.5", 262_144),
            ("Pro/zai-org/GLM-4.7", 202_752),
            ("anthropic/claude-sonnet-4.6", 1_000_000),
            ("anthropic/claude-opus-4.7", 1_000_000),
            ("openai/gpt-5.5", 1_050_000),
            ("openai/gpt-5.4", 1_050_000),
            ("google/gemini-3.1-pro-preview", 1_048_576),
            ("moonshotai/kimi-k2.6", 262_142),
            ("minimax/minimax-m2.7", 196_608),
            ("deepseek/deepseek-v4-pro", 1_048_576),
            ("doubao-seed-2-0-pro-260215", 1_000_000),
            ("doubao-seed-2-0-lite-260215", 1_000_000),
            ("doubao-1.5-pro-256k", 256_000),
            ("doubao-1.5-thinking-pro", 256_000),
            ("qwen3.6-plus", 1_000_000),
            ("qwen3-max", 262_144),
            ("qwen3-coder-plus", 1_000_000),
            ("qwen3-235b-a22b", 131_072),
            ("qwq-plus", 131_072),
            ("kimi-k2.6", 262_144),
            ("kimi-k2.5", 262_144),
            ("kimi-k2-thinking", 262_144),
            ("glm-5.1", 202_752),
            ("glm-5", 202_752),
            ("glm-5-turbo", 202_752),
            ("glm-4.7", 202_752),
        ],
    )
    def test_supported_provider_models_have_verified_context_windows(
        self,
        model,
        expected,
    ):
        assert get_context_window(model) == expected

    def test_exact_match_overrides_family(self):
        # claude-haiku-4-5 is 200K not 1M (exception to claude- family)
        assert get_context_window("claude-haiku-4-5") == 200_000

    def test_qwen36_27b_exact_override(self):
        assert get_context_window("qwen3.6-27b") == 262_000

    def test_family_match_claude(self):
        assert get_context_window("claude-opus-4-7-20260101") is None

    def test_family_match_gpt55(self):
        assert get_context_window("gpt-5.5-pro") == 1_050_000

    def test_family_match_kimi_k2(self):
        assert get_context_window("kimi-k2-thinking-turbo") is None

    def test_family_match_deepseek_v4(self):
        assert get_context_window("deepseek-v4-pro") == 1_000_000

    def test_family_match_qwen36_closed(self):
        assert get_context_window("qwen3.6-plus") == 1_000_000

    def test_unknown_returns_none(self):
        assert get_context_window("gpt-3.5-turbo") is None

    def test_empty_returns_none(self):
        assert get_context_window("") is None
        assert get_context_window(None) is None  # type: ignore[arg-type]


class TestDefaultFeatures:
    def test_anthropic_4_6_uses_adaptive_thinking(self):
        feats = get_default_features("anthropic", "claude-sonnet-4-6")
        assert feats.get("thinking") == {"type": "adaptive"}

    def test_anthropic_4_7_uses_adaptive_thinking(self):
        feats = get_default_features("anthropic", "claude-opus-4-7")
        assert feats.get("thinking") == {"type": "adaptive"}

    def test_anthropic_legacy_uses_enabled_thinking(self):
        feats = get_default_features("anthropic", "claude-sonnet-4-5")
        assert feats.get("thinking") == {
            "type": "enabled",
            "budget_tokens": 10000,
        }

    def test_anthropic_localhost_skips_thinking(self):
        feats = get_default_features(
            "anthropic", "claude-opus-4-7",
            base_url="http://127.0.0.1:11435/claude",
        )
        assert "thinking" not in feats

    def test_openai_5_5_uses_max_effort(self):
        feats = get_default_features("openai", "gpt-5.5")
        assert feats["extra_body"]["reasoning_effort"] == "max"

    def test_openai_codex_uses_max_effort(self):
        feats = get_default_features("openai", "gpt-5.3-codex")
        assert feats["extra_body"]["reasoning_effort"] == "max"

    def test_openai_legacy_uses_high_effort(self):
        feats = get_default_features("openai", "gpt-5")
        assert feats["extra_body"]["reasoning_effort"] == "high"

    def test_openai_localhost_skips_reasoning(self):
        feats = get_default_features(
            "openai", "gpt-5.5", base_url="http://localhost:8000/codex/v1"
        )
        assert feats == {}

    def test_gemini_includes_thoughts(self):
        feats = get_default_features("gemini", "gemini-3-flash-preview")
        assert feats["extra_body"]["include_thoughts"] is True

    def test_ollama_reasoning_true(self):
        feats = get_default_features("ollama", "qwen2.5:7b")
        assert feats["extra_body"]["reasoning"] is True

    def test_siliconflow_disables_thinking(self):
        feats = get_default_features("siliconflow", "Pro/zai-org/GLM-5")
        assert feats["extra_body"]["enable_thinking"] is False

    def test_default_features_no_overwrite(self):
        # Invariant I2: returned dict is fresh per call. Mutating one call's
        # result must NOT affect a subsequent call (so callers can use
        # dict.setdefault safely).
        d1 = get_default_features("anthropic", "claude-opus-4-7")
        d1["sentinel"] = True
        d2 = get_default_features("anthropic", "claude-opus-4-7")
        assert "sentinel" not in d2
        # Nested dicts are also fresh
        d2["thinking"]["__poison__"] = True
        d3 = get_default_features("anthropic", "claude-opus-4-7")
        assert "__poison__" not in d3["thinking"]

    def test_unknown_provider_empty(self):
        assert get_default_features("custom", "any-model") == {}

    def test_unknown_model_provider_known_anthropic(self):
        # Even for an unknown anthropic model, base policy applies (legacy budget)
        feats = get_default_features("anthropic", "claude-experimental-x")
        assert "thinking" in feats


class TestListing:
    def test_list_models_for_provider_anthropic(self):
        infos = list_models_for_provider("anthropic")
        short_names = [i.short_name for i in infos]
        assert "claude-opus-4-7" in short_names
        assert "claude-sonnet-4-6" in short_names

    def test_list_models_for_unknown_provider(self):
        assert list_models_for_provider("nonexistent") == []

    def test_all_short_names_dedups(self):
        names = all_short_names()
        # kimi-k2.5 appears in moonshot, siliconflow, nvidia — appears once
        assert names.count("kimi-k2.5") == 1

    def test_catalog_has_minimum_provider_coverage(self):
        providers = {p for _, _, p in MODEL_CATALOG}
        # All of OmicsClaw's PROVIDER_PRESETS keys with at least one model
        expected = {
            "anthropic", "openai", "gemini", "nvidia", "siliconflow",
            "openrouter", "volcengine", "dashscope", "moonshot", "zhipu",
            "deepseek",
        }
        assert expected.issubset(providers)

    def test_catalog_models_all_have_verified_context_windows(self):
        missing = [
            (provider, model)
            for _short_name, model, provider in MODEL_CATALOG
            if get_context_window(model) is None
        ]

        assert missing == []

    def test_removed_unverified_moonshot_v1_alias_is_not_catalogued(self):
        assert all(model != "moonshot-v1-auto" for _short, model, _provider in MODEL_CATALOG)
        assert get_context_window("moonshot-v1-auto") is None


class TestNeverRaises:
    def test_resolve_model_with_non_string_provider(self):
        # Invariant I4: never raises into callers
        info = resolve_model(42, "model")  # type: ignore[arg-type]
        assert info.model_id == "model"

    def test_resolve_model_with_non_string_model(self):
        info = resolve_model("anthropic", 42)  # type: ignore[arg-type]
        assert info.provider == "anthropic"

    def test_resolve_model_with_none_provider(self):
        info = resolve_model(None, "claude-opus-4-7")  # type: ignore[arg-type]
        assert info.model_id == "claude-opus-4-7"

    def test_list_models_with_non_string_provider(self):
        assert list_models_for_provider(42) == []  # type: ignore[arg-type]

    def test_get_default_features_with_non_string(self):
        assert get_default_features(42, 99) == {}  # type: ignore[arg-type]

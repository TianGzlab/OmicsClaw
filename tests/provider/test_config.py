"""Tests for ``omicsclaw.provider.config`` (plan 0026 §4).

This is ported configuration knowledge, not new design: the endpoints,
the key variables and the detection order come from
``omicsclaw/providers/registry.py``, where they were arrived at one
support incident at a time. The tests below pin the values themselves,
because a typo in a base URL is invisible until someone's key stops
working against the wrong host.

Every test passes an explicit ``env`` mapping. Reading the ambient
environment would make the suite pass or fail depending on whose machine
it runs on.
"""

from __future__ import annotations

import pytest

from omicsclaw.provider import (
    DETECT_ORDER,
    PRESETS,
    ProviderConfig,
    ProviderError,
    ProviderTier,
    detect_provider_from_env,
    preset_for,
    resolve_config,
)
from omicsclaw.provider.config import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    FALLBACK_MODEL,
    normalize_model_for_provider,
)

_THIRTEEN_PRESETS = {
    "deepseek",
    "openai",
    "anthropic",
    "gemini",
    "nvidia",
    "siliconflow",
    "openrouter",
    "volcengine",
    "dashscope",
    "moonshot",
    "zhipu",
    "ollama",
    "custom",
}


# --- The preset table -----------------------------------------------------


def test_all_thirteen_presets_survived_the_port():
    assert set(PRESETS) == _THIRTEEN_PRESETS


@pytest.mark.parametrize(
    ("name", "base_url"),
    [
        ("deepseek", "https://api.deepseek.com"),
        ("openai", ""),
        ("anthropic", "https://api.anthropic.com/v1/"),
        ("nvidia", "https://integrate.api.nvidia.com/v1"),
        ("siliconflow", "https://api.siliconflow.cn/v1"),
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("volcengine", "https://ark.cn-beijing.volces.com/api/v3"),
        ("dashscope", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("moonshot", "https://api.moonshot.cn/v1"),
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4"),
        ("ollama", "http://localhost:11434/v1"),
    ],
)
def test_preset_base_urls_are_unchanged(name, base_url):
    assert PRESETS[name].base_url == base_url


def test_openai_has_no_base_url_so_the_sdk_default_is_used():
    """A hard-coded URL here would break the day OpenAI moves the host."""
    assert PRESETS["openai"].base_url == ""


@pytest.mark.parametrize(
    ("name", "env_var"),
    [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
        ("nvidia", "NVIDIA_API_KEY"),
        ("siliconflow", "SILICONFLOW_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("volcengine", "VOLCENGINE_API_KEY"),
        ("dashscope", "DASHSCOPE_API_KEY"),
        ("moonshot", "MOONSHOT_API_KEY"),
        ("zhipu", "ZHIPU_API_KEY"),
    ],
)
def test_preset_api_key_variables_are_unchanged(name, env_var):
    assert PRESETS[name].api_key_env == env_var


def test_local_presets_need_no_api_key():
    assert PRESETS["ollama"].api_key_env == ""
    assert PRESETS["custom"].api_key_env == ""


def test_tiers_classify_every_preset():
    assert PRESETS["deepseek"].tier is ProviderTier.PRIMARY
    assert PRESETS["openrouter"].tier is ProviderTier.AGGREGATOR
    assert PRESETS["ollama"].tier is ProviderTier.LOCAL


def test_every_default_model_appears_in_its_curated_list():
    """A default absent from the picker is a default nobody can get back to."""
    for name, preset in PRESETS.items():
        if not preset.default_model:
            continue
        assert preset.default_model in preset.models, name


def test_the_preset_table_is_read_only():
    """Shared global state: a caller mutating it would reconfigure the
    whole process."""
    with pytest.raises(TypeError):
        PRESETS["deepseek"] = PRESETS["openai"]  # type: ignore[index]


def test_preset_lookup_tolerates_case_and_whitespace():
    assert preset_for("  DeepSeek ") is PRESETS["deepseek"]
    assert preset_for("nope") is None


# --- Detection order ------------------------------------------------------


def test_detect_order_is_the_documented_sequence():
    assert DETECT_ORDER == (
        "deepseek",
        "openai",
        "anthropic",
        "gemini",
        "nvidia",
        "siliconflow",
        "openrouter",
        "volcengine",
        "dashscope",
        "moonshot",
        "zhipu",
    )


def test_keyless_providers_are_not_auto_detectable():
    assert "ollama" not in DETECT_ORDER
    assert "custom" not in DETECT_ORDER


def test_an_explicit_provider_variable_beats_every_key():
    env = {"LLM_PROVIDER": "zhipu", "DEEPSEEK_API_KEY": "sk-1"}
    assert detect_provider_from_env(env=env) == "zhipu"


def test_the_first_key_in_order_wins_when_several_are_present():
    """Two keys must resolve the same way on every machine."""
    env = {"ANTHROPIC_API_KEY": "sk-a", "DEEPSEEK_API_KEY": "sk-d"}
    assert detect_provider_from_env(env=env) == "deepseek"


def test_no_key_detects_nothing():
    assert detect_provider_from_env(env={}) == ""


# --- Resolution -----------------------------------------------------------


def test_explicit_arguments_beat_everything():
    config = resolve_config(
        "openai",
        "gpt-5.4",
        base_url="https://proxy.internal/v1",
        api_key="sk-explicit",
        env={"OPENAI_API_KEY": "sk-env", "LLM_MODEL": "gpt-5"},
    )

    assert (config.provider, config.model) == ("openai", "gpt-5.4")
    assert config.base_url == "https://proxy.internal/v1"
    assert config.api_key == "sk-explicit"


def test_a_named_provider_falls_back_to_its_preset():
    config = resolve_config("anthropic", env={"ANTHROPIC_API_KEY": "sk-a"})

    assert config.model == "claude-sonnet-4-6"
    assert config.base_url == "https://api.anthropic.com/v1/"
    assert config.api_key == "sk-a"


def test_a_bare_key_in_the_environment_selects_the_provider():
    config = resolve_config(env={"MOONSHOT_API_KEY": "sk-m"})

    assert config.provider == "moonshot"
    assert config.model == "kimi-k2.6"
    assert config.api_key == "sk-m"


def test_an_unknown_provider_still_produces_a_usable_config():
    """A typo must degrade to something diagnosable, not raise at import."""
    config = resolve_config("typo", env={})

    assert config.provider == "typo"
    assert config.model == FALLBACK_MODEL
    assert config.base_url == ""


def test_a_provider_scoped_base_url_overrides_the_preset():
    config = resolve_config(
        "deepseek", env={"DEEPSEEK_BASE_URL": "http://localhost:8080/v1"}
    )
    assert config.base_url == "http://localhost:8080/v1"


def test_generic_env_does_not_hijack_a_different_explicit_provider():
    """``LLM_BASE_URL`` left over from one vendor must not silently
    redirect an explicit request for another."""
    env = {
        "LLM_PROVIDER": "openai",
        "LLM_BASE_URL": "https://openai.example/v1",
        "LLM_MODEL": "gpt-5",
        "LLM_API_KEY": "sk-openai",
        "ZHIPU_API_KEY": "sk-z",
    }
    config = resolve_config("zhipu", env=env)

    assert config.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert config.model == "glm-5.1"
    assert config.api_key == "sk-z"


def test_generic_env_applies_when_it_names_the_same_provider():
    env = {
        "LLM_PROVIDER": "zhipu",
        "LLM_BASE_URL": "https://gateway.example/v1",
        "LLM_MODEL": "glm-5-turbo",
        "LLM_API_KEY": "sk-generic",
    }
    config = resolve_config("zhipu", env=env)

    assert config.base_url == "https://gateway.example/v1"
    assert config.model == "glm-5-turbo"
    assert config.api_key == "sk-generic"


def test_openai_key_is_the_last_resort_for_an_unnamed_provider():
    config = resolve_config(env={"OPENAI_API_KEY": "sk-o"})
    assert config.api_key == "sk-o"


# --- Stale model repair ---------------------------------------------------


def test_another_providers_default_model_is_replaced():
    """Switching ``LLM_PROVIDER`` without updating the model is the most
    common misconfiguration, and it fails as a 404 that reads like an
    outage."""
    assert normalize_model_for_provider("zhipu", "kimi-k2.6") == "glm-5.1"


def test_a_retired_model_is_replaced_by_the_current_default():
    assert normalize_model_for_provider("deepseek", "deepseek-chat") == (
        "deepseek-v4-flash"
    )


def test_an_unrecognised_model_is_left_alone():
    assert normalize_model_for_provider("zhipu", "glm-5-preview") == "glm-5-preview"


def test_open_identifier_providers_are_never_rewritten():
    for provider in ("custom", "ollama", "openrouter", "siliconflow", "nvidia"):
        assert normalize_model_for_provider(provider, "kimi-k2.6") == "kimi-k2.6"


def test_a_custom_base_url_disables_the_repair():
    """An operator pointing at their own gateway knows the model names."""
    model = normalize_model_for_provider(
        "zhipu", "kimi-k2.6", base_url="https://gateway.internal/v1"
    )
    assert model == "kimi-k2.6"


# --- Timeouts and retries -------------------------------------------------


def test_timeout_defaults_come_from_this_repo_not_the_reference_harness():
    """600s is tuned for unattended batches; an interactive Surface would
    sit on a hung connection for ten minutes."""
    config = resolve_config("deepseek", env={})

    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 120.0
    assert config.connect_timeout_seconds == DEFAULT_CONNECT_TIMEOUT_SECONDS == 10.0


def test_the_repo_timeout_variable_is_honoured():
    config = resolve_config("deepseek", env={"OMICSCLAW_LLM_TIMEOUT_SECONDS": "45.5"})
    assert config.timeout_seconds == 45.5


def test_the_reference_harness_variable_is_accepted_as_an_alias():
    """A harness-shaped ``.env`` should still configure something."""
    config = resolve_config("deepseek", env={"LLM_REQUEST_TIMEOUT_SECS": "600"})
    assert config.timeout_seconds == 600.0


def test_the_repo_variable_wins_over_the_alias():
    config = resolve_config(
        "deepseek",
        env={
            "OMICSCLAW_LLM_TIMEOUT_SECONDS": "90",
            "LLM_REQUEST_TIMEOUT_SECS": "600",
        },
    )
    assert config.timeout_seconds == 90.0


@pytest.mark.parametrize("raw", ["", "  ", "abc", "0", "-5"])
def test_an_unusable_timeout_falls_back_to_the_default(raw):
    """Zero is not a faster timeout, it is a client that always fails."""
    config = resolve_config("deepseek", env={"OMICSCLAW_LLM_TIMEOUT_SECONDS": raw})
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS


def test_retries_default_to_five():
    assert resolve_config("deepseek", env={}).max_retries == DEFAULT_MAX_RETRIES == 5


def test_retries_can_be_disabled_with_zero():
    config = resolve_config("deepseek", env={"LLM_MAX_RETRIES": "0"})
    assert config.max_retries == 0


def test_an_unusable_retry_count_falls_back_to_the_default():
    config = resolve_config("deepseek", env={"LLM_MAX_RETRIES": "many"})
    assert config.max_retries == DEFAULT_MAX_RETRIES


def test_overrides_are_applied_after_resolution():
    config = resolve_config("deepseek", env={}, max_tokens=4096, temperature=0.0)
    assert (config.max_tokens, config.temperature) == (4096, 0.0)


# --- ProviderConfig itself ------------------------------------------------


def test_the_config_is_frozen():
    config = ProviderConfig(provider="deepseek", model="deepseek-v4-flash")
    with pytest.raises(Exception):
        config.model = "other"  # type: ignore[misc]


def test_with_overrides_leaves_the_original_untouched():
    original = ProviderConfig(provider="deepseek", model="deepseek-v4-flash")
    changed = original.with_overrides(model="deepseek-v4-pro", max_tokens=1024)

    assert changed.model == "deepseek-v4-pro"
    assert changed.max_tokens == 1024
    assert original.model == "deepseek-v4-flash"
    assert original.max_tokens == 0


def test_with_overrides_rejects_an_unknown_field():
    """A typo'd ``max_token=`` that quietly did nothing would surface much
    later as an unexplained truncation."""
    config = ProviderConfig(provider="deepseek", model="deepseek-v4-flash")
    with pytest.raises(ProviderError) as caught:
        config.with_overrides(max_token=10)

    assert "max_token" in str(caught.value)


def test_extra_defaults_are_not_shared_between_configs():
    first = ProviderConfig(provider="a", model="m")
    second = ProviderConfig(provider="b", model="m")
    assert first.extra == second.extra == {}


def test_extra_carries_vendor_knobs_without_a_schema_change():
    config = ProviderConfig(
        provider="openai", model="gpt-5.5", extra={"reasoning_effort": "max"}
    )
    assert config.extra["reasoning_effort"] == "max"


def test_max_output_tokens_prefers_an_explicit_ceiling():
    config = ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
    assert config.with_overrides(max_tokens=2048).max_output_tokens == 2048


def test_max_output_tokens_falls_back_to_the_model_registry():
    """Anthropic's API requires the parameter, so a number must always
    be derivable."""
    config = ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
    assert config.max_output_tokens == 64_000


def test_the_config_exposes_the_context_window_of_its_model():
    config = ProviderConfig(provider="openai", model="gpt-4o")
    assert config.limits.context_tokens == 128_000

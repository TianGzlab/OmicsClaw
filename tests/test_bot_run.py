from __future__ import annotations

from bot import run
from omicsclaw.core.provider_registry import PROVIDER_PRESETS


def test_resolve_bootstrap_llm_config_uses_provider_specific_key():
    provider, base_url, model, api_key, _auth_mode, _port = run._resolve_bootstrap_llm_config(
        {
            "DEEPSEEK_API_KEY": "deepseek-key",
        }
    )

    assert provider == "deepseek"
    assert base_url == PROVIDER_PRESETS["deepseek"][0]
    assert model == PROVIDER_PRESETS["deepseek"][1]
    assert api_key == "deepseek-key"


def test_resolve_bootstrap_llm_config_respects_explicit_custom_endpoint():
    provider, base_url, model, api_key, _auth_mode, _port = run._resolve_bootstrap_llm_config(
        {
            "LLM_PROVIDER": "custom",
            "LLM_BASE_URL": "https://llm.internal.example/v1",
            "OMICSCLAW_MODEL": "omics-model",
            "LLM_API_KEY": "generic-key",
        }
    )

    assert provider == "custom"
    assert base_url == "https://llm.internal.example/v1"
    assert model == "omics-model"
    assert api_key == "generic-key"


def test_resolve_bootstrap_llm_config_reads_oauth_env():
    provider, _base_url, _model, _api_key, auth_mode, ccproxy_port = (
        run._resolve_bootstrap_llm_config(
            {
                "LLM_PROVIDER": "anthropic",
                "LLM_AUTH_MODE": "oauth",
                "CCPROXY_PORT": "9100",
            }
        )
    )
    assert provider == "anthropic"
    assert auth_mode == "oauth"
    assert ccproxy_port == 9100


def test_resolve_bootstrap_llm_config_defaults_to_api_key():
    _p, _b, _m, _k, auth_mode, ccproxy_port = run._resolve_bootstrap_llm_config(
        {"DEEPSEEK_API_KEY": "x"}
    )
    assert auth_mode == "api_key"
    # Default must differ from the app-server's 8765 (Bug 1 regression).
    assert ccproxy_port == 11435

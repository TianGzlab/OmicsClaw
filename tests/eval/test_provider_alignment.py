"""Unit tests for ``tests/eval/runtime_config.resolve_eval_config``.

Covers the parity contract: eval inherits the production provider's
endpoint and model unless ``EVAL_MODEL`` explicitly overrides. Pure
Python — no LLM calls, runs in the default ``pytest`` invocation.
"""

from __future__ import annotations

from tests.eval.runtime_config import resolve_eval_config


def test_aligns_with_deepseek_production_env() -> None:
    cfg = resolve_eval_config(env={
        "LLM_PROVIDER": "deepseek",
        "LLM_API_KEY": "sk-fakedeepseek",
        "OMICSCLAW_MODEL": "deepseek-v4-flash",
    })
    assert cfg.api_key == "sk-fakedeepseek"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.model == "deepseek-v4-flash"


def test_eval_model_env_overrides_production_model() -> None:
    cfg = resolve_eval_config(env={
        "LLM_PROVIDER": "deepseek",
        "LLM_API_KEY": "sk-fake",
        "OMICSCLAW_MODEL": "deepseek-v4-flash",
        "EVAL_MODEL": "deepseek-reasoner",
    })
    assert cfg.model == "deepseek-reasoner"
    assert cfg.base_url == "https://api.deepseek.com"


def test_anthropic_key_picks_anthropic_endpoint_for_backward_compat() -> None:
    cfg = resolve_eval_config(env={
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    assert cfg.api_key == "sk-ant-fake"
    assert cfg.base_url == "https://api.anthropic.com/v1/"


def test_no_credential_yields_none_key() -> None:
    cfg = resolve_eval_config(env={})
    assert cfg.api_key is None

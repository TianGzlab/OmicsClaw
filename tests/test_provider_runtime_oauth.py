"""Tests for OAuth (ccproxy) support in provider_runtime.

Focus: ensure that when ``auth_mode="oauth"`` is set for an OAuth-capable
provider (anthropic/openai), the runtime snapshot and resolved config
point at a local ccproxy endpoint with the sentinel API key — and that
API-key mode behaves byte-identically to the pre-OAuth baseline.
"""

from __future__ import annotations

import pytest

from omicsclaw.core import provider_runtime as pr
from omicsclaw.core.ccproxy_manager import (
    OAUTH_PROVIDERS,
    provider_supports_oauth,
)


@pytest.fixture(autouse=True)
def _clear_runtime():
    pr.clear_active_provider_runtime()
    yield
    pr.clear_active_provider_runtime()


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def test_oauth_providers_registry_has_exactly_anthropic_and_openai():
    assert set(OAUTH_PROVIDERS.keys()) == {"anthropic", "openai"}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("anthropic", True),
        ("openai", True),
        ("ANTHROPIC", True),
        ("deepseek", False),
        ("gemini", False),
        ("", False),
    ],
)
def test_provider_supports_oauth(name, expected):
    assert provider_supports_oauth(name) is expected


# ---------------------------------------------------------------------------
# set_active_provider_runtime
# ---------------------------------------------------------------------------


def test_set_active_oauth_anthropic_overrides_base_url_and_key():
    rt = pr.set_active_provider_runtime(
        provider="anthropic", auth_mode="oauth", ccproxy_port=11435
    )
    assert rt.auth_mode == "oauth"
    assert rt.ccproxy_port == 11435
    assert rt.base_url == "http://127.0.0.1:11435/claude"
    assert rt.api_key == "ccproxy-oauth"


def test_set_active_oauth_openai_overrides_base_url_and_key():
    rt = pr.set_active_provider_runtime(
        provider="openai", auth_mode="oauth", ccproxy_port=9000
    )
    assert rt.base_url == "http://127.0.0.1:9000/codex/v1"
    assert rt.api_key == "ccproxy-oauth"


def test_set_active_oauth_ignored_for_unsupported_provider():
    """auth_mode=oauth on deepseek must NOT rewrite base_url."""
    rt = pr.set_active_provider_runtime(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-real",
        auth_mode="oauth",
    )
    assert rt.base_url == "https://api.deepseek.com"
    assert rt.api_key == "sk-real"
    assert rt.auth_mode == "oauth"  # field is set but has no effect


def test_set_active_api_key_mode_is_baseline():
    """Default auth_mode="api_key" behaves exactly as before the change."""
    rt = pr.set_active_provider_runtime(
        provider="anthropic",
        base_url="https://api.anthropic.com/v1/",
        api_key="sk-ant-xxx",
    )
    assert rt.auth_mode == "api_key"
    assert rt.base_url == "https://api.anthropic.com/v1/"
    assert rt.api_key == "sk-ant-xxx"


# ---------------------------------------------------------------------------
# _normalize_api_key_for_client
# ---------------------------------------------------------------------------


def test_normalize_api_key_returns_sentinel_for_oauth():
    assert (
        pr._normalize_api_key_for_client("anthropic", "", auth_mode="oauth")
        == "ccproxy-oauth"
    )
    assert (
        pr._normalize_api_key_for_client("openai", "", auth_mode="oauth")
        == "ccproxy-oauth"
    )


def test_normalize_api_key_oauth_ignored_for_non_oauth_provider():
    # deepseek in oauth mode without real key → empty (oauth not applicable)
    assert (
        pr._normalize_api_key_for_client("deepseek", "", auth_mode="oauth") == ""
    )


def test_normalize_api_key_keeps_explicit_key_over_sentinel():
    assert (
        pr._normalize_api_key_for_client("anthropic", "sk-real", auth_mode="oauth")
        == "sk-real"
    )


def test_normalize_api_key_api_key_mode_baseline():
    # ollama always gets the local placeholder
    assert pr._normalize_api_key_for_client("ollama", "") == "omicsclaw-local"
    # regular provider with empty key stays empty
    assert pr._normalize_api_key_for_client("deepseek", "") == ""


# ---------------------------------------------------------------------------
# resolve_provider_runtime
# ---------------------------------------------------------------------------


def test_resolve_oauth_overrides_preset_base_url(monkeypatch):
    """Even without setting an active runtime, explicit auth_mode=oauth
    on resolve_provider_runtime replaces the preset cloud URL."""
    resolved = pr.resolve_provider_runtime(
        provider="anthropic",
        auth_mode="oauth",
        ccproxy_port=11435,
        env={},
    )
    assert resolved.provider == "anthropic"
    assert resolved.base_url == "http://127.0.0.1:11435/claude"
    assert resolved.api_key == "ccproxy-oauth"
    assert resolved.auth_mode == "oauth"


def test_resolve_oauth_reuses_active_runtime():
    pr.set_active_provider_runtime(
        provider="openai", auth_mode="oauth", ccproxy_port=9100
    )
    resolved = pr.resolve_provider_runtime(env={})
    assert resolved.source == "active-runtime"
    assert resolved.base_url == "http://127.0.0.1:9100/codex/v1"
    assert resolved.api_key == "ccproxy-oauth"
    assert resolved.auth_mode == "oauth"
    assert resolved.ccproxy_port == 9100


def test_resolve_api_key_mode_unchanged(monkeypatch):
    """Regression: API key path must be byte-identical to pre-OAuth baseline."""
    resolved = pr.resolve_provider_runtime(
        provider="deepseek",
        api_key="sk-ds-xxx",
        env={},
    )
    assert resolved.provider == "deepseek"
    assert resolved.base_url == "https://api.deepseek.com"
    assert resolved.api_key == "sk-ds-xxx"
    assert resolved.auth_mode == "api_key"


def test_resolve_oauth_for_unsupported_provider_keeps_preset(monkeypatch):
    """auth_mode=oauth on gemini must NOT rewrite the cloud URL."""
    resolved = pr.resolve_provider_runtime(
        provider="gemini",
        auth_mode="oauth",
        env={"GOOGLE_API_KEY": "sk-g"},
    )
    assert resolved.provider == "gemini"
    assert "generativelanguage.googleapis.com" in resolved.base_url
    # sentinel NOT used because gemini is not OAuth-capable
    assert resolved.api_key != "ccproxy-oauth"

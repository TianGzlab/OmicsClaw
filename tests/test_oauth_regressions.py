"""Regression tests for the 6 OAuth / ccproxy bugs reported after Stage 1-4:

1. Critical: app-server + ccproxy both defaulted to port 8765 → conflict.
2. High: ``omicsclaw auth login claude`` raised KeyError('claude').
3. High: OAuth-injected env vars polluted subsequent api_key mode.
4. High: resolve_provider_runtime reused active runtime across auth_mode switches.
5. Medium: CLI/server logout bypassed ``_ccproxy_exe()`` venv-aware lookup.
6. Medium: bootstrap didn't fail-fast when ``auth_mode=oauth`` was paired
   with an OAuth-incapable provider.

All tests mock subprocess / httpx / shutil.which so they run offline.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from omicsclaw.core import ccproxy_manager as ccm
from omicsclaw.core import provider_runtime as pr


@pytest.fixture(autouse=True)
def _isolate_env_and_runtime():
    """Snapshot-and-restore the env vars ccproxy writes + clear active runtime."""
    keys = (
        "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL", "OPENAI_API_KEY",
    )
    snapshot = {k: os.environ.get(k) for k in keys}
    pr.clear_active_provider_runtime()
    try:
        yield
    finally:
        pr.clear_active_provider_runtime()
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Bug 1: default ports must not collide
# ---------------------------------------------------------------------------


def test_bug1_ccproxy_default_port_differs_from_app_server():
    """Regression for Bug 1 (Critical): ccproxy default port was 8765 =
    app-server default, so switching to OAuth would deadlock on bind."""
    from omicsclaw.app.server import DEFAULT_APP_API_PORT

    assert ccm.DEFAULT_CCPROXY_PORT != DEFAULT_APP_API_PORT
    assert pr.DEFAULT_CCPROXY_PORT != DEFAULT_APP_API_PORT
    assert ccm.DEFAULT_CCPROXY_PORT == pr.DEFAULT_CCPROXY_PORT


# ---------------------------------------------------------------------------
# Bug 2: CLI alias 'claude' must map to 'anthropic' (and 'codex' → 'openai')
# ---------------------------------------------------------------------------


def test_bug2_normalize_cli_provider_claude_alias():
    assert ccm.normalize_cli_provider("claude") == "anthropic"
    assert ccm.normalize_cli_provider("CLAUDE") == "anthropic"
    assert ccm.normalize_cli_provider("anthropic") == "anthropic"
    assert ccm.normalize_cli_provider("codex") == "openai"
    assert ccm.normalize_cli_provider("openai") == "openai"


def test_bug2_normalize_cli_provider_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown OAuth provider alias"):
        ccm.normalize_cli_provider("gemini")


def test_bug2_lookup_after_normalize_does_not_keyerror():
    """The original bug path: CLI alias → CCPROXY_PROVIDER_MAP lookup."""
    omics_name = ccm.normalize_cli_provider("claude")
    assert ccm.CCPROXY_PROVIDER_MAP[omics_name] == "claude_api"  # no KeyError


def test_bug2_maybe_start_ccproxy_error_message_uses_cli_alias(monkeypatch):
    """Error message should tell users to run `auth login claude`, not
    `auth login anthropic` (which argparse used to reject)."""
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "check_ccproxy_auth", lambda p: (False, "no creds"))

    with pytest.raises(RuntimeError, match=r"omicsclaw auth login claude\b"):
        ccm.maybe_start_ccproxy(anthropic_oauth=True, port=11435)

    with pytest.raises(RuntimeError, match=r"omicsclaw auth login openai\b"):
        ccm.maybe_start_ccproxy(openai_oauth=True, port=11435)


# ---------------------------------------------------------------------------
# Bug 3: OAuth must not pollute subsequent api_key mode
# ---------------------------------------------------------------------------


def test_bug3_clear_ccproxy_env_removes_oauth_injection():
    """After setup_ccproxy_env, clear_ccproxy_env must restore env to clean."""
    ccm.setup_ccproxy_env("anthropic", 11435)
    assert os.environ["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:11435/claude"
    assert os.environ["ANTHROPIC_API_KEY"] == "ccproxy-oauth"

    ccm.clear_ccproxy_env("anthropic")
    assert "ANTHROPIC_BASE_URL" not in os.environ
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_bug3_clear_ccproxy_env_preserves_real_credentials():
    """clear_ccproxy_env must NOT touch a real user-supplied ANTHROPIC_API_KEY."""
    os.environ["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com/v1/"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-real-key"

    ccm.clear_ccproxy_env("anthropic")

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-real-key"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com/v1/"


def test_bug3_clear_ccproxy_env_no_provider_clears_both():
    ccm.setup_ccproxy_env("anthropic", 11435)
    ccm.setup_ccproxy_env("openai", 11435)

    ccm.clear_ccproxy_env()  # no provider = clear all

    assert "ANTHROPIC_BASE_URL" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_bug3_api_key_mode_after_oauth_sees_clean_env(monkeypatch):
    """Full reproducer: OAuth session → api_key resolve must hit cloud URL."""
    from omicsclaw.core.provider_registry import resolve_provider

    # Simulate a prior OAuth session leaving env polluted.
    ccm.setup_ccproxy_env("anthropic", 9999)
    assert "127.0.0.1:9999" in os.environ["ANTHROPIC_BASE_URL"]

    # Before clear: resolve_provider would still return the ccproxy URL.
    polluted_url, _, _ = resolve_provider(provider="anthropic", api_key="sk-real")
    assert "127.0.0.1:9999" in str(polluted_url)  # documents the bug

    # After clear: clean cloud URL.
    ccm.clear_ccproxy_env("anthropic")
    clean_url, _, real_key = resolve_provider(provider="anthropic", api_key="sk-real")
    assert str(clean_url).startswith("https://api.anthropic.com")
    assert real_key == "sk-real"


# ---------------------------------------------------------------------------
# Bug 4: resolve_provider_runtime must respect explicit auth_mode switches
# ---------------------------------------------------------------------------


def test_bug4_oauth_active_runtime_honors_explicit_api_key_switch():
    """Active runtime is OAuth; explicit api_key request must NOT reuse it."""
    # Seed an OAuth active runtime
    pr.set_active_provider_runtime(
        provider="anthropic", auth_mode="oauth", ccproxy_port=11435
    )
    runtime_before = pr.get_active_provider_runtime()
    assert runtime_before is not None and runtime_before.auth_mode == "oauth"

    # Explicitly switch to api_key — must not return ccproxy URL / sentinel
    resolved = pr.resolve_provider_runtime(
        provider="anthropic",
        auth_mode="api_key",
        api_key="sk-real",
        env={"ANTHROPIC_API_KEY": "sk-real"},
    )
    assert resolved.auth_mode == "api_key"
    assert "127.0.0.1" not in resolved.base_url
    assert resolved.api_key == "sk-real"
    assert resolved.source != "active-runtime"  # must fall through full resolution


def test_bug4_api_key_active_runtime_honors_explicit_oauth_switch(monkeypatch):
    """Active runtime is api_key; explicit oauth request must override."""
    pr.set_active_provider_runtime(
        provider="anthropic",
        base_url="https://api.anthropic.com/v1/",
        api_key="sk-ant-real",
        auth_mode="api_key",
    )

    resolved = pr.resolve_provider_runtime(
        provider="anthropic",
        auth_mode="oauth",
        ccproxy_port=11435,
        env={},
    )
    assert resolved.auth_mode == "oauth"
    assert "127.0.0.1:11435" in resolved.base_url
    assert resolved.api_key == "ccproxy-oauth"


def test_bug4_unspecified_auth_mode_still_reuses_runtime():
    """If caller passes no auth_mode, active runtime reuse is unchanged."""
    pr.set_active_provider_runtime(
        provider="anthropic", auth_mode="oauth", ccproxy_port=11435
    )
    resolved = pr.resolve_provider_runtime(env={})
    assert resolved.source == "active-runtime"
    assert resolved.auth_mode == "oauth"


# ---------------------------------------------------------------------------
# Bug 5: CLI / server logout must go through ccproxy_executable()
# ---------------------------------------------------------------------------


def test_bug5_ccproxy_executable_public_api_exists():
    """ccproxy_executable() is the venv-aware binary lookup. Callers
    outside the module (CLI, server) should use it instead of literal
    'ccproxy' so they keep working when the binary is in the venv bin/
    but not on $PATH."""
    assert callable(ccm.ccproxy_executable)


def test_bug5_ccproxy_executable_returns_path_when_found(monkeypatch):
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/opt/venv/bin/ccproxy")
    assert ccm.ccproxy_executable() == "/opt/venv/bin/ccproxy"


def test_bug5_ccproxy_executable_falls_back_to_literal(monkeypatch):
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: None)
    assert ccm.ccproxy_executable() == "ccproxy"


# ---------------------------------------------------------------------------
# Bug 6: core.init must fail fast on auth_mode=oauth + non-OAuth provider
# ---------------------------------------------------------------------------


def test_bug6_core_init_rejects_oauth_for_unsupported_provider(monkeypatch):
    """LLM_AUTH_MODE=oauth + LLM_PROVIDER=deepseek should raise — not
    silently try to start ccproxy with both flags False."""
    from bot import core as botcore

    # Keep us from hitting AsyncOpenAI construction
    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    # Pretend ccproxy is installed so we don't bail on that check first
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)

    with pytest.raises(RuntimeError, match="auth_mode='oauth' is not supported"):
        botcore.init(
            provider="deepseek",
            api_key="sk-x",
            auth_mode="oauth",
            ccproxy_port=11435,
        )


def test_bug6_core_init_allows_oauth_for_anthropic(monkeypatch):
    """Happy path: anthropic + oauth should proceed to maybe_start_ccproxy."""
    from bot import core as botcore

    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "check_ccproxy_auth", lambda p: (True, "ok"))
    monkeypatch.setattr(ccm, "ensure_ccproxy", lambda port: None)

    botcore.init(
        provider="anthropic",
        api_key="",
        auth_mode="oauth",
        ccproxy_port=11435,
    )

    runtime = pr.get_active_provider_runtime()
    assert runtime is not None
    assert runtime.auth_mode == "oauth"
    assert runtime.base_url == "http://127.0.0.1:11435/claude"


# ---------------------------------------------------------------------------
# Bug 7 (post-Stage-4): bootstrap resilience — stale LLM_AUTH_MODE=oauth in
# .env combined with a missing ccproxy must not block app-server startup.
# ---------------------------------------------------------------------------


def test_bug7_core_init_bootstrap_degrades_when_ccproxy_missing(
    monkeypatch, caplog
):
    """strict_oauth=False + ccproxy missing → warn and fall back to api_key.

    Regression for user-reported symptom: uvicorn lifespan crashed with
    ``RuntimeError: ccproxy is required for OAuth mode but was not found``
    whenever ``.env`` had ``LLM_AUTH_MODE=oauth`` but ccproxy wasn't
    installed. The server should start and log a warning instead.
    """
    from bot import core as botcore

    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: False)

    with caplog.at_level("WARNING", logger="omicsclaw.bot"):
        botcore.init(
            provider="anthropic",
            api_key="sk-real",
            auth_mode="oauth",
            ccproxy_port=11435,
            strict_oauth=False,
        )

    runtime = pr.get_active_provider_runtime()
    assert runtime is not None
    assert runtime.auth_mode == "api_key"  # downgraded
    assert "127.0.0.1" not in runtime.base_url  # not routed through ccproxy
    # Warning should mention the reason
    assert any(
        "Falling back to auth_mode='api_key'" in rec.message
        for rec in caplog.records
    )


def test_bug7_core_init_strict_raises_when_ccproxy_missing(monkeypatch):
    """Default strict_oauth=True preserves fail-fast for explicit callers."""
    from bot import core as botcore

    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: False)

    with pytest.raises(RuntimeError, match="ccproxy is required for OAuth mode"):
        botcore.init(
            provider="anthropic",
            auth_mode="oauth",
            ccproxy_port=11435,
        )


def test_oauth_providers_table_is_self_consistent():
    """The single-source-of-truth ``OAUTH_PROVIDERS`` table must satisfy
    every invariant the rest of the system relies on.

    This is the refactor's contract test: if any of these assertions ever
    break, it means someone added a row without filling all required
    fields, or the backwards-compat views drifted from the table.
    """
    from omicsclaw.core.ccproxy_manager import (
        CCPROXY_PROVIDER_MAP,
        CLI_PROVIDER_ALIASES,
        OAUTH_PROVIDERS,
        _OAUTH_ALIAS_MAP,
        get_oauth_provider,
        normalize_oauth_provider,
        oauth_cli_aliases,
    )

    for canonical, p in OAUTH_PROVIDERS.items():
        # (1) dict key equals the row's canonical name
        assert canonical == p.omics_name

        # (2) every field is a non-empty string
        for field in (
            "omics_name", "cli_alias", "ccproxy_target",
            "base_url_path", "env_base_url", "env_api_key",
        ):
            assert getattr(p, field), f"empty {field} on {canonical}"

        # (3) base URL path always starts with '/'
        assert p.base_url_path.startswith("/")

        # (4) all three aliases (omics/cli/ccproxy) normalize back to canonical
        for alias in (p.omics_name, p.cli_alias, p.ccproxy_target):
            assert normalize_oauth_provider(alias) == canonical
            assert get_oauth_provider(alias) is p

    # (5) backwards-compat views are derived, not redeclared
    assert CCPROXY_PROVIDER_MAP == {
        p.omics_name: p.ccproxy_target for p in OAUTH_PROVIDERS.values()
    }
    assert CLI_PROVIDER_ALIASES == _OAUTH_ALIAS_MAP

    # (6) oauth_cli_aliases covers every alias of every row
    expected_aliases = {
        alias
        for p in OAUTH_PROVIDERS.values()
        for alias in (p.omics_name, p.cli_alias, p.ccproxy_target)
    }
    assert set(oauth_cli_aliases()) == expected_aliases


def test_bug7_bootstrap_degrades_for_unsupported_provider(monkeypatch, caplog):
    """stale LLM_AUTH_MODE=oauth + LLM_PROVIDER=deepseek → warn, not raise."""
    from bot import core as botcore

    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    # Even if ccproxy IS installed, deepseek isn't OAuth-capable.
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)

    with caplog.at_level("WARNING", logger="omicsclaw.bot"):
        botcore.init(
            provider="deepseek",
            api_key="sk-ds",
            auth_mode="oauth",
            ccproxy_port=11435,
            strict_oauth=False,
        )

    runtime = pr.get_active_provider_runtime()
    assert runtime is not None
    assert runtime.auth_mode == "api_key"


def test_bug8_core_init_normalizes_stale_cross_provider_model(monkeypatch, caplog):
    """provider remains authoritative; stale foreign default model is repaired."""
    from bot import core as botcore
    from omicsclaw.core.provider_registry import PROVIDER_PRESETS

    monkeypatch.setattr(botcore, "AsyncOpenAI", MagicMock())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with caplog.at_level("WARNING", logger="omicsclaw.bot"):
        botcore.init(
            provider="anthropic",
            model="deepseek-chat",
            auth_mode="api_key",
        )

    runtime = pr.get_active_provider_runtime()
    assert runtime is not None
    assert runtime.provider == "anthropic"
    assert runtime.model == PROVIDER_PRESETS["anthropic"][1]
    assert botcore.LLM_PROVIDER_NAME == "anthropic"
    assert botcore.OMICSCLAW_MODEL == PROVIDER_PRESETS["anthropic"][1]
    assert any(
        "Normalized stale model 'deepseek-chat'" in rec.message
        for rec in caplog.records
    )

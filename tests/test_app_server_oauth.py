"""Tests for the OAuth endpoints added to omicsclaw.app.server.

These call the FastAPI route handlers directly (as coroutines) to avoid
firing the full server lifespan on each test. ccproxy is mocked so no
real binary is needed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# /auth/{provider}/status
# ---------------------------------------------------------------------------


def test_oauth_status_rejects_unknown_provider():
    from omicsclaw.app import server

    with pytest.raises(HTTPException) as exc:
        _run(server.oauth_status("deepseek"))
    assert exc.value.status_code == 400
    assert "Unknown OAuth provider alias" in exc.value.detail


def test_oauth_status_fails_when_ccproxy_missing(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: False)

    with pytest.raises(HTTPException) as exc:
        _run(server.oauth_status("claude"))
    assert exc.value.status_code == 400
    assert "not installed" in exc.value.detail


def test_oauth_status_returns_authenticated(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(
        ccm, "check_ccproxy_auth", lambda p: (True, "user@example.com (plus)")
    )

    result = _run(server.oauth_status("claude"))
    assert result == {
        "provider": "anthropic",
        "authenticated": True,
        "message": "user@example.com (plus)",
    }


def test_oauth_status_accepts_both_aliases(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "check_ccproxy_auth", lambda p: (False, "no"))

    assert _run(server.oauth_status("anthropic"))["provider"] == "anthropic"
    assert _run(server.oauth_status("claude"))["provider"] == "anthropic"
    assert _run(server.oauth_status("openai"))["provider"] == "openai"
    assert _run(server.oauth_status("codex"))["provider"] == "openai"


# ---------------------------------------------------------------------------
# /auth/{provider}/login
# ---------------------------------------------------------------------------


def test_oauth_login_returns_client_side_command(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)

    result = _run(server.oauth_login("claude"))
    assert result["provider"] == "anthropic"
    assert result["command"] == "ccproxy auth login claude_api"
    # Hint must direct the user to the backend host — Docker / remote
    # deployments break if the login runs on a different machine.
    hint_lower = result["hint"].lower()
    assert "backend" in hint_lower
    assert "host" in hint_lower
    assert "local terminal" not in hint_lower

    result_openai = _run(server.oauth_login("openai"))
    assert result_openai["command"] == "ccproxy auth login codex"


def test_oauth_login_adds_env_unset_when_empty_proxies_detected(monkeypatch):
    """Regression for the httpx 'Unknown scheme for proxy URL URL("")'
    failure mode: when the backend process inherits empty-string proxy
    env vars (e.g. user launched uvicorn with ``HTTPS_PROXY=``), the
    command returned to the frontend must prepend ``env -u ...`` so
    copy-paste works from any shell that has the same poisoned env.
    """
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    # Simulate a server process whose env has HTTPS_PROXY="" (the toxic case)
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setenv("http_proxy", "")
    # A genuine proxy, by contrast, should NOT trigger the wrap
    monkeypatch.setenv("ALL_PROXY", "http://proxy.example:3128")

    result = _run(server.oauth_login("claude"))

    cmd = result["command"]
    assert cmd.startswith("env -u ")
    assert "-u HTTPS_PROXY" in cmd
    assert "-u http_proxy" in cmd
    # ALL_PROXY was a real value, not empty → must NOT be unset
    assert "-u ALL_PROXY" not in cmd
    assert "-u all_proxy" not in cmd
    assert cmd.endswith(" ccproxy auth login claude_api")
    assert "warning" in result
    assert "HTTPS_PROXY" in result["warning"]


def test_oauth_login_leaves_command_clean_when_env_is_ok(monkeypatch):
    """Default case: no proxy env hygiene issues → command has no prefix
    and no warning key is emitted."""
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    # Ensure clean env by removing any inherited proxy vars
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)

    result = _run(server.oauth_login("codex"))

    assert result["command"] == "ccproxy auth login codex"
    assert "warning" not in result


def test_oauth_login_rejects_unsupported_provider(monkeypatch):
    from omicsclaw.app import server

    with pytest.raises(HTTPException) as exc:
        _run(server.oauth_login("gemini"))
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# /auth/{provider}/logout
# ---------------------------------------------------------------------------


def test_oauth_logout_invokes_ccproxy(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "ccproxy_executable", lambda: "/opt/venv/bin/ccproxy")

    captured: dict = {}

    def _fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="logged out", stderr="")

    import subprocess

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = _run(server.oauth_logout("openai"))
    assert captured["cmd"] == ["/opt/venv/bin/ccproxy", "auth", "logout", "codex"]
    assert result["ok"] is True
    assert result["provider"] == "openai"


def test_oauth_logout_clears_active_oauth_runtime(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm
    from omicsclaw.core.provider_runtime import (
        clear_active_provider_runtime,
        get_active_provider_runtime,
        set_active_provider_runtime,
    )

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "ccproxy_executable", lambda: "/opt/venv/bin/ccproxy")

    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="logged out", stderr=""),
    )

    fake_core = MagicMock()
    fake_core.llm = object()
    monkeypatch.setattr(server, "_get_core", lambda: fake_core)

    clear_active_provider_runtime()
    set_active_provider_runtime(
        provider="anthropic",
        auth_mode="oauth",
        ccproxy_port=11435,
    )

    result = _run(server.oauth_logout("claude"))

    assert result["ok"] is True
    assert get_active_provider_runtime() is None
    assert fake_core.llm is None


def test_oauth_logout_persists_api_key_fallback_to_env(monkeypatch, tmp_path):
    """Logout of the active OAuth provider must rewrite .env to api_key.

    Regression: previously only in-memory state was cleared, so a restart
    would re-read LLM_AUTH_MODE=oauth and try to reconstruct the OAuth
    session against a now-unauthenticated ccproxy.
    """
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm
    from omicsclaw.core.provider_runtime import (
        clear_active_provider_runtime,
        set_active_provider_runtime,
    )

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_PROVIDER=anthropic\n"
        "LLM_AUTH_MODE=oauth\n"
        "CCPROXY_PORT=9000\n"
        "OMICSCLAW_MODEL=claude-sonnet-4-6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMICSCLAW_DIR", str(tmp_path))

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "ccproxy_executable", lambda: "/opt/venv/bin/ccproxy")

    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="logged out", stderr=""),
    )

    fake_core = MagicMock()
    fake_core.llm = object()
    fake_core.LLM_PROVIDER_NAME = "anthropic"
    fake_core.OMICSCLAW_MODEL = "claude-sonnet-4-6"
    monkeypatch.setattr(server, "_get_core", lambda: fake_core)

    clear_active_provider_runtime()
    set_active_provider_runtime(
        provider="anthropic",
        auth_mode="oauth",
        ccproxy_port=9000,
    )

    result = _run(server.oauth_logout("claude"))
    assert result["ok"] is True

    # In-memory core display state is reset so the frontend won't keep
    # surfacing the now-credentialless provider as active.
    assert fake_core.LLM_PROVIDER_NAME == ""
    assert fake_core.OMICSCLAW_MODEL == ""
    assert fake_core.llm is None

    body = env_path.read_text(encoding="utf-8")
    assert "LLM_AUTH_MODE=api_key" in body
    assert "CCPROXY_PORT=" not in body


def test_oauth_logout_non_active_provider_does_not_touch_env(monkeypatch, tmp_path):
    """Logout of a provider that isn't the active OAuth provider is a no-op
    on .env — we must not wipe the other provider's OAuth config."""
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm
    from omicsclaw.core.provider_runtime import (
        clear_active_provider_runtime,
        set_active_provider_runtime,
    )

    env_path = tmp_path / ".env"
    original = (
        "LLM_PROVIDER=anthropic\n"
        "LLM_AUTH_MODE=oauth\n"
        "CCPROXY_PORT=9000\n"
    )
    env_path.write_text(original, encoding="utf-8")
    monkeypatch.setenv("OMICSCLAW_DIR", str(tmp_path))

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "ccproxy_executable", lambda: "/opt/venv/bin/ccproxy")

    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="logged out", stderr=""),
    )

    fake_core = MagicMock()
    fake_core.llm = object()
    fake_core.LLM_PROVIDER_NAME = "anthropic"
    monkeypatch.setattr(server, "_get_core", lambda: fake_core)

    clear_active_provider_runtime()
    set_active_provider_runtime(
        provider="anthropic",
        auth_mode="oauth",
        ccproxy_port=9000,
    )

    # Log out the *other* provider (openai) while anthropic is active.
    _run(server.oauth_logout("openai"))

    body = env_path.read_text(encoding="utf-8")
    assert "LLM_AUTH_MODE=oauth" in body
    assert "CCPROXY_PORT=9000" in body


# ---------------------------------------------------------------------------
# chat-path provider switch persistence (regression for OAuth state leak)
# ---------------------------------------------------------------------------


def test_chat_provider_switch_clears_stale_oauth_env(monkeypatch, tmp_path):
    """Switching provider through the chat request must reset LLM_AUTH_MODE
    and drop CCPROXY_PORT; otherwise a restart re-enters the bad
    (new_provider + oauth) combination."""
    from omicsclaw.app import server

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_PROVIDER=anthropic\n"
        "LLM_AUTH_MODE=oauth\n"
        "CCPROXY_PORT=9000\n"
        "OMICSCLAW_MODEL=claude-sonnet-4-6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMICSCLAW_DIR", str(tmp_path))

    class FakeCore:
        LLM_PROVIDER_NAME = "anthropic"
        OMICSCLAW_MODEL = "claude-sonnet-4-6"

        def init(self, **kwargs):
            # Chat path never passes auth_mode, so we default to api_key,
            # mirroring the production bot.core.init() contract.
            assert "auth_mode" not in kwargs
            self.LLM_PROVIDER_NAME = kwargs["provider"]
            self.OMICSCLAW_MODEL = kwargs.get("model") or "deepseek-chat"

    fake_core = FakeCore()
    server._apply_chat_provider_switch(fake_core, "deepseek", "")

    body = env_path.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=deepseek" in body
    assert "LLM_AUTH_MODE=api_key" in body
    assert "CCPROXY_PORT=" not in body
    assert "OMICSCLAW_MODEL=deepseek-chat" in body


def test_chat_provider_switch_failure_leaves_env_untouched(monkeypatch, tmp_path):
    """If core.init raises, .env must not be partially rewritten — the
    previous provider config stays intact so the user can retry."""
    from omicsclaw.app import server

    env_path = tmp_path / ".env"
    original = (
        "LLM_PROVIDER=anthropic\n"
        "LLM_AUTH_MODE=oauth\n"
        "CCPROXY_PORT=9000\n"
    )
    env_path.write_text(original, encoding="utf-8")
    monkeypatch.setenv("OMICSCLAW_DIR", str(tmp_path))

    class FailingCore:
        LLM_PROVIDER_NAME = "anthropic"
        OMICSCLAW_MODEL = "claude-sonnet-4-6"

        def init(self, **kwargs):
            raise RuntimeError("provider unreachable")

    server._apply_chat_provider_switch(FailingCore(), "deepseek", "")

    assert env_path.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# /providers oauth fields
# ---------------------------------------------------------------------------


def test_cached_oauth_statuses_handles_missing_ccproxy(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: False)
    # Reset cache
    server._OAUTH_STATUS_CACHE["ts"] = 0.0

    result = server._cached_oauth_statuses()
    assert result == {}


def test_cached_oauth_statuses_queries_both_providers(monkeypatch):
    from omicsclaw.app import server
    from omicsclaw.core import ccproxy_manager as ccm

    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    calls: list[str] = []

    def _probe(p):
        calls.append(p)
        return (p == "claude_api", "ok" if p == "claude_api" else "no")

    monkeypatch.setattr(ccm, "check_ccproxy_auth", _probe)
    server._OAUTH_STATUS_CACHE["ts"] = 0.0

    result = server._cached_oauth_statuses()
    assert set(calls) == {"claude_api", "codex"}
    assert result["anthropic"]["authenticated"] is True
    assert result["openai"]["authenticated"] is False


# ---------------------------------------------------------------------------
# ProviderSwitchRequest oauth validation
# ---------------------------------------------------------------------------


def test_provider_switch_request_defaults_to_api_key():
    from omicsclaw.app.server import ProviderSwitchRequest

    req = ProviderSwitchRequest(provider="deepseek")
    assert req.auth_mode == "api_key"
    assert req.ccproxy_port == 11435  # must differ from app-server default 8765


def test_provider_switch_request_accepts_oauth():
    from omicsclaw.app.server import ProviderSwitchRequest

    req = ProviderSwitchRequest(
        provider="anthropic", auth_mode="oauth", ccproxy_port=9000
    )
    assert req.auth_mode == "oauth"
    assert req.ccproxy_port == 9000


def test_switch_provider_rejects_conflict_with_nondefault_app_port(monkeypatch):
    from omicsclaw.app import server

    monkeypatch.setenv("OMICSCLAW_APP_PORT", "9000")
    monkeypatch.setattr(server, "_get_core", lambda: MagicMock())

    with pytest.raises(HTTPException) as exc:
        _run(
            server.switch_provider(
                server.ProviderSwitchRequest(
                    provider="anthropic",
                    auth_mode="oauth",
                    ccproxy_port=9000,
                )
            )
        )
    assert exc.value.status_code == 400
    assert "conflicts with the OmicsClaw app-server port (9000)" in exc.value.detail


def test_switch_provider_clears_stale_base_url_and_persists_resolved_model(monkeypatch, tmp_path):
    from omicsclaw.app import server

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_PROVIDER=custom\n"
        "LLM_BASE_URL=https://gateway.example.test/v1\n"
        "OMICSCLAW_MODEL=old-model\n"
        "CCPROXY_PORT=9000\n",
        encoding="utf-8",
    )

    class FakeCore:
        LLM_PROVIDER_NAME = "custom"
        OMICSCLAW_MODEL = "old-model"

        def init(self, **kwargs):
            self.LLM_PROVIDER_NAME = kwargs.get("provider", "custom")
            self.OMICSCLAW_MODEL = kwargs.get("model") or "claude-sonnet-4-6"

    monkeypatch.setenv("OMICSCLAW_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_get_core", lambda: FakeCore())

    result = _run(
        server.switch_provider(
            server.ProviderSwitchRequest(
                provider="anthropic",
                api_key="sk-ant-new",
                auth_mode="api_key",
            )
        )
    )

    assert result == {
        "ok": True,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "auth_mode": "api_key",
    }

    body = env_path.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=anthropic" in body
    assert "OMICSCLAW_MODEL=claude-sonnet-4-6" in body
    assert "LLM_BASE_URL=" not in body
    assert "CCPROXY_PORT=" not in body

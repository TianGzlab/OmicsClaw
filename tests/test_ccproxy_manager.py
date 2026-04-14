"""Unit tests for omicsclaw.core.ccproxy_manager.

All subprocess / httpx / binary lookups are mocked so tests run offline
and do not require the optional ``ccproxy-api`` package.
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from omicsclaw.core import ccproxy_manager as ccm


@pytest.fixture(autouse=True)
def _restore_oauth_env_vars():
    """Isolate tests that mutate ANTHROPIC_/OPENAI_ env vars via os.environ.

    ``setup_ccproxy_env`` writes ``os.environ`` directly (bypassing
    ``monkeypatch``), so without this fixture the values leak into
    subsequent tests in the suite.
    """
    keys = (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
    )
    snapshot = {k: os.environ.get(k) for k in keys}
    try:
        yield
    finally:
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------


def test_is_ccproxy_available_true(monkeypatch):
    monkeypatch.setattr(ccm.shutil, "which", lambda name: "/usr/local/bin/ccproxy")
    assert ccm.is_ccproxy_available() is True


def test_is_ccproxy_available_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ccm.shutil, "which", lambda name: None)
    # Force a python executable that has no sibling ccproxy binary.
    import sys

    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python"))
    assert ccm.is_ccproxy_available() is False


def test_oauth_install_hint_returns_str():
    hint = ccm.oauth_install_hint()
    assert isinstance(hint, str) and "oauth" in hint


def test_ccproxy_diagnostic_hint_reports_python_path(monkeypatch):
    """When ccproxy is missing, the hint must tell the user WHICH Python
    was checked and where — so they can tell if the server is running in
    the wrong venv (the #1 real-world cause of 'ccproxy is not installed'
    despite having pip-installed it somewhere)."""
    monkeypatch.setattr(ccm.shutil, "which", lambda _n: None)
    import sys
    monkeypatch.setattr(sys, "executable", "/tmp/fake-python/bin/python")

    hint = ccm.ccproxy_diagnostic_hint()
    assert "/tmp/fake-python/bin/python" in hint  # sys.executable surfaced
    assert "PATH" in hint or "shutil.which" in hint
    assert "next to interpreter" in hint
    assert "venv" in hint.lower()  # activation hint present
    # Exact, copy-pasteable pip command bound to THIS interpreter.
    # Prevents the "I ran pip install, but in the wrong venv" loop.
    assert "/tmp/fake-python/bin/python -m pip install ccproxy-api" in hint


def test_ccproxy_diagnostic_hint_reports_found_path_when_available(monkeypatch):
    """When ccproxy IS found on PATH, the hint should reflect that and not
    emit the activation fallback suggestion."""
    monkeypatch.setattr(ccm.shutil, "which", lambda _n: "/opt/venv/bin/ccproxy")

    hint = ccm.ccproxy_diagnostic_hint()
    assert "/opt/venv/bin/ccproxy" in hint
    # Activation hint only fires when nothing is found
    assert "activate" not in hint.lower()


# ---------------------------------------------------------------------------
# Auth status parsing
# ---------------------------------------------------------------------------


def test_check_ccproxy_auth_authenticated(monkeypatch):
    stdout = (
        "Email               user@example.com\n"
        "Subscription        plus\n"
        "Subscription Status active\n"
    )
    completed = MagicMock(returncode=0, stdout=stdout, stderr="")
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm.subprocess, "run", lambda *a, **kw: completed)

    ok, msg = ccm.check_ccproxy_auth("claude_api")
    assert ok is True
    assert "user@example.com" in msg
    assert "plus" in msg


def test_check_ccproxy_auth_not_authenticated(monkeypatch):
    completed = MagicMock(returncode=1, stdout="Not authenticated", stderr="")
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm.subprocess, "run", lambda *a, **kw: completed)

    ok, msg = ccm.check_ccproxy_auth("claude_api")
    assert ok is False
    assert "not authenticated" in msg.lower() or "Not authenticated" in msg


def test_check_ccproxy_auth_timeout(monkeypatch):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="ccproxy", timeout=10)

    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm.subprocess, "run", _raise)

    ok, msg = ccm.check_ccproxy_auth("codex")
    assert ok is False
    assert "timed out" in msg.lower()


def test_check_ccproxy_auth_accepts_omicsclaw_alias(monkeypatch):
    """``anthropic`` should be mapped to ``claude_api`` internally."""
    captured: dict = {}

    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return MagicMock(returncode=1, stdout="Not authenticated", stderr="")

    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm.subprocess, "run", _run)

    ccm.check_ccproxy_auth("anthropic")
    assert captured["cmd"][-1] == "claude_api"

    ccm.check_ccproxy_auth("openai")
    assert captured["cmd"][-1] == "codex"


# ---------------------------------------------------------------------------
# Process lifecycle
# ---------------------------------------------------------------------------


def test_is_ccproxy_running_true(monkeypatch):
    fake_httpx = MagicMock()
    fake_httpx.get.return_value = MagicMock(status_code=200)
    fake_httpx.ConnectError = ConnectionError
    fake_httpx.TimeoutException = TimeoutError
    monkeypatch.setitem(
        __import__("sys").modules, "httpx", fake_httpx
    )
    assert ccm.is_ccproxy_running(8765) is True


def test_is_ccproxy_running_false_on_connection_error(monkeypatch):
    fake_httpx = MagicMock()
    fake_httpx.ConnectError = ConnectionError
    fake_httpx.TimeoutException = TimeoutError
    fake_httpx.get.side_effect = ConnectionError("refused")
    monkeypatch.setitem(
        __import__("sys").modules, "httpx", fake_httpx
    )
    assert ccm.is_ccproxy_running(8765) is False


def test_start_ccproxy_succeeds_when_healthy(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    monkeypatch.setattr(
        ccm.subprocess, "Popen", MagicMock(return_value=fake_proc)
    )
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm, "is_ccproxy_running", lambda port: True)

    proc = ccm.start_ccproxy(8765)
    assert proc is fake_proc


def test_start_ccproxy_raises_on_early_exit(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1
    fake_proc.returncode = 1
    monkeypatch.setattr(
        ccm.subprocess, "Popen", MagicMock(return_value=fake_proc)
    )
    monkeypatch.setattr(ccm, "_ccproxy_exe", lambda: "/usr/bin/ccproxy")
    monkeypatch.setattr(ccm, "is_ccproxy_running", lambda port: False)

    with pytest.raises(RuntimeError, match="exited immediately"):
        ccm.start_ccproxy(8765)


def test_stop_ccproxy_none_is_noop():
    ccm.stop_ccproxy(None)  # must not raise


def test_stop_ccproxy_terminates_gracefully():
    proc = MagicMock()
    ccm.stop_ccproxy(proc)
    proc.terminate.assert_called_once()
    proc.wait.assert_called()


def test_ensure_ccproxy_reuses_running(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_running", lambda port: True)
    assert ccm.ensure_ccproxy(8765) is None


def test_ensure_ccproxy_starts_when_absent(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_running", lambda port: False)
    sentinel = MagicMock(name="popen_handle")
    monkeypatch.setattr(ccm, "start_ccproxy", lambda port: sentinel)
    assert ccm.ensure_ccproxy(8765) is sentinel


# ---------------------------------------------------------------------------
# Environment wiring
# ---------------------------------------------------------------------------


def test_setup_ccproxy_env_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    ccm.setup_ccproxy_env("anthropic", 8765)

    import os

    assert os.environ["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8765/claude"
    assert os.environ["ANTHROPIC_API_KEY"] == ccm.OAUTH_SENTINEL_KEY


def test_setup_ccproxy_env_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    ccm.setup_ccproxy_env("openai", 9000)

    import os

    assert os.environ["OPENAI_BASE_URL"] == "http://127.0.0.1:9000/codex/v1"
    assert os.environ["OPENAI_API_KEY"] == ccm.OAUTH_SENTINEL_KEY


def test_setup_ccproxy_env_unsupported_provider():
    with pytest.raises(ValueError, match="Unknown OAuth provider alias"):
        ccm.setup_ccproxy_env("deepseek", 8765)


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------


def test_maybe_start_ccproxy_noop_when_no_oauth():
    assert ccm.maybe_start_ccproxy() is None


def test_maybe_start_ccproxy_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: False)
    with pytest.raises(RuntimeError, match="not found"):
        ccm.maybe_start_ccproxy(anthropic_oauth=True)


def test_maybe_start_ccproxy_raises_when_not_authenticated(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(
        ccm, "check_ccproxy_auth", lambda p: (False, "Not authenticated")
    )
    with pytest.raises(RuntimeError, match="not authenticated"):
        ccm.maybe_start_ccproxy(anthropic_oauth=True)


def test_maybe_start_ccproxy_rejects_invalid_port(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    with pytest.raises(ValueError, match="Invalid ccproxy port"):
        ccm.maybe_start_ccproxy(anthropic_oauth=True, port=99999)


def test_maybe_start_ccproxy_happy_path(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "check_ccproxy_auth", lambda p: (True, "ok"))
    sentinel = MagicMock(name="proc")
    monkeypatch.setattr(ccm, "ensure_ccproxy", lambda port: sentinel)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    proc = ccm.maybe_start_ccproxy(anthropic_oauth=True, port=8765)
    assert proc is sentinel

    import os

    assert os.environ["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8765/claude"
    assert os.environ["ANTHROPIC_API_KEY"] == "ccproxy-oauth"


def test_maybe_start_ccproxy_both_providers(monkeypatch):
    monkeypatch.setattr(ccm, "is_ccproxy_available", lambda: True)
    monkeypatch.setattr(ccm, "check_ccproxy_auth", lambda p: (True, "ok"))
    monkeypatch.setattr(ccm, "ensure_ccproxy", lambda port: None)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    ccm.maybe_start_ccproxy(
        anthropic_oauth=True, openai_oauth=True, port=8765
    )

    import os

    assert "/claude" in os.environ["ANTHROPIC_BASE_URL"]
    assert "/codex/v1" in os.environ["OPENAI_BASE_URL"]

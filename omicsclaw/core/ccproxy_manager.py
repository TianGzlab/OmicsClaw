"""ccproxy lifecycle management for OAuth-based Claude / OpenAI access.

Provides helpers to detect, authenticate, start, stop, and point OmicsClaw
at a local ``ccproxy`` server. Using ccproxy lets a user with a Claude
Pro/Max subscription or an OpenAI Codex subscription run OmicsClaw without
a separate API key — OAuth tokens are managed by ccproxy itself.

ccproxy is invoked via subprocess, so the optional ``ccproxy-api`` package
is not imported at module-load time. Install it with::

    pip install 'omicsclaw[oauth]'
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# OAuth provider registry — the single source of truth
# =============================================================================
#
# Every fact about an OAuth-capable provider lives in exactly one place: an
# ``OAuthProvider`` row in ``OAUTH_PROVIDERS``. All other helpers in this
# module (and in ``provider_runtime``, ``server.py``, ``omicsclaw.py`` CLI)
# derive from this table instead of restating the same mappings.
#
# To add a third OAuth backend (e.g. Google login via ccproxy), add one row
# here and the rest of the system picks it up automatically.


@dataclass(frozen=True)
class OAuthProvider:
    """Identity + wiring for one OAuth-capable provider."""

    omics_name: str       # OmicsClaw canonical name, e.g. "anthropic"
    cli_alias: str        # user-friendly CLI label, e.g. "claude"
    ccproxy_target: str   # ccproxy's internal identifier, e.g. "claude_api"
    base_url_path: str    # path suffix under the local proxy, e.g. "/claude"
    env_base_url: str     # SDK env var for base URL, e.g. "ANTHROPIC_BASE_URL"
    env_api_key: str      # SDK env var for API key, e.g. "ANTHROPIC_API_KEY"


OAUTH_PROVIDERS: dict[str, OAuthProvider] = {
    "anthropic": OAuthProvider(
        omics_name="anthropic",
        cli_alias="claude",
        ccproxy_target="claude_api",
        base_url_path="/claude",
        env_base_url="ANTHROPIC_BASE_URL",
        env_api_key="ANTHROPIC_API_KEY",
    ),
    "openai": OAuthProvider(
        omics_name="openai",
        cli_alias="openai",
        ccproxy_target="codex",
        base_url_path="/codex/v1",
        env_base_url="OPENAI_BASE_URL",
        env_api_key="OPENAI_API_KEY",
    ),
}


# Flat alias → canonical name, covers every known spelling (omics, CLI,
# ccproxy). Built once at module load from ``OAUTH_PROVIDERS``.
_OAUTH_ALIAS_MAP: dict[str, str] = {
    alias: p.omics_name
    for p in OAUTH_PROVIDERS.values()
    for alias in (p.omics_name, p.cli_alias, p.ccproxy_target)
}


# Default ccproxy port. Deliberately NOT 8765 (the OmicsClaw app-server's
# default) to avoid a startup-time self-conflict when the app-server
# switches to OAuth mode. 11434 is reserved for Ollama, so use 11435.
DEFAULT_CCPROXY_PORT: int = 11435

OAUTH_SENTINEL_KEY: str = "ccproxy-oauth"


def normalize_oauth_provider(alias: str) -> str:
    """Any known alias → canonical OmicsClaw provider name.

    Accepts omics canonical names (``anthropic``/``openai``), CLI aliases
    (``claude``/``openai``) and ccproxy internal identifiers
    (``claude_api``/``codex``). Case-insensitive. Raises ``ValueError``
    on unknown tokens.
    """
    key = str(alias or "").strip().lower()
    canonical = _OAUTH_ALIAS_MAP.get(key)
    if canonical is None:
        raise ValueError(
            f"Unknown OAuth provider alias '{alias}'. "
            f"Supported: {sorted(_OAUTH_ALIAS_MAP.keys())}"
        )
    return canonical


def get_oauth_provider(alias: str) -> OAuthProvider:
    """Return the ``OAuthProvider`` row for any known alias."""
    return OAUTH_PROVIDERS[normalize_oauth_provider(alias)]


def oauth_base_url(alias: str, port: int) -> str:
    """Build the local ccproxy base URL for an OAuth-capable provider."""
    p = get_oauth_provider(alias)
    return f"http://127.0.0.1:{int(port)}{p.base_url_path}"


def provider_supports_oauth(name: str) -> bool:
    """Return True if ``name`` matches any alias of an OAuth-capable provider."""
    key = str(name or "").strip().lower()
    return key in _OAUTH_ALIAS_MAP


def oauth_cli_aliases() -> list[str]:
    """Sorted list of every CLI-valid OAuth provider alias.

    Used to populate argparse ``choices`` — so the CLI automatically
    accepts any new provider added to ``OAUTH_PROVIDERS``.
    """
    return sorted(_OAUTH_ALIAS_MAP.keys())


# ---------------------------------------------------------------------------
# Backwards-compat views derived from ``OAUTH_PROVIDERS``.
# Kept so callers (and tests) that imported the old names keep working.
# Prefer ``get_oauth_provider()`` / ``OAUTH_PROVIDERS`` in new code.
# ---------------------------------------------------------------------------
CCPROXY_PROVIDER_MAP: dict[str, str] = {
    p.omics_name: p.ccproxy_target for p in OAUTH_PROVIDERS.values()
}
CLI_PROVIDER_ALIASES: dict[str, str] = dict(_OAUTH_ALIAS_MAP)


def normalize_cli_provider(alias: str) -> str:
    """Deprecated alias for :func:`normalize_oauth_provider`."""
    return normalize_oauth_provider(alias)


def ccproxy_executable() -> str:
    """Return an absolute path to the ``ccproxy`` binary, or ``'ccproxy'``.

    Public wrapper over :func:`_ccproxy_exe` so that callers outside this
    module (CLI handler, FastAPI endpoints) can invoke the same
    venv/editable-install-aware resolution instead of relying on ``$PATH``.
    """
    return _ccproxy_exe() or "ccproxy"


# =============================================================================
# Binary detection
# =============================================================================


def _ccproxy_exe() -> str | None:
    """Return the path to the ccproxy binary, or None if not found.

    Checks PATH first, then the current Python environment's bin directory
    (handles venv / conda envs where newly installed binaries may not be
    visible to ``shutil.which`` immediately after ``pip install``).
    """
    found = shutil.which("ccproxy")
    if found:
        return found
    import sys as _sys

    candidate = os.path.join(os.path.dirname(_sys.executable), "ccproxy")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def is_ccproxy_available() -> bool:
    """Return True if the ``ccproxy`` CLI binary is reachable."""
    return _ccproxy_exe() is not None


def ccproxy_diagnostic_hint() -> str:
    """Describe what ``_ccproxy_exe`` checked and why it came up empty.

    Written for the user-facing error message when ``is_ccproxy_available``
    returns False despite the user believing ccproxy is installed — almost
    always a "wrong Python interpreter" mismatch (e.g. server launched
    with system Python while ccproxy lives in an unactivated ``.venv``).
    """
    import sys as _sys

    path_found = shutil.which("ccproxy")
    bin_dir = os.path.dirname(_sys.executable)
    candidate = os.path.join(bin_dir, "ccproxy")
    venv_found = (
        candidate
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK)
        else None
    )

    lines = [
        f"Python interpreter in use: {_sys.executable}",
        "Searched for `ccproxy`:",
        f"  - on $PATH (shutil.which): {path_found or '(not found)'}",
        f"  - next to interpreter ({candidate}): "
        f"{venv_found or '(not found)'}",
    ]
    if path_found is None and venv_found is None:
        # Emit a copy-paste command bound to THIS interpreter. Avoids the
        # very common "I installed it, but in a different venv" confusion:
        # {sys.executable} -m pip always installs into the site-packages
        # that the running server process can actually import from.
        lines.append(
            f"Fix (exact command for this interpreter):\n"
            f"  {_sys.executable} -m pip install ccproxy-api"
        )
        lines.append(
            "Hint: if you installed ccproxy into a venv, start the server "
            "with that venv's Python (e.g. `source .venv/bin/activate` "
            "first, or run `.venv/bin/python -m uvicorn ...`) so "
            "sys.executable points there."
        )
    return "\n".join(lines)


def _is_editable_install() -> bool:
    """True if OmicsClaw is installed in editable/development mode."""
    try:
        import importlib.metadata as _meta
        import json

        for dist in _meta.distributions():
            name = (dist.metadata.get("Name", "") or "").lower()
            if name != "omicsclaw":
                continue
            direct_url = dist.read_text("direct_url.json")
            if direct_url is not None:
                data = json.loads(direct_url)
                if data.get("dir_info", {}).get("editable", False) is True:
                    return True
    except Exception:
        pass
    return False


def oauth_install_hint() -> str:
    """Return a user-facing install command appropriate for the install mode."""
    if _is_editable_install():
        return "pip install -e '.[oauth]'"
    return "pip install 'omicsclaw[oauth]'"


# =============================================================================
# Auth status
# =============================================================================


def _summarize_auth_output(raw: str) -> str:
    """Extract key fields from ``ccproxy auth status`` output as a one-liner.

    Parses the Rich table output for Email, Subscription, and Status fields.
    Returns e.g. ``"user@example.com (plus, active)"``. Falls back to
    ``"Authenticated"`` if parsing fails.
    """
    import re as _re

    clean = _re.sub(r"\x1b\[[0-9;]*m", "", raw)

    fields: dict[str, str] = {}
    for line in clean.splitlines():
        m = _re.match(r"\s*(.+?)\s{2,}(.+)", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if key in ("Email", "Subscription", "Subscription Status"):
            fields[key.lower().replace(" ", "_")] = val

    email = fields.get("email", "")
    sub = fields.get("subscription", "")
    status = fields.get("subscription_status", "")

    if email:
        detail = ", ".join(filter(None, [sub, status]))
        return f"{email} ({detail})" if detail else email
    return "Authenticated"


def check_ccproxy_auth(provider: str = "claude_api") -> tuple[bool, str]:
    """Check whether ccproxy holds valid OAuth credentials for ``provider``.

    Args:
        provider: any known alias — OmicsClaw canonical
            (``anthropic`` / ``openai``), CLI (``claude``), or ccproxy
            internal (``claude_api`` / ``codex``).

    Returns:
        ``(is_valid, message)``. ``message`` is either a one-line summary
        of the authenticated account, or a short failure reason.
    """
    try:
        target = get_oauth_provider(provider).ccproxy_target
    except ValueError as exc:
        return False, str(exc)
    try:
        exe = _ccproxy_exe() or "ccproxy"
        result = subprocess.run(
            [exe, "auth", "status", target],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import re as _re

        raw = (result.stdout + result.stderr).strip()
        clean = _re.sub(r"\x1b\[[0-9;]*m", "", raw)

        # Filter structlog noise so we only keep real status lines.
        status_lines = [
            line
            for line in clean.splitlines()
            if line.strip()
            and not _re.match(r"\d{4}-\d{2}-\d{2}", line.strip())
            and "warning" not in line.lower()
            and "plugin" not in line.lower()
        ]
        status_msg = " ".join(status_lines).strip()

        if result.returncode != 0 or "not authenticated" in clean.lower():
            return False, status_msg or "Not authenticated"

        summary = _summarize_auth_output(result.stdout)
        return True, summary or "Authenticated"
    except FileNotFoundError:
        return False, "ccproxy not found"
    except subprocess.TimeoutExpired:
        return False, "Auth check timed out"
    except Exception as exc:
        return False, f"Auth check failed: {exc}"


# =============================================================================
# Process lifecycle
# =============================================================================


def is_ccproxy_running(port: int) -> bool:
    """Return True if a ccproxy server is already serving on ``port``."""
    import httpx

    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health/live", timeout=2.0)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        return False


def start_ccproxy(port: int) -> subprocess.Popen:
    """Start ``ccproxy serve --port PORT`` as a background process.

    Blocks until the health endpoint responds (up to 30s on first launch).

    Raises:
        RuntimeError: ccproxy exited early or never became healthy.
        FileNotFoundError: ccproxy binary is not installed.
    """
    exe = _ccproxy_exe() or "ccproxy"
    proc = subprocess.Popen(
        [exe, "serve", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"ccproxy exited immediately with code {proc.returncode}"
            )
        if is_ccproxy_running(port):
            return proc
        time.sleep(0.3)

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    raise RuntimeError("ccproxy did not become healthy within 30 seconds")


def stop_ccproxy(proc: subprocess.Popen | None) -> None:
    """Gracefully stop a ccproxy process. Safe to call with ``None``."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
    except Exception:
        pass


def ensure_ccproxy(port: int) -> subprocess.Popen | None:
    """Reuse an existing ccproxy if alive on ``port``, otherwise start one.

    Returns the ``Popen`` handle of a newly started process, or ``None`` if
    an existing instance was reused.
    """
    if is_ccproxy_running(port):
        logger.debug("ccproxy already running on port %d", port)
        return None
    return start_ccproxy(port)


# =============================================================================
# Environment wiring
# =============================================================================


def setup_ccproxy_env(provider: str, port: int) -> None:
    """Point the OpenAI/Anthropic SDK at the local ccproxy for ``provider``.

    Sets the provider's ``{_BASE_URL, _API_KEY}`` env vars to a local URL
    + the sentinel key ``ccproxy-oauth``. Always overrides existing values
    — when this is called, OAuth mode is the decision.
    """
    p = get_oauth_provider(provider)
    os.environ[p.env_base_url] = oauth_base_url(p.omics_name, port)
    os.environ[p.env_api_key] = OAUTH_SENTINEL_KEY


def clear_ccproxy_env(provider: str | None = None) -> None:
    """Remove ccproxy-injected env vars for ``provider`` (or all if None).

    Necessary when switching away from OAuth mode back to API key mode —
    otherwise the previous sentinel values would leak into
    :func:`resolve_provider` and every subsequent request would keep
    going through ccproxy.

    ONLY clears values that match our sentinel / ccproxy URL shape, so
    legitimate user-supplied env values are never touched.
    """
    if provider is None:
        targets = list(OAUTH_PROVIDERS.values())
    else:
        try:
            targets = [get_oauth_provider(provider)]
        except ValueError:
            # Unknown alias → nothing to clear; not an error.
            return

    for p in targets:
        if os.environ.get(p.env_api_key, "") == OAUTH_SENTINEL_KEY:
            os.environ.pop(p.env_api_key, None)
        existing_url = os.environ.get(p.env_base_url, "")
        if (
            existing_url.startswith("http://127.0.0.1:")
            and existing_url.endswith(p.base_url_path)
        ):
            os.environ.pop(p.env_base_url, None)


# =============================================================================
# High-level orchestration
# =============================================================================


def maybe_start_ccproxy(
    *,
    anthropic_oauth: bool = False,
    openai_oauth: bool = False,
    port: int = DEFAULT_CCPROXY_PORT,
) -> subprocess.Popen | None:
    """Conditionally start ccproxy and wire env vars based on flags.

    Raises ``RuntimeError`` if OAuth is requested but ccproxy is missing
    or unauthenticated. Returns the new ``Popen`` handle, or ``None`` if
    ccproxy was already running or no OAuth was requested.
    """
    # Map keyword flags to the provider rows they enable.
    requested: list[OAuthProvider] = []
    if anthropic_oauth:
        requested.append(OAUTH_PROVIDERS["anthropic"])
    if openai_oauth:
        requested.append(OAUTH_PROVIDERS["openai"])

    if not requested:
        return None

    if not is_ccproxy_available():
        raise RuntimeError(
            "ccproxy is required for OAuth mode but was not found. "
            f"Install it with: {oauth_install_hint()}"
        )

    if not (1 <= int(port) <= 65535):
        raise ValueError(f"Invalid ccproxy port: {port}. Must be 1..65535.")

    for p in requested:
        ok, msg = check_ccproxy_auth(p.ccproxy_target)
        if not ok:
            raise RuntimeError(
                f"ccproxy OAuth for '{p.omics_name}' not authenticated: {msg}\n"
                f"Run: omicsclaw auth login {p.cli_alias}"
            )

    proc = ensure_ccproxy(port)

    for p in requested:
        setup_ccproxy_env(p.omics_name, port)

    if proc is not None:
        logger.info("Started ccproxy on port %d", port)
    else:
        logger.info("Reusing existing ccproxy on port %d", port)
    return proc


__all__ = [
    # Identity table & helpers (prefer these in new code)
    "OAuthProvider",
    "OAUTH_PROVIDERS",
    "get_oauth_provider",
    "normalize_oauth_provider",
    "oauth_base_url",
    "oauth_cli_aliases",
    "provider_supports_oauth",
    # Constants
    "DEFAULT_CCPROXY_PORT",
    "OAUTH_SENTINEL_KEY",
    # Lifecycle & diagnostics
    "ccproxy_diagnostic_hint",
    "ccproxy_executable",
    "check_ccproxy_auth",
    "clear_ccproxy_env",
    "ensure_ccproxy",
    "is_ccproxy_available",
    "is_ccproxy_running",
    "maybe_start_ccproxy",
    "oauth_install_hint",
    "setup_ccproxy_env",
    "start_ccproxy",
    "stop_ccproxy",
    # Backwards-compat views (derived from OAUTH_PROVIDERS)
    "CCPROXY_PROVIDER_MAP",
    "CLI_PROVIDER_ALIASES",
    "normalize_cli_provider",
]

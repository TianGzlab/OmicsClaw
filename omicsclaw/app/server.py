"""
server.py -- OmicsClaw desktop/web FastAPI backend
==================================================
Wraps bot.core (OmicsClaw query engine) as a streaming HTTP API consumed by
the Electron and Next.js frontends.

Start:
    python -m omicsclaw.app.server --host 127.0.0.1 --port 8765
    oc app-server --host 127.0.0.1 --port 8765

The server expects the OmicsClaw source tree to be importable, either from a
source checkout / editable install or from a Python environment where the
package has been installed.
"""

from __future__ import annotations

import asyncio
import argparse
import importlib.util
import json
import logging
import mimetypes
import os
import platform
import signal
import sys
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
try:
    from omicsclaw.app.notebook.kernel_manager import get_kernel_manager
    from omicsclaw.app.notebook.live_session import install_live_session_support
    from omicsclaw.app.notebook.router import router as notebook_router
    _NOTEBOOK_AVAILABLE = True
except ImportError as _nb_err:
    _NOTEBOOK_AVAILABLE = False
    get_kernel_manager = None  # type: ignore[assignment]
    install_live_session_support = None  # type: ignore[assignment]
    notebook_router = None  # type: ignore[assignment]
from omicsclaw.runtime.policy_state import ToolPolicyState
from omicsclaw.version import __version__

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("omicsclaw.app_server")

DEFAULT_APP_API_HOST = "127.0.0.1"
DEFAULT_APP_API_PORT = 8765
_APP_SERVER_INSTALL_HINT = 'pip install -e ".[desktop]"'
_DEFAULT_APP_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

# ---------------------------------------------------------------------------
# Lazy references to bot.core — resolved once at startup via lifespan
# ---------------------------------------------------------------------------

_core = None  # bot.core module
_memory_client = None  # MemoryClient instance (optional)


def _get_core():
    """Return the bot.core module, raising if not initialised."""
    if _core is None:
        raise RuntimeError("OmicsClaw core not initialised. Server startup failed?")
    return _core


def _read_first_config_value(*keys: str) -> str:
    for key in keys:
        value = str(os.environ.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _app_cors_origins() -> list[str]:
    raw = str(os.getenv("OMICSCLAW_APP_CORS_ORIGINS", "") or "").strip()
    if not raw:
        return list(_DEFAULT_APP_CORS_ORIGINS)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(_DEFAULT_APP_CORS_ORIGINS)


def _coerce_kg_home(candidate: str) -> Path:
    """Accept either a project root or a concrete `.omicsclaw/knowledge` path."""
    value = str(candidate or "").strip()
    path = Path(value).expanduser()
    if path.name == "knowledge" and path.parent.name == ".omicsclaw":
        return path
    return path / ".omicsclaw" / "knowledge"


def _register_optional_kg_router(app: FastAPI) -> None:
    """Mount OmicsClaw-KG under `/kg` when the optional package is available."""
    kg_source_dir = str(os.getenv("OMICSCLAW_KG_SOURCE_DIR", "") or "").strip()
    if kg_source_dir and kg_source_dir not in sys.path:
        sys.path.insert(0, kg_source_dir)

    if importlib.util.find_spec("omicsclaw_kg") is None:
        logger.info("OmicsClaw-KG package not available; skipping embedded KG routes")
        return

    try:
        from omicsclaw_kg import config as kg_config
        from omicsclaw_kg.http_api import build_router as build_kg_router
        from omicsclaw_kg.http_api import get_kg_config as kg_workspace_dependency
    except ImportError as exc:
        logger.info("OmicsClaw-KG import failed; skipping embedded KG routes: %s", exc)
        return

    def _embedded_kg_config(
        x_omicsclaw_workspace: str | None = Header(None, alias="X-OmicsClaw-Workspace"),
        workspace: str | None = Query(None),
    ):
        explicit = str(x_omicsclaw_workspace or workspace or "").strip()
        if explicit:
            return kg_config.resolve(_coerce_kg_home(explicit))

        explicit_kg = str(os.getenv("OMICSCLAW_KG_HOME", "") or "").strip()
        if explicit_kg:
            return kg_config.resolve(explicit_kg)

        workspace_root = _resolve_scoped_memory_workspace("")
        if workspace_root:
            return kg_config.resolve(_coerce_kg_home(workspace_root))

        raise HTTPException(
            status_code=400,
            detail=(
                "missing workspace: pass X-OmicsClaw-Workspace, "
                "or configure OMICSCLAW_WORKSPACE / OMICSCLAW_KG_HOME"
            ),
        )

    app.dependency_overrides[kg_workspace_dependency] = _embedded_kg_config
    app.include_router(build_kg_router(enable_writes=True), prefix="/kg")
    logger.info("Mounted embedded OmicsClaw-KG routes under /kg")


def _resolve_backend_init_config() -> dict[str, str]:
    """Resolve backend startup config from the documented env surface.

    The local setup guide and `.env.example` use the `LLM_*` namespace.
    Older desktop integrations may still populate `OMICSCLAW_*`, so we
    support both and prefer the newer documented keys.
    """
    return {
        "provider": _read_first_config_value("LLM_PROVIDER", "OMICSCLAW_PROVIDER"),
        "api_key": _read_first_config_value("LLM_API_KEY", "OMICSCLAW_API_KEY"),
        "base_url": _read_first_config_value("LLM_BASE_URL", "OMICSCLAW_BASE_URL"),
        "model": _read_first_config_value("OMICSCLAW_MODEL"),
    }


# ---------------------------------------------------------------------------
# Provider-aware thinking support
# ---------------------------------------------------------------------------

# Providers whose APIs natively accept the ``thinking`` extra-body parameter.
# For these, ``adaptive`` maps to ``enabled`` with a sensible default budget.
_THINKING_NATIVE_PROVIDERS: frozenset[str] = frozenset({
    "deepseek",
})

# Providers where the ``thinking`` extra-body parameter is known to cause
# gateway errors (e.g. SiliconFlow rejects ``{"type": "adaptive"}``).
# For explicit ``enabled`` requests we still attempt delivery — the user
# made a deliberate choice and should see the provider error if it fails.
_THINKING_INCOMPATIBLE_PROVIDERS: frozenset[str] = frozenset({
    "siliconflow",
})

# Model-name substrings that imply thinking / reasoning support.  Used for
# gateway providers (openrouter, nvidia, volcengine, …) whose capability
# depends on which upstream model is selected rather than the gateway itself.
_THINKING_CAPABLE_MODEL_PATTERNS: tuple[str, ...] = (
    "deepseek-r1",
    "deepseek-reasoner",
    "deepseek-chat",
    "deepseek-v3",
)

_DEFAULT_THINKING_BUDGET: int = 10000


def _parse_thinking_budget(thinking: dict) -> int:
    budget = thinking.get("budgetTokens", _DEFAULT_THINKING_BUDGET)
    try:
        return int(budget)
    except (TypeError, ValueError):
        return _DEFAULT_THINKING_BUDGET


def _build_thinking_extra_body(
    thinking: Any,
    *,
    provider: str = "",
    model: str = "",
) -> dict[str, Any] | None:
    """Normalize optional thinking controls for provider-compatible requests.

    The ``adaptive`` thinking type is a frontend UX concept, not a portable
    provider contract.  This function resolves it to a concrete action based
    on the active provider and model:

    * **Native providers** (e.g. ``deepseek``): ``adaptive`` → ``enabled``
      with a default budget so that reasoning tokens are always generated.
    * **Incompatible providers** (e.g. ``siliconflow``): ``adaptive`` → omit
      the field entirely to avoid gateway errors.
    * **Gateway providers** (e.g. ``openrouter``, ``nvidia``): check whether
      the selected *model* name matches a known thinking-capable pattern; if
      so, enable thinking; otherwise omit.
    * **Unknown providers**: omit (safe default).

    Explicit ``enabled`` / ``disabled`` choices from the user are always
    honoured regardless of provider.
    """
    if not isinstance(thinking, dict):
        return None

    thinking_type = str(thinking.get("type", "") or "").strip().lower()

    # -- Explicit user choices: always honour ---------------------------------
    if thinking_type == "enabled":
        return {"type": "enabled", "budget_tokens": _parse_thinking_budget(thinking)}

    if thinking_type == "disabled":
        return {"type": "disabled"}

    # -- Adaptive: resolve per provider/model ---------------------------------
    provider_lower = provider.strip().lower()

    # 1) Known-incompatible gateways → omit
    if provider_lower in _THINKING_INCOMPATIBLE_PROVIDERS:
        return None

    # 2) Native thinking providers → enable
    if provider_lower in _THINKING_NATIVE_PROVIDERS:
        return {"type": "enabled", "budget_tokens": _parse_thinking_budget(thinking)}

    # 3) Gateway / unknown providers → check model name for thinking support
    model_lower = (model or "").strip().lower()
    if model_lower and any(
        pattern in model_lower for pattern in _THINKING_CAPABLE_MODEL_PATTERNS
    ):
        return {"type": "enabled", "budget_tokens": _parse_thinking_budget(thinking)}

    # 4) Unrecognised provider + model → safe default: omit
    return None


# ---------------------------------------------------------------------------
# Active session tracking (for abort support)
# ---------------------------------------------------------------------------

# Maps session_id -> asyncio.Task running llm_tool_loop
_active_sessions: dict[str, asyncio.Task] = {}
_pending_permission_requests: dict[str, dict[str, Any]] = {}
_session_policy_states: dict[str, ToolPolicyState] = {}
_session_permission_profiles: dict[str, str] = {}

# Cached MCP server entries for prompt injection
_mcp_entries: tuple = ()
_mcp_load_fn = None  # lazy reference to omicsclaw.interactive._mcp


# ---------------------------------------------------------------------------
# Lifespan — initialise OmicsClaw once
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _core, _memory_client

    # Resolve OmicsClaw project dir — either from env or auto-detect
    omicsclaw_dir = os.getenv("OMICSCLAW_DIR", "")
    if omicsclaw_dir:
        omicsclaw_dir = str(Path(omicsclaw_dir).resolve())
        if omicsclaw_dir not in sys.path:
            sys.path.insert(0, omicsclaw_dir)

    try:
        import bot.core as core
        _core = core
    except ImportError as exc:
        logger.error(
            "Cannot import bot.core — is OmicsClaw on sys.path or "
            "OMICSCLAW_DIR set? Error: %s", exc,
        )
        raise

    # Initialise the LLM client from environment / provider config
    startup_config = _resolve_backend_init_config()
    provider = startup_config["provider"]
    api_key = startup_config["api_key"]
    base_url = startup_config["base_url"]
    model = startup_config["model"]

    core.init(
        api_key=api_key,
        base_url=base_url or None,
        model=model,
        provider=provider,
    )
    logger.info(
        "OmicsClaw core initialised: provider=%s model=%s",
        core.LLM_PROVIDER_NAME,
        core.OMICSCLAW_MODEL,
    )
    if _NOTEBOOK_AVAILABLE:
        install_live_session_support()
    else:
        logger.info("Notebook module not available (non-fatal): %s", _nb_err)

    # Optionally expose MemoryClient for browse/search endpoints
    try:
        from omicsclaw.memory.memory_client import MemoryClient
        _memory_client = MemoryClient()
        await _memory_client.initialize()
        logger.info("MemoryClient initialised")
    except Exception as exc:
        logger.warning("MemoryClient unavailable (non-fatal): %s", exc)
        _memory_client = None

    # Optionally load MCP server support
    global _mcp_load_fn
    try:
        from omicsclaw.interactive._mcp import (
            load_active_mcp_server_entries_for_prompt,
            list_mcp_servers,
            add_mcp_server,
            remove_mcp_server,
        )
        _mcp_load_fn = load_active_mcp_server_entries_for_prompt
        logger.info("MCP support loaded (%d servers configured)", len(list_mcp_servers()))
    except ImportError as exc:
        logger.info("MCP module not available (non-fatal): %s", exc)
        _mcp_load_fn = None

    yield

    # Shutdown: stop bridge if running
    global _channel_manager, _bridge_task
    if _channel_manager is not None:
        try:
            if _bridge_task and not _bridge_task.done():
                _bridge_task.cancel()
                try:
                    await _bridge_task
                except asyncio.CancelledError:
                    pass
            await _channel_manager.stop_all()
        except Exception as exc:
            logger.warning("Error stopping bridge during shutdown: %s", exc)
        _channel_manager = None
        _bridge_task = None

    # Shutdown: cancel any active sessions
    for task in _active_sessions.values():
        task.cancel()
    _active_sessions.clear()

    if _NOTEBOOK_AVAILABLE:
        try:
            await get_kernel_manager().shutdown_all()
        except Exception as exc:
            logger.warning("Notebook kernel shutdown failed during app shutdown: %s", exc)

    if _memory_client:
        await _memory_client.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OmicsClaw-App Backend",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_app_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount autoagent optimization router
try:
    from omicsclaw.autoagent.api import router as optimize_router
    app.include_router(optimize_router)
except ImportError:
    pass  # autoagent module not available

_register_optional_kg_router(app)

if _NOTEBOOK_AVAILABLE:
    app.include_router(notebook_router, prefix="/notebook", tags=["notebook"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    """Optional per-request provider override."""
    provider: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class ChatRequest(BaseModel):
    """POST /chat/stream body."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    workspace: str = ""
    pipeline_workspace: str = ""
    output_style: str = ""
    provider_config: Optional[ProviderConfig] = None
    # Runtime controls forwarded from desktop-app frontend
    model: str = ""
    mode: str = ""
    provider_id: str = ""
    effort: str = ""
    thinking: Optional[dict] = None
    context_1m: bool = False
    permission_profile: str = "default"
    files: Optional[list[dict]] = None
    system_prompt_append: str = ""


class AbortRequest(BaseModel):
    """POST /chat/abort body."""
    session_id: str


class PermissionResponseRequest(BaseModel):
    """POST /chat/permission body."""
    permissionRequestId: str
    decision: dict[str, Any]


class SessionPermissionProfileRequest(BaseModel):
    """POST /chat/session-permission-profile body."""
    session_id: str
    permission_profile: str = "default"


class SkillInstallRequest(BaseModel):
    """POST /skills/install body."""
    source: str


class SkillUninstallRequest(BaseModel):
    """POST /skills/uninstall body."""
    name: str


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_line(event_type: str, data: Any) -> str:
    """Format a single SSE data frame."""
    if isinstance(data, (dict, list)):
        payload = json.dumps(data, ensure_ascii=False, default=str)
    else:
        payload = str(data)
    return f"data: {json.dumps({'type': event_type, 'data': payload}, ensure_ascii=False, default=str)}\n\n"


def _sse_error(message: str) -> str:
    return _sse_line("error", message)


def _sse_done() -> str:
    return _sse_line("done", "")


def _omicsclaw_project_dir() -> Path:
    core = _get_core()
    omicsclaw_dir = getattr(core, "OMICSCLAW_DIR", "")
    if omicsclaw_dir:
        return Path(omicsclaw_dir).resolve()

    env_value = os.getenv("OMICSCLAW_DIR", "")
    if env_value:
        return Path(env_value).resolve()

    raise RuntimeError("OMICSCLAW_DIR is not available")


def _serialize_skill_command_statuses(statuses: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "level": str(getattr(status, "level", "info") or "info"),
            "text": str(getattr(status, "text", "") or ""),
        }
        for status in statuses
    ]


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _runtime_health_payload(core: Any) -> dict[str, Any]:
    skill_python = (
        core.get_skill_runner_python()
        if hasattr(core, "get_skill_runner_python")
        else str(getattr(core, "PYTHON", "") or "").strip() or sys.executable
    )
    omicsclaw_dir = ""
    try:
        omicsclaw_dir = str(_omicsclaw_project_dir())
    except Exception:
        omicsclaw_dir = ""

    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "skill_python_executable": skill_python,
        "omicsclaw_dir": omicsclaw_dir,
        "dependencies": {
            "cellcharter": _module_available("cellcharter"),
            "squidpy": _module_available("squidpy"),
        },
    }


def _resolve_scoped_memory_workspace(explicit_workspace: str = "") -> str:
    workspace = str(explicit_workspace or "").strip()
    if workspace:
        return workspace

    workspace = str(os.getenv("OMICSCLAW_WORKSPACE", "") or "").strip()
    if workspace:
        return workspace

    try:
        core = _get_core()
        return str(getattr(core, "DATA_DIR", "") or "").strip()
    except Exception:
        return ""


def _permission_profile_to_policy_state(
    session_id: str,
    permission_profile: str,
) -> ToolPolicyState:
    persisted = _session_policy_states.get(session_id, ToolPolicyState(surface="app"))
    profile = str(permission_profile or "default").strip().lower()
    if profile == "full_access":
        return ToolPolicyState(
            surface="app",
            trusted=True,
            auto_approve_ask=True,
            approved_tool_names=persisted.approved_tool_names,
        )
    return ToolPolicyState(
        surface="app",
        approved_tool_names=persisted.approved_tool_names,
    )


def _normalize_permission_profile(permission_profile: str) -> str:
    profile = str(permission_profile or "default").strip().lower()
    return "full_access" if profile == "full_access" else "default"


def _effective_permission_profile(session_id: str, fallback: str = "default") -> str:
    return _session_permission_profiles.get(
        session_id,
        _normalize_permission_profile(fallback),
    )


def _set_session_permission_profile(
    session_id: str,
    permission_profile: str,
) -> ToolPolicyState:
    normalized = _normalize_permission_profile(permission_profile)
    _session_permission_profiles[session_id] = normalized
    next_state = _permission_profile_to_policy_state(session_id, normalized)
    _session_policy_states[session_id] = next_state
    return next_state


def _with_approved_tools(
    state: ToolPolicyState,
    tool_names: set[str],
) -> ToolPolicyState:
    if not tool_names:
        return state
    return ToolPolicyState(
        surface=state.surface,
        trusted=state.trusted,
        background=state.background,
        auto_approve_ask=state.auto_approve_ask,
        approved_tool_names=state.approved_tool_names | frozenset(tool_names),
    )


def _tool_names_from_permission_suggestions(
    suggestions: list[dict[str, Any]] | None,
) -> set[str]:
    tool_names: set[str] = set()
    for suggestion in suggestions or []:
        if not isinstance(suggestion, dict):
            continue
        for rule in suggestion.get("rules", []) or []:
            if not isinstance(rule, dict):
                continue
            tool_name = str(rule.get("toolName", "") or "").strip()
            if tool_name:
                tool_names.add(tool_name)
    return tool_names


def _build_token_usage(response_usage: Any, usage_totals: dict[str, float]) -> dict[str, Any]:
    prompt_tokens = int(getattr(response_usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(response_usage, "completion_tokens", 0) or 0)

    # Extract cache tokens from all known provider formats:
    #   OpenAI:    prompt_tokens_details.cached_tokens / .cache_creation_tokens
    #   DeepSeek:  prompt_cache_hit_tokens (top-level)
    #   Anthropic: cache_read_input_tokens / cache_creation_input_tokens (top-level)
    prompt_details = getattr(response_usage, "prompt_tokens_details", None)
    cache_read_tokens = int(getattr(prompt_details, "cached_tokens", 0) or 0)
    cache_creation_tokens = int(
        getattr(prompt_details, "cache_creation_tokens", 0) or 0
    )
    # DeepSeek: prompt_cache_hit_tokens
    if not cache_read_tokens:
        cache_read_tokens = int(
            getattr(response_usage, "prompt_cache_hit_tokens", 0) or 0
        )
    # Anthropic: cache_read_input_tokens / cache_creation_input_tokens
    if not cache_read_tokens:
        cache_read_tokens = int(
            getattr(response_usage, "cache_read_input_tokens", 0) or 0
        )
    if not cache_creation_tokens:
        cache_creation_tokens = int(
            getattr(response_usage, "cache_creation_input_tokens", 0) or 0
        )

    usage_totals["input_tokens"] += prompt_tokens
    usage_totals["output_tokens"] += completion_tokens
    usage_totals["cache_read_input_tokens"] += cache_read_tokens
    usage_totals["cache_creation_input_tokens"] += cache_creation_tokens

    core = _get_core()
    cost_usd = 0.0
    get_prices = getattr(core, "_get_token_price", None)
    if callable(get_prices):
        input_price, output_price = get_prices(core.OMICSCLAW_MODEL)
        cost_usd = (
            usage_totals["input_tokens"] / 1_000_000 * float(input_price or 0.0)
            + usage_totals["output_tokens"] / 1_000_000 * float(output_price or 0.0)
        )

    usage_payload: dict[str, Any] = {
        "input_tokens": int(usage_totals["input_tokens"]),
        "output_tokens": int(usage_totals["output_tokens"]),
    }
    if usage_totals["cache_read_input_tokens"] > 0:
        usage_payload["cache_read_input_tokens"] = int(
            usage_totals["cache_read_input_tokens"]
        )
    if usage_totals["cache_creation_input_tokens"] > 0:
        usage_payload["cache_creation_input_tokens"] = int(
            usage_totals["cache_creation_input_tokens"]
        )
    if cost_usd > 0:
        usage_payload["cost_usd"] = round(cost_usd, 6)
    return usage_payload


def _extract_blocked_path(arguments: dict[str, Any]) -> str:
    for key in (
        "path",
        "file_path",
        "destination",
        "source",
        "workspace",
        "pipeline_workspace",
    ):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Multimodal content helpers
# ---------------------------------------------------------------------------

def _build_multimodal_content(text: str, files: list[dict]) -> str | list[dict]:
    """Convert text + FileAttachment list to OpenAI multimodal content.

    Returns a plain ``str`` when no images are present (text files are
    inlined as context), or a ``list[dict]`` with ``image_url`` blocks
    when images are attached.
    """
    import base64 as _b64

    image_parts: list[dict] = []
    text_addendum: list[str] = []

    for f in files:
        mime = f.get("type", "application/octet-stream")
        name = f.get("name", "file")
        data = f.get("data", "")

        if mime.startswith("image/"):
            image_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"},
            })
        else:
            try:
                decoded = _b64.b64decode(data).decode("utf-8", errors="replace")
                text_addendum.append(f"### File: {name}\n```\n{decoded[:50000]}\n```")
            except Exception:
                text_addendum.append(f"### File: {name}\n(binary, {f.get('size', 0)} bytes)")

    full_text = text
    if text_addendum:
        full_text = text + "\n\n" + "\n\n".join(text_addendum)

    if image_parts:
        return [{"type": "text", "text": full_text}] + image_parts
    return full_text


# ---------------------------------------------------------------------------
# POST /chat/stream — SSE streaming chat
# ---------------------------------------------------------------------------

async def _handle_slash_command(command: str, arg: str, session_id: str) -> str | None:
    """
    Handle slash commands locally without going through the LLM.
    Returns the text response, or None if the command is not handled
    (falls through to llm_tool_loop).
    """
    core = _get_core()

    if command == "/skills":
        registry = core._skill_registry()
        lines = []
        domain_filter = arg.strip().lower() if arg.strip() else None

        # Group by domain
        domain_skills: dict[str, list[str]] = {}
        for alias, info in registry.skills.items():
            if alias != info.get("alias", alias):
                continue
            domain = info.get("domain", "other")
            if domain_filter and domain_filter not in domain.lower():
                continue
            domain_skills.setdefault(domain, []).append(
                f"  - {alias}: {info.get('description', '')[:80]}"
            )

        if not domain_skills:
            return f"No skills found{' for domain: ' + arg.strip() if arg.strip() else ''}."

        for domain in sorted(domain_skills.keys()):
            lines.append(f"\n**{domain}** ({len(domain_skills[domain])} skills)")
            lines.extend(sorted(domain_skills[domain]))

        total = sum(len(v) for v in domain_skills.values())
        header = f"## OmicsClaw Skills ({total} total)"
        if domain_filter:
            header += f" — filtered: {arg.strip()}"
        return header + "\n" + "\n".join(lines)

    elif command == "/usage":
        usage = core.get_usage_snapshot()
        lines = ["## Usage Statistics"]
        for k, v in usage.items():
            lines.append(f"- **{k}**: {v}")
        return "\n".join(lines)

    elif command == "/context":
        return (
            f"## Context Info\n"
            f"- Model: {core.OMICSCLAW_MODEL}\n"
            f"- Provider: {core.LLM_PROVIDER_NAME}\n"
            f"- Max history: {core.MAX_HISTORY}\n"
            f"- Max tool iterations: {core.MAX_TOOL_ITERATIONS}\n"
            f"- Data dir: {core.DATA_DIR}\n"
            f"- Output dir: {core.OUTPUT_DIR}"
        )

    elif command == "/doctor":
        import platform as plat
        lines = [
            "## Environment Diagnostics",
            f"- Python: {plat.python_version()}",
            f"- Platform: {plat.platform()}",
            f"- Provider: {core.LLM_PROVIDER_NAME}",
            f"- Model: {core.OMICSCLAW_MODEL}",
            f"- Skills: {core._primary_skill_count()}",
            f"- Tools: {len(core.get_tool_executors())}",
            f"- Memory: {'enabled' if _memory_client else 'disabled'}",
            f"- MCP: {'loaded' if _mcp_load_fn else 'not available'}",
        ]
        return "\n".join(lines)

    elif command == "/help":
        try:
            from omicsclaw.interactive._constants import SLASH_COMMANDS
            lines = ["## Available Commands\n"]
            for cmd, desc in SLASH_COMMANDS:
                lines.append(f"- `{cmd}` — {desc}")
            return "\n".join(lines)
        except ImportError:
            return "Help not available (interactive module not found)."

    elif command == "/mcp":
        if _mcp_load_fn is None:
            return "MCP module not available."
        try:
            from omicsclaw.interactive._mcp import list_mcp_servers
            servers = list_mcp_servers()
            if not servers:
                return "No MCP servers configured."
            lines = ["## MCP Servers\n"]
            for s in servers:
                status = "active" if s.get("active") else "configured"
                lines.append(f"- **{s['name']}** ({s.get('transport', 'stdio')}) — {status}")
            return "\n".join(lines)
        except Exception as exc:
            return f"MCP error: {exc}"

    elif command == "/style":
        if arg.strip():
            return f"Style switching via desktop app is not yet supported. Use the CLI: `omicsclaw` → `/style set {arg.strip()}`"
        return "Use `/style list` or `/style set <name>` in the OmicsClaw CLI."

    elif command == "/config":
        settings = {
            "provider": core.LLM_PROVIDER_NAME,
            "model": core.OMICSCLAW_MODEL,
            "max_history": core.MAX_HISTORY,
            "data_dir": str(core.DATA_DIR),
            "output_dir": str(core.OUTPUT_DIR),
        }
        lines = ["## Configuration\n"]
        for k, v in settings.items():
            lines.append(f"- **{k}**: `{v}`")
        return "\n".join(lines)

    # Not handled locally → pass through to LLM
    return None


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Run llm_tool_loop and stream events via SSE.

    Events emitted:
      - {"type": "status",             "data": "{...}"} — init/status metadata
      - {"type": "mode_changed",       "data": "..."}   — current SDK mode
      - {"type": "text",               "data": "..."}   — streamed LLM text chunk
      - {"type": "tool_use",           "data": "{...}"} — tool call start
      - {"type": "tool_output",        "data": "..."}   — tool progress/output
      - {"type": "tool_result",        "data": "{...}"} — tool result
      - {"type": "tool_timeout",       "data": "{...}"} — tool timed out
      - {"type": "permission_request", "data": "{...}"} — approval required
      - {"type": "task_update",        "data": "{...}"} — task/todo sync
      - {"type": "result",             "data": "{...}"} — final usage summary
      - {"type": "keep_alive",         "data": ""}      — idle heartbeat
      - {"type": "done",               "data": ""}      — stream finished
      - {"type": "error",              "data": "..."}   — error
    """
    core = _get_core()
    session_id = req.session_id

    # If a provider config override is supplied, re-init the core.
    # NOTE: In a production multi-tenant setup you would scope this per-request
    # with a separate AsyncOpenAI client. For the desktop-app (single user) this
    # is acceptable.
    if req.provider_config and req.provider_config.provider:
        pc = req.provider_config
        core.init(
            api_key=pc.api_key,
            base_url=pc.base_url or None,
            model=pc.model,
            provider=pc.provider,
        )
    elif req.provider_id and req.provider_id.lower() != core.LLM_PROVIDER_NAME.lower():
        # Frontend selected a different provider — switch to it.
        # API key is auto-resolved from environment variables by core.init().
        try:
            core.init(provider=req.provider_id, model=req.model or "")
            # Persist to .env so the choice survives a restart
            env_path = _get_omicsclaw_env_path()
            if env_path:
                updates: dict[str, str] = {"LLM_PROVIDER": req.provider_id}
                if req.model:
                    updates["OMICSCLAW_MODEL"] = req.model
                _update_env_file(env_path, updates)
            logger.info(
                "Auto-switched provider=%s model=%s (from chat request)",
                core.LLM_PROVIDER_NAME, core.OMICSCLAW_MODEL,
            )
        except Exception as exc:
            logger.warning("Provider switch to %s failed: %s", req.provider_id, exc)

    # --- Build per-request runtime overrides from frontend controls ---
    model_override = req.model or ""
    extra_api_params: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}

    if req.effort and req.effort in ("low", "medium", "high", "max"):
        extra_body["reasoning_effort"] = req.effort

    effective_model = model_override or core.OMICSCLAW_MODEL
    normalized_thinking = _build_thinking_extra_body(
        req.thinking,
        provider=core.LLM_PROVIDER_NAME,
        model=effective_model,
    )
    if normalized_thinking:
        extra_body["thinking"] = normalized_thinking

    if extra_body:
        extra_api_params["extra_body"] = extra_body

    max_tokens_override = 16384 if req.context_1m else 0

    # Convert file attachments to multimodal content
    user_content: str | list = req.content
    if req.files:
        user_content = _build_multimodal_content(req.content, req.files)

    # asyncio.Queue bridges callbacks (invoked inside llm_tool_loop's task)
    # to the SSE generator running in the response.
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    streamed_text = ""
    streamed_text_chunks = 0
    usage_totals: dict[str, float] = {
        "input_tokens": 0.0,
        "output_tokens": 0.0,
        "cache_read_input_tokens": 0.0,
        "cache_creation_input_tokens": 0.0,
    }
    usage_payload: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
    current_policy_state = _set_session_permission_profile(
        session_id,
        req.permission_profile,
    )

    # Sentinel to signal end-of-stream
    _DONE = None
    # Keep-alive interval (seconds)
    _KEEPALIVE_INTERVAL = 25

    # ---- Callbacks pushed to queue ----

    tool_call_ids_by_name: dict[str, deque[str]] = {}
    tool_progress_tasks: dict[str, asyncio.Task] = {}
    permission_request_ids: set[str] = set()

    slash_commands: list[dict[str, str]] = []
    try:
        from omicsclaw.interactive._constants import SLASH_COMMANDS

        slash_commands = [
            {"command": str(command), "description": str(description)}
            for command, description in SLASH_COMMANDS
        ]
    except Exception:
        slash_commands = []

    mcp_servers_meta: list[dict[str, Any]] = []
    if _mcp_load_fn is not None:
        try:
            from omicsclaw.interactive._mcp import list_mcp_servers

            mcp_servers_meta = list_mcp_servers()
        except Exception:
            mcp_servers_meta = []

    skill_names = sorted(
        alias
        for alias, info in core._skill_registry().skills.items()
        if alias == info.get("alias", alias)
    )
    effective_mode = req.mode or "ask"
    status_payload = {
        "session_id": session_id,
        "requested_model": model_override or core.OMICSCLAW_MODEL,
        "model": model_override or core.OMICSCLAW_MODEL,
        "provider": core.LLM_PROVIDER_NAME,
        "effort": req.effort or "",
        "thinking": req.thinking if req.thinking else None,
        "context_1m": req.context_1m,
        "max_tokens": max_tokens_override if max_tokens_override > 0 else 8192,
        "mode": effective_mode,
        "permission_profile": req.permission_profile or "default",
        "tools": sorted(core.get_tool_executors().keys()),
        "slash_commands": slash_commands,
        "skills": skill_names,
        "mcp_servers": mcp_servers_meta,
        "output_style": req.output_style or "",
    }

    async def _queue_event(event_type: str, data: Any) -> None:
        await queue.put({"type": event_type, "data": data})

    def _current_tool_use_id(tool_name: str) -> str:
        pending_ids = tool_call_ids_by_name.get(tool_name)
        if pending_ids:
            return pending_ids[0]
        return ""

    def _finish_tool_progress(tool_use_id: str) -> None:
        task = tool_progress_tasks.pop(tool_use_id, None)
        if task is not None:
            task.cancel()

    async def _emit_tool_progress(tool_name: str, tool_use_id: str) -> None:
        started_at = time.monotonic()
        try:
            while True:
                elapsed = max(1, int(time.monotonic() - started_at))
                await _queue_event(
                    "tool_output",
                    json.dumps(
                        {
                            "_progress": True,
                            "tool_name": tool_name,
                            "elapsed_time_seconds": elapsed,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    def _extract_media_from_display_output(
        tool_name: str,
        display_output: Any,
    ) -> list[dict[str, Any]]:
        media: list[dict[str, Any]] = []
        try:
            if isinstance(display_output, dict):
                parsed = display_output
            elif isinstance(display_output, str):
                try:
                    parsed = json.loads(display_output)
                except (json.JSONDecodeError, ValueError):
                    parsed = {}
            else:
                parsed = {}

            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

            def _extract_paths(obj: Any, depth: int = 0) -> None:
                if depth > 3:
                    return
                if isinstance(obj, str) and "/" in obj:
                    ext = os.path.splitext(obj)[1].lower()
                    if ext in IMAGE_EXTS and os.path.isfile(obj):
                        media.append(
                            {
                                "type": "image",
                                "mimeType": f"image/{ext.lstrip('.')}".replace(
                                    "jpg", "jpeg"
                                ),
                                "localPath": obj,
                            }
                        )
                    elif (
                        ext in {".csv", ".tsv", ".md", ".json", ".html", ".ipynb"}
                        and os.path.isfile(obj)
                    ):
                        media.append(
                            {
                                "type": "file",
                                "mimeType": "application/octet-stream",
                                "localPath": obj,
                            }
                        )
                elif isinstance(obj, dict):
                    for value in obj.values():
                        _extract_paths(value, depth + 1)
                elif isinstance(obj, (list, tuple)):
                    for item in obj:
                        _extract_paths(item, depth + 1)

            _extract_paths(parsed)

            for key in ("image_path", "plot_path", "figure_path", "output_path"):
                path = parsed.get(key)
                if isinstance(path, str) and os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if ext in IMAGE_EXTS and not any(
                        item["localPath"] == path for item in media
                    ):
                        media.append(
                            {
                                "type": "image",
                                "mimeType": f"image/{ext.lstrip('.')}".replace(
                                    "jpg", "jpeg"
                                ),
                                "localPath": path,
                            }
                        )

            for key in ("output_dir", "output_directory"):
                out_dir = parsed.get(key)
                if isinstance(out_dir, str) and os.path.isdir(out_dir):
                    fig_dir = os.path.join(out_dir, "figures")
                    if os.path.isdir(fig_dir):
                        for fname in sorted(os.listdir(fig_dir)):
                            fpath = os.path.join(fig_dir, fname)
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in IMAGE_EXTS and not any(
                                item["localPath"] == fpath for item in media
                            ):
                                media.append(
                                    {
                                        "type": "image",
                                        "mimeType": f"image/{ext.lstrip('.')}".replace(
                                            "jpg", "jpeg"
                                        ),
                                        "localPath": fpath,
                                    }
                                )

            if not media:
                output_dir = str(core.OUTPUT_DIR)
                if os.path.isdir(output_dir):
                    candidates: list[tuple[float, str]] = []
                    for entry in os.scandir(output_dir):
                        if not entry.is_dir():
                            continue
                        if entry.name.startswith(tool_name.replace("-", "_").split("_")[0]):
                            candidates.append((entry.stat().st_mtime, entry.path))
                        elif tool_name.replace("-", "_") in entry.name:
                            candidates.append((entry.stat().st_mtime, entry.path))
                        elif tool_name in entry.name:
                            candidates.append((entry.stat().st_mtime, entry.path))
                    if candidates:
                        candidates.sort(reverse=True)
                        latest_dir = candidates[0][1]
                        fig_dir = os.path.join(latest_dir, "figures")
                        if os.path.isdir(fig_dir):
                            for fname in sorted(os.listdir(fig_dir)):
                                fpath = os.path.join(fig_dir, fname)
                                ext = os.path.splitext(fname)[1].lower()
                                if ext in IMAGE_EXTS and os.path.isfile(fpath):
                                    media.append(
                                        {
                                            "type": "image",
                                            "mimeType": f"image/{ext.lstrip('.')}".replace(
                                                "jpg", "jpeg"
                                            ),
                                            "localPath": fpath,
                                        }
                                    )
                        for fname in ("report.md", "result.json", "README.md"):
                            fpath = os.path.join(latest_dir, fname)
                            if os.path.isfile(fpath):
                                media.append(
                                    {
                                        "type": "file",
                                        "mimeType": (
                                            "text/markdown"
                                            if fname.endswith(".md")
                                            else "application/json"
                                        ),
                                        "localPath": fpath,
                                    }
                                )
        except Exception:
            return media
        return media

    async def on_stream_content(chunk: str):
        nonlocal streamed_text, streamed_text_chunks
        streamed_text += chunk
        if chunk:
            streamed_text_chunks += 1
        await _queue_event("text", chunk)

    async def on_stream_reasoning(chunk: str):
        if chunk:
            await _queue_event("thinking", chunk)

    async def on_tool_call(tool_name: str, arguments: dict):
        tool_use_id = f"call_{tool_name}_{uuid.uuid4().hex[:8]}"
        tool_call_ids_by_name.setdefault(tool_name, deque()).append(tool_use_id)
        await _queue_event(
            "tool_use",
            json.dumps(
                {
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": arguments,
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        await _queue_event("tool_output", f"Starting {tool_name}")
        tool_progress_tasks[tool_use_id] = asyncio.create_task(
            _emit_tool_progress(tool_name, tool_use_id)
        )

    def _tool_timeout_seconds(metadata: Any) -> int | None:
        if not isinstance(metadata, dict) or not metadata.get("timed_out"):
            return None
        raw_seconds = metadata.get("elapsed_seconds")
        if not isinstance(raw_seconds, (int, float)):
            return None
        return max(1, round(raw_seconds))

    def _tool_result_is_error(metadata: Any) -> bool:
        return isinstance(metadata, dict) and bool(metadata.get("is_error"))

    async def on_tool_result(tool_name: str, display_output: Any, metadata: Any = None):
        content_str = str(display_output) if display_output is not None else ""
        pending_ids = tool_call_ids_by_name.get(tool_name)
        tool_use_id = pending_ids.popleft() if pending_ids else ""
        _finish_tool_progress(tool_use_id)
        timeout_seconds = _tool_timeout_seconds(metadata)
        if timeout_seconds is not None:
            await _queue_event("tool_output", f"{tool_name} timed out after {timeout_seconds}s")
        else:
            await _queue_event("tool_output", f"Completed {tool_name}")

        media = _extract_media_from_display_output(tool_name, display_output)

        result_data: dict[str, Any] = {
            "tool_use_id": tool_use_id,
            "tool_name": tool_name,
            "content": content_str,
        }
        if _tool_result_is_error(metadata):
            result_data["is_error"] = True
        if media:
            result_data["media"] = media

        await _queue_event(
            "tool_result",
            json.dumps(result_data, ensure_ascii=False, default=str),
        )
        if timeout_seconds is not None:
            await _queue_event(
                "tool_timeout",
                json.dumps(
                    {
                        "tool_name": tool_name,
                        "elapsed_seconds": timeout_seconds,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        if tool_name in {"task_create", "task_update", "todo_write"}:
            await _queue_event(
                "task_update",
                json.dumps(
                    {"session_id": session_id, "tool_name": tool_name},
                    ensure_ascii=False,
                    default=str,
                ),
            )

    def usage_accumulator(response_usage: Any) -> dict[str, int]:
        nonlocal usage_payload
        base_accumulator = getattr(core, "_accumulate_usage", None)
        if callable(base_accumulator):
            delta = base_accumulator(response_usage) or {}
        else:
            delta = {
                "prompt_tokens": int(getattr(response_usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(
                    getattr(response_usage, "completion_tokens", 0) or 0
                ),
                "total_tokens": int(getattr(response_usage, "total_tokens", 0) or 0),
            }
        usage_payload = _build_token_usage(response_usage, usage_totals)
        return delta

    async def request_tool_approval(request: Any, execution_result: Any) -> dict[str, Any]:
        nonlocal current_policy_state

        tool_use_id = _current_tool_use_id(request.name)
        if tool_use_id:
            _finish_tool_progress(tool_use_id)

        current_policy_state = _permission_profile_to_policy_state(
            session_id,
            _effective_permission_profile(session_id, req.permission_profile),
        )
        _session_policy_states[session_id] = current_policy_state

        if current_policy_state.trusted:
            if tool_use_id:
                tool_progress_tasks[tool_use_id] = asyncio.create_task(
                    _emit_tool_progress(request.name, tool_use_id)
                )
            return {
                "behavior": "allow",
                "updated_input": None,
                "policy_state": current_policy_state.to_dict(),
                "persist": False,
            }

        permission_request_id = f"perm_{uuid.uuid4().hex[:10]}"
        suggestions = [
            {
                "type": "tool_permission",
                "behavior": "allow",
                "rules": [
                    {
                        "toolName": request.name,
                        "ruleContent": f"Allow `{request.name}` for this session",
                    }
                ],
            }
        ]
        payload = {
            "permissionRequestId": permission_request_id,
            "toolName": request.name,
            "toolInput": dict(request.arguments or {}),
            "suggestions": suggestions,
            "decisionReason": str(
                getattr(execution_result.policy_decision, "reason", "") or ""
            ),
            "blockedPath": _extract_blocked_path(dict(request.arguments or {})),
            "toolUseId": tool_use_id,
            "description": str(
                getattr(request.spec, "description", "") or ""
            ).strip(),
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        permission_request_ids.add(permission_request_id)
        _pending_permission_requests[permission_request_id] = {
            "future": future,
            "session_id": session_id,
            "tool_name": request.name,
            "tool_use_id": tool_use_id,
        }

        await _queue_event(
            "permission_request",
            json.dumps(payload, ensure_ascii=False, default=str),
        )
        await _queue_event("tool_output", f"{request.name} is waiting for approval")

        try:
            decision = await future
        finally:
            permission_request_ids.discard(permission_request_id)
            _pending_permission_requests.pop(permission_request_id, None)

        current_policy_state = _permission_profile_to_policy_state(
            session_id,
            _effective_permission_profile(session_id, req.permission_profile),
        )
        _session_policy_states[session_id] = current_policy_state

        behavior = str(decision.get("behavior", "deny") or "deny").strip().lower()
        updated_input = decision.get("updated_input")
        if not isinstance(updated_input, dict):
            updated_input = None

        updated_tool_names = _tool_names_from_permission_suggestions(
            decision.get("updated_permissions")
            if isinstance(decision.get("updated_permissions"), list)
            else None
        )
        policy_state = current_policy_state
        if updated_tool_names:
            current_policy_state = _with_approved_tools(
                current_policy_state,
                updated_tool_names,
            )
            _session_policy_states[session_id] = current_policy_state
            policy_state = current_policy_state
        elif behavior == "allow":
            policy_state = _with_approved_tools(current_policy_state, {request.name})

        if behavior == "allow":
            await _queue_event("tool_output", f"Permission granted for {request.name}")
            if tool_use_id:
                tool_progress_tasks[tool_use_id] = asyncio.create_task(
                    _emit_tool_progress(request.name, tool_use_id)
                )
            return {
                "behavior": "allow",
                "updated_input": updated_input,
                "policy_state": policy_state.to_dict(),
                "persist": bool(updated_tool_names),
            }

        deny_message = str(
            decision.get("message") or f"Permission denied for `{request.name}`."
        )
        await _queue_event("tool_output", f"Permission denied for {request.name}")
        return {
            "behavior": "deny",
            "message": deny_message,
        }

    # ---- Background task running the tool loop ----

    async def _run_loop():
        try:
            # Load active MCP servers for this session
            mcp_servers = ()
            if _mcp_load_fn is not None:
                try:
                    mcp_servers = await _mcp_load_fn()
                except Exception as mcp_exc:
                    logger.warning("Failed to load MCP servers: %s", mcp_exc)

            result = await core.llm_tool_loop(
                chat_id=session_id,
                user_content=user_content,
                user_id="desktop_user",
                workspace=req.workspace,
                pipeline_workspace=req.pipeline_workspace,
                output_style=req.output_style,
                platform="app",
                mcp_servers=mcp_servers,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
                on_stream_content=on_stream_content,
                on_stream_reasoning=on_stream_reasoning,
                usage_accumulator=usage_accumulator,
                request_tool_approval=request_tool_approval,
                policy_state=current_policy_state.to_dict(),
                # Per-request runtime overrides
                model_override=model_override,
                extra_api_params=extra_api_params if extra_api_params else None,
                max_tokens_override=max_tokens_override,
                system_prompt_append=req.system_prompt_append,
                mode=req.mode,
            )
            # If the result contains text that was NOT streamed (non-streaming
            # path, or slash-command response), emit only the missing suffix.
            # queue.qsize() is not reliable here because the SSE consumer may
            # already have drained previously streamed chunks by the time the
            # tool loop returns.
            if result:
                if streamed_text_chunks == 0:
                    await queue.put({"type": "text", "data": result})
                elif isinstance(result, str) and result.startswith(streamed_text):
                    suffix = result[len(streamed_text):]
                    if suffix:
                        await queue.put({"type": "text", "data": suffix})
                elif result != streamed_text:
                    logger.debug(
                        "Session %s returned final text differing from streamed content; "
                        "skipping replay to avoid duplicate assistant output",
                        session_id,
                    )
            await _queue_event(
                "result",
                json.dumps(
                    {
                        "usage": usage_payload,
                        "model": model_override or core.OMICSCLAW_MODEL,
                        "provider": core.LLM_PROVIDER_NAME,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        except asyncio.CancelledError:
            await _queue_event("error", "Session aborted")
        except Exception as exc:
            logger.exception("llm_tool_loop error for session %s", session_id)
            await _queue_event("error", str(exc))
        finally:
            for permission_request_id in list(permission_request_ids):
                pending = _pending_permission_requests.pop(permission_request_id, None)
                if pending is None:
                    continue
                future = pending.get("future")
                if future is not None and not future.done():
                    future.cancel()
                permission_request_ids.discard(permission_request_id)
            for task in list(tool_progress_tasks.values()):
                task.cancel()
            tool_progress_tasks.clear()
            await queue.put(_DONE)
            _active_sessions.pop(session_id, None)

    # ---- SSE generator ----

    async def event_generator():
        yield _sse_line("status", status_payload)
        yield _sse_line("mode_changed", effective_mode)

        task = asyncio.create_task(_run_loop())
        _active_sessions[session_id] = task

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
                except asyncio.TimeoutError:
                    yield _sse_line("keep_alive", "")
                    continue

                if event is _DONE:
                    yield _sse_done()
                    break

                yield _sse_line(event["type"], event["data"])
        except asyncio.CancelledError:
            task.cancel()
            yield _sse_error("Client disconnected")
            yield _sse_done()
        finally:
            _active_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /chat/abort — cancel a running session
# ---------------------------------------------------------------------------

@app.post("/chat/abort")
async def chat_abort(req: AbortRequest):
    """Cancel a running llm_tool_loop session."""
    task = _active_sessions.get(req.session_id)
    if task is None:
        raise HTTPException(404, detail="No active session with that ID")
    task.cancel()
    _active_sessions.pop(req.session_id, None)
    return {"status": "aborted", "session_id": req.session_id}


@app.post("/chat/permission")
async def chat_permission(req: PermissionResponseRequest):
    """Resolve a pending chat permission request."""
    pending = _pending_permission_requests.get(req.permissionRequestId)
    if pending is None:
        return {
            "ok": False,
            "permissionRequestId": req.permissionRequestId,
            "status": "expired",
        }

    future = pending.get("future")
    if future is None or future.done():
        return {
            "ok": False,
            "permissionRequestId": req.permissionRequestId,
            "status": "resolved",
        }

    decision = req.decision or {}
    behavior = str(decision.get("behavior", "deny") or "deny").strip().lower()
    payload = {
        "behavior": "allow" if behavior == "allow" else "deny",
        "updated_input": (
            decision.get("updatedInput")
            if isinstance(decision.get("updatedInput"), dict)
            else None
        ),
        "updated_permissions": (
            decision.get("updatedPermissions")
            if isinstance(decision.get("updatedPermissions"), list)
            else []
        ),
        "message": str(decision.get("message", "") or "").strip(),
    }
    future.set_result(payload)
    return {
        "ok": True,
        "permissionRequestId": req.permissionRequestId,
        "behavior": payload["behavior"],
        "session_id": pending.get("session_id", ""),
    }


@app.post("/chat/session-permission-profile")
async def chat_session_permission_profile(req: SessionPermissionProfileRequest):
    """Update the live permission profile for a session and release pending approvals."""
    policy_state = _set_session_permission_profile(req.session_id, req.permission_profile)
    profile = _effective_permission_profile(req.session_id, req.permission_profile)
    auto_approved_requests = 0

    if profile == "full_access":
        for pending in list(_pending_permission_requests.values()):
            if pending.get("session_id") != req.session_id:
                continue

            future = pending.get("future")
            if future is None or future.done():
                continue

            future.set_result({
                "behavior": "allow",
                "updated_input": None,
                "updated_permissions": [],
                "message": "",
            })
            auto_approved_requests += 1

    return {
        "ok": True,
        "session_id": req.session_id,
        "permission_profile": profile,
        "active": req.session_id in _active_sessions,
        "auto_approved_requests": auto_approved_requests,
        "policy_state": policy_state.to_dict(),
    }


# ---------------------------------------------------------------------------
# GET /workspace — current runtime workspace configuration
# ---------------------------------------------------------------------------

@app.get("/workspace")
async def get_workspace():
    core = _get_core()
    trusted_dirs = [str(d) for d in getattr(core, "TRUSTED_DATA_DIRS", [])]
    workspace = str(os.environ.get("OMICSCLAW_WORKSPACE", "") or "").strip()
    if not workspace and trusted_dirs:
        workspace = trusted_dirs[0]
    return {
        "workspace": workspace or None,
        "trusted_dirs": trusted_dirs,
    }


# ---------------------------------------------------------------------------
# PUT /workspace — sync default project directory from frontend
# ---------------------------------------------------------------------------

class WorkspaceRequest(BaseModel):
    workspace: str

@app.put("/workspace")
async def set_workspace(req: WorkspaceRequest):
    """Update the default workspace directory.

    Called by the frontend when the user selects a new project directory.
    Adds the directory to OMICSCLAW_DATA_DIRS so the backend's tool
    execution can read/write files there, and sets OMICSCLAW_WORKSPACE
    so workspace-scoped features use the same root on subsequent requests.
    """
    ws = req.workspace.strip()
    if not ws:
        raise HTTPException(400, detail="workspace is required")
    ws_path = Path(ws)
    if not ws_path.is_absolute():
        raise HTTPException(400, detail="workspace must be an absolute path")
    if not ws_path.is_dir():
        raise HTTPException(400, detail=f"directory does not exist: {ws}")
    core = _get_core()

    # Add to TRUSTED_DATA_DIRS at runtime so tools can access files there
    if ws_path not in core.TRUSTED_DATA_DIRS:
        core.TRUSTED_DATA_DIRS.append(ws_path)
        logger.info("Added workspace to trusted dirs: %s", ws)

    # Update env var so _build_trusted_dirs() picks it up on next rebuild
    existing = os.environ.get("OMICSCLAW_DATA_DIRS", "")
    dirs = [d.strip() for d in existing.split(",") if d.strip()] if existing else []
    if ws not in dirs:
        dirs.append(ws)
        os.environ["OMICSCLAW_DATA_DIRS"] = ",".join(dirs)
    else:
        os.environ["OMICSCLAW_DATA_DIRS"] = ",".join(dirs)

    os.environ["OMICSCLAW_WORKSPACE"] = ws

    # Persist to .env for next restart
    env_path = _get_omicsclaw_env_path()
    if env_path:
        _update_env_file(
            env_path,
            {
                "OMICSCLAW_DATA_DIRS": ",".join(dirs),
                "OMICSCLAW_WORKSPACE": ws,
            },
        )

    return {
        "ok": True,
        "workspace": ws,
        "trusted_dirs": [str(d) for d in core.TRUSTED_DATA_DIRS],
        "workspace_env": os.environ.get("OMICSCLAW_WORKSPACE", ""),
    }


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    core = _get_core()
    return {
        "status": "ok",
        "version": __version__,
        "provider": core.LLM_PROVIDER_NAME,
        "model": core.OMICSCLAW_MODEL,
        "skills_count": core._primary_skill_count(),
        **_runtime_health_payload(core),
    }


# ---------------------------------------------------------------------------
# GET /skills — list all skills grouped by domain
# ---------------------------------------------------------------------------

@app.get("/skills")
async def list_skills():
    core = _get_core()
    skill_registry = core._skill_registry()

    domain_groups: dict[str, list[dict]] = {}

    for alias, info in skill_registry.skills.items():
        # Skip alias pointers (only show canonical entries)
        if alias != info.get("alias", alias):
            continue

        domain = info.get("domain", "other")
        script = info.get("script")
        entry = {
            "name": alias,
            "description": info.get("description", ""),
            "domain": domain,
            "status": "ready" if (script and script.exists()) else "planned",
        }
        domain_groups.setdefault(domain, []).append(entry)

    # Build response with domain metadata
    result = []
    for domain_key, domain_info in skill_registry.domains.items():
        skills_in_domain = domain_groups.get(domain_key, [])
        if not skills_in_domain:
            continue
        result.append({
            "domain": domain_key,
            "domain_name": domain_info.get("name", domain_key.title()),
            "primary_data_types": domain_info.get("primary_data_types", []),
            "skills": skills_in_domain,
        })

    # Include "other" domain for dynamically discovered skills
    known_domains = set(skill_registry.domains.keys())
    other_skills = []
    for domain_key, skills in domain_groups.items():
        if domain_key not in known_domains:
            other_skills.extend(skills)
    if other_skills:
        result.append({
            "domain": "other",
            "domain_name": "Other (Dynamically Discovered)",
            "primary_data_types": [],
            "skills": other_skills,
        })

    return {"domains": result, "total": sum(len(d["skills"]) for d in result)}


# ---------------------------------------------------------------------------
# GET /skills/{domain}/{skill_name} — single skill detail
# ---------------------------------------------------------------------------

@app.get("/skills/{domain}/{skill_name}")
async def get_skill(domain: str, skill_name: str):
    core = _get_core()
    skill_registry = core._skill_registry()

    info = skill_registry.skills.get(skill_name)
    if info is None:
        raise HTTPException(404, detail=f"Skill '{skill_name}' not found")

    skill_domain = info.get("domain", "other")
    if skill_domain != domain:
        raise HTTPException(
            404,
            detail=f"Skill '{skill_name}' belongs to domain '{skill_domain}', not '{domain}'",
        )

    script = info.get("script")
    return {
        "name": skill_name,
        "domain": skill_domain,
        "description": info.get("description", ""),
        "status": "ready" if (script and script.exists()) else "planned",
        "script_path": str(script) if script else None,
        "aliases": [
            a for a, i in skill_registry.skills.items()
            if i.get("alias") == skill_name and a != skill_name
        ],
    }


# ---------------------------------------------------------------------------
# GET /skills/installed — list OmicsClaw user-installed skill packs
# ---------------------------------------------------------------------------

@app.get("/skills/installed")
async def list_installed_skills():
    try:
        from omicsclaw.extensions import list_installed_extensions

        entries = await asyncio.to_thread(
            list_installed_extensions,
            _omicsclaw_project_dir(),
            extension_types=("skill-pack",),
        )

        result: list[dict[str, Any]] = []
        for entry in entries:
            record = entry.record
            result.append({
                "name": record.extension_name if record is not None else entry.path.name,
                "directory_name": entry.path.name,
                "manifest_name": record.manifest_name if record is not None else "",
                "source": record.source if record is not None else "",
                "source_kind": record.source_kind if record is not None else "",
                "installed_at": record.installed_at if record is not None else "",
                "path": str(entry.path),
                "relative_install_path": record.relative_install_path if record is not None else "",
                "tracked": record is not None,
                "enabled": entry.state.enabled,
                "disabled_reason": entry.state.disabled_reason,
            })

        result.sort(
            key=lambda item: ((item["installed_at"] or ""), item["name"].lower()),
            reverse=True,
        )
        return {"skills": result, "total": len(result)}
    except Exception as exc:
        logger.exception("Installed skills list failed")
        raise HTTPException(500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /skills/install — install a user skill pack into OmicsClaw
# ---------------------------------------------------------------------------

@app.post("/skills/install")
async def install_skill(req: SkillInstallRequest):
    source = req.source.strip()
    if not source:
        raise HTTPException(400, detail="source is required")

    try:
        from omicsclaw.interactive._skill_management_support import install_skill_from_source

        statuses = await asyncio.to_thread(
            install_skill_from_source,
            source,
            omicsclaw_dir=_omicsclaw_project_dir(),
        )
    except Exception as exc:
        logger.exception("Skill install failed")
        raise HTTPException(500, detail=str(exc))

    success = not any(str(getattr(status, "level", "")) == "error" for status in statuses)
    return {
        "success": success,
        "source": source,
        "statuses": _serialize_skill_command_statuses(statuses),
    }


# ---------------------------------------------------------------------------
# POST /skills/uninstall — remove a user-installed skill pack
# ---------------------------------------------------------------------------

@app.post("/skills/uninstall")
async def uninstall_skill(req: SkillUninstallRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, detail="name is required")

    try:
        from omicsclaw.interactive._skill_management_support import uninstall_extension

        statuses = await asyncio.to_thread(
            uninstall_extension,
            name,
            omicsclaw_dir=_omicsclaw_project_dir(),
            expected_type="skill-pack",
        )
    except Exception as exc:
        logger.exception("Skill uninstall failed")
        raise HTTPException(500, detail=str(exc))

    success = not any(str(getattr(status, "level", "")) == "error" for status in statuses)
    return {
        "success": success,
        "name": name,
        "statuses": _serialize_skill_command_statuses(statuses),
    }


# ---------------------------------------------------------------------------
# GET /memory/browse — browse memory graph nodes
# ---------------------------------------------------------------------------

@app.get("/memory/browse")
async def memory_browse(
    path: str = Query("", description="Node path to browse"),
    domain: str = Query("core", description="Memory domain"),
):
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        uri = f"{domain}://{path}" if path else f"{domain}://"
        children = await _memory_client.list_children(uri)

        # Also get the node itself if path is provided
        node = None
        if path:
            node = await _memory_client.recall(f"{domain}://{path}")

        return {
            "path": path,
            "domain": domain,
            "node": node,
            "children": children,
        }
    except Exception as exc:
        logger.exception("Memory browse error")
        raise HTTPException(500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /memory/search — full-text search across memories
# ---------------------------------------------------------------------------

@app.get("/memory/search")
async def memory_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    domain: Optional[str] = Query(None, description="Optional domain filter"),
):
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        results = await _memory_client.search(q, limit=limit, domain=domain)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as exc:
        logger.exception("Memory search error")
        raise HTTPException(500, detail=str(exc))


# ---------------------------------------------------------------------------
# Memory CRUD & Management Endpoints
# ---------------------------------------------------------------------------

# -- Pydantic models for memory endpoints -----------------------------------

class MemoryCreateRequest(BaseModel):
    parent_path: str = ""
    content: str
    title: str = ""
    domain: str = "core"
    priority: int = 0


class MemoryUpdateRequest(BaseModel):
    path: str
    domain: str = "core"
    content: Optional[str] = None
    priority: Optional[int] = None


class MemoryRollbackRequest(BaseModel):
    path: str = ""
    domain: str = "core"
    target_memory_id: int


class GlossaryRequest(BaseModel):
    keyword: str
    node_uuid: str


class ScopedPruneRequest(BaseModel):
    scope: str = ""
    apply: bool = False
    workspace: str = ""


# -- Helper: get graph / glossary / changeset services ----------------------

def _get_graph_service():
    """Return GraphService, raising 503 if the memory module is not available."""
    try:
        from omicsclaw.memory import get_graph_service
        return get_graph_service()
    except Exception as exc:
        raise HTTPException(503, detail=f"Memory graph service unavailable: {exc}")


def _get_glossary_service():
    """Return GlossaryService, raising 503 if the memory module is not available."""
    try:
        from omicsclaw.memory import get_glossary_service
        return get_glossary_service()
    except Exception as exc:
        raise HTTPException(503, detail=f"Memory glossary service unavailable: {exc}")


def _get_changeset_store():
    """Return ChangesetStore, raising 503 if the memory module is not available."""
    try:
        from omicsclaw.memory.snapshot import get_changeset_store
        return get_changeset_store()
    except Exception as exc:
        raise HTTPException(503, detail=f"Memory changeset store unavailable: {exc}")


def _memory_review_model_map():
    from omicsclaw.memory import Edge, GlossaryKeyword, Memory, Node, Path

    return {
        "nodes": Node,
        "memories": Memory,
        "edges": Edge,
        "paths": Path,
        "glossary_keywords": GlossaryKeyword,
    }


def _coerce_memory_snapshot_row(model_cls, row: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import DateTime as SADateTime

    payload: dict[str, Any] = {}
    for column in model_cls.__table__.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        if isinstance(column.type, SADateTime) and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                pass
        payload[column.name] = value
    return payload


def _memory_snapshot_row_identity(table: str, row: dict[str, Any]):
    if table == "nodes":
        return row["uuid"]
    if table in {"memories", "edges"}:
        return row["id"]
    if table == "paths":
        return (row["domain"], row["path"])
    if table == "glossary_keywords":
        if "id" in row and row["id"] is not None:
            return row["id"]
        return None
    raise ValueError(f"Unsupported memory review table '{table}'")


async def _resolve_memory_review_node_uuid(
    *,
    table: str,
    ref: dict[str, Any] | None,
    all_rows: dict[str, Any],
    session,
) -> str:
    if not ref:
        return ""
    if table == "nodes":
        return str(ref.get("uuid", "") or "")
    if table in {"memories", "glossary_keywords"}:
        return str(ref.get("node_uuid", "") or "")
    if table == "edges":
        return str(ref.get("child_uuid", "") or "")
    if table == "paths":
        node_uuid = str(ref.get("node_uuid", "") or "")
        if node_uuid:
            return node_uuid
        edge_id = ref.get("edge_id")
        if edge_id is None:
            return ""

        edge_entry = all_rows.get(f"edges:{edge_id}")
        if isinstance(edge_entry, dict):
            edge_ref = edge_entry.get("after") or edge_entry.get("before")
            if isinstance(edge_ref, dict) and edge_ref.get("child_uuid"):
                return str(edge_ref["child_uuid"])

        from sqlalchemy import select

        model_map = _memory_review_model_map()
        edge_model = model_map["edges"]
        result = await session.execute(
            select(edge_model.child_uuid).where(edge_model.id == edge_id)
        )
        return str(result.scalar_one_or_none() or "")
    return ""


async def _discard_pending_memory_review_changes() -> dict[str, Any]:
    from sqlalchemy import select

    from omicsclaw.memory import get_db_manager, get_search_indexer
    from omicsclaw.memory.snapshot import _rows_equal

    store = _get_changeset_store()
    all_rows = store.get_all_rows_dict()
    changed_entries = [
        (key, entry)
        for key, entry in all_rows.items()
        if not _rows_equal(entry.get("table", ""), entry.get("before"), entry.get("after"))
    ]
    if not changed_entries:
        return {"discarded": 0, "remaining": 0, "nodes_refreshed": 0}

    model_map = _memory_review_model_map()
    delete_order = ("paths", "glossary_keywords", "edges", "memories", "nodes")
    restore_order = ("nodes", "memories", "edges", "paths", "glossary_keywords")
    affected_node_uuids: set[str] = set()
    by_table: dict[str, list[dict[str, Any]]] = {
        table: [] for table in model_map
    }
    for _, entry in changed_entries:
        table = str(entry.get("table", "") or "")
        if table in by_table:
            by_table[table].append(entry)

    db = get_db_manager()
    search = get_search_indexer()

    async with db.session() as session:
        for _, entry in changed_entries:
            node_uuid = await _resolve_memory_review_node_uuid(
                table=str(entry.get("table", "") or ""),
                ref=(entry.get("after") or entry.get("before")),
                all_rows=all_rows,
                session=session,
            )
            if node_uuid:
                affected_node_uuids.add(node_uuid)

        for table in delete_order:
            model_cls = model_map[table]
            for entry in by_table[table]:
                before = entry.get("before")
                after = entry.get("after")
                if before is not None or after is None:
                    continue

                identity = _memory_snapshot_row_identity(table, after)
                instance = None
                if identity is not None:
                    instance = await session.get(model_cls, identity)
                elif table == "glossary_keywords":
                    instance = (
                        await session.execute(
                            select(model_cls).where(
                                model_cls.keyword == after.get("keyword"),
                                model_cls.node_uuid == after.get("node_uuid"),
                            )
                        )
                    ).scalar_one_or_none()

                if instance is not None:
                    await session.delete(instance)

        for table in restore_order:
            model_cls = model_map[table]
            for entry in by_table[table]:
                before = entry.get("before")
                after = entry.get("after")
                if before is None or after is not None:
                    continue

                payload = _coerce_memory_snapshot_row(model_cls, before)
                if table == "memories":
                    identity = _memory_snapshot_row_identity(table, before)
                    if identity is None:
                        raise ValueError("Cannot restore memory review row without an identity")
                    existing = await session.get(model_cls, identity)
                    if existing is None and "content" not in payload:
                        raise ValueError(
                            "Cannot discard pending memory deletion because snapshot content is unavailable"
                        )
                await session.merge(model_cls(**payload))

        for table in restore_order:
            model_cls = model_map[table]
            for entry in by_table[table]:
                before = entry.get("before")
                after = entry.get("after")
                if before is None or after is None:
                    continue

                payload = _coerce_memory_snapshot_row(model_cls, before)
                await session.merge(model_cls(**payload))

        await session.flush()
        for node_uuid in sorted(affected_node_uuids):
            await search.refresh_search_documents_for_node(node_uuid, session=session)

    discarded = store.discard_all()
    return {
        "discarded": discarded,
        "remaining": store.get_change_count(),
        "nodes_refreshed": len(affected_node_uuids),
    }


# -- POST /memory/create ----------------------------------------------------

@app.post("/memory/create")
async def memory_create(req: MemoryCreateRequest):
    """Create a new memory node."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    if not req.content.strip():
        raise HTTPException(400, detail="Content must not be empty")

    try:
        # Build URI: domain://parent_path/title or domain://title
        if req.parent_path:
            path = f"{req.parent_path}/{req.title}" if req.title else req.parent_path
        else:
            path = req.title if req.title else ""
        uri = f"{req.domain}://{path}"

        result = await _memory_client.remember(
            uri=uri,
            content=req.content,
            priority=req.priority,
        )
        return {"ok": True, "uri": uri, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        logger.exception("Memory create error")
        raise HTTPException(500, detail=str(exc))


# -- PUT /memory/update ------------------------------------------------------

@app.put("/memory/update")
async def memory_update(req: MemoryUpdateRequest):
    """Update an existing memory node's content or priority."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    if req.content is None and req.priority is None:
        raise HTTPException(400, detail="At least one of content or priority must be provided")

    try:
        graph = _get_graph_service()
        result = await graph.update_memory(
            path=req.path,
            content=req.content,
            priority=req.priority,
            domain=req.domain,
        )
        return {"ok": True, "path": req.path, "domain": req.domain, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        logger.exception("Memory update error")
        raise HTTPException(500, detail=str(exc))


# -- DELETE /memory/delete ---------------------------------------------------

@app.delete("/memory/delete")
async def memory_delete(
    path: str = Query(..., description="Memory path to delete"),
    domain: str = Query("core", description="Memory domain"),
):
    """Delete (forget) a memory by its path."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        uri = f"{domain}://{path}"
        result = await _memory_client.forget(uri)
        return {"ok": True, "uri": uri, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        logger.exception("Memory delete error")
        raise HTTPException(500, detail=str(exc))


# -- GET /memory/children ---------------------------------------------------

@app.get("/memory/children")
async def memory_children(
    node_uuid: str = Query("", description="Parent node UUID (empty = root)"),
    domain: str = Query("core", description="Context domain"),
    path: str = Query("", description="Context path"),
):
    """List direct children of a memory node."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        graph = _get_graph_service()
        from omicsclaw.memory.models import ROOT_NODE_UUID
        parent_uuid = node_uuid if node_uuid else ROOT_NODE_UUID
        children = await graph.get_children(
            node_uuid=parent_uuid,
            context_domain=domain,
            context_path=path or None,
        )
        return {"node_uuid": parent_uuid, "domain": domain, "children": children}
    except Exception as exc:
        logger.exception("Memory children error")
        raise HTTPException(500, detail=str(exc))


# -- GET /memory/domains ----------------------------------------------------

@app.get("/memory/domains")
async def memory_domains():
    """List all memory domains with node counts."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        graph = _get_graph_service()
        all_paths = await graph.get_all_paths(domain=None)

        # Group by domain and count
        domain_counts: dict[str, int] = {}
        for p in all_paths:
            d = p.get("domain", "core")
            domain_counts[d] = domain_counts.get(d, 0) + 1

        domains = [
            {"domain": d, "node_count": c}
            for d, c in sorted(domain_counts.items())
        ]
        return {"domains": domains, "total_nodes": len(all_paths)}
    except Exception as exc:
        logger.exception("Memory domains error")
        raise HTTPException(500, detail=str(exc))


# -- GET /memory/recent ------------------------------------------------------

@app.get("/memory/recent")
async def memory_recent(
    limit: int = Query(10, ge=1, le=100, description="Max results"),
):
    """Get recently updated memories."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        results = await _memory_client.get_recent(limit=limit)
        return {"results": results, "count": len(results)}
    except Exception as exc:
        logger.exception("Memory recent error")
        raise HTTPException(500, detail=str(exc))


# -- GET /memory/review/changes ----------------------------------------------

@app.get("/memory/review/changes")
async def memory_review_changes():
    """Get pending AI-made changes awaiting review."""
    try:
        store = _get_changeset_store()
        changed_rows = store.get_changed_rows()
        return {
            "count": len(changed_rows),
            "changes": changed_rows,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Memory review changes error")
        raise HTTPException(500, detail=str(exc))


# -- POST /memory/review/approve ---------------------------------------------

@app.post("/memory/review/approve")
async def memory_review_approve():
    """Approve and clear all pending changes (integrate into memory)."""
    try:
        store = _get_changeset_store()
        count = store.clear_all()
        return {"ok": True, "cleared": count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Memory review approve error")
        raise HTTPException(500, detail=str(exc))


# -- POST /memory/review/rollback --------------------------------------------

@app.post("/memory/review/rollback")
async def memory_review_rollback(req: MemoryRollbackRequest):
    """Rollback a specific memory to a previous version."""
    if _memory_client is None:
        raise HTTPException(503, detail="Memory system not available")

    try:
        graph = _get_graph_service()
        result = await graph.rollback_to_memory(target_memory_id=req.target_memory_id)
        return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Memory review rollback error")
        raise HTTPException(500, detail=str(exc))


# -- POST /memory/review/clear -----------------------------------------------

@app.post("/memory/review/clear")
async def memory_review_clear():
    """Discard all pending changes by rolling memory state back to snapshots."""
    try:
        result = await _discard_pending_memory_review_changes()
        return {"ok": True, "cleared": result["discarded"], **result}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        logger.exception("Memory review clear error")
        raise HTTPException(500, detail=str(exc))


# -- POST /memory/glossary/add -----------------------------------------------

@app.post("/memory/glossary/add")
async def memory_glossary_add(req: GlossaryRequest):
    """Bind a glossary keyword to a memory node."""
    try:
        glossary = _get_glossary_service()
        result = await glossary.add_glossary_keyword(
            keyword=req.keyword,
            node_uuid=req.node_uuid,
        )
        return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Glossary add error")
        raise HTTPException(500, detail=str(exc))


# -- DELETE /memory/glossary/remove -------------------------------------------

@app.delete("/memory/glossary/remove")
async def memory_glossary_remove(req: GlossaryRequest):
    """Remove a glossary keyword binding from a memory node."""
    try:
        glossary = _get_glossary_service()
        result = await glossary.remove_glossary_keyword(
            keyword=req.keyword,
            node_uuid=req.node_uuid,
        )
        return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Glossary remove error")
        raise HTTPException(500, detail=str(exc))


# -- GET /memory/scoped -------------------------------------------------------

@app.get("/memory/scoped")
async def memory_scoped_list(
    workspace: str = Query("", description="Workspace directory to scan"),
    scope: str = Query("", description="Filter by scope (user, project, etc.)"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
):
    """List scoped memory files from the workspace's .omicsclaw/scoped_memory/ directory."""
    try:
        from omicsclaw.memory.scoped_memory import resolve_scoped_memory_root
        from omicsclaw.memory.scoped_memory_index import scan_scoped_memory_headers
    except ImportError:
        raise HTTPException(503, detail="Scoped memory module not available")

    ws = _resolve_scoped_memory_workspace(workspace)

    if not ws:
        return {"records": [], "count": 0, "error": "No workspace configured"}

    root = resolve_scoped_memory_root(workspace_dir=ws)
    if root is None or not root.exists():
        return {"records": [], "count": 0, "root": str(root) if root else None}

    headers = scan_scoped_memory_headers(root, scope=scope, limit=limit)

    records = []
    for h in headers:
        records.append({
            "memory_id": h.memory_id,
            "scope": h.scope,
            "title": h.title,
            "description": h.description,
            "owner": h.owner,
            "freshness": h.freshness,
            "updated_at": h.updated_at,
            "created_at": h.created_at,
            "domain": h.domain,
            "keywords": list(h.keywords),
            "dataset_refs": list(h.dataset_refs),
            "path": str(h.path),
            "relative_path": h.relative_path,
        })

    return {"records": records, "count": len(records), "root": str(root)}


# -- POST /memory/scoped/prune -----------------------------------------------

@app.post("/memory/scoped/prune")
async def memory_scoped_prune(req: ScopedPruneRequest):
    """Prune stale or duplicate scoped memories."""
    try:
        from omicsclaw.memory.scoped_memory import prune_scoped_memories
    except ImportError:
        raise HTTPException(503, detail="Scoped memory module not available")

    ws = _resolve_scoped_memory_workspace(req.workspace)

    if not ws:
        raise HTTPException(400, detail="No workspace configured; provide 'workspace' in request body")

    try:
        result = prune_scoped_memories(
            workspace_dir=ws,
            scope=req.scope,
            apply_changes=req.apply,
        )
        candidates = []
        for c in result.candidates:
            candidates.append({
                "memory_id": c.record.memory_id,
                "title": c.record.title,
                "scope": c.record.scope,
                "reason": c.reason,
                "path": str(c.record.path),
            })
        return {
            "ok": True,
            "applied": req.apply,
            "scope": result.scope,
            "candidates": candidates,
            "deleted_count": result.deleted_count,
            "root": str(result.root),
        }
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception as exc:
        logger.exception("Scoped prune error")
        raise HTTPException(500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /settings — current OmicsClaw configuration
# ---------------------------------------------------------------------------

@app.get("/settings")
async def get_settings():
    core = _get_core()
    usage = core.get_usage_snapshot()
    uptime = int(time.time() - core.BOT_START_TIME)

    return {
        "provider": core.LLM_PROVIDER_NAME,
        "model": core.OMICSCLAW_MODEL,
        "max_history": core.MAX_HISTORY,
        "max_history_chars": core.MAX_HISTORY_CHARS,
        "max_tool_iterations": core.MAX_TOOL_ITERATIONS,
        "skills_count": core._primary_skill_count(),
        "tools_count": len(core.get_tool_executors()),
        "data_dir": str(core.DATA_DIR),
        "output_dir": str(core.OUTPUT_DIR),
        "uptime_seconds": uptime,
        "usage": usage,
        "memory_enabled": _memory_client is not None,
    }


def _claude_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read_claude_settings() -> dict[str, Any]:
    settings_path = _claude_settings_path()
    try:
        if not settings_path.exists():
            return {}
        parsed = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_claude_settings(settings: dict[str, Any]) -> None:
    settings_path = _claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class ClaudeSettingsRequest(BaseModel):
    settings: dict[str, Any]


@app.get("/claude/settings")
async def get_claude_settings():
    return {"settings": _read_claude_settings()}


@app.put("/claude/settings")
async def put_claude_settings(req: ClaudeSettingsRequest):
    _write_claude_settings(req.settings)
    return {"success": True}


# ---------------------------------------------------------------------------
# GET /providers — list all supported LLM providers
# ---------------------------------------------------------------------------

def _read_first_env(*keys: str) -> str:
    for key in keys:
        value = str(os.environ.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _configured_provider_name() -> str:
    return _read_first_env("LLM_PROVIDER", "OMICSCLAW_PROVIDER").lower()


def _provider_base_url_source(provider_name: str, active_provider: str) -> str:
    explicit_provider = _configured_provider_name()
    provider_base_url = _read_first_env(f"{provider_name.upper()}_BASE_URL")
    if provider_base_url and explicit_provider == provider_name:
        return "provider-base-url"

    generic_base_url = _read_first_env("LLM_BASE_URL", "OMICSCLAW_BASE_URL")
    if generic_base_url and (explicit_provider == provider_name or active_provider == provider_name):
        return "generic-base-url"

    return ""


def _provider_configuration_source(provider_name: str, env_key: str, active_provider: str) -> str:
    explicit_provider = _configured_provider_name()

    if env_key and _read_first_env(env_key):
        return "provider-env"

    generic_key = _read_first_env("LLM_API_KEY", "OMICSCLAW_API_KEY")
    if explicit_provider == provider_name or active_provider == provider_name:
        if generic_key:
            return "generic-env"

        base_url_source = _provider_base_url_source(provider_name, active_provider)
        if provider_name == "custom" and base_url_source:
            return base_url_source
        if provider_name == "ollama":
            if explicit_provider == provider_name:
                return "explicit-provider"
            if base_url_source:
                return base_url_source

    return ""


@app.get("/providers")
async def list_providers():
    """List all supported LLM providers with current selection."""
    core = _get_core()

    try:
        from omicsclaw.core.provider_registry import (
            PROVIDER_PRESETS,
            build_provider_registry_entries,
        )
    except ImportError:
        return {"providers": [], "current": core.LLM_PROVIDER_NAME, "current_model": core.OMICSCLAW_MODEL}

    providers = []
    try:
        provider_entries = build_provider_registry_entries(PROVIDER_PRESETS)
    except Exception:
        provider_entries = [
            {
                "name": name,
                "base_url": base_url,
                "default_model": default_model,
                "env_key": env_key,
                "display_name": name,
                "description": "",
                "description_zh": "",
                "tier": "local",
                "models": [default_model] if default_model else [],
            }
            for name, (base_url, default_model, env_key) in PROVIDER_PRESETS.items()
        ]

    for entry in provider_entries:
        name = str(entry.get("name", "") or "")
        env_key = str(entry.get("env_key", "") or "")
        credential_source = _provider_configuration_source(name, env_key, core.LLM_PROVIDER_NAME)
        providers.append({
            **entry,
            "configured": bool(credential_source),
            "configured_via": credential_source or None,
            "active": name == core.LLM_PROVIDER_NAME,
        })

    return {
        "providers": providers,
        "current": core.LLM_PROVIDER_NAME,
        "current_model": core.OMICSCLAW_MODEL,
    }


# ---------------------------------------------------------------------------
# PUT /providers — switch LLM provider
# ---------------------------------------------------------------------------

class ProviderSwitchRequest(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@app.put("/providers")
async def switch_provider(req: ProviderSwitchRequest):
    """Switch the active LLM provider. Re-initializes the core LLM client."""
    core = _get_core()

    # Validate provider name
    try:
        from omicsclaw.core.provider_registry import PROVIDER_PRESETS
        if req.provider not in PROVIDER_PRESETS and req.provider != "custom":
            raise HTTPException(400, detail=f"Unknown provider: {req.provider}")
    except ImportError:
        pass

    # Re-init core with new provider
    try:
        core.init(
            api_key=req.api_key or os.environ.get("LLM_API_KEY", ""),
            base_url=req.base_url or None,
            model=req.model,
            provider=req.provider,
        )
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to switch provider: {exc}")

    # Persist to .env
    env_path = _get_omicsclaw_env_path()
    if env_path:
        updates: dict[str, str] = {"LLM_PROVIDER": req.provider}
        if req.model:
            updates["OMICSCLAW_MODEL"] = req.model
        if req.api_key:
            updates["LLM_API_KEY"] = req.api_key
        if req.base_url:
            updates["LLM_BASE_URL"] = req.base_url
        _update_env_file(env_path, updates)

    logger.info("Switched to provider=%s model=%s", core.LLM_PROVIDER_NAME, core.OMICSCLAW_MODEL)

    return {
        "ok": True,
        "provider": core.LLM_PROVIDER_NAME,
        "model": core.OMICSCLAW_MODEL,
    }


# ---------------------------------------------------------------------------
# MCP Server Management — bridges frontend config with OmicsClaw runtime
# ---------------------------------------------------------------------------

@app.get("/mcp/servers")
async def mcp_list_servers():
    """List all configured MCP servers and their active/probe status."""
    try:
        from omicsclaw.interactive._mcp import list_mcp_servers
        servers = list_mcp_servers()
    except ImportError:
        return {"servers": [], "error": "MCP module not available"}
    except Exception as exc:
        logger.warning("mcp list error: %s", exc)
        return {"servers": [], "error": str(exc)}

    # Probe active status
    active_entries = ()
    if _mcp_load_fn is not None:
        try:
            active_entries = await _mcp_load_fn()
        except Exception:
            pass

    active_names = set()
    for entry in active_entries:
        if isinstance(entry, dict):
            active_names.add(entry.get("name", ""))
        elif isinstance(entry, str):
            active_names.add(entry)

    result = []
    for srv in servers:
        name = srv.get("name", "")
        enabled = bool(srv.get("enabled", True))
        result.append({
            "name": name,
            "transport": srv.get("transport", "stdio"),
            "type": srv.get("transport", "stdio"),
            "target": srv.get("command") or srv.get("url", ""),
            "command": srv.get("command", ""),
            "url": srv.get("url", ""),
            "active": enabled and name in active_names,
            "enabled": enabled,
            "extra_args": srv.get("args", []),
            "args": srv.get("args", []),
            "env": srv.get("env", {}),
            "headers": srv.get("headers", {}),
            "header_keys": sorted((srv.get("headers") or {}).keys()),
            "tools": srv.get("tools"),
        })

    return {"servers": result}


class McpAddRequest(BaseModel):
    name: str
    target: str
    transport: str = ""
    extra_args: list[str] = []
    env: dict[str, str] = {}
    headers: dict[str, str] = {}
    enabled: bool | None = None
    tools: list[str] = []


@app.post("/mcp/servers")
async def mcp_add_server(req: McpAddRequest):
    """Add or update an MCP server in OmicsClaw config."""
    try:
        from omicsclaw.interactive._mcp import add_mcp_server
        add_mcp_server(
            name=req.name,
            target=req.target,
            transport=req.transport or None,
            extra_args=req.extra_args or None,
            env=req.env or None,
            headers=req.headers or None,
            enabled=req.enabled,
            tools=req.tools or None,
        )
        return {"ok": True, "name": req.name}
    except ImportError:
        raise HTTPException(503, detail="MCP module not available")
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.delete("/mcp/servers/{name}")
async def mcp_remove_server(name: str):
    """Remove an MCP server from OmicsClaw config."""
    try:
        from omicsclaw.interactive._mcp import remove_mcp_server
        removed = remove_mcp_server(name)
        if not removed:
            raise HTTPException(404, detail=f"Server '{name}' not found")
        return {"ok": True, "name": name}
    except ImportError:
        raise HTTPException(503, detail="MCP module not available")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


def _reconcile_mcp_servers(incoming: Any) -> dict[str, Any]:
    try:
        from omicsclaw.interactive._mcp import add_mcp_server, list_mcp_servers, remove_mcp_server
    except ImportError:
        raise HTTPException(503, detail="MCP module not available")

    if incoming is None:
        raise HTTPException(400, detail="mcpServers is required")
    if not isinstance(incoming, dict):
        raise HTTPException(400, detail="mcpServers must be an object")

    desired_servers: list[dict[str, Any]] = []
    for raw_name, config in incoming.items():
        name = str(raw_name or "").strip()
        if not name:
            raise HTTPException(400, detail="MCP server names must not be empty")
        if not isinstance(config, dict):
            raise HTTPException(400, detail=f"Config for MCP server '{name}' must be an object")

        cmd = config.get("command", "")
        url = config.get("url", "")
        target = str(cmd or url or "").strip()
        if not target:
            raise HTTPException(
                400,
                detail=f"MCP server '{name}' is missing both command and url",
            )

        desired_servers.append(
            {
                "name": name,
                "target": target,
                "transport": config.get("type") or config.get("transport", ""),
                "extra_args": config.get("args", []),
                "env": config.get("env", {}),
                "headers": config.get("headers", {}),
                "enabled": config.get("enabled") if "enabled" in config else None,
                "tools": config.get("tools", []),
            }
        )

    existing = {
        str(server.get("name", "")).strip(): server
        for server in list_mcp_servers()
        if str(server.get("name", "")).strip()
    }
    desired_names = {server["name"] for server in desired_servers}

    removed = 0
    for name in sorted(set(existing) - desired_names):
        if remove_mcp_server(name):
            removed += 1

    synced = 0
    for server in desired_servers:
        add_mcp_server(
            name=server["name"],
            target=server["target"],
            transport=server["transport"] or None,
            extra_args=server["extra_args"] or None,
            env=server["env"] or None,
            headers=server["headers"] or None,
            enabled=server["enabled"],
            tools=server["tools"] or None,
        )
        synced += 1

    return {"ok": True, "synced": synced, "removed": removed}


class McpReplaceRequest(BaseModel):
    mcpServers: dict[str, Any]


@app.put("/mcp/servers")
async def mcp_replace_servers(req: McpReplaceRequest):
    return _reconcile_mcp_servers(req.mcpServers)


@app.post("/mcp/sync")
async def mcp_sync_from_frontend(request: Request):
    """
    Backward-compatible bulk MCP replace endpoint.
    """
    body = await request.json()
    return _reconcile_mcp_servers(body.get("mcpServers"))


# ---------------------------------------------------------------------------
# Outputs — list OmicsClaw analysis output directories
# ---------------------------------------------------------------------------

# File-type classification for the outputs API
_OUTPUT_FILE_TYPES: dict[str, str] = {
    ".md": "markdown",
    ".json": "json",
    ".csv": "csv",
    ".tsv": "tsv",
    ".h5ad": "data",
    ".h5": "data",
    ".loom": "data",
    ".rds": "data",
    ".pdf": "pdf",
    ".html": "html",
    ".ipynb": "notebook",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",
    ".gif": "image",
    ".webp": "image",
    ".txt": "text",
    ".log": "text",
}

_IMAGE_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def _parse_run_dir_name(name: str) -> tuple[str, str | None]:
    """
    Parse an output directory name like ``sc-preprocessing__20260405_145208__dbe3570a``
    into (skill_name, iso_timestamp_or_None).

    The naming convention is: {skill}__{method}__{YYYYMMDD_HHMMSS}__{suffix}
    but the number of ``__`` segments varies, so we use a best-effort approach.
    """
    parts = name.split("__")
    skill = parts[0].replace("_", "-") if parts else name

    # Try to find a segment that looks like a timestamp (YYYYMMDD_HHMMSS)
    timestamp_iso: str | None = None
    for i, part in enumerate(parts):
        # A timestamp segment is 15 chars: YYYYMMDD_HHMMSS
        if len(part) == 15 and part[8] == "_":
            try:
                dt = datetime.strptime(part, "%Y%m%d_%H%M%S")
                timestamp_iso = dt.isoformat()
                break
            except ValueError:
                pass
        # Also handle without separator: YYYYMMDDHHMMSS (14 chars)
        if len(part) == 14 and part.isdigit():
            try:
                dt = datetime.strptime(part, "%Y%m%d%H%M%S")
                timestamp_iso = dt.isoformat()
                break
            except ValueError:
                pass

    return skill, timestamp_iso


def _classify_file(file_path: Path) -> str:
    """Return a type string for a file based on its extension."""
    return _OUTPUT_FILE_TYPES.get(file_path.suffix.lower(), "other")


def _collect_figures(run_dir: Path) -> list[dict]:
    """Collect image files from the ``figures/`` subdirectory."""
    figures_dir = run_dir / "figures"
    if not figures_dir.is_dir():
        return []

    results: list[dict] = []
    for f in sorted(figures_dir.iterdir()):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        mime = _IMAGE_MIME_MAP.get(ext)
        if mime:
            results.append({
                "name": f.name,
                "path": str(f),
                "mimeType": mime,
            })
    return results


def _collect_key_files(run_dir: Path) -> list[dict]:
    """
    Collect notable files from the run directory (non-recursive, top-level only).

    Includes: report.md, result.json, README.md, *.csv, *.h5ad, and similar.
    """
    KEY_PATTERNS = {"report.md", "result.json", "readme.md"}
    KEY_EXTENSIONS = {".csv", ".tsv", ".h5ad", ".h5", ".loom", ".rds", ".pdf", ".html", ".ipynb"}

    results: list[dict] = []
    for f in sorted(run_dir.iterdir()):
        if not f.is_file():
            continue
        if f.name.lower() in KEY_PATTERNS or f.suffix.lower() in KEY_EXTENSIONS:
            results.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "type": _classify_file(f),
            })
    return results


def _read_result_json(run_dir: Path) -> tuple[str, Any]:
    """
    Read ``result.json`` and extract status + summary.

    Returns (status, summary_or_None).
    """
    result_file = run_dir / "result.json"
    if not result_file.is_file():
        # No result.json — infer status from presence of output files
        figures_dir = run_dir / "figures"
        if figures_dir.is_dir() and any(figures_dir.iterdir()):
            return ("completed", None)
        return ("running", None)

    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        status = data.get("status", "")
        # Infer status when not explicitly set
        if not status:
            if data.get("completed_at"):
                status = "completed"
            elif data.get("error"):
                status = "failed"
            else:
                status = "completed"
        summary = data.get("summary") or data.get("message")
        # Build a summary from common fields if no explicit summary
        if not summary:
            parts: list[str] = []
            for k in ("n_cells", "n_genes", "n_clusters", "n_samples", "n_features"):
                if k in data:
                    parts.append(f"{k}={data[k]}")
            if parts:
                summary = ", ".join(parts)
        return (str(status), summary)
    except Exception:
        return ("unknown", None)


@app.get("/outputs/latest")
async def outputs_latest(limit: int = Query(10, ge=1, le=50)):
    """
    List the most recent output directories from OmicsClaw's OUTPUT_DIR.

    Each entry includes parsed metadata, figures, key files, and a summary
    extracted from ``result.json`` when available.
    """
    core = _get_core()
    output_dir = Path(str(core.OUTPUT_DIR))

    if not output_dir.is_dir():
        return {"runs": [], "output_dir": str(output_dir), "total": 0}

    # Gather all subdirectories with their mtime
    dir_entries: list[tuple[float, Path]] = []
    try:
        for entry in output_dir.iterdir():
            if entry.is_dir():
                try:
                    dir_entries.append((entry.stat().st_mtime, entry))
                except OSError:
                    pass
    except OSError as exc:
        raise HTTPException(500, detail=f"Cannot read output directory: {exc}")

    total = len(dir_entries)

    # Sort by mtime descending (newest first) and apply limit
    dir_entries.sort(key=lambda x: x[0], reverse=True)
    dir_entries = dir_entries[:limit]

    runs: list[dict] = []
    for mtime, d in dir_entries:
        skill, timestamp_iso = _parse_run_dir_name(d.name)
        status, summary = _read_result_json(d)
        figures = _collect_figures(d)
        files = _collect_key_files(d)

        # Use mtime as the authoritative timestamp (always timezone-correct).
        # Fall back to the parsed directory-name timestamp only if mtime fails.
        effective_timestamp = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        if not effective_timestamp and timestamp_iso:
            effective_timestamp = timestamp_iso

        run_entry: dict[str, Any] = {
            "id": d.name,
            "skill": skill,
            "timestamp": effective_timestamp,
            "status": status,
            "path": str(d),
            "figures": figures,
            "files": files,
        }
        if summary:
            run_entry["summary"] = summary

        runs.append(run_entry)

    return {"runs": runs, "output_dir": str(output_dir), "total": total}


@app.get("/outputs/{run_id}/files")
async def outputs_run_files(run_id: str):
    """
    List all files in a specific output directory (recursive).

    Returns a flat list of every file with path, size, and type classification.
    """
    core = _get_core()
    output_dir = Path(str(core.OUTPUT_DIR))
    run_dir = output_dir / run_id

    if not run_dir.is_dir():
        raise HTTPException(404, detail=f"Output run '{run_id}' not found")

    # Security: ensure the resolved path is still under OUTPUT_DIR
    try:
        run_dir.resolve().relative_to(output_dir.resolve())
    except ValueError:
        raise HTTPException(400, detail="Invalid run_id (path traversal)")

    files: list[dict] = []
    try:
        for f in sorted(run_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(run_dir)
            mime, _ = mimetypes.guess_type(str(f))
            files.append({
                "name": f.name,
                "relative_path": str(rel),
                "path": str(f),
                "size": f.stat().st_size,
                "type": _classify_file(f),
                "mimeType": mime or "application/octet-stream",
            })
    except OSError as exc:
        raise HTTPException(500, detail=f"Cannot read run directory: {exc}")

    return {
        "run_id": run_id,
        "path": str(run_dir),
        "files": files,
        "total": len(files),
    }


# ---------------------------------------------------------------------------
# Bridge — Remote Channel Management
# ---------------------------------------------------------------------------

# Global ChannelManager instance (like _core for the LLM engine)
_channel_manager = None
_bridge_task: asyncio.Task | None = None

# Map each channel name to the env vars required for it to be considered
# "configured". If ALL listed vars are non-empty the channel is configured.
_CHANNEL_ENV_KEYS: dict[str, list[str]] = {
    "telegram":  ["TELEGRAM_BOT_TOKEN"],
    "feishu":    ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    "dingtalk":  ["DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"],
    "discord":   ["DISCORD_BOT_TOKEN"],
    "slack":     ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
    "wechat":    ["WECOM_CORP_ID"],  # or WECHAT_APP_ID — either backend
    "qq":        ["QQ_APP_ID", "QQ_APP_SECRET"],
    "email":     ["EMAIL_IMAP_HOST", "EMAIL_IMAP_USERNAME", "EMAIL_SMTP_HOST", "EMAIL_SMTP_USERNAME"],
    "imessage":  [],  # macOS only, no secrets required
}

# Extended map: every env key relevant to a channel (for config endpoints).
_CHANNEL_ALL_CONFIG_KEYS: dict[str, list[str]] = {
    "telegram": [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "RATE_LIMIT_PER_HOUR",
    ],
    "feishu": [
        "FEISHU_APP_ID", "FEISHU_APP_SECRET",
        "FEISHU_THINKING_THRESHOLD_MS", "FEISHU_MAX_INBOUND_IMAGE_MB",
        "FEISHU_MAX_INBOUND_FILE_MB", "FEISHU_MAX_ATTACHMENTS",
        "FEISHU_RATE_LIMIT_PER_HOUR", "FEISHU_BRIDGE_DEBUG",
    ],
    "dingtalk": [
        "DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET",
        "DINGTALK_RATE_LIMIT_PER_HOUR",
    ],
    "discord": [
        "DISCORD_BOT_TOKEN", "DISCORD_RATE_LIMIT_PER_HOUR", "DISCORD_PROXY",
    ],
    "slack": [
        "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_RATE_LIMIT_PER_HOUR",
    ],
    "wechat": [
        "WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET",
        "WECOM_TOKEN", "WECOM_ENCODING_AES_KEY", "WECOM_WEBHOOK_PORT",
        "WECHAT_APP_ID", "WECHAT_APP_SECRET", "WECHAT_TOKEN",
        "WECHAT_ENCODING_AES_KEY", "WECHAT_WEBHOOK_PORT",
    ],
    "qq": [
        "QQ_APP_ID", "QQ_APP_SECRET", "QQ_ALLOWED_SENDERS",
        "QQ_RATE_LIMIT_PER_HOUR",
    ],
    "email": [
        "EMAIL_IMAP_HOST", "EMAIL_IMAP_PORT", "EMAIL_IMAP_USERNAME",
        "EMAIL_IMAP_PASSWORD", "EMAIL_IMAP_MAILBOX", "EMAIL_IMAP_USE_SSL",
        "EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT", "EMAIL_SMTP_USERNAME",
        "EMAIL_SMTP_PASSWORD", "EMAIL_SMTP_STARTTLS",
        "EMAIL_FROM_ADDRESS", "EMAIL_POLL_INTERVAL", "EMAIL_MARK_SEEN",
        "EMAIL_ALLOWED_SENDERS",
    ],
    "imessage": [
        "IMESSAGE_CLI_PATH", "IMESSAGE_SERVICE", "IMESSAGE_REGION",
        "IMESSAGE_ALLOWED_SENDERS",
    ],
}

# Keys whose values must be masked in config responses
_SECRET_SUFFIXES = ("_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY", "_KEY")


def _is_channel_configured(name: str) -> bool:
    """Check whether a channel's required env vars are all set."""
    required = _CHANNEL_ENV_KEYS.get(name, [])
    if not required:
        # wechat has two backends — check either
        if name == "wechat":
            return bool(os.environ.get("WECOM_CORP_ID") or os.environ.get("WECHAT_APP_ID"))
        # imessage: always "configured" on macOS, never on other platforms
        if name == "imessage":
            return sys.platform == "darwin"
        return False
    return all(os.environ.get(k) for k in required)


def _mask_value(key: str, value: str) -> str:
    """Mask secret values, showing only the last 4 chars."""
    if not value:
        return ""
    if any(key.upper().endswith(s) for s in _SECRET_SUFFIXES):
        if len(value) <= 4:
            return "****"
        return "*" * (len(value) - 4) + value[-4:]
    return value


def _get_omicsclaw_env_path() -> Path:
    """Return the path to the OmicsClaw project .env file."""
    omicsclaw_dir = os.getenv("OMICSCLAW_DIR", "")
    if omicsclaw_dir:
        return Path(omicsclaw_dir).resolve() / ".env"
    # Fallback: try parent of the bot package location
    try:
        import bot
        return Path(bot.__file__).resolve().parent.parent / ".env"
    except Exception:
        return Path.cwd() / ".env"


def _update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """Update key=value pairs in a .env file, preserving comments and order."""
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        raw_key = stripped.split("=", 1)[0].strip()
        if raw_key.startswith("export "):
            raw_key = raw_key[7:].strip()
        if raw_key in updates:
            new_lines.append(f"{raw_key}={updates[raw_key]}")
            updated_keys.add(raw_key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    for key, value in updates.items():
        os.environ[key] = str(value)

    logger.info("Updated %d key(s) in %s", len(updates), env_path)


# ---- Pydantic models for bridge endpoints --------------------------------

class BridgeStartRequest(BaseModel):
    channels: list[str]


class BridgeStopRequest(BaseModel):
    channels: list[str] = []  # empty = stop all


class BridgeConfigUpdateRequest(BaseModel):
    """Key-value pairs to write into the .env file."""
    # Accept arbitrary env var names as keys
    model_config = {"extra": "allow"}


# ---- GET /bridge/channels ------------------------------------------------

@app.get("/bridge/channels")
async def bridge_list_channels():
    """List all 9 available channels with configuration and running status."""
    global _channel_manager

    try:
        from bot.channels import CHANNEL_REGISTRY
    except ImportError:
        raise HTTPException(503, detail="OmicsClaw channel system not available")

    channels = []
    for name in sorted(CHANNEL_REGISTRY.keys()):
        module_path, class_name = CHANNEL_REGISTRY[name]

        # Check if currently running + health info
        running = False
        stats = {}
        last_error = ""
        if _channel_manager is not None:
            running = name in _channel_manager.running_channels()
            health_data = _channel_manager.get_health()
            ch_health = health_data.get("channel_health", {}).get(name, {})
            stats = {
                "total_inbound": ch_health.get("total_inbound", 0),
                "total_outbound": ch_health.get("total_outbound", 0),
                "total_errors": ch_health.get("total_errors", 0),
            }
            last_error = ch_health.get("last_error", "")

        channels.append({
            "name": name,
            "class": class_name,
            "configured": _is_channel_configured(name),
            "running": running,
            "stats": stats,
            "last_error": last_error,
        })

    return {"channels": channels, "total": len(channels)}


# ---- POST /bridge/start --------------------------------------------------

@app.post("/bridge/start")
async def bridge_start(req: BridgeStartRequest):
    """Start one or more channels via ChannelManager in a background task."""
    global _channel_manager, _bridge_task

    if not req.channels:
        raise HTTPException(400, detail="No channels specified")

    # Validate channel names
    try:
        from bot.channels import CHANNEL_REGISTRY
    except ImportError:
        raise HTTPException(503, detail="OmicsClaw channel system not available")

    unknown = [c for c in req.channels if c not in CHANNEL_REGISTRY]
    if unknown:
        raise HTTPException(
            400,
            detail=f"Unknown channel(s): {', '.join(unknown)}. "
                   f"Available: {', '.join(sorted(CHANNEL_REGISTRY))}",
        )

    try:
        from bot.run import CHANNEL_BUILDERS, _build_middleware
        from bot.channels.manager import ChannelManager
    except ImportError as exc:
        raise HTTPException(503, detail=f"Cannot import channel system: {exc}")

    # Load the OmicsClaw .env so channel builders can read their config
    try:
        from omicsclaw.common.runtime_env import load_env_file
        env_path = _get_omicsclaw_env_path()
        if env_path.exists():
            load_env_file(env_path, override=False)
            logger.info("Loaded OmicsClaw env from %s", env_path)
    except ImportError:
        logger.warning("Could not import load_env_file — env vars may be missing")

    core = _get_core()

    # Skip channels that are already running
    already_running = (
        _channel_manager.running_channels()
        if _channel_manager is not None
        else []
    )
    to_start = [c for c in req.channels if c not in already_running]
    skipped = [c for c in req.channels if c in already_running]

    if not to_start:
        return {
            "ok": True,
            "started": already_running,
            "registered": [],
            "skipped": skipped,
            "errors": None,
        }

    # Build and register each requested channel
    errors = {}
    registered = []

    # If manager already exists, add channels to it; otherwise create a new one
    if _channel_manager is not None:
        manager = _channel_manager
        for name in to_start:
            if name not in CHANNEL_BUILDERS:
                errors[name] = f"No builder for channel '{name}'"
                continue
            try:
                channel = CHANNEL_BUILDERS[name]()
                manager.register(channel)
                await manager.start_channel(name)
                registered.append(name)
                logger.info("Hot-added channel: %s", name)
            except Exception as exc:
                errors[name] = str(exc)
                logger.error("Failed to hot-add channel '%s': %s", name, exc)
    else:
        middleware = _build_middleware()
        manager = ChannelManager(middleware=middleware)
        for name in to_start:
            if name not in CHANNEL_BUILDERS:
                errors[name] = f"No builder for channel '{name}'"
                continue
            try:
                channel = CHANNEL_BUILDERS[name]()
                manager.register(channel)
                registered.append(name)
                logger.info("Built and registered channel: %s", name)
            except Exception as exc:
                errors[name] = str(exc)
                logger.error("Failed to build channel '%s': %s", name, exc)

        if not registered:
            raise HTTPException(
                500,
                detail=f"No channels could be started. Errors: {errors}",
            )

        _channel_manager = manager

        # Run manager in a background asyncio task (don't block FastAPI)
        async def _run_bridge():
            try:
                await manager.start_all()
                logger.info(
                    "Bridge started with %d channel(s): %s",
                    len(manager.running_channels()),
                    ", ".join(manager.running_channels()),
                )
                core.audit(
                    "bridge_start",
                    channels=manager.running_channels(),
                )
                await manager.run()
            except asyncio.CancelledError:
                logger.info("Bridge task cancelled")
            except Exception as exc:
                logger.exception("Bridge task error: %s", exc)
            finally:
                await manager.stop_all()
                logger.info("Bridge stopped")

        _bridge_task = asyncio.create_task(_run_bridge(), name="bridge-manager")

    # Give channels a moment to initialise before responding
    await asyncio.sleep(0.5)

    return {
        "ok": True,
        "started": manager.running_channels(),
        "registered": registered,
        "skipped": skipped if skipped else None,
        "errors": errors if errors else None,
    }


# ---- POST /bridge/stop ---------------------------------------------------

@app.post("/bridge/stop")
async def bridge_stop(req: BridgeStopRequest = BridgeStopRequest()):
    """Stop running channels.

    If ``req.channels`` is provided, stop only those channels (the
    manager keeps running for the remaining ones).  If empty, stop
    everything and tear down the manager.
    """
    global _channel_manager, _bridge_task

    if _channel_manager is None:
        return {"ok": True, "message": "No bridge running", "stopped": []}

    # --- Per-channel stop ---
    if req.channels:
        stopped: list[str] = []
        for name in req.channels:
            if name in _channel_manager.running_channels():
                try:
                    await _channel_manager.stop_channel(name)
                    stopped.append(name)
                except Exception as exc:
                    logger.warning("Error stopping channel '%s': %s", name, exc)
        # If no channels remain, tear down the manager entirely
        if not _channel_manager.running_channels() and not _channel_manager.enabled_channels:
            if _bridge_task and not _bridge_task.done():
                _bridge_task.cancel()
                try:
                    await _bridge_task
                except asyncio.CancelledError:
                    pass
            _channel_manager = None
            _bridge_task = None
        return {"ok": True, "stopped": stopped}

    # --- Stop all ---
    stopped_all = list(_channel_manager.running_channels())

    if _bridge_task and not _bridge_task.done():
        _bridge_task.cancel()
        try:
            await _bridge_task
        except asyncio.CancelledError:
            pass

    try:
        await _channel_manager.stop_all()
    except Exception as exc:
        logger.warning("Error during bridge stop_all: %s", exc)

    _channel_manager = None
    _bridge_task = None

    return {"ok": True, "stopped": stopped_all}


# ---- GET /bridge/status --------------------------------------------------

@app.get("/bridge/status")
async def bridge_status():
    """Return overall bridge status with per-channel health."""
    global _channel_manager

    if _channel_manager is None:
        return {
            "running": False,
            "active_channels": [],
            "health": {},
        }

    health = _channel_manager.get_health()
    return {
        "running": bool(_channel_manager.running_channels()),
        "active_channels": _channel_manager.running_channels(),
        "registered_channels": _channel_manager.enabled_channels,
        "health": health,
    }


# ---- GET /bridge/config/{channel} ----------------------------------------

@app.get("/bridge/config/{channel}")
async def bridge_get_config(channel: str):
    """Return the configuration keys for a specific channel (secrets masked)."""
    if channel not in _CHANNEL_ALL_CONFIG_KEYS:
        raise HTTPException(
            404,
            detail=f"Unknown channel: {channel}. "
                   f"Available: {', '.join(sorted(_CHANNEL_ALL_CONFIG_KEYS))}",
        )

    keys = _CHANNEL_ALL_CONFIG_KEYS[channel]
    config = {}
    for key in keys:
        value = os.environ.get(key, "")
        config[key] = {
            "value": _mask_value(key, value),
            "set": bool(value),
        }

    return {
        "channel": channel,
        "configured": _is_channel_configured(channel),
        "config": config,
    }


# ---- PUT /bridge/config/{channel} ----------------------------------------

@app.put("/bridge/config/{channel}")
async def bridge_update_config(channel: str, request: Request):
    """Update .env file at the OmicsClaw project root with provided key-value pairs."""
    if channel not in _CHANNEL_ALL_CONFIG_KEYS:
        raise HTTPException(
            404,
            detail=f"Unknown channel: {channel}. "
                   f"Available: {', '.join(sorted(_CHANNEL_ALL_CONFIG_KEYS))}",
        )

    body = await request.json()
    if not body or not isinstance(body, dict):
        raise HTTPException(400, detail="Request body must be a JSON object with key-value pairs")

    # Validate that all keys belong to this channel
    allowed_keys = set(_CHANNEL_ALL_CONFIG_KEYS[channel])
    invalid_keys = [k for k in body.keys() if k not in allowed_keys]
    if invalid_keys:
        raise HTTPException(
            400,
            detail=f"Keys not valid for channel '{channel}': {', '.join(invalid_keys)}. "
                   f"Allowed: {', '.join(sorted(allowed_keys))}",
        )

    env_path = _get_omicsclaw_env_path()

    # Read existing .env content
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    # Parse existing key=value pairs, preserving order and comments
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        # Preserve comments and blank lines
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        # Parse KEY=VALUE (handle optional quotes, export prefix)
        eq_idx = stripped.find("=")
        if eq_idx < 0:
            new_lines.append(line)
            continue
        raw_key = stripped[:eq_idx].strip()
        if raw_key.startswith("export "):
            raw_key = raw_key[7:].strip()
        if raw_key in body:
            # Replace this line with the new value
            new_lines.append(f"{raw_key}={body[raw_key]}")
            updated_keys.add(raw_key)
        else:
            new_lines.append(line)

    # Append any keys that were not already in the file
    for key, value in body.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    # Write back
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Also update os.environ so changes take effect immediately
    for key, value in body.items():
        os.environ[key] = str(value)

    logger.info(
        "Updated %d config key(s) for channel '%s' in %s",
        len(body), channel, env_path,
    )

    return {
        "ok": True,
        "channel": channel,
        "updated_keys": list(body.keys()),
        "env_path": str(env_path),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the OmicsClaw desktop/web API server")
    parser.add_argument(
        "--host",
        default=os.getenv("OMICSCLAW_APP_HOST", DEFAULT_APP_API_HOST),
        help=f"Host to bind (default: {DEFAULT_APP_API_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OMICSCLAW_APP_PORT", str(DEFAULT_APP_API_PORT))),
        help=f"Port to bind (default: {DEFAULT_APP_API_PORT})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("OMICSCLAW_APP_RELOAD", "false").lower() in ("true", "1", "yes"),
        help="Enable uvicorn reload mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    """Run the server from command line."""
    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: uvicorn is not installed. "
            f"Install with: {_APP_SERVER_INSTALL_HINT}",
            file=sys.stderr,
        )
        print("Minimal alternative: pip install fastapi uvicorn", file=sys.stderr)
        raise SystemExit(1)

    args = _parse_args(argv)

    logger.info("Starting OmicsClaw app backend on %s:%d", args.host, args.port)
    uvicorn.run(
        "omicsclaw.app.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()

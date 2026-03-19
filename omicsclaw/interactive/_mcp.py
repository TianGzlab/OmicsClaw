"""MCP (Model Context Protocol) server configuration for OmicsClaw.

Stores server configs in ~/.config/omicsclaw/mcp.yaml
Optionally loads tools via langchain_mcp_adapters (if installed).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from ._constants import MCP_CONFIG_NAME

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _get_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    d = base / "omicsclaw"
    d.mkdir(parents=True, exist_ok=True)
    return d


MCP_CONFIG_PATH = _get_config_dir() / MCP_CONFIG_NAME

# Env var interpolation regex
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")

VALID_TRANSPORTS = {"stdio", "http", "streamable_http", "sse", "websocket"}


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def _load_raw() -> dict[str, Any]:
    if not _HAS_YAML:
        return {}
    if not MCP_CONFIG_PATH.is_file():
        return {}
    try:
        data = yaml.safe_load(MCP_CONFIG_PATH.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load MCP config: %s", e)
        return {}


def _save_raw(config: dict[str, Any]) -> None:
    if not _HAS_YAML:
        raise RuntimeError("pyyaml is required to save MCP config. Install with: pip install pyyaml")
    MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    MCP_CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def _interpolate(value: Any) -> Any:
    """Replace ${VAR} placeholders with env var values."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            v = os.environ.get(m.group(1), "")
            if not v:
                logger.warning("MCP config: env var $%s is not set", m.group(1))
            return v
        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def load_mcp_config() -> dict[str, Any]:
    """Load and interpolate MCP config from YAML."""
    return _interpolate(_load_raw())


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_mcp_servers() -> list[dict[str, Any]]:
    """Return list of configured MCP servers with their settings."""
    raw = _load_raw()
    result = []
    for name, cfg in raw.items():
        entry = {"name": name, **cfg}
        result.append(entry)
    return result


def add_mcp_server(
    name: str,
    target: str,
    *,
    extra_args: list[str] | None = None,
    transport: str | None = None,
    env: dict[str, str] | None = None,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    """Add or replace an MCP server.

    Args:
        name: Server name (used as key in config)
        target: Command (stdio) or URL (http/sse/websocket)
        extra_args: Additional args for stdio command
        transport: Transport type (auto-detected from target if None)
        env: Environment variables for stdio (KEY=VALUE pairs)
        tools: Tool allowlist (None = all)

    Returns:
        The server entry that was written.
    """
    if transport is None:
        transport = _infer_transport(target)

    if transport not in VALID_TRANSPORTS:
        raise ValueError(
            f"Unknown transport '{transport}'. Must be one of: {', '.join(sorted(VALID_TRANSPORTS))}"
        )

    entry: dict[str, Any] = {"transport": transport}

    if transport == "stdio":
        entry["command"] = target
        entry["args"] = list(extra_args) if extra_args else []
        if env:
            entry["env"] = env
    else:
        entry["url"] = target

    if tools:
        entry["tools"] = tools

    raw = _load_raw()
    raw[name] = entry
    _save_raw(raw)
    return entry


def remove_mcp_server(name: str) -> bool:
    """Remove an MCP server from config. Returns True if removed."""
    raw = _load_raw()
    if name not in raw:
        return False
    del raw[name]
    _save_raw(raw)
    return True


def _infer_transport(target: str) -> str:
    if target.startswith(("ws://", "wss://")):
        return "websocket"
    if target.startswith(("http://", "https://")):
        return "http"
    return "stdio"


# ---------------------------------------------------------------------------
# Tool loading (optional — requires langchain_mcp_adapters)
# ---------------------------------------------------------------------------

async def load_mcp_tools_as_openai_functions() -> list[dict]:
    """Load all MCP tools and convert to OpenAI function-calling format.

    Returns empty list if no MCP servers configured or adapters not installed.
    """
    config = load_mcp_config()
    if not config:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.debug("langchain_mcp_adapters not installed — MCP tools unavailable")
        return []

    connections: dict[str, Any] = {}
    for name, server in config.items():
        transport = server.get("transport", "")
        if transport == "stdio":
            connections[name] = {
                "transport": "stdio",
                "command": server.get("command", ""),
                "args": server.get("args", []),
                **({"env": server["env"]} if "env" in server else {}),
            }
        elif transport in {"http", "streamable_http", "sse", "websocket"}:
            connections[name] = {
                "transport": transport,
                "url": server.get("url", ""),
            }

    if not connections:
        return []

    openai_tools: list[dict] = []
    try:
        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.args_schema.schema() if hasattr(tool, "args_schema") else {"type": "object", "properties": {}},
                },
                "_mcp": True,  # tag for dispatch
            })
        logger.info("Loaded %d MCP tool(s) from %d server(s)", len(openai_tools), len(connections))
    except Exception as e:
        logger.warning("MCP tool loading failed: %s", e)

    return openai_tools

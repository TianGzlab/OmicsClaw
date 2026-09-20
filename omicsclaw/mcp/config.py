"""Reading ``.mcp.json``: which MCP servers to connect, and how.

The file uses the ``mcpServers`` shape most MCP clients share::

    {
      "mcpServers": {
        "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "remote": {
          "type": "http",
          "url": "https://example.org/mcp",
          "headers": {"Authorization": "Bearer ${REMOTE_TOKEN}"}
        }
      }
    }

Per server:

``type`` / ``transport``
    ``"stdio"`` or ``"http"`` (``"streamable-http"`` and
    ``"streamable_http"`` are accepted spellings of ``"http"``). When
    omitted it is inferred: ``command`` means stdio, ``url`` means http.
    ``"sse"`` and ``"websocket"`` are rejected as unsupported.
``command``, ``args``, ``env``
    The stdio server's program, its arguments, and extra environment
    variables — an object, or a list of ``"KEY=VALUE"`` strings.
``url``, ``headers``
    The HTTP server's endpoint and request headers.
``enabled`` / ``disabled``
    A server can be switched off without deleting it.
``tools``
    An allowlist of the server's own tool names; absent means all.

``${VAR}`` and ``${VAR:-default}`` are expanded in ``command``, ``args``,
``env`` values, ``url`` and ``headers`` values. Unknown keys are ignored.

A missing file is an empty configuration. A file that cannot be read or
parsed raises :exc:`MCPConfigError`. An invalid entry is *rejected* — kept
on :attr:`MCPConfig.rejected` with its reason — and the other entries still
load.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

__all__ = [
    "MCPConfig",
    "MCPConfigError",
    "RejectedServer",
    "ServerConfig",
    "TransportKind",
    "load_mcp_config",
    "parse_mcp_config",
]

SERVERS_KEY = "mcpServers"

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

_EMPTY: Mapping[str, str] = MappingProxyType({})


class MCPConfigError(ValueError):
    """The configuration file as a whole cannot be used."""


class TransportKind(StrEnum):
    """How a client reaches a server."""

    STDIO = "stdio"
    HTTP = "http"


_TRANSPORT_SPELLINGS: Mapping[str, TransportKind] = {
    "stdio": TransportKind.STDIO,
    "http": TransportKind.HTTP,
    "streamable-http": TransportKind.HTTP,
    "streamable_http": TransportKind.HTTP,
}

_UNSUPPORTED_TRANSPORTS = frozenset({"sse", "websocket", "ws"})


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """One server entry, validated and with variables expanded."""

    name: str
    kind: TransportKind
    command: str = ""
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=lambda: _EMPTY)
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=lambda: _EMPTY)
    enabled: bool = True
    tools: tuple[str, ...] | None = None
    """Allowlist of the server's own tool names; ``None`` allows all."""


@dataclass(frozen=True, slots=True)
class RejectedServer:
    """An entry that could not be used, and why."""

    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class MCPConfig:
    """Every server entry of one file, in file order."""

    servers: tuple[ServerConfig, ...] = ()
    rejected: tuple[RejectedServer, ...] = ()
    source: Path | None = None

    @property
    def is_empty(self) -> bool:
        """True when the file named no server at all, valid or not."""
        return not self.servers and not self.rejected


def load_mcp_config(
    path: Path,
    env: Mapping[str, str] | None = None,
) -> MCPConfig:
    """Read *path*, expanding variables from *env* (default ``os.environ``).

    Returns an empty :class:`MCPConfig` when *path* does not exist. Raises
    :exc:`MCPConfigError` when it exists but cannot be read or is not a
    JSON object with an ``mcpServers`` object inside.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return MCPConfig(source=path)
    except (OSError, UnicodeDecodeError) as exc:
        raise MCPConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise MCPConfigError(f"{path} is not valid JSON: {exc}") from exc
    try:
        config = parse_mcp_config(data, env)
    except MCPConfigError as exc:
        raise MCPConfigError(f"{path}: {exc}") from exc
    return MCPConfig(config.servers, config.rejected, source=path)


def parse_mcp_config(
    data: Any,
    env: Mapping[str, str] | None = None,
) -> MCPConfig:
    """Validate an already-decoded configuration document.

    Raises :exc:`MCPConfigError` when *data* is not an object or its
    ``mcpServers`` value is not an object. A document without
    ``mcpServers`` is an empty configuration.
    """
    if not isinstance(data, Mapping):
        raise MCPConfigError(
            f"the top level must be a JSON object, not {_json_type(data)}"
        )
    entries = data.get(SERVERS_KEY, {})
    if not isinstance(entries, Mapping):
        raise MCPConfigError(
            f"{SERVERS_KEY!r} must be an object, not {_json_type(entries)}"
        )

    variables = os.environ if env is None else env
    servers: list[ServerConfig] = []
    rejected: list[RejectedServer] = []
    for name, entry in entries.items():
        try:
            servers.append(_parse_server(str(name), entry, variables))
        except _Rejected as exc:
            rejected.append(RejectedServer(str(name), str(exc)))
    return MCPConfig(tuple(servers), tuple(rejected))


# ---- internals ----------------------------------------------------------


class _Rejected(ValueError):
    """One entry is unusable; the message says why."""


def _parse_server(
    name: str,
    entry: Any,
    variables: Mapping[str, str],
) -> ServerConfig:
    if not name.strip():
        raise _Rejected("a server needs a non-empty name")
    if not isinstance(entry, Mapping):
        raise _Rejected(f"the entry must be an object, not {_json_type(entry)}")

    kind = _transport_kind(entry)
    enabled = _enabled(entry)
    tools = _allowlist(entry.get("tools"))

    if kind is TransportKind.STDIO:
        command = _expand(_string(entry, "command"), variables)
        if not command.strip():
            raise _Rejected("a stdio server needs a non-empty 'command'")
        return ServerConfig(
            name=name,
            kind=kind,
            command=command,
            args=tuple(_expand(arg, variables) for arg in _strings(entry, "args")),
            env=_frozen(_expand_values(_env(entry.get("env")), variables)),
            enabled=enabled,
            tools=tools,
        )

    url = _expand(_string(entry, "url"), variables).strip()
    if not url.startswith(("http://", "https://")):
        raise _Rejected(f"an http server needs an http(s) 'url', got {url!r}")
    return ServerConfig(
        name=name,
        kind=kind,
        url=url,
        headers=_frozen(_expand_values(_string_map(entry, "headers"), variables)),
        enabled=enabled,
        tools=tools,
    )


def _transport_kind(entry: Mapping[str, Any]) -> TransportKind:
    declared = [
        entry[key].strip().lower()
        for key in ("type", "transport")
        if isinstance(entry.get(key), str) and entry[key].strip()
    ]
    for key in ("type", "transport"):
        if key in entry and not isinstance(entry[key], str):
            raise _Rejected(f"'{key}' must be a string")
    if len(set(declared)) > 1:
        raise _Rejected(
            f"'type' and 'transport' disagree ({declared[0]!r} vs {declared[1]!r})"
        )
    if declared:
        spelled = declared[0]
        if spelled in _UNSUPPORTED_TRANSPORTS:
            raise _Rejected(
                f"transport {spelled!r} is not supported; use stdio or "
                "streamable http"
            )
        kind = _TRANSPORT_SPELLINGS.get(spelled)
        if kind is None:
            raise _Rejected(f"unknown transport {spelled!r}")
        return kind

    has_command = bool(entry.get("command"))
    has_url = bool(entry.get("url"))
    if has_command and has_url:
        raise _Rejected("both 'command' and 'url' are set; add a 'type'")
    if has_command:
        return TransportKind.STDIO
    if has_url:
        return TransportKind.HTTP
    raise _Rejected("needs a 'command' (stdio) or a 'url' (http)")


def _enabled(entry: Mapping[str, Any]) -> bool:
    enabled = entry.get("enabled", True)
    disabled = entry.get("disabled", False)
    if not isinstance(enabled, bool) or not isinstance(disabled, bool):
        raise _Rejected("'enabled' and 'disabled' must be true or false")
    return enabled and not disabled


def _allowlist(raw: Any) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise _Rejected("'tools' must be a list of tool names")
    return tuple(raw)


def _string(entry: Mapping[str, Any], key: str) -> str:
    value = entry.get(key, "")
    if not isinstance(value, str):
        raise _Rejected(f"'{key}' must be a string, not {_json_type(value)}")
    return value


def _strings(entry: Mapping[str, Any], key: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _Rejected(f"'{key}' must be a list of strings")
    return value


def _string_map(entry: Mapping[str, Any], key: str) -> dict[str, str]:
    value = entry.get(key, {})
    if not isinstance(value, Mapping) or not all(
        isinstance(item, str) for item in value.values()
    ):
        raise _Rejected(f"'{key}' must be an object of strings")
    return {str(k): v for k, v in value.items()}


def _env(raw: Any) -> dict[str, str]:
    """``env`` as an object, or as a list of ``KEY=VALUE`` strings."""
    if raw is None:
        return {}
    if isinstance(raw, list):
        pairs: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, str) or "=" not in item:
                raise _Rejected("'env' list items must look like 'KEY=VALUE'")
            key, _, value = item.partition("=")
            if not key:
                raise _Rejected("'env' list items must look like 'KEY=VALUE'")
            pairs[key] = value
        return pairs
    return _string_map({"env": raw}, "env")


def _expand(text: str, variables: Mapping[str, str]) -> str:
    """Replace ``${VAR}`` and ``${VAR:-default}``; reject an unset ``${VAR}``."""

    def substitute(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        value = variables.get(name)
        if default is not None:
            return value if value else default
        if value is None:
            raise _Rejected(f"environment variable {name} is not set")
        return value

    return _VARIABLE.sub(substitute, text)


def _expand_values(
    values: Mapping[str, str],
    variables: Mapping[str, str],
) -> dict[str, str]:
    return {key: _expand(value, variables) for key, value in values.items()}


def _frozen(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values)) if values else _EMPTY


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    return type(value).__name__

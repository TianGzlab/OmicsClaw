"""Every configured MCP server: connecting, reporting, and handing over tools.

:class:`MCPManager` connects all enabled servers concurrently, each within
its own timeout. A server that fails is recorded as failed and the others
carry on. Once connected, :meth:`MCPManager.tools` returns each server's
tools as :class:`~omicsclaw.tools.MCPTool` objects named
``mcp__{server}__{tool}``, ready for a :class:`~omicsclaw.tools.ToolRegistry`.
Each tool's output is cut to ``max_output_chars`` before the model sees it,
and its approval prompt names where the call goes.

The tool set is fixed when :meth:`MCPManager.start` returns; servers that
later announce changed tools are not re-listed. A manager belongs to the
event loop that started it.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from omicsclaw.tools import MCPTool

from .client import MCPClient, MCPToolError, ServerInfo
from .config import MCPConfig, ServerConfig, TransportKind
from .stdio import StdioTransport
from .streamable_http import DEFAULT_TIMEOUT_S, HTTPTransport, redact_url
from .transport import MCPError, Transport

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_S",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "MCPManager",
    "ServerState",
    "ServerStatus",
    "StatusListener",
    "ToolDetail",
    "TransportFactory",
    "open_transport",
    "origin_of",
    "truncate_output",
]

DEFAULT_CONNECT_TIMEOUT_S = 30.0
"""How long one server may take to start and finish the handshake."""

DEFAULT_MAX_OUTPUT_CHARS = 32_000
"""Characters of one tool result passed on to the model."""


class ServerState(StrEnum):
    """Where one server's connection stands."""

    PENDING = "pending"
    CONNECTED = "connected"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ToolDetail:
    """One mounted tool: its registry name, its own name, its description."""

    name: str
    tool: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ServerStatus:
    """A snapshot of one server, for display."""

    name: str
    state: ServerState
    transport: str = ""
    tools: tuple[ToolDetail, ...] = ()
    skipped: tuple[str, ...] = ()
    """Tools the server offered, or the allowlist named, that were not
    mounted — each entry says which and why."""
    error: str = ""
    info: ServerInfo | None = None


StatusListener = Callable[[tuple[ServerStatus, ...]], None]
"""Called with every server's status each time one of them changes."""

TransportFactory = Callable[[ServerConfig], Transport]


def open_transport(
    server: ServerConfig,
    *,
    cwd: Path | None = None,
    request_timeout_s: float | None = DEFAULT_TIMEOUT_S,
) -> Transport:
    """The transport *server* is configured for, not yet started."""
    if server.kind is TransportKind.STDIO:
        return StdioTransport(server.command, server.args, env=server.env, cwd=cwd)
    return HTTPTransport(
        server.url, headers=server.headers, timeout_s=request_timeout_s
    )


def origin_of(server: ServerConfig) -> str:
    """Where *server*'s tool calls go, for a human deciding whether to allow one."""
    if server.kind is TransportKind.STDIO:
        return f"local process {server.command}"
    return f"remote {redact_url(server.url)}"


def truncate_output(text: str, limit: int) -> str:
    """*text* cut to *limit* characters, with a line saying how much was cut.

    ``limit <= 0`` means no limit.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    return (
        f"{text[:limit]}\n\n[output truncated: showing the first {limit} of "
        f"{len(text)} characters]"
    )


class MCPManager:
    """The connections to every server in one :class:`MCPConfig`.

    Usable as an async context manager: entering starts every server,
    leaving closes them.
    """

    def __init__(
        self,
        config: MCPConfig,
        *,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        cwd: Path | None = None,
        request_timeout_s: float | None = DEFAULT_TIMEOUT_S,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        on_change: StatusListener | None = None,
        transport_factory: TransportFactory | None = None,
    ) -> None:
        """Raises :exc:`ValueError` unless *connect_timeout_s* is positive.

        *request_timeout_s* is the socket timeout of an HTTP server's
        requests; ``None`` or ``<= 0`` waits indefinitely.
        """
        if not connect_timeout_s > 0:
            raise ValueError(
                f"connect_timeout_s must be positive, got {connect_timeout_s!r}"
            )
        self._config = config
        self._connect_timeout_s = connect_timeout_s
        self._max_output_chars = max_output_chars
        self._on_change = on_change
        self._open = transport_factory or functools.partial(
            open_transport, cwd=cwd, request_timeout_s=request_timeout_s
        )
        self._statuses: dict[str, ServerStatus] = {}
        self._clients: dict[str, MCPClient] = {}
        self._tools: tuple[MCPTool, ...] = ()
        self._started = False
        self._closed = False

    @property
    def config(self) -> MCPConfig:
        return self._config

    async def start(self) -> tuple[ServerStatus, ...]:
        """Connect every enabled server, concurrently. Returns the outcome.

        Each server gets ``connect_timeout_s``; one that has not finished
        its handshake by then is killed. Never raises for a server that
        fails to connect: its status says why. Raises :exc:`RuntimeError`
        if called twice.
        """
        if self._started:
            raise RuntimeError("this MCP manager has already been started")
        self._started = True

        for rejected in self._config.rejected:
            self._statuses[rejected.name] = ServerStatus(
                rejected.name, ServerState.FAILED, error=rejected.reason
            )
        enabled = []
        for server in self._config.servers:
            state = ServerState.PENDING if server.enabled else ServerState.DISABLED
            self._statuses[server.name] = ServerStatus(
                server.name, state, transport=server.kind.value
            )
            if server.enabled:
                enabled.append(server)
        self._notify()

        try:
            await asyncio.gather(*(self._connect(server) for server in enabled))
        except BaseException:
            await self.aclose()
            raise
        self._tools = self._mount()
        self._notify()
        return self.statuses()

    def tools(self) -> tuple[MCPTool, ...]:
        """Every mounted tool, servers in configuration order.

        Within a server, tools keep the server's order and are filtered by
        its allowlist. A tool whose registry name is already taken is left
        out and recorded in :attr:`ServerStatus.skipped`.
        """
        return self._tools

    def statuses(self) -> tuple[ServerStatus, ...]:
        """Every server's status: configured servers first, then rejected ones."""
        return tuple(self._statuses.values())

    async def aclose(self) -> None:
        """Close every connection. Idempotent."""
        if self._closed:
            return
        self._closed = True
        clients, self._clients = self._clients, {}
        await asyncio.gather(
            *(client.aclose() for client in clients.values()),
            return_exceptions=True,
        )

    async def __aenter__(self) -> MCPManager:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---- internals ------------------------------------------------------

    async def _connect(self, server: ServerConfig) -> None:
        try:
            client = MCPClient(server.name, self._open(server))
            async with asyncio.timeout(self._connect_timeout_s):
                info = await client.connect()
        except TimeoutError:
            self._fail(
                server,
                f"did not finish connecting within {self._connect_timeout_s:g}s",
            )
            return
        except MCPError as exc:
            self._fail(server, str(exc) or type(exc).__name__)
            return
        except Exception as exc:
            self._fail(server, f"{type(exc).__name__}: {exc}")
            return

        if self._closed:
            await client.aclose()
            return
        self._clients[server.name] = client
        self._update(server.name, state=ServerState.CONNECTED, info=info)

    def _fail(self, server: ServerConfig, reason: str) -> None:
        self._update(server.name, state=ServerState.FAILED, error=reason)

    def _mount(self) -> tuple[MCPTool, ...]:
        taken: set[str] = set()
        mounted: list[MCPTool] = []
        for server in self._config.servers:
            client = self._clients.get(server.name)
            if client is None:
                continue
            details: list[ToolDetail] = []
            skipped: list[str] = []
            if client.unnamed_tools:
                skipped.append(f"{client.unnamed_tools} listed tool(s) had no name")
            offered = {remote.name for remote in client.tools}
            for missing in server.tools or ():
                if missing not in offered:
                    skipped.append(f"{missing}: named in 'tools' but not offered")
            for remote in client.tools:
                if server.tools is not None and remote.name not in server.tools:
                    continue
                tool = MCPTool(
                    server.name,
                    remote.name,
                    caller=functools.partial(self._call, client, remote.name),
                    description=remote.description,
                    input_schema=remote.input_schema,
                    origin=origin_of(server),
                )
                if tool.name in taken:
                    skipped.append(f"{remote.name}: {tool.name} is already taken")
                    continue
                taken.add(tool.name)
                mounted.append(tool)
                details.append(ToolDetail(tool.name, remote.name, remote.description))
            self._update(server.name, tools=tuple(details), skipped=tuple(skipped))
        return tuple(mounted)

    async def _call(self, client: MCPClient, tool: str, arguments: str) -> str:
        limit = self._max_output_chars
        try:
            return truncate_output(await client.call_tool(tool, arguments), limit)
        except MCPToolError as exc:
            raise MCPToolError(truncate_output(str(exc), limit)) from None

    def _update(self, name: str, **changes: object) -> None:
        self._statuses[name] = replace(self._statuses[name], **changes)
        self._notify()

    def _notify(self) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(self.statuses())
        except Exception:
            pass

"""One MCP server, seen from the client side: handshake, tools, calls.

:meth:`MCPClient.connect` performs the handshake —
``initialize`` → ``notifications/initialized`` → ``tools/list`` (following
``nextCursor`` across pages) — and :meth:`MCPClient.call_tool` runs one
tool and renders its result as text. The transport is supplied by the
caller, so the client does not know whether the server is a subprocess or
a URL.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from omicsclaw.version import __version__

from .transport import MCPError, MCPProtocolError, Transport

__all__ = [
    "CLIENT_NAME",
    "MAX_TOOL_PAGES",
    "MCPClient",
    "MCPToolError",
    "PROTOCOL_VERSION",
    "RemoteTool",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "ServerInfo",
    "render_result",
]

PROTOCOL_VERSION = "2025-06-18"
"""The version this client asks for."""

SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18"})
"""Versions a server may answer with. Any other fails the handshake."""

CLIENT_NAME = "omicsclaw"

MAX_TOOL_PAGES = 100
"""Pages of ``tools/list`` followed before the listing is refused."""


class MCPToolError(MCPError):
    """A tool ran and reported failure (``isError``); the message is its output."""


@dataclass(frozen=True, slots=True)
class RemoteTool:
    """One tool as the server lists it."""

    name: str
    description: str = ""
    input_schema: Any = None
    title: str = ""


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """What the server said about itself during the handshake."""

    name: str = ""
    version: str = ""
    protocol_version: str = ""
    instructions: str = ""


class MCPClient:
    """The client half of one MCP connection."""

    def __init__(self, name: str, transport: Transport) -> None:
        self.name = name
        self._transport = transport
        self._tools: tuple[RemoteTool, ...] = ()
        self._unnamed = 0
        self._info: ServerInfo | None = None

    @property
    def tools(self) -> tuple[RemoteTool, ...]:
        """The tools listed during :meth:`connect`, in the server's order."""
        return self._tools

    @property
    def unnamed_tools(self) -> int:
        """Entries of ``tools/list`` that had no name and were left out."""
        return self._unnamed

    @property
    def info(self) -> ServerInfo | None:
        """The server's self-description, once connected."""
        return self._info

    async def connect(self) -> ServerInfo:
        """Start the transport, shake hands and list the server's tools.

        On any failure — including cancellation — the transport is closed
        before the exception propagates. Raises :exc:`MCPProtocolError`
        when the server picks a protocol version this client does not
        support.
        """
        try:
            await self._transport.start()
            initialized = await self._transport.request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": CLIENT_NAME, "version": __version__},
                },
            )
            info = _server_info(initialized)
            self._transport.negotiated(info.protocol_version)
            await self._transport.notify("notifications/initialized")
            self._tools = await self._list_tools()
        except BaseException:
            await self._transport.aclose()
            raise
        self._info = info
        return info

    async def call_tool(self, name: str, arguments: str) -> str:
        """Call tool *name* with the model's raw JSON *arguments*.

        Returns the result as text (see :func:`render_result`). Raises
        :exc:`ValueError` when *arguments* is not a JSON object, and
        :exc:`MCPToolError` when the tool reports ``isError``.
        """
        params = {"name": name, "arguments": _arguments_object(arguments)}
        result = await self._transport.request("tools/call", params)
        text, is_error = render_result(result)
        if is_error:
            raise MCPToolError(text or f"{name} reported an error without a message")
        return text

    async def aclose(self) -> None:
        """Close the connection."""
        await self._transport.aclose()

    async def _list_tools(self) -> tuple[RemoteTool, ...]:
        """Every listed tool. Entries without a name are counted and skipped."""
        tools: list[RemoteTool] = []
        cursor: str | None = None
        for _ in range(MAX_TOOL_PAGES):
            params = {"cursor": cursor} if cursor else None
            page = await self._transport.request("tools/list", params)
            if not isinstance(page, Mapping) or not isinstance(page.get("tools"), list):
                raise MCPProtocolError("tools/list did not return a list of tools")
            for entry in page["tools"]:
                tool = _remote_tool(entry)
                if tool is None:
                    self._unnamed += 1
                else:
                    tools.append(tool)
            cursor = page.get("nextCursor")
            if not cursor:
                return tuple(tools)
        raise MCPProtocolError(f"tools/list did not end within {MAX_TOOL_PAGES} pages")


def render_result(result: Any) -> tuple[str, bool]:
    """A ``tools/call`` result as ``(text, is_error)``.

    Text blocks, and the text of embedded text resources, are joined with
    newlines. Other blocks become one bracketed line saying what was left
    out. ``structuredContent`` is used when there is no text at all.
    """
    if not isinstance(result, Mapping):
        raise MCPProtocolError("tools/call did not return an object")
    content = result.get("content")
    blocks = content if isinstance(content, list) else []
    text = "\n".join(part for part in map(_render_block, blocks) if part)
    structured = result.get("structuredContent")
    if not text and structured is not None:
        text = json.dumps(structured, ensure_ascii=False)
    return text, result.get("isError") is True


# ---- internals ----------------------------------------------------------


def _server_info(result: Any) -> ServerInfo:
    if not isinstance(result, Mapping):
        raise MCPProtocolError("initialize did not return an object")
    version = result.get("protocolVersion")
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_PROTOCOL_VERSIONS))
        raise MCPProtocolError(
            f"the server chose protocol version {version!r}; this client "
            f"supports {supported}"
        )
    about = result.get("serverInfo")
    about = about if isinstance(about, Mapping) else {}
    instructions = result.get("instructions")
    return ServerInfo(
        name=str(about.get("name", "")),
        version=str(about.get("version", "")),
        protocol_version=version,
        instructions=instructions if isinstance(instructions, str) else "",
    )


def _remote_tool(entry: Any) -> RemoteTool | None:
    if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
        return None
    if not entry["name"]:
        return None
    description = entry.get("description")
    title = entry.get("title")
    return RemoteTool(
        name=entry["name"],
        description=description if isinstance(description, str) else "",
        input_schema=entry.get("inputSchema"),
        title=title if isinstance(title, str) else "",
    )


def _arguments_object(arguments: str) -> dict[str, Any]:
    if not arguments.strip():
        return {}
    try:
        decoded = json.loads(arguments)
    except ValueError as exc:
        raise ValueError(f"arguments are not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError(
            f"arguments must be a JSON object, not {type(decoded).__name__}"
        )
    return decoded


def _render_block(block: Any) -> str:
    if not isinstance(block, Mapping):
        return ""
    kind = block.get("type")
    if kind == "text":
        text = block.get("text")
        return text if isinstance(text, str) else ""
    if kind == "resource":
        resource = block.get("resource")
        resource = resource if isinstance(resource, Mapping) else {}
        if isinstance(resource.get("text"), str):
            return resource["text"]
        return (
            f"[binary resource {resource.get('uri', '')} "
            f"({resource.get('mimeType', 'unknown type')}) not shown]"
        )
    if kind == "resource_link":
        return f"[resource link: {block.get('name', '')} {block.get('uri', '')}]"
    if kind in ("image", "audio"):
        data = block.get("data")
        size = len(data) if isinstance(data, str) else 0
        return (
            f"[{kind} ({block.get('mimeType', 'unknown type')}, "
            f"{size} base64 characters) not shown]"
        )
    return f"[content of type {kind!r} not shown]"


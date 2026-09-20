"""The channel an MCP client talks over, and the JSON-RPC 2.0 framing on it.

A :class:`Transport` carries requests and notifications and returns
results. It knows nothing about MCP methods: the handshake and tool calls
live in :mod:`omicsclaw.mcp.client`, and the two implementations are
:class:`~omicsclaw.mcp.stdio.StdioTransport` and
:class:`~omicsclaw.mcp.streamable_http.HTTPTransport`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "JSONRPC_VERSION",
    "MCPError",
    "MCPProtocolError",
    "MCPRemoteError",
    "MCPTransportError",
    "MessageKind",
    "Transport",
    "classify",
    "encode",
    "error_response",
    "is_request_id",
    "notification",
    "request",
    "result_of",
    "success_response",
]

JSONRPC_VERSION = "2.0"

METHOD_NOT_FOUND = -32601

MessageKind = Literal["response", "request", "notification", "invalid"]


class MCPError(Exception):
    """Base class for every failure raised by :mod:`omicsclaw.mcp`."""


class MCPTransportError(MCPError):
    """The channel failed, or was closed, before an answer arrived."""


class MCPProtocolError(MCPError):
    """The server answered with something the protocol does not allow."""


class MCPRemoteError(MCPError):
    """The server answered a request with a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"server error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


@runtime_checkable
class Transport(Protocol):
    """One connection to one server.

    ``request`` and ``notify`` may be called concurrently once ``start``
    has returned. Cancelling a ``request`` abandons it without closing the
    transport. After ``aclose`` every call raises
    :exc:`MCPTransportError`; ``aclose`` itself may be called repeatedly.
    """

    async def start(self) -> None:
        """Open the channel (spawn the process, or nothing for HTTP)."""
        ...

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Send a request and return its ``result``.

        Raises :exc:`MCPRemoteError` for an error response and
        :exc:`MCPTransportError` when no response can arrive.
        """
        ...

    async def notify(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a notification; nothing comes back."""
        ...

    def negotiated(self, protocol_version: str) -> None:
        """Record the protocol version the handshake settled on."""
        ...

    async def aclose(self) -> None:
        """Close the channel and release what it holds."""
        ...


def encode(message: Mapping[str, Any]) -> bytes:
    """*message* as compact UTF-8 JSON. Never contains a raw newline."""
    text = json.dumps(
        message, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return text.encode("utf-8")


def is_request_id(value: Any, request_id: int) -> bool:
    """Whether *value* is the id *request_id*; ``true`` is not ``1``."""
    return type(value) is int and value == request_id


def request(
    request_id: int,
    method: str,
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """A request object."""
    message: dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "method": method,
    }
    if params is not None:
        message["params"] = dict(params)
    return message


def notification(
    method: str,
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """A notification object: a request without an id."""
    message: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        message["params"] = dict(params)
    return message


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    """A response carrying *result* for a request the server sent."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """A response carrying an error for a request the server sent."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def classify(message: Any) -> MessageKind:
    """Which of the three JSON-RPC message kinds *message* is.

    A message with both an ``id`` and a ``method`` is a request *from the
    server*, never a response to one of ours, even when the ids coincide.
    """
    if not isinstance(message, Mapping):
        return "invalid"
    has_id = message.get("id") is not None
    has_method = isinstance(message.get("method"), str)
    if has_method:
        return "request" if has_id else "notification"
    if has_id and ("result" in message or "error" in message):
        return "response"
    return "invalid"


def result_of(response: Mapping[str, Any]) -> Any:
    """The ``result`` of a response, or :exc:`MCPRemoteError` for an error."""
    error = response.get("error")
    if error is not None:
        if isinstance(error, Mapping):
            code = error.get("code")
            raise MCPRemoteError(
                code if isinstance(code, int) else 0,
                str(error.get("message", "")),
                error.get("data"),
            )
        raise MCPRemoteError(0, str(error))
    return response.get("result")

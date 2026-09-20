"""A server reached over Streamable HTTP: one ``POST`` per message.

Each request is posted with ``Accept: application/json, text/event-stream``
and the answer is read from either a JSON body or an event stream. A
session id the server assigns (``Mcp-Session-Id``) is sent back on every
later message, the negotiated protocol version travels in
``MCP-Protocol-Version``, and closing the transport ends the session with a
``DELETE``.

Redirects are refused rather than followed, so configured headers are
never re-sent to a host nobody configured. Error messages show the URL
without its user-info and query, where credentials tend to live.

Each request runs on its own daemon thread. Cancelling one returns
immediately; the thread finishes within the socket timeout and never
holds up the process exiting.
"""

from __future__ import annotations

import asyncio
import http.client
import itertools
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeVar

from .transport import (
    MCPProtocolError,
    MCPTransportError,
    classify,
    encode,
    is_request_id,
    notification,
    request,
    result_of,
)

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "HTTPTransport",
    "MAX_RESPONSE_BYTES",
    "PROTOCOL_VERSION_HEADER",
    "SESSION_HEADER",
]

SESSION_HEADER = "Mcp-Session-Id"
PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"
ACCEPT = "application/json, text/event-stream"

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
"""Largest response body read before the request is failed."""

DEFAULT_TIMEOUT_S = 600.0
"""Socket timeout for one request: how long the server may stay silent.
``None`` or ``<= 0`` waits indefinitely."""

_CLOSE_TIMEOUT_S = 5.0
_ERROR_SNIPPET_BYTES = 500

_T = TypeVar("_T")


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Turn every redirect into the HTTP error it came as."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class HTTPTransport:
    """A :class:`~omicsclaw.mcp.transport.Transport` over Streamable HTTP."""

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = DEFAULT_TIMEOUT_S,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self._url = url
        self._shown_url = redact_url(url)
        self._headers = dict(headers or {})
        self._timeout_s = timeout_s if timeout_s is not None and timeout_s > 0 else None
        self._opener = opener or urllib.request.build_opener(_RefuseRedirects())
        self._ids = itertools.count(1)
        self._session_id = ""
        self._protocol_version = ""
        self._started = False
        self._closed = ""

    @property
    def session_id(self) -> str:
        """The session the server assigned, or ``""``."""
        return self._session_id

    async def start(self) -> None:
        """Nothing to open: every message is its own request."""
        if self._closed:
            raise MCPTransportError(self._closed)
        self._started = True

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Post a request and return its result."""
        self._ensure_open()
        request_id = next(self._ids)
        payload = encode(request(request_id, method, params))
        response = await _in_daemon_thread(self._post, payload, request_id)
        return result_of(response)

    async def notify(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Post a notification; the body of the answer is ignored."""
        self._ensure_open()
        await _in_daemon_thread(self._post, encode(notification(method, params)), None)

    def negotiated(self, protocol_version: str) -> None:
        """Send *protocol_version* on every later message."""
        self._protocol_version = protocol_version

    async def aclose(self) -> None:
        """End the server-side session, if there is one. Idempotent."""
        if self._closed:
            return
        self._closed = "the transport was closed"
        if self._session_id:
            try:
                await asyncio.wait_for(
                    _in_daemon_thread(self._delete_session), _CLOSE_TIMEOUT_S
                )
            except Exception:
                pass

    # ---- internals ------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._closed:
            raise MCPTransportError(self._closed)
        if not self._started:
            raise MCPTransportError("the transport has not been started")

    def _message_headers(self) -> dict[str, str]:
        headers = dict(self._headers)
        if self._session_id:
            headers[SESSION_HEADER] = self._session_id
        if self._protocol_version:
            headers[PROTOCOL_VERSION_HEADER] = self._protocol_version
        return headers

    def _post(self, payload: bytes, request_id: int | None) -> Mapping[str, Any] | None:
        headers = self._message_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = ACCEPT
        outgoing = urllib.request.Request(
            self._url, data=payload, headers=headers, method="POST"
        )
        with self._open(outgoing) as response:
            assigned = response.headers.get(SESSION_HEADER)
            if assigned:
                self._session_id = assigned
            if request_id is None:
                return None
            content_type = response.headers.get_content_type()
            if content_type == "application/json":
                return _matching(json_messages(_read_capped(response)), request_id)
            if content_type == "text/event-stream":
                return _matching(event_messages(response), request_id)
            raise MCPProtocolError(
                f"the server answered with {content_type!r}, not JSON or an "
                "event stream"
            )

    def _open(self, outgoing: urllib.request.Request) -> http.client.HTTPResponse:
        try:
            return self._opener.open(outgoing, timeout=self._timeout_s)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            reason = getattr(exc, "reason", exc)
            raise MCPTransportError(
                f"cannot reach {self._shown_url}: {reason}"
            ) from exc

    def _http_error(self, exc: urllib.error.HTTPError) -> MCPTransportError:
        if 300 <= exc.code < 400:
            target = exc.headers.get("Location", "") if exc.headers else ""
            return MCPTransportError(
                f"{self._shown_url} redirected (HTTP {exc.code}) to "
                f"{redact_url(target)!r}; redirects are not followed, "
                "configure the final URL"
            )
        if exc.code == 404 and self._session_id:
            return MCPTransportError(
                "the server no longer recognises this session (HTTP 404); "
                "restart to reconnect"
            )
        try:
            snippet = exc.read(_ERROR_SNIPPET_BYTES).decode("utf-8", "replace")
        except Exception:
            snippet = ""
        detail = f": {snippet.strip()}" if snippet.strip() else ""
        return MCPTransportError(f"HTTP {exc.code} from {self._shown_url}{detail}")

    def _delete_session(self) -> None:
        outgoing = urllib.request.Request(
            self._url, headers=self._message_headers(), method="DELETE"
        )
        try:
            with self._opener.open(outgoing, timeout=_CLOSE_TIMEOUT_S):
                pass
        except Exception:
            pass


def redact_url(url: str) -> str:
    """*url* without user-info, query or fragment."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    suffix = "?…" if parts.query else ""
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", "")) + suffix


def _in_daemon_thread(function: Callable[..., _T], *args: Any) -> asyncio.Future[_T]:
    """Run *function* on a new daemon thread; its outcome resolves the future.

    Unlike :func:`asyncio.to_thread`, a call abandoned by its awaiter
    neither occupies the loop's shared executor nor delays process exit.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[_T] = loop.create_future()

    def settle(outcome: Any, failed: bool) -> None:
        if future.done():
            return
        if failed:
            future.set_exception(outcome)
        else:
            future.set_result(outcome)

    def work() -> None:
        try:
            outcome, failed = function(*args), False
        except BaseException as exc:  # handed to the awaiting task
            outcome, failed = exc, True
        try:
            loop.call_soon_threadsafe(settle, outcome, failed)
        except RuntimeError:  # the loop is gone; nobody is waiting
            pass

    threading.Thread(target=work, name="omicsclaw-mcp-http", daemon=True).start()
    return future


def json_messages(body: bytes) -> Iterable[Any]:
    """The messages in a JSON body: one object, or a batch of them."""
    try:
        decoded = json.loads(body)
    except ValueError as exc:
        raise MCPProtocolError(f"the server's answer is not JSON: {exc}") from exc
    return decoded if isinstance(decoded, list) else [decoded]


def event_messages(lines: Iterable[bytes]) -> Iterable[Any]:
    """The JSON payload of each event in a ``text/event-stream``.

    Events whose data is not JSON are skipped. Reading stops with
    :exc:`MCPTransportError` past :data:`MAX_RESPONSE_BYTES`.
    """
    data: list[str] = []
    total = 0
    for raw in lines:
        total += len(raw)
        if total > MAX_RESPONSE_BYTES:
            raise MCPTransportError(
                f"the server's event stream exceeded {MAX_RESPONSE_BYTES} bytes"
            )
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            if data:
                yield from _decoded("\n".join(data))
                data = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field == "data":
            data.append(value[1:] if value.startswith(" ") else value)
    if data:
        yield from _decoded("\n".join(data))


def _decoded(text: str) -> Iterable[Any]:
    try:
        yield json.loads(text)
    except ValueError:
        return


def _matching(messages: Iterable[Any], request_id: int) -> Mapping[str, Any]:
    """The response to *request_id* among *messages*."""
    for message in messages:
        if classify(message) == "response" and is_request_id(
            message.get("id"), request_id
        ):
            return message
    raise MCPProtocolError(
        f"the server's answer holds no response to request {request_id}"
    )


def _read_capped(response: http.client.HTTPResponse) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise MCPTransportError(
            f"the server's answer exceeded {MAX_RESPONSE_BYTES} bytes"
        )
    return body


"""The Streamable HTTP transport, against a real server on the loopback.

The server below enforces what the specification requires of a client and
harness9's ``HTTPTransport`` does not send: an ``Accept`` header naming
both JSON and event streams (without it a conforming server answers 406),
the session id it assigned, and ``MCP-Protocol-Version`` after the
handshake. It answers in JSON or as an event stream, per test.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

import subprocess
import sys

from omicsclaw.mcp import (
    HTTPTransport,
    MCPClient,
    MCPToolError,
    MCPTransportError,
)
from omicsclaw.mcp.streamable_http import redact_url
from tests.mcp._support import run

SESSION = "session-42"


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, mode: str) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.mode = mode
        self.seen: list[tuple[str, dict[str, str], Any]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/mcp"


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass

    def do_DELETE(self) -> None:  # noqa: N802
        self.server.seen.append(("DELETE", _lowered(self.headers), None))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        message = json.loads(self.rfile.read(length))
        self.server.seen.append(("POST", _lowered(self.headers), message))
        mode = self.server.mode

        if mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        accept = self.headers.get("Accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            self._plain(406, "Not Acceptable")
            return
        method = message.get("method")
        if method != "initialize" and self.headers.get("Mcp-Session-Id") != SESSION:
            self._plain(400, "missing session")
            return
        if method not in ("initialize", None) and not self.headers.get(
            "MCP-Protocol-Version"
        ):
            self._plain(400, "missing protocol version")
            return
        if "id" not in message:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        result = self._result(message)
        response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        if mode == "sse":
            events = [
                {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}},
                response,
            ]
            body = "".join(
                f"event: message\ndata: {json.dumps(event)}\n\n" for event in events
            ).encode()
            content_type = "text/event-stream"
        else:
            body = json.dumps(response).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if method == "initialize":
            self.send_header("Mcp-Session-Id", SESSION)
        self.end_headers()
        self.wfile.write(body)

    def _result(self, message: dict) -> Any:
        method = message["method"]
        if method == "initialize":
            return {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "loopback", "version": "1"},
            }
        if method == "tools/list":
            return {"tools": [{"name": "echo"}, {"name": "fail"}]}
        arguments = message["params"]["arguments"]
        if message["params"]["name"] == "fail":
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}
        return {"content": [{"type": "text", "text": json.dumps(arguments)}]}

    def _plain(self, status: int, text: str) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _lowered(headers) -> dict[str, str]:
    """Header names are case-insensitive; urllib sends ``Mcp-session-id``."""
    return {name.lower(): value for name, value in headers.items()}


@pytest.fixture(params=["json", "sse"])
def server(request):
    instance = _Server(request.param)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


@pytest.fixture
def redirecting():
    instance = _Server("redirect")
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


def _client(url: str) -> MCPClient:
    return MCPClient(
        "remote",
        HTTPTransport(url, headers={"Authorization": "Bearer t0k"}, timeout_s=5),
    )


def test_a_full_session_in_json_and_as_an_event_stream(server: _Server):
    async def main():
        client = _client(server.url)
        await client.connect()
        try:
            names = [tool.name for tool in client.tools]
            output = await client.call_tool("echo", '{"gene": "TP53"}')
        finally:
            await client.aclose()
        return names, output

    names, output = run(main())

    assert names == ["echo", "fail"]
    assert json.loads(output) == {"gene": "TP53"}


def test_every_message_carries_the_headers_the_specification_requires(
    server: _Server,
):
    async def main():
        client = _client(server.url)
        await client.connect()
        await client.call_tool("echo", "{}")
        await client.aclose()

    run(main())

    posts = [(h, message) for verb, h, message in server.seen if verb == "POST"]
    for headers, _ in posts:
        assert "text/event-stream" in headers["accept"]
        assert headers["authorization"] == "Bearer t0k"
    assert "mcp-session-id" not in posts[0][0]
    assert all(h["mcp-session-id"] == SESSION for h, _ in posts[1:])
    later = [h for h, m in posts if m.get("method") in ("tools/list", "tools/call")]
    assert later
    assert all(h["mcp-protocol-version"] == "2025-06-18" for h in later)


def test_closing_ends_the_session(server: _Server):
    async def main():
        client = _client(server.url)
        await client.connect()
        await client.aclose()
        await client.aclose()

    run(main())

    deletes = [headers for verb, headers, _ in server.seen if verb == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0]["mcp-session-id"] == SESSION


def test_a_tool_error_is_raised_with_its_text(server: _Server):
    async def main():
        client = _client(server.url)
        await client.connect()
        try:
            with pytest.raises(MCPToolError, match="nope"):
                await client.call_tool("fail", "{}")
        finally:
            await client.aclose()

    run(main())


def test_a_redirect_is_refused_rather_than_followed(redirecting: _Server):
    """Following it would re-send the Authorization header to a host
    nobody configured."""

    async def main():
        client = _client(redirecting.url)
        with pytest.raises(MCPTransportError, match="redirects are not followed"):
            await client.connect()

    run(main())
    assert len(redirecting.seen) == 1


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_no_timeout_means_wait_rather_than_never_connect(server: _Server, timeout):
    """``tool_timeout_s <= 0`` means "no limit" to the engine; handed to a
    socket as ``0`` it would make every connection non-blocking and fail."""

    async def main():
        client = MCPClient("remote", HTTPTransport(server.url, timeout_s=timeout))
        await client.connect()
        await client.aclose()
        return client.tools

    assert run(main())


def test_credentials_in_the_url_never_reach_an_error_message():
    async def main():
        client = MCPClient(
            "remote",
            HTTPTransport("http://user:pa55@127.0.0.1:9/mcp?key=s3cr3t", timeout_s=5),
        )
        with pytest.raises(MCPTransportError) as caught:
            await client.connect()
        return str(caught.value)

    message = run(main())

    assert "127.0.0.1:9/mcp" in message
    assert "pa55" not in message and "s3cr3t" not in message


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://h/mcp", "https://h/mcp"),
        ("https://u:p@h:8443/mcp?token=x#f", "https://h:8443/mcp?…"),
        ("http://[::1]:9/mcp", "http://[::1]:9/mcp"),
    ],
)
def test_redaction_keeps_what_locates_the_server(url: str, shown: str):
    assert redact_url(url) == shown


_SILENT_SERVER_PROBE = """
import asyncio, socket, sys, threading, time
from omicsclaw.mcp import MCPManager, parse_mcp_config

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(8)
held = []
threading.Thread(
    target=lambda: [held.append(listener.accept()) for _ in range(8)], daemon=True
).start()
url = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"


async def main():
    config = parse_mcp_config({"mcpServers": {"silent": {"url": url}}}, {})
    manager = MCPManager(config, connect_timeout_s=0.5, request_timeout_s=600)
    (status,) = await manager.start()
    assert status.state == "failed", status
    await manager.aclose()


started = time.monotonic()
asyncio.run(main())
print(f"{time.monotonic() - started:.1f}")
"""


def test_an_abandoned_request_does_not_hold_the_process_open():
    """A server that accepts and never answers: the handshake is abandoned
    after 0.5 s, and the process must be able to exit then — not after the
    600 s socket timeout a thread in the loop's default executor would hold
    it for."""
    result = subprocess.run(
        [sys.executable, "-c", _SILENT_SERVER_PROBE],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert float(result.stdout.strip()) < 5


def test_an_unreachable_server_fails_with_its_url():
    async def main():
        client = _client("http://127.0.0.1:9/mcp")
        with pytest.raises(MCPTransportError, match="127.0.0.1:9"):
            await client.connect()

    run(main())


def test_an_http_error_carries_the_status_and_the_body():
    instance = _Server("json")
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:

        async def main():
            transport = HTTPTransport(instance.url, timeout_s=5)
            await transport.start()
            with pytest.raises(MCPTransportError, match="HTTP 400.*missing session"):
                await transport.request("tools/list")

        run(main())
    finally:
        instance.shutdown()
        instance.server_close()

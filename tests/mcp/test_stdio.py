"""The stdio transport and the client, against a real subprocess.

Every test here spawns ``fake_server.py`` with ``sys.executable``, so the
pipes, the process group and the signals are real. Where harness9 has a
defect the test says so, because each of these is a place a port would
have copied it:

* a server *request* whose id equals a pending client request was routed
  as that request's response (``readLoop`` looks only at the id);
* ``tools/list`` stopped after the first page;
* stderr was discarded, so a crash surfaced as "transport closed";
* the child inherited the whole environment, API keys included.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from omicsclaw.mcp import (
    MCPClient,
    MCPProtocolError,
    MCPRemoteError,
    MCPToolError,
    MCPTransportError,
    StdioTransport,
)
from omicsclaw.mcp.stdio import child_environment
from tests.mcp._support import FAKE_SERVER, pid_alive, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the process-group checks are POSIX"
)


def _transport(*flags: str, **kwargs) -> StdioTransport:
    return StdioTransport(sys.executable, (str(FAKE_SERVER), *flags), **kwargs)


def _logged(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


async def _connected(*flags: str, **kwargs) -> MCPClient:
    client = MCPClient("fake", _transport(*flags, **kwargs))
    await client.connect()
    return client


# ---- handshake ------------------------------------------------------------


def test_the_handshake_lists_the_server_s_tools(tmp_path: Path):
    log = tmp_path / "log.jsonl"

    async def main():
        client = await _connected("--log", str(log), "--instructions", "be kind")
        try:
            return client.info, [tool.name for tool in client.tools]
        finally:
            await client.aclose()

    info, names = run(main())

    assert names[:3] == ["echo", "fail", "image"]
    assert (info.name, info.protocol_version, info.instructions) == (
        "fake",
        "2025-06-18",
        "be kind",
    )
    methods = [message.get("method") for message in _logged(log)]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/list"]
    initialize = _logged(log)[0]["params"]
    assert initialize["protocolVersion"] == "2025-06-18"
    assert initialize["clientInfo"]["name"] == "omicsclaw"


def test_every_page_of_tools_is_listed():
    """harness9 read one page; a server with more tools lost the rest."""

    async def main():
        client = await _connected("--page-size", "3")
        try:
            return [tool.name for tool in client.tools]
        finally:
            await client.aclose()

    names = run(main())

    assert len(names) == 8
    assert len(set(names)) == 8


def test_a_banner_on_stdout_does_not_break_the_handshake():
    async def main():
        client = await _connected("--banner")
        await client.aclose()
        return client.tools

    assert run(main())


def test_an_unsupported_protocol_version_fails_the_handshake_and_names_it():
    async def main():
        transport = _transport("--version", "1999-01-01")
        client = MCPClient("fake", transport)
        with pytest.raises(MCPProtocolError, match="1999-01-01"):
            await client.connect()
        return transport

    transport = run(main())
    assert transport.pid is not None and not pid_alive(transport.pid)


def test_a_command_that_does_not_exist_fails_with_its_name():
    async def main():
        client = MCPClient("x", StdioTransport("/no/such/omicsclaw-mcp-server"))
        with pytest.raises(MCPTransportError, match="omicsclaw-mcp-server"):
            await client.connect()

    run(main())


def test_a_crashing_server_reports_its_exit_code_and_stderr():
    """The whole diagnosis of a server that will not start is on stderr."""

    async def main():
        client = MCPClient("fake", _transport("--crash"))
        with pytest.raises(MCPTransportError) as caught:
            await client.connect()
        return str(caught.value)

    message = run(main())

    assert "exit code 3" in message
    assert "could not find its data" in message


def test_a_server_that_never_finishes_the_handshake_is_killed_at_once():
    """Graceful shutdown is for a server that served. One stuck before its
    handshake, and deaf to EOF and SIGTERM, would otherwise add two grace
    periods to every connect timeout."""

    async def main():
        transport = _transport("--hang-init", "--ignore-eof", "--ignore-sigterm")
        client = MCPClient("fake", transport)
        loop = asyncio.get_running_loop()
        started = loop.time()
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.5):
                await client.connect()
        return loop.time() - started, transport.pid

    elapsed, pid = run(main())

    assert elapsed < 1.5
    assert not pid_alive(pid)


def test_a_transport_used_from_a_second_event_loop_fails_at_once():
    """Each ``asyncio.run`` is a new loop; the first one's reader died with it.

    Before the repair the second loop's call waited forever for a
    response nothing would ever read.
    """
    transport = _transport()
    client = MCPClient("fake", transport)
    run(client.connect())

    async def later():
        with pytest.raises(MCPTransportError, match="event loop"):
            await client.call_tool("echo", "{}")

    run(later(), timeout=5)


def test_a_call_cancelled_before_it_was_written_is_not_cancelled_on_the_server(
    tmp_path: Path,
):
    log = tmp_path / "log.jsonl"

    async def main():
        transport = _transport("--log", str(log))
        client = MCPClient("fake", transport)
        await client.connect()
        try:
            async with transport._write_lock:  # hold the pipe
                queued = asyncio.ensure_future(client.call_tool("echo", "{}"))
                await asyncio.sleep(0.1)
                queued.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await queued
            return await client.call_tool("echo", '{"after": 1}')
        finally:
            await client.aclose()

    assert json.loads(run(main())) == {"after": 1}
    methods = [m.get("method") for m in _logged(log)]
    assert "notifications/cancelled" not in methods
    assert methods.count("tools/call") == 1


def test_a_boolean_id_is_not_mistaken_for_request_one():
    """``True == 1`` in Python; a response carrying ``"id": true`` is not
    the answer to request 1."""

    async def main():
        transport = _transport()
        await transport.start()
        try:
            future = asyncio.get_running_loop().create_future()
            transport._pending[1] = future
            transport._dispatch(b'{"jsonrpc": "2.0", "id": true, "result": {}}')
            return future.done()
        finally:
            await transport.aclose()

    assert run(main()) is False


def test_a_handshake_abandoned_by_timeout_leaves_no_process():
    async def main():
        transport = _transport("--hang-init")
        client = MCPClient("fake", transport)
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.5):
                await client.connect()
        return transport.pid

    pid = run(main())
    assert pid is not None and not pid_alive(pid)


# ---- calls ----------------------------------------------------------------


def test_a_call_passes_the_arguments_and_returns_the_text():
    async def main():
        client = await _connected()
        try:
            return await client.call_tool("echo", '{"text": "TP53", "n": 2}')
        finally:
            await client.aclose()

    assert json.loads(run(main())) == {"n": 2, "text": "TP53"}


def test_arguments_spread_over_several_lines_do_not_break_the_framing():
    """A model may pretty-print its JSON. Embedded raw, the newlines would
    split one message into several lines of the NDJSON stream."""

    async def main():
        client = await _connected()
        try:
            return await client.call_tool("echo", '{\n  "text": "a\\nb"\n}')
        finally:
            await client.aclose()

    assert json.loads(run(main())) == {"text": "a\nb"}


@pytest.mark.parametrize("arguments", ["[1, 2]", "not json", '"text"'])
def test_arguments_that_are_not_an_object_are_refused(arguments: str):
    async def main():
        client = await _connected()
        try:
            with pytest.raises(ValueError):
                await client.call_tool("echo", arguments)
        finally:
            await client.aclose()

    run(main())


def test_empty_arguments_mean_an_empty_object():
    async def main():
        client = await _connected()
        try:
            return await client.call_tool("echo", "")
        finally:
            await client.aclose()

    assert run(main()) == "{}"


def test_a_tool_that_reports_an_error_raises_with_its_output():
    async def main():
        client = await _connected()
        try:
            with pytest.raises(MCPToolError, match="it broke"):
                await client.call_tool("fail", "{}")
        finally:
            await client.aclose()

    run(main())


def test_an_unknown_tool_is_the_server_s_error():
    async def main():
        client = await _connected()
        try:
            with pytest.raises(MCPRemoteError, match="unknown tool"):
                await client.call_tool("nope", "{}")
        finally:
            await client.aclose()

    run(main())


def test_calls_run_concurrently_on_one_connection():
    async def main():
        client = await _connected()
        try:
            started = asyncio.get_running_loop().time()
            results = await asyncio.gather(
                *(client.call_tool("sleep", '{"seconds": 0.4}') for _ in range(4))
            )
            return results, asyncio.get_running_loop().time() - started
        finally:
            await client.aclose()

    results, elapsed = run(main())

    assert results == ["slept"] * 4
    assert elapsed < 1.4


def test_a_server_request_is_answered_not_mistaken_for_a_response():
    """The fake pings the client with the *same id* as the pending call.

    Routing by id alone — harness9's ``readLoop`` — would resolve the call
    with the ping, and the tool would appear to return nothing.
    """

    async def main():
        client = await _connected()
        try:
            return await client.call_tool("ping-first", "{}")
        finally:
            await client.aclose()

    output = run(main())

    assert output.startswith("pong: ")
    pong = json.loads(output.removeprefix("pong: "))
    assert pong["result"] == {}


def test_an_abandoned_call_is_cancelled_on_the_server(tmp_path: Path):
    log = tmp_path / "log.jsonl"

    async def main():
        client = await _connected("--log", str(log))
        try:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.3):
                    await client.call_tool("sleep", '{"seconds": 5}')
            # The connection survives the abandoned call.
            return await client.call_tool("echo", "{}")
        finally:
            await client.aclose()

    assert run(main()) == "{}"
    received = _logged(log)
    cancelled = [m for m in received if m.get("method") == "notifications/cancelled"]
    (notice,) = cancelled
    call_ids = [
        m["id"] for m in _logged(log) if m.get("method") == "tools/call"
    ]
    assert notice["params"]["requestId"] == call_ids[0]


def test_a_server_that_dies_fails_the_calls_waiting_on_it():
    async def main():
        transport = _transport()
        client = MCPClient("fake", transport)
        await client.connect()
        waiting = asyncio.ensure_future(client.call_tool("sleep", '{"seconds": 5}'))
        await asyncio.sleep(0.2)
        os.killpg(transport.pid, 9)
        with pytest.raises(MCPTransportError, match="closed its output"):
            await asyncio.wait_for(waiting, 5)
        with pytest.raises(MCPTransportError):
            await client.call_tool("echo", "{}")
        await client.aclose()

    run(main())


def test_an_oversized_message_closes_the_transport_with_the_reason():
    async def main():
        client = await _connected(max_message_bytes=64 * 1024)
        try:
            with pytest.raises(MCPTransportError, match="larger than 65536 bytes"):
                await client.call_tool("big", '{"size": 200000}')
        finally:
            await client.aclose()

    run(main())


# ---- environment ------------------------------------------------------------


def test_the_child_inherits_only_the_allowlist_and_its_configuration():
    environment = child_environment(
        {"TOKEN": "configured"},
        inherited={
            "PATH": "/bin",
            "HOME": "/home/u",
            "LLM_API_KEY": "sk-secret",
            "TELEGRAM_BOT_TOKEN": "t",
            "SHELL": "() { evil; }",
        },
    )

    assert environment == {"PATH": "/bin", "HOME": "/home/u", "TOKEN": "configured"}


def test_a_secret_in_this_process_does_not_reach_the_server(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-must-not-leak")

    async def main():
        client = await _connected(env={"GIVEN": "yes"})
        try:
            leaked = await client.call_tool("env", '{"name": "LLM_API_KEY"}')
            given = await client.call_tool("env", '{"name": "GIVEN"}')
            return leaked, given
        finally:
            await client.aclose()

    assert run(main()) == ("<unset>", "yes")


# ---- closing --------------------------------------------------------------


def test_closing_ends_the_server_and_its_descendants(tmp_path: Path):
    """``npx`` starts ``node``; killing only the child leaves ``node`` holding
    the pipes. The process group goes with it."""
    log = tmp_path / "log.jsonl"

    async def main():
        transport = _transport("--log", str(log), "--spawn-child")
        client = MCPClient("fake", transport)
        await client.connect()
        await client.aclose()
        return transport.pid

    pid = run(main())
    grandchild = next(m["grandchild"] for m in _logged(log) if "grandchild" in m)

    assert not pid_alive(pid)
    assert not pid_alive(grandchild)


def test_a_server_that_ignores_eof_and_sigterm_is_killed():
    async def main():
        transport = _transport("--ignore-eof", "--ignore-sigterm", exit_grace_s=0.2)
        client = MCPClient("fake", transport)
        await client.connect()
        await client.aclose()
        return transport.pid

    assert not pid_alive(run(main()))


def test_closing_twice_is_harmless_and_later_calls_fail_cleanly():
    async def main():
        client = await _connected()
        await asyncio.gather(client.aclose(), client.aclose())
        await client.aclose()
        with pytest.raises(MCPTransportError, match="closed"):
            await client.call_tool("echo", "{}")

    run(main())

"""The manager: concurrent, fail-soft, and the one place tools are minted.

harness9's ``Manager`` gives three guarantees worth keeping — servers
connect concurrently, one server failing touches no other, and a name
clash skips a tool rather than aborting the injection — and one worth not
keeping: it iterates a Go map, so the injected order is random, and here
the tool order is part of the prompt-cache prefix. Mounting happens after
every server has answered, in configuration order.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import pytest

from omicsclaw.mcp import (
    MCPConfig,
    MCPManager,
    RejectedServer,
    ServerConfig,
    ServerState,
    TransportKind,
    parse_mcp_config,
)
from omicsclaw.schema import ToolCall
from omicsclaw.tools import ApprovalMode, ToolPolicy, ToolRegistry, use_tool_context
from tests.mcp._support import (
    ScriptedTransport,
    fake_server,
    pid_alive,
    run,
    scripted_server,
)


def _stdio(name: str) -> ServerConfig:
    return ServerConfig(name=name, kind=TransportKind.STDIO, command="unused")


def _manager(config: MCPConfig, transports: dict, **kwargs) -> MCPManager:
    return MCPManager(
        config, transport_factory=lambda server: transports[server.name], **kwargs
    )


def _auto(registry: ToolRegistry) -> ToolRegistry:
    """Re-register every tool with an ``AUTO`` policy, as a trusting
    deployment would, so a test can call through the registry."""
    trusted = ToolRegistry()
    for name in registry.names():
        trusted.register(
            registry.get(name), ToolPolicy(approval_mode=ApprovalMode.AUTO)
        )
    return trusted


def test_servers_connect_concurrently():
    names = [f"s{i}" for i in range(4)]
    transports = {name: scripted_server() for name in names}
    for transport in transports.values():
        transport.delay = 0.3
    manager = _manager(MCPConfig(tuple(map(_stdio, names))), transports)

    started = time.monotonic()
    run(manager.start())

    # Three requests each at 0.3 s: sequential would be 3.6 s.
    assert time.monotonic() - started < 2.0
    assert all(s.state is ServerState.CONNECTED for s in manager.statuses())


def test_one_failing_server_does_not_touch_the_others():
    transports = {
        "good": scripted_server(tools=[{"name": "a"}]),
        "bad": ScriptedTransport({"initialize": ConnectionError("refused")}),
    }
    manager = _manager(MCPConfig((_stdio("bad"), _stdio("good"))), transports)

    statuses = {s.name: s for s in run(manager.start())}

    assert statuses["bad"].state is ServerState.FAILED
    assert "ConnectionError: refused" in statuses["bad"].error
    assert statuses["good"].state is ServerState.CONNECTED
    assert [tool.name for tool in manager.tools()] == ["mcp__good__a"]
    assert transports["bad"].closed


def test_a_server_that_hangs_is_given_up_on_within_the_timeout():
    slow = scripted_server()
    slow.delay = 60
    manager = _manager(
        MCPConfig((_stdio("slow"), _stdio("quick"))),
        {"slow": slow, "quick": scripted_server()},
        connect_timeout_s=0.3,
    )

    started = time.monotonic()
    statuses = {s.name: s for s in run(manager.start())}

    assert time.monotonic() - started < 3
    assert statuses["slow"].state is ServerState.FAILED
    assert "within 0.3s" in statuses["slow"].error
    assert statuses["quick"].state is ServerState.CONNECTED
    assert slow.closed


def test_a_bug_in_one_server_s_path_is_contained():
    """harness9 records any connection error; so does this, whatever its type."""

    def factory(server):
        if server.name == "broken":
            raise TypeError("factory bug")
        return scripted_server()

    manager = MCPManager(
        MCPConfig((_stdio("broken"), _stdio("fine"))), transport_factory=factory
    )

    statuses = {s.name: s for s in run(manager.start())}

    assert statuses["broken"].error == "TypeError: factory bug"
    assert statuses["fine"].state is ServerState.CONNECTED


def test_disabled_and_rejected_servers_are_reported_but_never_started():
    config = parse_mcp_config(
        {
            "mcpServers": {
                "off": {"command": "x", "enabled": False},
                "broken": {"type": "sse", "url": "http://x"},
            }
        },
        {},
    )
    opened: list[str] = []
    manager = MCPManager(
        config, transport_factory=lambda s: opened.append(s.name) or scripted_server()
    )

    statuses = {s.name: s for s in run(manager.start())}

    assert opened == []
    assert statuses["off"].state is ServerState.DISABLED
    assert statuses["broken"].state is ServerState.FAILED
    assert "not supported" in statuses["broken"].error


def test_tools_follow_configuration_order_not_connection_order():
    first = scripted_server(tools=[{"name": "x"}, {"name": "y"}])
    first.delay = 0.3
    second = scripted_server(tools=[{"name": "z"}])
    manager = _manager(
        MCPConfig((_stdio("first"), _stdio("second"))),
        {"first": first, "second": second},
    )

    run(manager.start())

    assert [tool.name for tool in manager.tools()] == [
        "mcp__first__x",
        "mcp__first__y",
        "mcp__second__z",
    ]


def test_the_allowlist_filters_and_reports_names_the_server_lacks():
    server = ServerConfig(
        name="s", kind=TransportKind.STDIO, command="x", tools=("b", "missing")
    )
    transport = scripted_server(tools=[{"name": "a"}, {"name": "b"}])
    manager = _manager(MCPConfig((server,)), {"s": transport})

    run(manager.start())

    assert [tool.tool for tool in manager.tools()] == ["b"]
    (status,) = manager.statuses()
    assert [detail.name for detail in status.tools] == ["mcp__s__b"]
    assert status.skipped == ("missing: named in 'tools' but not offered",)


def test_a_name_clash_skips_the_later_tool_and_says_so():
    """``get-thing`` and ``get_thing`` both sanitise to ``get_thing``.

    Handed to a registry as-is, the second would raise
    ``ToolAlreadyRegistered`` and take start-up down with it.
    """
    transport = scripted_server(tools=[{"name": "get-thing"}, {"name": "get_thing"}])
    manager = _manager(MCPConfig((_stdio("s"),)), {"s": transport})

    run(manager.start())

    assert [tool.tool for tool in manager.tools()] == ["get-thing"]
    (status,) = manager.statuses()
    assert status.skipped == ("get_thing: mcp__s__get_thing is already taken",)
    ToolRegistry(manager.tools())  # registers without a clash


def test_every_status_change_is_announced_and_a_broken_listener_is_contained():
    seen: list[dict[str, str]] = []

    def listener(statuses):
        seen.append({s.name: s.state.value for s in statuses})
        raise RuntimeError("the UI crashed")

    manager = _manager(
        MCPConfig((_stdio("a"),)), {"a": scripted_server()}, on_change=listener
    )

    run(manager.start())

    assert seen[0] == {"a": "pending"}
    assert seen[-1] == {"a": "connected"}


def test_starting_twice_is_refused():
    manager = _manager(MCPConfig((_stdio("a"),)), {"a": scripted_server()})
    run(manager.start())

    with pytest.raises(RuntimeError):
        run(manager.start())


def test_closing_closes_every_connection_once():
    transports = {name: scripted_server() for name in ("a", "b")}
    manager = _manager(MCPConfig((_stdio("a"), _stdio("b"))), transports)

    async def main():
        async with manager:
            pass
        await manager.aclose()

    run(main())

    assert all(transport.closed for transport in transports.values())


def test_a_cancelled_start_closes_what_had_already_connected():
    quick = scripted_server()
    slow = scripted_server()
    slow.delay = 60
    manager = _manager(
        MCPConfig((_stdio("quick"), _stdio("slow"))), {"quick": quick, "slow": slow}
    )

    async def main():
        task = asyncio.ensure_future(manager.start())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(main())

    assert quick.closed and slow.closed


# ---- end to end, through the registry ----------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process checks")
def test_a_real_server_s_tools_run_through_the_registry():
    config = MCPConfig((fake_server("fake", tools=("echo", "fail")),))
    manager = MCPManager(config)

    async def main():
        await manager.start()
        registry = _auto(ToolRegistry(manager.tools()))
        try:
            ok = await registry.execute(
                ToolCall(id="1", name="mcp__fake__echo", arguments='{"x": 1}')
            )
            failed = await registry.execute(
                ToolCall(id="2", name="mcp__fake__fail", arguments="{}")
            )
        finally:
            await manager.aclose()
        return ok, failed

    ok, failed = run(main())

    assert (json.loads(ok.output), ok.is_error) == ({"x": 1}, False)
    assert failed.is_error and "it broke" in failed.output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process checks")
def test_with_no_approval_channel_an_mcp_tool_never_reaches_its_server(tmp_path):
    """The default policy is ``ASK``, and absence of a channel is not consent."""
    log = tmp_path / "log.jsonl"
    manager = MCPManager(MCPConfig((fake_server("fake", "--log", str(log)),)))

    async def main():
        await manager.start()
        registry = ToolRegistry(manager.tools())
        try:
            with use_tool_context():
                return await registry.execute(
                    ToolCall(id="1", name="mcp__fake__echo", arguments="{}")
                )
        finally:
            await manager.aclose()

    result = run(main())

    assert result.is_error and "ApprovalUnavailable" in result.output
    methods = [json.loads(line).get("method") for line in log.read_text().splitlines()]
    assert "tools/call" not in methods


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process checks")
def test_closing_the_manager_leaves_no_server_process(tmp_path):
    log = tmp_path / "log.jsonl"
    manager = MCPManager(
        MCPConfig((fake_server("a", "--log", str(log), "--spawn-child"),))
    )

    async def main():
        await manager.start()
        await manager.aclose()

    run(main())

    grandchild = next(
        json.loads(line)["grandchild"]
        for line in log.read_text().splitlines()
        if "grandchild" in line
    )
    assert not pid_alive(grandchild)


def test_a_timeout_that_is_not_positive_is_refused():
    with pytest.raises(ValueError, match="connect_timeout_s"):
        MCPManager(MCPConfig(), connect_timeout_s=0)


def test_tool_output_is_capped_before_the_model_sees_it():
    long = {"content": [{"type": "text", "text": "y" * 100}]}
    failing = {"content": [{"type": "text", "text": "z" * 100}], "isError": True}
    transport = scripted_server(tools__call=[long, failing])
    manager = _manager(
        MCPConfig((_stdio("s"),)), {"s": transport}, max_output_chars=10
    )

    async def main():
        await manager.start()
        registry = _auto(ToolRegistry(manager.tools()))
        call = ToolCall(id="1", name="mcp__s__echo", arguments="{}")
        return await registry.execute(call), await registry.execute(call)

    ok, failed = run(main())

    assert ok.output.startswith("y" * 10 + "\n")
    assert "first 10 of 100" in ok.output
    assert failed.is_error and "first 10 of 100" in failed.output
    assert "z" * 11 not in failed.output


def test_nameless_tools_are_reported_as_skipped():
    transport = scripted_server(tools=[{"description": "?"}, {"name": "a"}])
    manager = _manager(MCPConfig((_stdio("s"),)), {"s": transport})

    (status,) = run(manager.start())

    assert status.skipped == ("1 listed tool(s) had no name",)
    assert [tool.tool for tool in manager.tools()] == ["a"]


def test_the_approval_prompt_says_where_the_call_goes():
    """Q2 of the plan: the human deciding must see whether the arguments
    leave this machine — and must not see the URL's credentials."""
    remote = ServerConfig(
        name="r",
        kind=TransportKind.HTTP,
        url="https://u:pw@mcp.example.org/v1?token=s3cr3t",
    )
    reasons: list[str] = []
    manager = _manager(
        MCPConfig((_stdio("local"), remote)),
        {"local": scripted_server(), "r": scripted_server()},
    )

    def human(request):
        reasons.append(request.reason)
        return True

    async def main():
        await manager.start()
        registry = ToolRegistry(manager.tools())
        with use_tool_context(approval=human):
            for name in ("mcp__local__echo", "mcp__r__echo"):
                await registry.execute(ToolCall(id="1", name=name, arguments="{}"))

    run(main())

    local, far = reasons
    assert "local process unused" in local
    assert "remote https://mcp.example.org/v1?…" in far
    assert "pw" not in far and "s3cr3t" not in far


def test_rejected_entries_have_no_transport():
    manager = MCPManager(MCPConfig(rejected=(RejectedServer("x", "why"),)))

    (status,) = run(manager.start())

    assert (status.state, status.transport, status.error) == (
        ServerState.FAILED,
        "",
        "why",
    )
    assert manager.tools() == ()

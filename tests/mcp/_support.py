"""Shared helpers for the MCP tests: running coroutines, the fake server."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Coroutine, TypeVar

from omicsclaw.mcp import ServerConfig, TransportKind

_T = TypeVar("_T")

FAKE_SERVER = Path(__file__).resolve().parent / "fake_server.py"


def run(main: Coroutine[Any, Any, _T], timeout: float = 20.0) -> _T:
    """Run *main* on a fresh loop, failing the test if it hangs."""
    return asyncio.run(asyncio.wait_for(main, timeout))


def fake_server(
    name: str = "fake",
    *flags: str,
    env: Mapping[str, str] | None = None,
    tools: tuple[str, ...] | None = None,
    enabled: bool = True,
) -> ServerConfig:
    """A stdio server entry that runs ``fake_server.py`` with *flags*."""
    return ServerConfig(
        name=name,
        kind=TransportKind.STDIO,
        command=sys.executable,
        args=(str(FAKE_SERVER), *flags),
        env=dict(env or {}),
        tools=tools,
        enabled=enabled,
    )


def pid_alive(pid: int) -> bool:
    """Whether *pid* names a live, non-zombie process."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            state = handle.read().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return state != "Z"


class ScriptedTransport:
    """A :class:`~omicsclaw.mcp.Transport` that answers from a table.

    *answers* maps a method to its result, to an exception to raise, or to
    a list consumed one element per call. Every request and notification is
    recorded in :attr:`sent`.
    """

    def __init__(
        self,
        answers: Mapping[str, Any] | None = None,
        *,
        delay: float = 0.0,
    ) -> None:
        self.answers = dict(answers or {})
        self.delay = delay
        self.sent: list[tuple[str, Any]] = []
        self.started = False
        self.closed = False
        self.version = ""

    async def start(self) -> None:
        self.started = True

    async def request(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> Any:
        self.sent.append((method, params))
        if self.delay:
            await asyncio.sleep(self.delay)
        answer = self.answers[method]
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    async def notify(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> None:
        self.sent.append((method, params))

    def negotiated(self, protocol_version: str) -> None:
        self.version = protocol_version

    async def aclose(self) -> None:
        self.closed = True


def initialize_result(version: str = "2025-06-18", **extra: Any) -> dict[str, Any]:
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "scripted", "version": "0.1"},
        **extra,
    }


def scripted_server(
    tools: list[dict[str, Any]] | None = None,
    **answers: Any,
) -> ScriptedTransport:
    """A transport for a well-behaved server offering *tools*."""
    table: dict[str, Any] = {
        "initialize": initialize_result(),
        "tools/list": {"tools": tools if tools is not None else [{"name": "echo"}]},
        "tools/call": {"content": [{"type": "text", "text": "ok"}]},
    }
    table.update({key.replace("__", "/"): value for key, value in answers.items()})
    return ScriptedTransport(table)

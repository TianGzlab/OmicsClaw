"""A server that is a subprocess, spoken to over its stdin and stdout.

Messages are newline-delimited JSON. Lines on stdout that are not JSON are
ignored, since servers commonly print a banner there. stderr is drained
continuously and its last lines are attached to the error raised when the
process goes away.

The child starts in its own process group (POSIX) and inherits only
:data:`INHERITED_ENV_VARS` from this process, plus the variables its
configuration names. Closing a server that completed its handshake
follows the order the MCP specification recommends: close stdin, wait,
``SIGTERM``, wait, ``SIGKILL``. A server closed before its handshake
completed is killed at once.

A transport belongs to the event loop that started it. When that loop
stops, the transport is closed and later calls fail immediately.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import signal
import sys
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from .transport import (
    METHOD_NOT_FOUND,
    MCPTransportError,
    classify,
    encode,
    error_response,
    notification,
    request,
    result_of,
    success_response,
)

__all__ = [
    "EXIT_GRACE_S",
    "INHERITED_ENV_VARS",
    "MAX_MESSAGE_BYTES",
    "StdioTransport",
    "child_environment",
]

INHERITED_ENV_VARS: tuple[str, ...] = (
    (
        "APPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "USERNAME",
        "USERPROFILE",
    )
    if sys.platform == "win32"
    else ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
)
"""The only variables a server inherits from this process.

API keys and bot tokens in this process's environment do not reach a
third-party server unless its configuration passes them explicitly.
"""

MAX_MESSAGE_BYTES = 8 * 1024 * 1024
"""Longest single message accepted from a server. A longer one closes the
transport, failing every request still waiting."""

EXIT_GRACE_S = 2.0
"""How long each shutdown step waits before escalating."""

STDERR_TAIL_LINES = 20
STDERR_LINE_CHARS = 500

_POSIX = os.name == "posix"
_KILL = getattr(signal, "SIGKILL", signal.SIGTERM)
_POLL_S = 0.02


def child_environment(
    configured: Mapping[str, str],
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The environment a server process starts with.

    :data:`INHERITED_ENV_VARS` taken from *inherited* (default
    ``os.environ``), skipping exported shell functions, overlaid with
    *configured*.
    """
    source = os.environ if inherited is None else inherited
    environment = {
        name: source[name]
        for name in INHERITED_ENV_VARS
        if name in source and not source[name].startswith("()")
    }
    environment.update(configured)
    return environment


class StdioTransport:
    """A :class:`~omicsclaw.mcp.transport.Transport` over a child process."""

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        *,
        env: Mapping[str, str] | None = None,
        cwd: Path | str | None = None,
        inherited_env: Mapping[str, str] | None = None,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
        exit_grace_s: float = EXIT_GRACE_S,
    ) -> None:
        self._command = command
        self._args = tuple(args)
        self._environment = child_environment(env or {}, inherited_env)
        self._cwd = cwd
        self._max_message_bytes = max_message_bytes
        self._exit_grace_s = exit_grace_s

        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._write_lock = asyncio.Lock()
        self._closed = ""
        self._serving = False
        self._closing: asyncio.Future[None] | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)

    @property
    def pid(self) -> int | None:
        """The child's process id, once started."""
        return None if self._process is None else self._process.pid

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        """The last lines the server wrote to stderr."""
        return tuple(self._stderr_tail)

    async def start(self) -> None:
        """Spawn the server. Raises :exc:`MCPTransportError` if it cannot run."""
        if self._process is not None or self._closed:
            raise MCPTransportError("this transport was already started")
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._environment,
                cwd=self._cwd,
                limit=self._max_message_bytes,
                start_new_session=_POSIX,
            )
        except OSError as exc:
            self._closed = f"cannot start {self._command!r}: {exc}"
            raise MCPTransportError(self._closed) from exc
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Send a request and wait for its response.

        Cancelling the call after it was written sends
        ``notifications/cancelled`` for it (except for ``initialize``) and
        leaves the transport open.
        """
        self._ensure_open()
        request_id = next(self._ids)
        data = _line(request(request_id, method, params))
        future: asyncio.Future[Mapping[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        written = False
        try:
            async with self._write_lock:
                self._write(data)
                written = True
                await self._drain()
            response = await future
        except asyncio.CancelledError:
            abandoned = self._pending.pop(request_id, None) is not None
            if abandoned and written and method != "initialize":
                self._send_nowait(
                    notification(
                        "notifications/cancelled",
                        {
                            "requestId": request_id,
                            "reason": "the client stopped waiting",
                        },
                    )
                )
            raise
        finally:
            self._pending.pop(request_id, None)
        return result_of(response)

    async def notify(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a notification."""
        self._ensure_open()
        await self._send(notification(method, params))

    def negotiated(self, protocol_version: str) -> None:
        """Mark the handshake complete; stdio carries no per-message version."""
        self._serving = True

    async def aclose(self) -> None:
        """Stop the server and fail every request still waiting.

        Safe to call more than once; later calls wait for the first.
        """
        if self._closing is None:
            self._closing = asyncio.ensure_future(self._shutdown())
        await asyncio.shield(self._closing)

    # ---- writing --------------------------------------------------------

    async def _send(self, message: Mapping[str, Any]) -> None:
        data = _line(message)
        async with self._write_lock:
            self._write(data)
            await self._drain()

    def _write(self, data: bytes) -> None:
        self._ensure_open()
        try:
            self._stdin().write(data)
        except (ConnectionError, RuntimeError) as exc:
            raise MCPTransportError(f"cannot write to the server: {exc}") from exc

    async def _drain(self) -> None:
        try:
            await self._stdin().drain()
        except (ConnectionError, RuntimeError) as exc:
            raise MCPTransportError(f"cannot write to the server: {exc}") from exc

    def _send_nowait(self, message: Mapping[str, Any]) -> None:
        """Write without waiting for the pipe to drain; drop it if closed."""
        if self._closed or self._process is None:
            return
        with suppress(ConnectionError, RuntimeError, ValueError):
            self._stdin().write(_line(message))

    def _stdin(self) -> asyncio.StreamWriter:
        assert self._process is not None and self._process.stdin is not None
        return self._process.stdin

    def _ensure_open(self) -> None:
        if self._closed:
            raise MCPTransportError(self._closed)
        if self._process is None:
            raise MCPTransportError("the transport has not been started")

    # ---- reading --------------------------------------------------------

    async def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout
        reason = "the server closed its output"
        try:
            while True:
                try:
                    line = await stdout.readline()
                except ValueError:
                    reason = (
                        "the server sent a message larger than "
                        f"{self._max_message_bytes} bytes"
                    )
                    break
                if not line:
                    break
                self._dispatch(line)
        except asyncio.CancelledError:
            self._mark_closed("the event loop serving this transport stopped")
            raise
        except Exception as exc:
            reason = f"reading from the server failed: {exc}"
        if not self._closed:
            self._mark_closed(reason + await self._exit_detail())

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        stderr = self._process.stderr
        partial = ""
        with suppress(Exception):
            while chunk := await stderr.read(4096):
                partial += chunk.decode("utf-8", "replace")
                *lines, partial = partial.split("\n")
                for line in lines:
                    self._remember(line)
                if len(partial) > STDERR_LINE_CHARS:
                    self._remember(partial)
                    partial = ""
        self._remember(partial)

    def _remember(self, line: str) -> None:
        line = line.strip()
        if line:
            self._stderr_tail.append(line[:STDERR_LINE_CHARS])

    def _dispatch(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            return
        kind = classify(message)
        if kind == "response":
            request_id = message["id"]
            future = (
                self._pending.pop(request_id, None)
                if type(request_id) is int
                else None
            )
            if future is not None and not future.done():
                future.set_result(message)
        elif kind == "request":
            self._answer(message)

    def _answer(self, message: Mapping[str, Any]) -> None:
        """Reply to a request the server sent: ``ping`` only."""
        method = message["method"]
        if method == "ping":
            reply = success_response(message["id"], {})
        else:
            reply = error_response(
                message["id"],
                METHOD_NOT_FOUND,
                f"this client does not support {method!r}",
            )
        self._send_nowait(reply)

    async def _exit_detail(self) -> str:
        """Exit code and stderr tail, for the message of a lost connection."""
        await self._wait_exit(1.0)
        if self._stderr_task is not None:
            await asyncio.wait({self._stderr_task}, timeout=0.5)
        parts = []
        if self._process is not None and self._process.returncode is not None:
            parts.append(f"exit code {self._process.returncode}")
        if self._stderr_tail:
            parts.append("stderr: " + " | ".join(self._stderr_tail))
        return f" ({'; '.join(parts)})" if parts else ""

    # ---- closing --------------------------------------------------------

    def _mark_closed(self, reason: str) -> None:
        if not self._closed:
            self._closed = reason
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(MCPTransportError(self._closed))

    async def _shutdown(self) -> None:
        self._mark_closed("the transport was closed")
        process = self._process
        if process is None:
            return
        if process.returncode is None and self._serving:
            with suppress(Exception):
                self._stdin().close()
            if not await self._wait_exit(self._exit_grace_s):
                self._signal(signal.SIGTERM)
                if not await self._wait_exit(self._exit_grace_s):
                    self._signal(_KILL)
                    await self._wait_exit(self._exit_grace_s)
        # Descendants (``npx`` → ``node``) share the group and may outlive
        # the child; they hold the pipes open if left alone.
        self._signal(_KILL)
        await self._wait_exit(self._exit_grace_s)
        for task in (self._stdout_task, self._stderr_task):
            if task is None or task.done():
                continue
            await asyncio.wait({task}, timeout=0.5)
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _wait_exit(self, timeout: float) -> bool:
        """Whether the child has exited, waiting up to *timeout* seconds.

        Polls ``returncode`` rather than awaiting ``wait()``, which also
        waits for every pipe to close — and a surviving grandchild keeps
        them open indefinitely.
        """
        assert self._process is not None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._process.returncode is None:
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(_POLL_S)
        return True

    def _signal(self, signum: int) -> None:
        assert self._process is not None
        with suppress(ProcessLookupError, PermissionError, OSError):
            if _POSIX:
                os.killpg(self._process.pid, signum)
            elif self._process.returncode is None:
                self._process.send_signal(signum)


def _line(message: Mapping[str, Any]) -> bytes:
    """One message as one newline-terminated line."""
    return encode(message) + b"\n"

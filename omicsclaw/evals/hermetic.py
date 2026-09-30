"""An environment an eval run cannot leak out of.

:func:`hermetic_env` removes credentials and provider settings from
``os.environ``, turns telemetry off, points ``HOME`` at a scratch
directory, pins the time zone and locale, and refuses outbound network
connections other than to loopback, for the duration of a ``with``
block. :func:`hermetic_changes` returns the same environment edits as
data, for callers that apply them another way (a pytest ``monkeypatch``).
"""

from __future__ import annotations

import ipaddress
import os
import socket
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = [
    "NETWORK_DISABLED",
    "block_network",
    "hermetic_changes",
    "hermetic_env",
]

NETWORK_DISABLED = "network disabled in hermetic eval"
"""The message of the :exc:`OSError` a refused connection raises."""

_SECRET_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET")
_PREFIXES = ("LLM_", "OTEL_EXPORTER_")
_NAMES = (
    "OMICSCLAW_PROVIDER",
    "OMICSCLAW_MODEL",
    "OMICSCLAW_BASE_URL",
    "OMICSCLAW_OTEL_CAPTURE_CONTENT",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
)


def hermetic_changes(
    home: Path,
    environ: Mapping[str, str] | None = None,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """The environment edits a hermetic run makes.

    :param home: The directory to use as ``HOME``.
    :param environ: The environment to read. ``None`` reads ``os.environ``.
    :returns: ``(removed, set)``: names to delete, and names to set with
        their values.
    """
    source = os.environ if environ is None else environ
    removed = tuple(
        sorted(
            name
            for name in source
            if name.endswith(_SECRET_SUFFIXES)
            or name.startswith(_PREFIXES)
            or name in _NAMES
        )
    )
    updates = {
        "OTEL_ENABLED": "false",
        "HOME": str(home),
        "TZ": "UTC",
        "LANG": "C.UTF-8",
    }
    return removed, updates


def _is_loopback(address: Any, family: int) -> bool:
    if family == getattr(socket, "AF_UNIX", object()):
        return True
    host = address[0] if isinstance(address, tuple) and address else address
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


@contextmanager
def block_network() -> Iterator[None]:
    """Refuse every socket connection that is not to loopback.

    Replaces :meth:`socket.socket.connect` and
    :meth:`socket.socket.connect_ex` inside the block. A refused
    ``connect`` raises :exc:`OSError` with :data:`NETWORK_DISABLED`;
    ``connect_ex`` does the same, since returning an errno would let a
    caller retry silently. Unix sockets and ``127.0.0.0/8``, ``::1`` and
    ``localhost`` are allowed.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def connect(self: socket.socket, address: Any) -> Any:
        if not _is_loopback(address, self.family):
            raise OSError(f"{NETWORK_DISABLED}: {address!r}")
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> Any:
        if not _is_loopback(address, self.family):
            raise OSError(f"{NETWORK_DISABLED}: {address!r}")
        return original_connect_ex(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]


def _tzset() -> None:
    if hasattr(time, "tzset"):
        time.tzset()


@contextmanager
def hermetic_env(home: Path, extra: Mapping[str, str] | None = None) -> Iterator[None]:
    """Run the block in a hermetic environment, then restore the original.

    :param home: The directory to use as ``HOME``. Created if missing.
    :param extra: Variables set last, over the hermetic ones.
    """
    home.mkdir(parents=True, exist_ok=True)
    saved = dict(os.environ)
    removed, updates = hermetic_changes(home)
    try:
        for name in removed:
            os.environ.pop(name, None)
        os.environ.update(updates)
        if extra:
            os.environ.update(extra)
        _tzset()
        with block_network():
            yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
        _tzset()

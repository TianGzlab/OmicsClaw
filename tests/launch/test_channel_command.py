"""``oc channel`` —— the one long-lived process, and how it stops.

Plan 0037 §8-4 asks for "a real process smoke, by a real ``__main__``", and
what was delivered for this surface was ``oc channel -- --list``: a command
that printed the adapter registry and returned **before**
``resolve_app_config`` was called, before an agent was assembled and before a
manager existed. It passed, it ran a real process, and it started nothing.
That is the same shape as step 6's most expensive lesson —— a green suite over
a thing that was never launched —— and the reason this file exists.

**What is real here and what is not.** Everything the shell owns is real: the
deployment is resolved, :func:`~omicsclaw.entry.open_app` assembles an agent,
:func:`~omicsclaw.entry.channel.compose_channel_runtime` builds one runtime,
:class:`~omicsclaw.entry.channel.ChannelManager` opens ingress and runs, a
signal arrives at a real process and the exit code is read by the caller. The
one double is the *adapter*: a :class:`~omicsclaw.entry.channel.base.Channel`
subclass with no platform SDK, because neither ``telegram`` nor ``lark_oapi``
is installed and neither would have a network to reach. The double is
narrower than the protocol, not wider —— it is a real subclass of the real
base class —— which is the direction plan 0031 trap 8 says to keep it.

**Why the probe registers itself as ``"telegram"``.** ``--channels`` is
validated against ``CHANNEL_REGISTRY`` before anything is built, so borrowing
a registered name exercises that check instead of bypassing it.
"""

from __future__ import annotations

import pathlib
import signal
import subprocess
import sys
import time

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_STARTED = "PROBE-STARTED"
_STOPPED = "PROBE-STOPPED"
_DRAINED = "PROBE-SESSIONS-DRAINED"
_RUNTIME_CLOSED = "PROBE-RUNTIME-CLOSED"

_CHANNEL_PROCESS = f'''
import sys

from omicsclaw.entry.channel.base import Channel
from omicsclaw.entry.channel.binding import ChannelSurfaceBinding
from omicsclaw.entry.channel.runtime import ChannelRuntime
from omicsclaw.entry.ingress import SenderPolicy
from omicsclaw.entry.session import SessionRegistry
from omicsclaw.launch import _surfaces, main

# Two witnesses for two cleanup calls that leave no trace of their own.
# AgentApp is a frozen slots dataclass, so its aclose cannot be wrapped on
# the instance; the method it delegates to can be, and it is the only thing
# on this path that calls it. Both wrappers run the real code —— they
# observe, they do not replace.
_real_drain = SessionRegistry.shutdown
_real_close = ChannelRuntime.close


async def _watched_drain(self, grace_s):
    print({_DRAINED!r}, flush=True)
    return await _real_drain(self, grace_s)


async def _watched_close(self, *args, **kwargs):
    print({_RUNTIME_CLOSED!r}, flush=True)
    return await _real_close(self, *args, **kwargs)


SessionRegistry.shutdown = _watched_drain
ChannelRuntime.close = _watched_close


async def _deliver(_request):
    raise AssertionError("this probe never delivers a reply")


class Probe(Channel):
    """A real Channel with no platform behind it."""

    name = "telegram"
    authoritative_ingress = True

    async def start(self):
        self._running = True
        print({_STARTED!r}, flush=True)

    async def stop(self):
        self._running = False
        print({_STOPPED!r}, flush=True)

    async def _send_chunk(self, chat_id, text, **kwargs):
        return None

    async def prepare_control_binding(self):
        return ChannelSurfaceBinding(
            adapter="telegram",
            account_namespace="probe",
            sender_policy=SenderPolicy(
                allowed_senders=frozenset({{"owner"}}), bot_identity="bot"
            ),
            delivery_adapter=_deliver,
        )


_surfaces._CHANNEL_BUILDERS["telegram"] = lambda env: Probe()

sys.exit(
    main(
        [
            "channel",
            "--workspace",
            sys.argv[1],
            "--approval-timeout",
            "5",
            "--",
            "--channels",
            "telegram",
        ],
        {{}},
    )
)
'''

_START_TIMEOUT_S = 90.0
"""Long enough for a cold import of the whole stack on a loaded machine.

A bound and not a wait: there is no ``pytest-timeout`` here, so a test that
blocks blocks the suite. The loop below reads a line at a time and gives up
with the output it has, which is a failure message rather than a hang.
"""

_STOP_TIMEOUT_S = 60.0


def _start_probe(
    workspace: pathlib.Path,
) -> tuple["subprocess.Popen[str]", str]:
    """Launch the command; return once its channel is serving.

    The start-up lines are returned with the process because they are
    read off the pipe here and would otherwise be lost to the
    :meth:`~subprocess.Popen.communicate` that follows —— and they are
    the evidence that a deployment was assembled rather than printed.
    """
    process = subprocess.Popen(
        [sys.executable, "-c", _CHANNEL_PROCESS, str(workspace)],
        cwd=str(_REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    deadline = time.monotonic() + _START_TIMEOUT_S
    seen: list[str] = []
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line:
            seen.append(line)
            if _STARTED in line:
                return process, "".join(seen)
            continue
        if process.poll() is not None:
            break
    process.kill()
    rest, _ = process.communicate(timeout=_STOP_TIMEOUT_S)
    pytest.fail(f"the channel never started:\n{''.join(seen)}{rest}")


def _signal_and_wait(
    process: "subprocess.Popen[str]", number: int, prefix: str = ""
) -> tuple[int, str]:
    process.send_signal(number)
    output, _ = process.communicate(timeout=_STOP_TIMEOUT_S)
    return process.returncode, prefix + output


@pytest.mark.parametrize(
    "number, expected",
    [(signal.SIGTERM, 143), (signal.SIGINT, 130)],
    ids=["sigterm", "sigint"],
)
def test_a_signal_drains_the_channels_and_is_reported_as_128_plus_it(
    tmp_path, number, expected
):
    """Plan 0037 B1 and B2, on the process rather than on a coroutine.

    Before this, ``SIGTERM`` —— what a container, a systemd unit and a
    bare ``kill`` all send —— had no handler, so the default disposition
    applied: the process died where it stood with no channel stopped, no
    runtime closed and no ``AgentApp.aclose``, even though that method's
    docstring says a channel runner closes it on exactly this signal.
    ``SIGINT`` did run the cleanup and then reported ``0``, because
    :meth:`ChannelManager.run` absorbs the cancellation —— so a
    supervisor could not tell "the operator stopped it" from "it
    finished the work".

    Both halves are asserted because the earlier behaviour passed one of
    them each: an exit code alone would have called the ``SIGTERM`` case
    fixed the moment a handler existed, and a shutdown log alone would
    have called the ``SIGINT`` case fixed all along.

    Four cleanup steps and four witnesses. The channel's own ``stop``
    and the manager's log line come for free; the runtime close and the
    session drain do not, and a first version of this test asserted only
    the first two —— under which deleting ``await app.aclose()`` from
    the command was a mutation that survived. Every step of a shutdown
    needs a witness or the shutdown is only partly tested.
    """
    process, started = _start_probe(tmp_path)
    code, output = _signal_and_wait(process, number, started)

    assert code == expected, output
    assert _STOPPED in output, output
    assert "ChannelManager stopped" in output, output
    assert _RUNTIME_CLOSED in output, output
    assert _DRAINED in output, output
    assert "Traceback" not in output, output


def test_the_channel_command_really_assembles_an_agent_before_it_serves(tmp_path):
    """Plan 0037 §8-4 for this surface, replacing a smoke that started nothing.

    ``oc channel -- --list`` returns two statements into
    :func:`~omicsclaw.launch._surfaces.start_channel`. Asserting on the
    *log of a running deployment* is what distinguishes a command that
    launched from a command that printed: the three lines below are
    emitted by three different layers —— assembly, the channel runtime
    and the manager's start-up barrier —— and none of them can be
    reached without the two before it.
    """
    process, started = _start_probe(tmp_path)
    try:
        code, output = _signal_and_wait(process, signal.SIGTERM, started)
    finally:
        if process.poll() is None:  # pragma: no cover - only on a failure
            process.kill()

    assert code == 143, output
    assert "assembled: provider=" in output, output
    assert "channel runtime started for telegram" in output, output
    assert "ChannelManager started (1/1 channels active)" in output, output

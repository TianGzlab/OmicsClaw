"""``ensure_daemon_ready``: probe, optionally start, then poll within a bound."""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from omicsclaw.sandbox import (
    CommandTimedOut,
    SandboxError,
    desktop_starter,
    ensure_daemon_ready,
)

from ._support import ScriptedRunner, fail, ok


def _fast(**overrides):
    values = {"probe_interval_s": 0.01, "restart_grace_s": 0.1, "start_timeout_s": 0.5}
    values.update(overrides)
    return values


def test_a_daemon_that_answers_is_probed_once():
    runner = ScriptedRunner(lambda args: ok("27.0.0"))

    asyncio.run(ensure_daemon_ready(runner, **_fast()))

    assert runner.calls == [["info", "--format", "{{.ServerVersion}}"]]


def test_a_daemon_coming_back_within_the_grace_is_waited_for():
    answers = iter([fail("down"), fail("down"), ok("27.0.0")])
    runner = ScriptedRunner(lambda args: next(answers))

    asyncio.run(ensure_daemon_ready(runner, **_fast()))

    assert len(runner.calls) == 3


def test_no_daemon_and_nothing_started_fails_fast():
    """The short grace is what spares a user without Docker a 90 s wait."""
    runner = ScriptedRunner(lambda args: fail("Cannot connect to the Docker daemon"))

    started = time.monotonic()
    with pytest.raises(SandboxError, match="Cannot connect") as caught:
        asyncio.run(ensure_daemon_ready(runner, **_fast()))

    assert time.monotonic() - started < 0.5
    assert "start attempted: no" in str(caught.value)


def test_a_started_daemon_gets_the_longer_budget():
    attempts: list[bool] = []
    answers = iter([fail("down")] * 20 + [ok("27.0.0")])
    runner = ScriptedRunner(lambda args: next(answers))

    async def start() -> bool:
        attempts.append(True)
        return True

    asyncio.run(
        ensure_daemon_ready(
            runner, start_daemon=start, **_fast(restart_grace_s=0.05, start_timeout_s=5)
        )
    )

    assert attempts == [True]
    assert len(runner.calls) == 21


def test_a_missing_cli_is_not_polled():
    runner = ScriptedRunner(lambda args: SandboxError("cannot run 'docker'"))

    with pytest.raises(SandboxError, match="cannot run"):
        asyncio.run(ensure_daemon_ready(runner, **_fast()))

    assert len(runner.calls) == 1


def test_a_hanging_probe_counts_as_down():
    answers = iter([CommandTimedOut("docker info did not finish"), ok("27.0.0")])
    runner = ScriptedRunner(lambda args: next(answers))

    asyncio.run(ensure_daemon_ready(runner, **_fast()))

    assert len(runner.calls) == 2


def test_only_docker_desktop_on_macos_is_ever_started():
    """On Linux the daemon belongs to the init system and needs root."""
    if sys.platform == "darwin":
        assert desktop_starter("docker") is not None
    else:
        assert desktop_starter("docker") is None
    assert desktop_starter("podman") is None

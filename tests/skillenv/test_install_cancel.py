"""Cancelling an installation, or running past its limit, leaves nothing behind (plan 0061 case 20, §4.5 step 8).

pip is replaced here, at one stage, by a process that starts a ``sleep``
child in its own process group and then sleeps: a stand-in for a long
resolution or download. Cancelling the call — a turn timeout or a person
interrupting — must kill that whole group, remove the overlay directory
that has no fingerprint, release the lock so the next call can take it
straight away, and let the cancellation propagate. Running past
``skill_env_install_timeout_s`` takes the same path but ends as an ordinary
failed result.

Liveness is read from ``/proc``, because a killed but unreaped process is a
zombie and ``os.kill(pid, 0)`` would still find it.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
import time
from pathlib import Path

import pytest

from omicsclaw.skillenv.overlay import InstallLimits
from omicsclaw.tools.context import ApprovalDecision, use_tool_context

from .installing import SKILL, harness
from .wheels import make_wheel, pip_conf

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads process state from /proc")


def _running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat[stat.rfind(")") + 2:].split()[0] != "Z"


def _dies(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while _running(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def _sleepy(h, stage: str, pidfile: Path) -> None:
    code = (
        "import subprocess, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    inner = h.runner.inner

    class Sleepy:
        async def run(self, argv, *, cwd, env, timeout):
            call_stage = _stage(argv)
            if call_stage == stage:
                argv = [sys.executable, "-c", code]
            return await inner.run(argv, cwd=cwd, env=env, timeout=timeout)

    h.runner.inner = Sleepy()


def _stage(argv) -> str:
    rest = list(argv[4:])
    if "--dry-run" in rest:
        return "dry-run"
    if rest[:1] == ["install"]:
        return "install"
    return ""


def _lock_is_free(root: Path) -> bool:
    (lock,) = list((root / ".locks").glob("*.lock"))
    handle = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(handle)


def _wheels(directory: Path) -> Path:
    make_wheel(directory, "oc-leaf", "1.0", requires=["oc-dep>=1"])
    make_wheel(directory, "oc-dep", "1.0")
    return directory


@pytest.mark.parametrize("stage", ["dry-run", "install"])
def test_cancelling_kills_pip_removes_the_overlay_and_frees_the_lock(tmp_path, stage):
    pidfile = tmp_path / "child.pid"
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))
    _sleepy(h, stage, pidfile)

    async def main():
        with use_tool_context(approval=lambda request: ApprovalDecision(approved=True)):
            task = asyncio.ensure_future(h.tool.execute(json.dumps({"skill": SKILL, "packages": ["oc-leaf"]})))
            deadline = time.monotonic() + 120
            while not pidfile.exists():
                assert time.monotonic() < deadline and not task.done(), "the stand-in never started"
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(main())
    assert _dies(int(pidfile.read_text()))
    assert h.key_dirs() == []
    assert _lock_is_free(h.root)


def test_running_past_the_limit_takes_the_same_path(tmp_path):
    pidfile = tmp_path / "child.pid"
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]),
                limits=InstallLimits(total_s=6.0))
    _sleepy(h, "dry-run", pidfile)
    began = time.monotonic()
    output = h.call(["oc-leaf"])
    assert time.monotonic() - began < 60
    assert "did not finish within 6 s" in output, output
    assert _dies(int(pidfile.read_text()))
    assert h.key_dirs() == []
    assert _lock_is_free(h.root)

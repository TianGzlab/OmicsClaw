"""Where trial commands run: this machine, or the ``bash`` sandbox.

Local trials start in a process group of their own, in their own trial
directory, with an environment built from a whitelist — the agent's API keys
never reach a skill script. Cancellation kills the whole group. The sandbox
path cannot pass an environment to ``run_bash``, so variables travel as an
``env K=V`` prefix, and every argument is shell-quoted because a path or a
parameter value with a space or a quote must arrive as one argument.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from omicsclaw.ensemble.execution import (
    ENV_WHITELIST,
    LocalExecutor,
    SandboxExecutor,
    whitelisted_environment,
)

_PRINT_ENV = (
    "import os, json; print(json.dumps({'cwd': os.getcwd(), "
    "'env': {k: os.environ.get(k) for k in ('TMPDIR', 'MPLCONFIGDIR', 'NUMBA_CACHE_DIR', "
    "'LLM_API_KEY', 'PATH', 'CUDA_VISIBLE_DEVICES')}}))"
)


def _trial_env(trial: Path) -> dict[str, str]:
    return {
        "TMPDIR": str(trial / "tmp"),
        "MPLCONFIGDIR": str(trial / "tmp" / "mpl"),
        "NUMBA_CACHE_DIR": str(trial / "tmp" / "numba"),
        "CUDA_VISIBLE_DEVICES": "",
    }


def test_the_whitelist_drops_secrets():
    env = whitelisted_environment({"PATH": "/bin", "LLM_API_KEY": "sk-x", "TELEGRAM_BOT_TOKEN": "t"})
    assert env == {"PATH": "/bin"}
    assert "LLM_API_KEY" not in ENV_WHITELIST


def test_a_local_command_runs_in_its_trial_directory_with_its_own_temp_dirs(tmp_path):
    import json

    executor = LocalExecutor(base_env={"PATH": os.environ["PATH"], "LLM_API_KEY": "sk-secret"})
    seen = []
    for name in ("t0001", "t0002"):
        trial = tmp_path / name
        (trial / "tmp").mkdir(parents=True)
        log = trial / "run.log"
        result = asyncio.run(
            executor.run([sys.executable, "-c", _PRINT_ENV], cwd=trial, env=_trial_env(trial), log=log, timeout=30)
        )
        assert result.exit_code == 0 and not result.timed_out
        seen.append(json.loads(log.read_text()))
    assert seen[0]["cwd"] == str(tmp_path / "t0001")
    assert seen[0]["env"]["LLM_API_KEY"] is None
    assert seen[0]["env"]["CUDA_VISIBLE_DEVICES"] == ""
    for key in ("TMPDIR", "MPLCONFIGDIR", "NUMBA_CACHE_DIR"):
        assert seen[0]["env"][key] != seen[1]["env"][key]
        assert seen[0]["env"][key].startswith(str(tmp_path / "t0001"))


def test_a_local_timeout_kills_the_group(tmp_path):
    executor = LocalExecutor()
    pidfile = tmp_path / "child.pid"
    code = f"import subprocess, time; p = subprocess.Popen(['sleep', '60']); open({str(pidfile)!r}, 'w').write(str(p.pid)); time.sleep(60)"
    began = time.monotonic()
    result = asyncio.run(
        executor.run([sys.executable, "-c", code], cwd=tmp_path, env={}, log=tmp_path / "log", timeout=1.0)
    )
    assert result.timed_out and time.monotonic() - began < 10
    _assert_dead(int(pidfile.read_text()))


def test_cancelling_a_local_command_kills_the_group(tmp_path):
    executor = LocalExecutor()
    pidfile = tmp_path / "child.pid"
    code = f"import subprocess, time; p = subprocess.Popen(['sleep', '60']); open({str(pidfile)!r}, 'w').write(str(p.pid)); time.sleep(60)"

    async def main():
        task = asyncio.ensure_future(
            executor.run([sys.executable, "-c", code], cwd=tmp_path, env={}, log=tmp_path / "log", timeout=60)
        )
        for _ in range(200):
            if pidfile.exists() and pidfile.read_text():
                break
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(main(), 30))
    _assert_dead(int(pidfile.read_text()))


def test_capture_returns_output(tmp_path):
    result = asyncio.run(LocalExecutor().capture([sys.executable, "-c", "print('ready')"], cwd=tmp_path, timeout=30))
    assert result.exit_code == 0 and result.output.strip() == "ready"


def _assert_dead(pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with open(f"/proc/{pid}/stat") as handle:
                if handle.read().split(")")[-1].split()[0] == "Z":
                    return
        except OSError:
            return
        time.sleep(0.05)
    os.kill(pid, 9)
    pytest.fail(f"process {pid} outlived its group")


# ---- the sandbox path ----------------------------------------------------------------------


@dataclass
class _Outcome:
    output: str
    exit_code: int
    timed_out: bool = False


class _FakeEnvironment:
    def __init__(self):
        self.calls: list[tuple[str, str, float]] = []

    async def run_bash(self, command, cwd, timeout):
        self.calls.append((command, cwd, timeout))
        return _Outcome(output="", exit_code=0)


def test_the_sandbox_command_is_quoted_with_an_env_prefix(tmp_path):
    environment = _FakeEnvironment()
    executor = SandboxExecutor(environment)
    trial = tmp_path / "run 1" / "t0001"
    argv = ["python", "/repo/omicsclaw/ensemble/_supervise.py", "--", "python", "script.py", "--input", "/ws/a b's.h5ad"]
    result = asyncio.run(
        executor.run(argv, cwd=trial, env={"TMPDIR": str(trial / "tmp"), "CUDA_VISIBLE_DEVICES": ""},
                     log=trial / "run.log", timeout=123.0)
    )
    assert result.exit_code == 0
    command, cwd, timeout = environment.calls[0]
    assert cwd == str(trial) and timeout == 123.0
    words = shlex.split(command)
    assert words[0] == "env"
    assert words[1] == f"TMPDIR={trial / 'tmp'}"
    assert words[2] == "CUDA_VISIBLE_DEVICES="
    assert words[3:3 + len(argv)] == argv
    assert words[-3:] == [">>", str(trial / "run.log"), "2>&1"]
    assert "LLM_API_KEY" not in command
    assert executor.python == "python" and executor.location == "sandbox"

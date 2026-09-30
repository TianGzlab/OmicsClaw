"""GPU detection for the ensemble pool.

An empty ``ensemble_gpus`` means "detect": ``nvidia-smi`` on this machine, or
inside the container when the sandbox runs, because a container sees only the
devices passed to it. A sandbox started without ``--gpus`` sees none, and that
is said out loud rather than discovered as a slow CPU run. A missing or broken
``nvidia-smi`` is zero GPUs, never a start-up failure. An explicit list is
taken as given and nothing is probed.
"""

from __future__ import annotations

import asyncio
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

from omicsclaw.ensemble.resources import detect_gpus, parse_gpu_setting


def _fake_smi(directory: Path, lines: int, *, exit_code: int = 0) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "nvidia-smi"
    body = "".join(f"echo {i}\n" for i in range(lines))
    script.write_text(f"#!/bin/sh\n{body}exit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return {"PATH": f"{directory}:/usr/bin:/bin"}


@pytest.mark.parametrize("lines", [0, 2, 4])
def test_detection_counts_what_nvidia_smi_lists(tmp_path, lines):
    env = _fake_smi(tmp_path / "bin", lines)
    found = asyncio.run(detect_gpus("", env=env))
    assert found.ids == tuple(str(i) for i in range(lines))
    assert found.source == "detected"
    assert found.describe().startswith(f"{lines} ")


def test_a_missing_nvidia_smi_is_zero_gpus(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    found = asyncio.run(detect_gpus("", env={"PATH": str(empty)}))
    assert found.ids == () and "not on PATH" in found.detail


def test_a_failing_nvidia_smi_is_zero_gpus(tmp_path):
    env = _fake_smi(tmp_path / "bin", 4, exit_code=9)
    found = asyncio.run(detect_gpus("", env=env))
    assert found.ids == () and "exited 9" in found.detail


def test_cuda_visible_devices_narrows_detection(tmp_path):
    env = _fake_smi(tmp_path / "bin", 4)
    env["CUDA_VISIBLE_DEVICES"] = "1,3"
    assert asyncio.run(detect_gpus("", env=env)).ids == ("1", "3")
    env["CUDA_VISIBLE_DEVICES"] = ""
    assert asyncio.run(detect_gpus("", env=env)).ids == ()


def test_an_explicit_setting_is_not_probed(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    found = asyncio.run(detect_gpus("0,2", env={"PATH": str(empty)}))
    assert (found.ids, found.source) == (("0", "2"), "configured")
    none = asyncio.run(detect_gpus("none", env={"PATH": str(empty)}))
    assert (none.ids, none.source) == ((), "none")


def test_parse_gpu_setting():
    assert parse_gpu_setting("") is None
    assert parse_gpu_setting("NONE") == ()
    assert parse_gpu_setting("0, 1") == ("0", "1")
    with pytest.raises(ValueError):
        parse_gpu_setting("0,,1")


@dataclass
class _Outcome:
    output: str
    exit_code: int


class _FakeSandbox:
    def __init__(self, output: str = "0\n1\n", exit_code: int = 0):
        self.output = output
        self.exit_code = exit_code
        self.commands: list[tuple[str, str, float]] = []

    async def run_bash(self, command, cwd, timeout):
        self.commands.append((command, cwd, timeout))
        return _Outcome(self.output, self.exit_code)


def test_in_the_sandbox_detection_runs_inside_the_container():
    sandbox = _FakeSandbox("0\n1\n")
    found = asyncio.run(detect_gpus("", environment=sandbox, cwd="/ws", sandbox_gpus="all"))
    assert found.ids == ("0", "1")
    assert sandbox.commands[0][0].startswith("nvidia-smi --query-gpu=index")
    assert sandbox.commands[0][1] == "/ws"


def test_a_sandbox_without_gpus_detects_none_and_warns():
    sandbox = _FakeSandbox("0\n")
    found = asyncio.run(detect_gpus("", environment=sandbox, cwd="/ws", sandbox_gpus=""))
    assert found.ids == ()
    assert "--sandbox-gpus" in found.warning
    assert sandbox.commands == []


def test_a_failing_probe_in_the_sandbox_is_zero_gpus():
    sandbox = _FakeSandbox("", exit_code=127)
    found = asyncio.run(detect_gpus("", environment=sandbox, cwd="/ws", sandbox_gpus="all"))
    assert found.ids == () and "exited 127" in found.detail

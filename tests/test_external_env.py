"""Tests for the cross-env subprocess bridge."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from omicsclaw.core.external_env import (
    EnvNotFoundError,
    is_env_available,
    run_python_in_env,
)


def _current_env_name() -> str:
    """Return the active conda env name, or skip if not in a conda env."""
    name = os.environ.get("CONDA_DEFAULT_ENV", "")
    if not name or not shutil.which("mamba"):
        pytest.skip("requires conda/mamba env")
    return name


def test_is_env_available_true_for_current_env():
    name = _current_env_name()
    assert is_env_available(name)


def test_is_env_available_false_for_missing_env():
    assert not is_env_available("omicsclaw_definitely_does_not_exist_xyz")


def test_is_env_available_falls_back_when_preferred_runner_fails(monkeypatch):
    import omicsclaw.core.external_env as external_env

    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return f"/bin/{name}" if name in {"mamba", "conda"} else None

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[0] == "mamba":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="mamba broken")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="# conda environments:\nOmicsClaw * /envs/OmicsClaw\n",
            stderr="",
        )

    monkeypatch.setattr(external_env.shutil, "which", fake_which)
    monkeypatch.setattr(external_env.subprocess, "run", fake_run)

    assert is_env_available("OmicsClaw")
    assert calls == [["mamba", "env", "list"], ["conda", "env", "list"]]


def test_run_python_in_env_returns_stdout():
    name = _current_env_name()
    out = run_python_in_env(name, "import sys; print(sys.version_info[0])")
    assert out.strip() == "3"


def test_run_python_in_env_raises_on_missing_env():
    with pytest.raises(EnvNotFoundError):
        run_python_in_env("omicsclaw_does_not_exist", "print(1)")


def test_run_python_in_env_propagates_subprocess_error():
    name = _current_env_name()
    with pytest.raises(subprocess.CalledProcessError):
        run_python_in_env(name, "raise RuntimeError('boom')")

"""Start-up of the skill environment check, and what the local probe inherits.

Added after the independent review of plan 0061 P1:

* ``open_app`` must actually log ``skill_env=… location=… python=…`` — the
  line is written from ``_swept``, so a ``_swept`` that stops calling it
  would leave every unit test of ``log_skill_env`` green (review mutation M12).
* Read-only mode in a sandbox runs no probe, because running one writes
  files under the workspace's ``.omicsclaw/sandbox``; the line says
  ``python=unchecked`` instead (M11).
* ``_swept`` promises that only a cancellation gets out and that it closes
  the memory database on the way; the probe can wait up to ten seconds, so a
  cancellation during it must close the database too.
* The local probe runs with the environment ``bash`` gets, which has the
  framework's control-plane credential removed, compared case-insensitively
  (M6).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig
from omicsclaw.entry.sandbox import SandboxBinding
from omicsclaw.entry.skill_env import build_skill_env, log_skill_env
from omicsclaw.permission import PermissionMode
from omicsclaw.skillenv.probe import LocalProbeRunner
from omicsclaw.tools.builtin.bash import CommandOutcome
from tests.entry.test_golden_deployment import _Offline

from .conftest import FIXTURE_SKILLS

LOGGER = "omicsclaw.entry.skill_env"


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def _config(tmp_path, **overrides) -> AppConfig:
    return AppConfig(workspace=tmp_path, skills_dir=FIXTURE_SKILLS, **overrides)


def test_open_app_writes_the_startup_line(tmp_path, offline, caplog):
    async def main():
        app = await assembly.open_app(_config(tmp_path))
        await app.aclose()

    with caplog.at_level(logging.INFO, logger=LOGGER):
        asyncio.run(main())
    lines = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert any(line.startswith("skill_env=probe location=local python=/") for line in lines), lines


class _RecordingEnvironment:
    def __init__(self):
        self.calls: list[str] = []

    async def run_bash(self, command, cwd, timeout):
        self.calls.append(command)
        return CommandOutcome(output="", exit_code=1)


def test_read_only_in_a_sandbox_runs_no_probe(tmp_path, caplog):
    config = _config(tmp_path, permission_mode=PermissionMode.READ_ONLY)
    environment = _RecordingEnvironment()
    binding = build_skill_env(config, assembly.build_skill_index(config), SandboxBinding(environment=environment))
    assert binding.location == "sandbox"
    with caplog.at_level(logging.INFO, logger=LOGGER):
        asyncio.run(log_skill_env(binding, config))
    assert environment.calls == []
    assert [r.getMessage() for r in caplog.records if r.name == LOGGER] == [
        "skill_env=probe location=sandbox python=unchecked"
    ]


class _ForeverRunner:
    location = "local"

    def __init__(self):
        self.started = asyncio.Event()

    async def run(self, command, *, cwd, timeout, env=None):
        self.started.set()
        await asyncio.Event().wait()


class _Memory:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


def test_a_cancellation_during_the_startup_probe_closes_memory(tmp_path, offline, monkeypatch):
    async def no_maintenance(memory):
        return 0

    monkeypatch.setattr(assembly, "prepare_memory", no_maintenance)
    config = _config(tmp_path)
    app = assembly.build_app(config)
    real_memory = app.memory
    try:
        runner = _ForeverRunner()
        memory = _Memory()
        app = dataclasses.replace(
            app, memory=memory, skill_env=dataclasses.replace(app.skill_env, runner=runner)
        )

        async def main():
            task = asyncio.create_task(assembly._swept(app))
            started = asyncio.create_task(runner.started.wait())
            await asyncio.wait({task, started}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
            assert runner.started.is_set(), "the start-up probe never ran"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(main())
        assert memory.closed == 1
    finally:
        if real_memory is not None:
            real_memory.close()


def test_the_local_probe_does_not_inherit_the_control_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "secret-upper")
    monkeypatch.setenv("omicsclaw_remote_auth_token", "secret-lower")
    monkeypatch.setenv("OMICSCLAW_PROBE_SENTINEL", "kept")
    code, output = asyncio.run(LocalProbeRunner().run("env", cwd=str(tmp_path), timeout=10))
    assert code == 0
    names = {line.split("=", 1)[0].upper() for line in output.splitlines() if "=" in line}
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" not in names
    assert "secret" not in output
    assert "OMICSCLAW_PROBE_SENTINEL=kept" in output

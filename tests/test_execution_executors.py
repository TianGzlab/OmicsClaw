"""Executor abstraction scaffolding.

``omicsclaw/execution/executors/`` provides the Executor Protocol that
real executors (``SkillRunnerExecutor`` for the in-process runner,
``SubprocessExecutor`` for the SSH/Slurm path) implement. The legacy
``LocalExecutor`` ``executor_not_implemented`` stub was removed during
OMI-12 P1.5 — tests that need an instant-return executor define one
inline.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest


def test_base_module_exports_protocol_and_dataclasses() -> None:
    from omicsclaw.execution.executors import (
        Executor,
        JobContext,
        JobOutcome,
    )

    assert inspect.isclass(JobContext)
    assert inspect.isclass(JobOutcome)
    assert hasattr(Executor, "run")


def test_executor_protocol_accepts_duck_typed_implementations() -> None:
    """Any callable that exposes ``async def run(ctx) -> JobOutcome`` is a
    valid ``Executor`` — no subclassing required. This is the contract that
    SSH / Slurm / mock executors all rely on."""
    from omicsclaw.execution.executors import Executor, JobContext, JobOutcome

    class FakeExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            return JobOutcome(
                exit_code=0,
                error=None,
                stdout_text="custom-run",
            )

    # Structural — no runtime isinstance needed; this asserts the shape.
    fake: Executor = FakeExecutor()  # type: ignore[assignment]
    outcome = asyncio.run(fake.run(  # type: ignore[arg-type]
        JobContext(
            job_id="x",
            workspace=Path("/tmp"),
            skill="noop",
            inputs={},
            params={},
            artifact_root=Path("/tmp/a"),
            stdout_log=Path("/tmp/s.log"),
        )
    ))
    assert outcome.exit_code == 0
    assert outcome.stdout_text == "custom-run"


def test_jobs_router_dispatches_via_executor(monkeypatch, tmp_path: Path) -> None:
    """Swap the default executor and confirm a submitted job's terminal
    state reflects the custom outcome — i.e. the router delegates to the
    abstraction rather than hard-coding the stub behavior."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.execution.executors import JobContext, JobOutcome
    from omicsclaw.remote.app_integration import register_remote_routers
    from omicsclaw.remote.routers import jobs as jobs_module

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)

    class SuccessExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            return JobOutcome(
                exit_code=0,
                error=None,
                stdout_text="custom-success-marker",
            )

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", SuccessExecutor())

    app = FastAPI()
    register_remote_routers(app)
    client = TestClient(app)

    response = client.post("/jobs", json={"skill": "noop", "inputs": {}})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    assert "event: job_succeeded" in body
    assert "event: job_failed" not in body

    final = client.get(f"/jobs/{job_id}").json()
    assert final["status"] == "succeeded"
    assert final["exit_code"] == 0

    stdout = (
        workspace
        / ".omicsclaw"
        / "remote"
        / "jobs"
        / job_id
        / "stdout.log"
    ).read_text(encoding="utf-8")
    assert "custom-success-marker" in stdout

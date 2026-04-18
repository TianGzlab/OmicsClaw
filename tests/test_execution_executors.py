"""Executor abstraction scaffolding.

``omicsclaw/execution/executors/`` provides the Executor Protocol and a
baseline ``LocalExecutor`` that wraps today's ``executor_not_implemented``
stub behavior. Keeping the same wire-level semantics lets us swap in a
real in-process runner later without changing the App-facing contract.

A matching Protocol makes SSH / Slurm executors a drop-in replacement once
they land (plan §Non-Goals pins Slurm to Phase 9).
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


def test_local_executor_returns_executor_not_implemented_outcome(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import (
        JobContext,
        JobOutcome,
        LocalExecutor,
    )

    stdout_log = tmp_path / "stdout.log"
    artifact_root = tmp_path / "artifacts"
    ctx = JobContext(
        job_id="job-1",
        workspace=tmp_path,
        skill="spatial-preprocess",
        inputs={"dataset_id": "abc"},
        params={},
        artifact_root=artifact_root,
        stdout_log=stdout_log,
    )
    outcome = asyncio.run(LocalExecutor().run(ctx))
    assert isinstance(outcome, JobOutcome)
    assert outcome.exit_code == 1
    assert outcome.error == "executor_not_implemented"
    assert outcome.stdout_text
    assert "executor_not_implemented" in outcome.stdout_text


def test_local_executor_supports_custom_implementations() -> None:
    """LocalExecutor itself can be replaced by any Executor-compatible
    callable. Smoke-check Protocol duck-typing so alternate executors
    don't need to subclass anything."""
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

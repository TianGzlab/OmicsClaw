"""``POST /jobs/{id}/cancel`` must interrupt the in-flight executor.

Before Stage 6 the cancel endpoint only flipped ``job.json`` to
``canceled``; the asyncio task driving the executor (and any subprocess
beneath it) kept running to completion. This file pins the real
requirement at the unit level: ``cancel_job`` must call
``asyncio.Task.cancel()`` on the registered task so ``CancelledError``
reaches the executor's ``await`` point and e.g. ``SubprocessExecutor``'s
SIGTERM path runs.

Tests drive the handler directly via ``asyncio.run`` rather than through
``TestClient``. The TestClient's underlying httpx Client is explicitly
not thread-safe, so cross-thread SSE+cancel scenarios serialize on the
connection pool — a cancel sent from a side thread stays queued behind
the streaming read until the stream naturally closes, making it
impossible to observe real cancel propagation through that code path.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from omicsclaw.remote.routers import jobs as jobs_module
from omicsclaw.remote.schemas import Job


def _seed_running_job(workspace: Path, job_id: str) -> None:
    job_dir = workspace / ".omicsclaw" / "remote" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    job = Job(
        job_id=job_id,
        session_id="",
        skill="slow",
        status="running",
        workspace=str(workspace),
        inputs={},
        params={},
        created_at="2025-01-01T00:00:00+00:00",
        started_at="2025-01-01T00:00:01+00:00",
    )
    (job_dir / "job.json").write_text(
        json.dumps(job.model_dump()),
        encoding="utf-8",
    )


def _prepare_workspace(monkeypatch, tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)
    # Avoid reconciler flipping our seeded running job.
    jobs_module._RECONCILED_WORKSPACES.add(workspace.resolve())
    return workspace


def test_cancel_job_calls_task_cancel_on_registered_task(
    monkeypatch, tmp_path: Path
) -> None:
    """The one-line fix: cancel_job must call ``task.cancel()`` so a
    running executor observes ``CancelledError`` instead of running to
    its natural (30 s) completion.

    Verification uses passive observation (``task.done()`` after a short
    yield) rather than ``asyncio.wait_for`` — wait_for cancels the task
    itself on timeout, which would mask the exact bug we're testing.
    """
    workspace = _prepare_workspace(monkeypatch, tmp_path)
    job_id = "cancel-subject"
    _seed_running_job(workspace, job_id)

    async def scenario() -> tuple[bool, bool]:
        async def long_lived() -> None:
            await asyncio.sleep(30.0)

        task = asyncio.create_task(long_lived())
        jobs_module._STUB_JOB_TASKS[job_id] = task
        try:
            await asyncio.sleep(0.05)  # park the task inside sleep
            assert not task.done(), "precondition: task should still be sleeping"

            result = await jobs_module.cancel_job(job_id)
            assert result.status == "canceled"

            # Yield a few times so any scheduled cancellation can land.
            for _ in range(5):
                await asyncio.sleep(0.05)
                if task.done():
                    break

            return task.done(), task.cancelled()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            jobs_module._STUB_JOB_TASKS.pop(job_id, None)

    done, cancelled = asyncio.run(scenario())
    assert done, (
        "task still running 0.25 s after cancel_job — cancel_job did not "
        "call task.cancel() (task is still in its 30 s sleep)"
    )
    assert cancelled, "task.done() but task.cancelled() is False"


def test_cancel_job_idempotent_second_call_is_noop(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = _prepare_workspace(monkeypatch, tmp_path)
    job_id = "idempotent-subject"
    _seed_running_job(workspace, job_id)

    async def scenario() -> None:
        async def immediate() -> None:
            return None

        task = asyncio.create_task(immediate())
        await task
        jobs_module._STUB_JOB_TASKS[job_id] = task
        try:
            first = await jobs_module.cancel_job(job_id)
            second = await jobs_module.cancel_job(job_id)
            assert first.status == "canceled"
            assert second.status == "canceled"
        finally:
            jobs_module._STUB_JOB_TASKS.pop(job_id, None)

    asyncio.run(scenario())


def test_cancel_job_without_registered_task_still_flips_status(
    monkeypatch, tmp_path: Path
) -> None:
    """Cancel must not require a live task in the registry — running jobs
    restored from disk (or ones whose task already finished) should still
    receive a clean status flip."""
    workspace = _prepare_workspace(monkeypatch, tmp_path)
    job_id = "no-task-subject"
    _seed_running_job(workspace, job_id)

    async def scenario() -> str:
        assert job_id not in jobs_module._STUB_JOB_TASKS
        result = await jobs_module.cancel_job(job_id)
        return result.status

    assert asyncio.run(scenario()) == "canceled"


def test_cancel_job_does_not_raise_when_task_is_already_done(
    monkeypatch, tmp_path: Path
) -> None:
    """``asyncio.Task.cancel()`` on a completed task returns False but
    must not raise — regression guard for a common footgun."""
    workspace = _prepare_workspace(monkeypatch, tmp_path)
    job_id = "already-done-subject"
    _seed_running_job(workspace, job_id)

    async def scenario() -> str:
        async def already_done() -> None:
            return None

        task = asyncio.create_task(already_done())
        await task
        assert task.done()
        jobs_module._STUB_JOB_TASKS[job_id] = task
        try:
            result = await jobs_module.cancel_job(job_id)
            return result.status
        finally:
            jobs_module._STUB_JOB_TASKS.pop(job_id, None)

    assert asyncio.run(scenario()) == "canceled"

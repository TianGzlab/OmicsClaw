"""Server-restart reconcile for orphaned ``running`` jobs.

Scenario: the backend writes a job JSON with status ``running`` and an
asyncio stub task that drives it to terminal state. If the process restarts
while the job is running, the JSON stays at ``running`` but no task is
driving it — the App would see "running forever". On first touch of a
workspace, the router must mark such orphans as ``failed`` with a specific
error code and persist diagnostic artifacts so the App can surface the
reason.

Newly submitted jobs (no prior stub task yet) must NOT be touched by the
reconciler: they are legitimately queued/running on the current process.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.remote.app_integration import register_remote_routers
from omicsclaw.remote.routers import jobs as jobs_module


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)
    app = FastAPI()
    register_remote_routers(app)
    return TestClient(app)


def _seed_pre_existing_job(workspace: Path, job_id: str, status: str) -> Path:
    """Plant a job JSON on disk as if it predated the current process."""
    job_dir = workspace / ".omicsclaw" / "remote" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    payload = {
        "job_id": job_id,
        "session_id": "",
        "skill": "spatial-preprocess",
        "status": status,
        "workspace": str(workspace),
        "inputs": {},
        "params": {},
        "created_at": "2025-01-01T00:00:00+00:00",
        "started_at": "2025-01-01T00:00:01+00:00" if status == "running" else None,
        "finished_at": None,
        "exit_code": None,
        "error": None,
        "artifact_root": None,
    }
    (job_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")
    return job_dir


def test_orphaned_running_job_marked_failed_on_first_touch(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "orphan-1", status="running")

    response = client.get("/jobs/orphan-1")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "server_restart_orphaned_job"
    assert body["exit_code"] == 1
    assert body["finished_at"] is not None
    assert body["artifact_root"] is not None


def test_orphan_reconcile_persists_diagnostic_artifacts(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "orphan-2", status="running")

    # Trigger reconcile.
    client.get("/jobs/orphan-2")

    artifacts = client.get("/artifacts", params={"job_id": "orphan-2"}).json()
    paths = {artifact["relative_path"] for artifact in artifacts["artifacts"]}
    assert "diagnostics/stdout.log" in paths
    assert "diagnostics/env_doctor.json" in paths


def test_queued_pre_existing_job_is_not_reconciled(
    client: TestClient, tmp_path: Path
) -> None:
    """Queued jobs auto-recover via _ensure_stub_job; the reconciler must
    never flip them to failed."""
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "queued-1", status="queued")

    response = client.get("/jobs/queued-1")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json().get("error") is None


def test_new_submitted_job_not_touched_by_reconcile(client: TestClient) -> None:
    """Submitting a fresh job must not be reconciled as orphaned — its
    stub task is alive on the current process."""
    response = client.post(
        "/jobs", json={"skill": "spatial-preprocess", "inputs": {}}
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    immediate = client.get(f"/jobs/{job_id}").json()
    # Must not have been prematurely failed with the orphan reason.
    assert immediate.get("error") != "server_restart_orphaned_job"


def test_terminal_jobs_not_reconciled(client: TestClient, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "already-done", status="succeeded")

    response = client.get("/jobs/already-done")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body.get("error") is None


def test_list_jobs_also_reconciles_orphans(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "orphan-list", status="running")

    listed = client.get("/jobs").json()
    orphan = next(j for j in listed["jobs"] if j["job_id"] == "orphan-list")
    assert orphan["status"] == "failed"
    assert orphan["error"] == "server_restart_orphaned_job"


def test_orphan_reconcile_retries_workspace_after_transient_failure(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    _seed_pre_existing_job(workspace, "orphan-retry", status="running")
    jobs_module._RECONCILED_WORKSPACES.clear()

    original = jobs_module._persist_failure_diagnostics
    attempts = {"count": 0}

    def flaky_persist(workspace: Path, job_id: str, *, stdout_text: str) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("disk full")
        return original(workspace, job_id, stdout_text=stdout_text)

    monkeypatch.setattr(jobs_module, "_persist_failure_diagnostics", flaky_persist)

    first = client.get("/jobs/orphan-retry")
    assert first.status_code == 200
    assert first.json()["status"] == "running"

    second = client.get("/jobs/orphan-retry")
    assert second.status_code == 200
    assert second.json()["status"] == "failed"
    assert second.json()["error"] == "server_restart_orphaned_job"
    assert attempts["count"] == 2


def test_orphan_reconcile_continues_after_single_job_failure(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    bad_dir = _seed_pre_existing_job(workspace, "bad-job", status="running")
    good_dir = _seed_pre_existing_job(workspace, "good-job", status="running")
    jobs_module._RECONCILED_WORKSPACES.clear()

    jobs_dir = workspace / ".omicsclaw" / "remote" / "jobs"
    original_iterdir = Path.iterdir

    def ordered_iterdir(self: Path):
        if self == jobs_dir:
            return iter([bad_dir, good_dir])
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", ordered_iterdir)

    original = jobs_module._persist_failure_diagnostics

    def flaky_persist(workspace: Path, job_id: str, *, stdout_text: str) -> str:
        if job_id == "bad-job":
            raise OSError("diagnostics write failed")
        return original(workspace, job_id, stdout_text=stdout_text)

    monkeypatch.setattr(jobs_module, "_persist_failure_diagnostics", flaky_persist)

    response = client.get("/jobs")
    assert response.status_code == 200

    rows = {job["job_id"]: job for job in response.json()["jobs"]}
    assert rows["bad-job"]["status"] == "running"
    assert rows["bad-job"]["error"] is None
    assert rows["good-job"]["status"] == "failed"
    assert rows["good-job"]["error"] == "server_restart_orphaned_job"

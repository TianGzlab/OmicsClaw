"""Contract tests for ``omicsclaw/remote/`` routers.

Validates the JSON shape that ``OmicsClaw-App`` (Stage 0/1 already shipped)
relies on. These tests pin the wire format; behavioural changes that affect
the App must update both sides.

Test pattern follows ``tests/test_app_server.py``: build an ad-hoc FastAPI
instance and ``include_router`` directly to skip the heavy lifespan.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.execution.executors import LocalExecutor
from omicsclaw.remote.app_integration import register_remote_routers
from omicsclaw.remote.routers import jobs as jobs_module


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    # Contract tests pin wire format, not executor behavior. Keep the
    # cheap instant-return stub so every submitted job deterministically
    # ends in ``failed`` with ``executor_not_implemented`` — the real
    # default (``SubprocessExecutor``) is covered separately.
    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", LocalExecutor())

    app = FastAPI()
    register_remote_routers(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /connections/test  +  /env/doctor
# ---------------------------------------------------------------------------


def test_connections_test_returns_version_and_extras(client: TestClient) -> None:
    response = client.post("/connections/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["version"], str) and body["version"]
    assert "server_time" in body
    extras = body["extras"]
    assert "gpu" in extras and "available" in extras["gpu"]
    assert "disk_free_bytes" in extras


def test_env_doctor_returns_doctor_report_shape(client: TestClient) -> None:
    response = client.get("/env/doctor")
    assert response.status_code == 200
    body = response.json()
    for field in ("generated_at", "workspace_dir", "omicsclaw_dir",
                  "overall_status", "failure_count", "warning_count", "checks"):
        assert field in body, f"missing field: {field}"
    assert body["overall_status"] in {"ok", "warn", "fail"}
    assert isinstance(body["checks"], list)
    if body["checks"]:
        check = body["checks"][0]
        assert {"name", "status", "summary", "details"} <= set(check.keys())


# ---------------------------------------------------------------------------
# /datasets
# ---------------------------------------------------------------------------


def test_dataset_upload_persists_and_lists(client: TestClient) -> None:
    payload = b"H5AD-fake-content" * 64
    response = client.post(
        "/datasets/upload",
        files={"file": ("demo.h5ad", io.BytesIO(payload), "application/octet-stream")},
        data={"display_name": "Demo dataset", "execution_target": "local"},
    )
    assert response.status_code == 200, response.text
    ref = response.json()
    assert ref["display_name"] == "Demo dataset"
    assert ref["execution_target"] == "local"
    assert ref["size_bytes"] == len(payload)
    assert ref["checksum"].startswith("sha256-64k:")
    assert ref["status"] == "synced"
    dataset_id = ref["dataset_id"]

    listed = client.get("/datasets")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert any(d["dataset_id"] == dataset_id for d in body["datasets"])


def test_import_remote_rejects_relative_path(client: TestClient) -> None:
    response = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": "relative/file.h5ad",
            "execution_target": "remote:profile-a",
        },
    )
    assert response.status_code == 400


def test_import_remote_registers_existing_file(client: TestClient, tmp_path: Path) -> None:
    src = tmp_path / "remote_input.h5ad"
    src.write_bytes(b"x" * 1024)
    response = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": str(src),
            "display_name": "from-scp",
            "execution_target": "remote:profile-a",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["display_name"] == "from-scp"
    assert body["size_bytes"] == 1024
    assert body["storage_uri"].startswith("file://")
    assert body["execution_target"] == "remote:profile-a"


def test_dataset_upload_requires_execution_target(client: TestClient) -> None:
    response = client.post(
        "/datasets/upload",
        files={"file": ("demo.h5ad", io.BytesIO(b"x" * 16), "application/octet-stream")},
    )
    assert response.status_code == 422


def test_import_remote_requires_execution_target(client: TestClient, tmp_path: Path) -> None:
    src = tmp_path / "remote_required.h5ad"
    src.write_bytes(b"x" * 16)
    response = client.post(
        "/datasets/import-remote",
        json={"remote_path": str(src)},
    )
    assert response.status_code == 422


def test_dataset_upload_same_payload_does_not_cross_execution_target_boundaries(
    client: TestClient,
) -> None:
    payload = b"same-content" * 64
    first = client.post(
        "/datasets/upload",
        files={"file": ("same.h5ad", io.BytesIO(payload), "application/octet-stream")},
        data={"execution_target": "remote:profile-a"},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/datasets/upload",
        files={"file": ("same.h5ad", io.BytesIO(payload), "application/octet-stream")},
        data={"execution_target": "remote:profile-b"},
    )
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()
    assert first_body["checksum"] == second_body["checksum"]
    assert first_body["dataset_id"] != second_body["dataset_id"]
    assert first_body["execution_target"] == "remote:profile-a"
    assert second_body["execution_target"] == "remote:profile-b"

    listed = client.get("/datasets")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert {dataset["execution_target"] for dataset in body["datasets"]} == {
        "remote:profile-a",
        "remote:profile-b",
    }


def test_list_datasets_marks_missing_storage_as_stale(
    client: TestClient,
    tmp_path: Path,
) -> None:
    src = tmp_path / "remote_missing.h5ad"
    src.write_bytes(b"x" * 16)
    imported = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": str(src),
            "execution_target": "remote:profile-a",
        },
    )
    assert imported.status_code == 200, imported.text
    dataset_id = imported.json()["dataset_id"]

    src.unlink()

    listed = client.get("/datasets")
    assert listed.status_code == 200
    body = listed.json()
    stale = next(dataset for dataset in body["datasets"] if dataset["dataset_id"] == dataset_id)
    assert stale["status"] == "stale"


def test_import_remote_does_not_deduplicate_against_stale_dataset(
    client: TestClient,
    tmp_path: Path,
) -> None:
    original = tmp_path / "remote_original.h5ad"
    original.write_bytes(b"same-content" * 16)
    first = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": str(original),
            "execution_target": "remote:profile-a",
        },
    )
    assert first.status_code == 200, first.text
    first_body = first.json()

    original.unlink()
    listed = client.get("/datasets")
    assert listed.status_code == 200
    stale = next(
        dataset
        for dataset in listed.json()["datasets"]
        if dataset["dataset_id"] == first_body["dataset_id"]
    )
    assert stale["status"] == "stale"

    replacement = tmp_path / "remote_replacement.h5ad"
    replacement.write_bytes(b"same-content" * 16)
    second = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": str(replacement),
            "execution_target": "remote:profile-a",
        },
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["dataset_id"] != first_body["dataset_id"]
    assert second_body["status"] == "synced"
    assert second_body["storage_uri"] == replacement.resolve().as_uri()


# ---------------------------------------------------------------------------
# /jobs
# ---------------------------------------------------------------------------


def _submit_job(
    client: TestClient,
    skill: str = "spatial-preprocess",
    session_id: str = "",
) -> str:
    payload = {"skill": skill, "inputs": {"dataset_id": "abc"}}
    if session_id:
        payload["session_id"] = session_id
    response = client.post("/jobs", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert isinstance(body["job_id"], str) and body["job_id"]
    return body["job_id"]


def test_job_submit_list_get_round_trip(client: TestClient) -> None:
    job_id = _submit_job(client)

    detail = client.get(f"/jobs/{job_id}").json()
    assert detail["job_id"] == job_id
    assert detail["status"] == "queued"
    assert detail["skill"] == "spatial-preprocess"
    assert detail["inputs"] == {"dataset_id": "abc"}

    listed = client.get("/jobs", params={"status": "queued"}).json()
    assert any(j["job_id"] == job_id for j in listed["jobs"])


def test_job_submit_uses_resolved_workspace_not_client_claim(client: TestClient) -> None:
    import os

    response = client.post(
        "/jobs",
        json={"skill": "spatial-preprocess", "workspace": "/tmp/not-the-real-workspace"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    detail = client.get(f"/jobs/{body['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["workspace"] == os.environ["OMICSCLAW_WORKSPACE"]


def test_chat_display_job_submission_stays_queued_until_chat_stream_binds_it(
    client: TestClient,
) -> None:
    response = client.post(
        "/jobs",
        json={
            "skill": "chat",
            "session_id": "sess-chat",
            "params": {"job_kind": "chat_stream", "display_name": "chat turn"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"

    detail = client.get(f"/jobs/{body['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"


def test_job_cancel_marks_canceled(client: TestClient) -> None:
    job_id = _submit_job(client)
    response = client.post(f"/jobs/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    # Idempotent — second cancel does not flip status.
    again = client.post(f"/jobs/{job_id}/cancel")
    assert again.json()["status"] == "canceled"


def test_job_retry_creates_new_job(client: TestClient) -> None:
    original = _submit_job(client)
    # Drive to terminal state first — retry only works on finished jobs.
    client.post(f"/jobs/{original}/cancel")
    response = client.post(f"/jobs/{original}/retry")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["job_id"] != original


def test_job_retry_rejects_active_job(client: TestClient) -> None:
    queued = _submit_job(client)
    response = client.post(f"/jobs/{queued}/retry")
    assert response.status_code == 400
    assert "terminal" in response.json()["detail"].lower() or "finished" in response.json()["detail"].lower()


def test_job_events_streams_lifecycle(client: TestClient) -> None:
    job_id = _submit_job(client)
    with client.stream("GET", f"/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    # Required SSE event names — App's EventSource subscribes to these.
    for marker in ("event: job_queued", "event: job_started",
                   "event: job_log", "event: job_failed", "event: done"):
        assert marker in body, f"missing SSE marker: {marker}"


def test_job_events_do_not_rewrite_canceled_job(client: TestClient) -> None:
    job_id = _submit_job(client)
    canceled = client.post(f"/jobs/{job_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"

    with client.stream("GET", f"/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: job_canceled" in body
    assert "event: job_started" not in body
    assert "event: job_failed" not in body

    final = client.get(f"/jobs/{job_id}")
    assert final.status_code == 200
    assert final.json()["status"] == "canceled"


def test_jobs_total_reports_matches_before_limit(client: TestClient) -> None:
    _submit_job(client, skill="skill-a")
    _submit_job(client, skill="skill-b")
    _submit_job(client, skill="skill-c")

    response = client.get("/jobs", params={"limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert len(body["jobs"]) == 1
    assert body["total"] == 3


# ---------------------------------------------------------------------------
# /artifacts
# ---------------------------------------------------------------------------


def test_artifacts_list_empty_when_no_outputs(client: TestClient) -> None:
    response = client.get("/artifacts", params={"job_id": "nonexistent"})
    assert response.status_code == 200
    assert response.json() == {"artifacts": [], "total": 0}


def test_artifacts_list_picks_up_files(client: TestClient) -> None:
    import os

    ws = Path(os.environ["OMICSCLAW_WORKSPACE"])
    job_id = "job_with_output"
    artifact_dir = ws / ".omicsclaw" / "remote" / "jobs" / job_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "report.md").write_text("# hi\n")

    response = client.get("/artifacts", params={"job_id": job_id})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    artifact = body["artifacts"][0]
    assert artifact["relative_path"] == "report.md"
    assert artifact["mime_type"].startswith("text/")

    download = client.get(f"/artifacts/{artifact['artifact_id']}/download")
    assert download.status_code == 200
    assert download.text == "# hi\n"


def test_artifacts_created_at_is_stable_across_list_calls(client: TestClient) -> None:
    import os
    import time

    ws = Path(os.environ["OMICSCLAW_WORKSPACE"])
    job_id = "job_stable_artifact_time"
    artifact_dir = ws / ".omicsclaw" / "remote" / "jobs" / job_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    report = artifact_dir / "report.md"
    report.write_text("# hi\n")

    first = client.get("/artifacts", params={"job_id": job_id})
    assert first.status_code == 200
    created_at_1 = first.json()["artifacts"][0]["created_at"]

    time.sleep(0.01)

    second = client.get("/artifacts", params={"job_id": job_id})
    assert second.status_code == 200
    created_at_2 = second.json()["artifacts"][0]["created_at"]
    assert created_at_1 == created_at_2


def test_artifacts_reject_unsafe_job_id_query(client: TestClient) -> None:
    response = client.get("/artifacts", params={"job_id": "../../../../outside"})
    assert response.status_code == 400


def test_artifact_download_rejects_unsafe_job_id_in_artifact_id(client: TestClient) -> None:
    response = client.get("/artifacts/..%2F..%2F..%2F..%2Foutside:secret.txt/download")
    assert response.status_code == 400


def test_failed_job_persists_diagnostic_artifacts(client: TestClient) -> None:
    import os

    job_id = _submit_job(client, session_id="sess-diagnostics")

    with client.stream("GET", f"/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: job_failed" in body

    detail = client.get(f"/jobs/{job_id}")
    assert detail.status_code == 200
    job = detail.json()
    assert job["status"] == "failed"
    assert isinstance(job["artifact_root"], str) and job["artifact_root"]

    ws = Path(os.environ["OMICSCLAW_WORKSPACE"])
    job_dir = ws / ".omicsclaw" / "remote" / "jobs" / job_id
    stdout_path = job_dir / "stdout.log"
    assert stdout_path.is_file()
    stdout_text = stdout_path.read_text(encoding="utf-8")
    assert "executor_not_implemented" in stdout_text

    listed = client.get("/artifacts", params={"job_id": job_id})
    assert listed.status_code == 200
    artifacts = {artifact["relative_path"]: artifact for artifact in listed.json()["artifacts"]}
    assert "diagnostics/env_doctor.json" in artifacts
    assert "diagnostics/stdout.log" in artifacts

    env_doctor = client.get(
        f"/artifacts/{artifacts['diagnostics/env_doctor.json']['artifact_id']}/download"
    )
    assert env_doctor.status_code == 200
    env_payload = env_doctor.json()
    assert "overall_status" in env_payload
    assert "checks" in env_payload

    stdout_download = client.get(
        f"/artifacts/{artifacts['diagnostics/stdout.log']['artifact_id']}/download"
    )
    assert stdout_download.status_code == 200
    assert "executor_not_implemented" in stdout_download.text


# ---------------------------------------------------------------------------
# /sessions
# ---------------------------------------------------------------------------


def test_session_resume_returns_active_jobs(client: TestClient) -> None:
    queued = _submit_job(client, session_id="sess-xyz")
    response = client.post("/sessions/sess-xyz/resume")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "sess-xyz"
    assert body["resumed"] is True
    assert queued in body["active_job_ids"]


def test_session_resume_filters_active_jobs_by_session_id(client: TestClient) -> None:
    session_a = client.post(
        "/jobs",
        json={"skill": "spatial-preprocess", "session_id": "sess-a"},
    )
    assert session_a.status_code == 200
    job_a = session_a.json()["job_id"]

    session_b = client.post(
        "/jobs",
        json={"skill": "spatial-preprocess", "session_id": "sess-b"},
    )
    assert session_b.status_code == 200
    job_b = session_b.json()["job_id"]

    resumed = client.post("/sessions/sess-a/resume")
    assert resumed.status_code == 200
    body = resumed.json()
    assert job_a in body["active_job_ids"]
    assert job_b not in body["active_job_ids"]


def test_dataset_upload_deduplicates_same_payload(client: TestClient) -> None:
    payload = b"same-content" * 64
    first = client.post(
        "/datasets/upload",
        files={"file": ("same.h5ad", io.BytesIO(payload), "application/octet-stream")},
        data={"execution_target": "local"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/datasets/upload",
        files={"file": ("same.h5ad", io.BytesIO(payload), "application/octet-stream")},
        data={"execution_target": "local"},
    )
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()
    assert first_body["checksum"] == second_body["checksum"]
    assert first_body["dataset_id"] == second_body["dataset_id"]

    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

"""``GET /artifacts/:id/download`` Range header support.

Plan §API contract: "产物下载（支持 Range）". Large artifacts (e.g. a
500 MB ``.h5ad``) must be resumable — both for flaky tunnels and for
App-side browsers that issue Range by default when seeking a video /
large file preview.

FastAPI's ``FileResponse`` handles Range automatically, but "works by
accident" is a regression waiting to happen. These tests pin the
contract so swapping the response type later cannot silently break it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.remote.app_integration import register_remote_routers


@pytest.fixture()
def client_with_artifact(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)

    # Seed a fixed-content artifact of known size.
    job_id = "range-subject"
    artifact_dir = workspace / ".omicsclaw" / "remote" / "jobs" / job_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    payload = bytes(range(256)) * 4  # 1024 bytes, each byte value known
    (artifact_dir / "data.bin").write_bytes(payload)

    app = FastAPI()
    register_remote_routers(app)
    client = TestClient(app)
    return client, job_id, payload


def _artifact_id(job_id: str, rel: str = "data.bin") -> str:
    return f"{job_id}:{rel}"


def test_download_without_range_returns_full_content(client_with_artifact) -> None:
    client, job_id, payload = client_with_artifact
    response = client.get(f"/artifacts/{_artifact_id(job_id)}/download")
    assert response.status_code == 200
    assert response.content == payload


def test_download_with_range_returns_206_partial(client_with_artifact) -> None:
    client, job_id, payload = client_with_artifact
    response = client.get(
        f"/artifacts/{_artifact_id(job_id)}/download",
        headers={"Range": "bytes=100-199"},
    )
    assert response.status_code == 206, response.text
    assert response.content == payload[100:200]
    assert len(response.content) == 100


def test_download_with_range_sets_content_range_header(
    client_with_artifact,
) -> None:
    client, job_id, _ = client_with_artifact
    response = client.get(
        f"/artifacts/{_artifact_id(job_id)}/download",
        headers={"Range": "bytes=0-9"},
    )
    assert response.status_code == 206
    content_range = response.headers.get("content-range", "")
    assert content_range.startswith("bytes 0-9/"), content_range


def test_download_with_open_ended_range(client_with_artifact) -> None:
    """``Range: bytes=N-`` means "from byte N to end"."""
    client, job_id, payload = client_with_artifact
    response = client.get(
        f"/artifacts/{_artifact_id(job_id)}/download",
        headers={"Range": "bytes=1000-"},
    )
    assert response.status_code == 206
    assert response.content == payload[1000:]


def test_download_with_suffix_range(client_with_artifact) -> None:
    """``Range: bytes=-N`` means "last N bytes"."""
    client, job_id, payload = client_with_artifact
    response = client.get(
        f"/artifacts/{_artifact_id(job_id)}/download",
        headers={"Range": "bytes=-50"},
    )
    assert response.status_code == 206
    assert response.content == payload[-50:]


def test_download_advertises_accept_ranges_bytes(client_with_artifact) -> None:
    """Clients inspect ``Accept-Ranges`` to decide whether resume is
    even an option. Must be ``bytes`` (or present at all)."""
    client, job_id, _ = client_with_artifact
    response = client.get(f"/artifacts/{_artifact_id(job_id)}/download")
    # Starlette's FileResponse includes this on 200s.
    accept_ranges = response.headers.get("accept-ranges", "")
    assert accept_ranges.lower() == "bytes", (
        f"expected Accept-Ranges: bytes, got {accept_ranges!r}"
    )

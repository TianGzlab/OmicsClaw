"""``DELETE /datasets/{dataset_id}`` — remove a registered dataset.

Semantics:
- ``upload``-type datasets: the file lives inside the dataset dir, so
  ``shutil.rmtree(dataset_dir)`` removes both the file and ``meta.json``.
- ``import-remote``-type datasets: ``storage_uri`` points to a path
  outside the workspace; the dataset dir only holds ``meta.json``. The
  same rmtree just unregisters it — **the source file MUST NOT be
  touched**, since deleting a user-provided path is a data-loss risk
  the backend cannot recover from.

Also verifies path-sandboxing on ``dataset_id`` and standard 404/204
HTTP semantics.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.remote.app_integration import register_remote_routers


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)
    app = FastAPI()
    register_remote_routers(app)
    return TestClient(app)


def _upload_demo(
    client: TestClient, *, name: str = "demo.h5ad", payload: bytes | None = None
) -> str:
    if payload is None:
        payload = name.encode("utf-8") * 16  # vary content per name to dodge
                                             # checksum dedup from _upload_dataset
    response = client.post(
        "/datasets/upload",
        files={"file": (name, io.BytesIO(payload), "application/octet-stream")},
        data={"execution_target": "local"},
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset_id"]


def _import_remote(client: TestClient, src: Path) -> str:
    response = client.post(
        "/datasets/import-remote",
        json={
            "remote_path": str(src),
            "execution_target": "remote:profile-a",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset_id"]


def test_delete_upload_dataset_removes_file_and_meta(
    client: TestClient, tmp_path: Path
) -> None:
    dataset_id = _upload_demo(client)
    workspace = tmp_path / "workspace"
    dataset_dir = (
        workspace / ".omicsclaw" / "remote" / "datasets" / dataset_id
    )
    assert dataset_dir.is_dir()

    response = client.delete(f"/datasets/{dataset_id}")
    assert response.status_code == 204

    assert not dataset_dir.exists()
    listing = client.get("/datasets").json()
    assert all(d["dataset_id"] != dataset_id for d in listing["datasets"])


def test_delete_import_remote_dataset_preserves_source_file(
    client: TestClient, tmp_path: Path
) -> None:
    """CRITICAL: unregistering an imported path must not delete the
    user's source file. Tests put the source OUTSIDE the workspace so a
    naive ``shutil.rmtree`` on storage_uri would be caught."""
    source = tmp_path / "outside" / "big-cohort.h5ad"
    source.parent.mkdir()
    source.write_bytes(b"precious" * 128)

    dataset_id = _import_remote(client, source)

    response = client.delete(f"/datasets/{dataset_id}")
    assert response.status_code == 204

    # Source must still exist — removing the meta dir is fine, deleting
    # the referenced source is a data-loss bug.
    assert source.is_file(), (
        "DELETE /datasets/:id removed the user's source file — data loss"
    )
    assert source.read_bytes() == b"precious" * 128


def test_delete_unknown_dataset_returns_404(client: TestClient) -> None:
    response = client.delete("/datasets/not-a-real-id-xyz")
    assert response.status_code == 404


def test_delete_rejects_unsafe_dataset_id(client: TestClient) -> None:
    """Path-traversal attempts and absolute paths must never reach
    ``shutil.rmtree``.

    ``.`` / ``..`` get canonicalized by httpx into ``/datasets`` or
    ``/datasets/``, which the router resolves to the GET endpoint →
    405 Method Not Allowed. That's a correct rejection at the routing
    layer; anything in {400, 404, 405} means the dangerous id never hit
    the handler.
    """
    for bad in ("../etc/passwd", "foo/bar", "..", "."):
        response = client.delete(f"/datasets/{bad}")
        assert response.status_code in (400, 404, 405), (
            f"unsafe id {bad!r} accepted as {response.status_code}"
        )


def test_delete_is_idempotent_second_call_is_404(client: TestClient) -> None:
    dataset_id = _upload_demo(client, name="once.h5ad")
    first = client.delete(f"/datasets/{dataset_id}")
    assert first.status_code == 204
    second = client.delete(f"/datasets/{dataset_id}")
    assert second.status_code == 404


def test_delete_does_not_disturb_siblings(
    client: TestClient, tmp_path: Path
) -> None:
    keep_id = _upload_demo(client, name="keep.h5ad")
    drop_id = _upload_demo(client, name="drop.h5ad")

    response = client.delete(f"/datasets/{drop_id}")
    assert response.status_code == 204

    listing = client.get("/datasets").json()
    remaining_ids = {d["dataset_id"] for d in listing["datasets"]}
    assert keep_id in remaining_ids
    assert drop_id not in remaining_ids

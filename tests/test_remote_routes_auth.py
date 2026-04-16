"""Bearer token auth for remote control-plane routers.

When ``OMICSCLAW_REMOTE_AUTH_TOKEN`` is set, every request to remote routers
must carry ``Authorization: Bearer <token>``. When the env var is unset the
routers stay open so local development / single-user SSH-tunnel setups keep
working unchanged (MVP-1 default in the plan — tunnel is the first layer,
token is the second).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.remote.app_integration import register_remote_routers


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _make_client(workspace: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    app = FastAPI()
    register_remote_routers(app)
    return TestClient(app)


def test_no_auth_required_when_token_env_unset(monkeypatch, workspace: Path) -> None:
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)
    client = _make_client(workspace, monkeypatch)
    assert client.post("/connections/test").status_code == 200


def test_auth_required_returns_401_without_header(monkeypatch, workspace: Path) -> None:
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "s3cret-token")
    client = _make_client(workspace, monkeypatch)
    response = client.post("/connections/test")
    assert response.status_code == 401


def test_auth_rejects_wrong_token(monkeypatch, workspace: Path) -> None:
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "s3cret-token")
    client = _make_client(workspace, monkeypatch)
    response = client.post(
        "/connections/test",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_auth_rejects_non_bearer_scheme(monkeypatch, workspace: Path) -> None:
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "s3cret-token")
    client = _make_client(workspace, monkeypatch)
    response = client.post(
        "/connections/test",
        headers={"Authorization": "Basic s3cret-token"},
    )
    assert response.status_code == 401


def test_auth_accepts_correct_bearer(monkeypatch, workspace: Path) -> None:
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "s3cret-token")
    client = _make_client(workspace, monkeypatch)
    response = client.post(
        "/connections/test",
        headers={"Authorization": "Bearer s3cret-token"},
    )
    assert response.status_code == 200


def test_auth_applies_to_all_remote_routers(monkeypatch, workspace: Path) -> None:
    """Every router shares the same dependency — no back-door endpoints."""
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "s3cret-token")
    client = _make_client(workspace, monkeypatch)
    unauthorized_endpoints = [
        ("POST", "/connections/test"),
        ("GET", "/env/doctor"),
        ("GET", "/datasets"),
        ("GET", "/jobs"),
        ("GET", "/artifacts?job_id=anything"),
        ("POST", "/sessions/foo/resume"),
    ]
    for method, path in unauthorized_endpoints:
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} should require auth"


def test_auth_whitespace_and_empty_token_env_not_enforced(
    monkeypatch, workspace: Path
) -> None:
    """Empty / whitespace-only token env is treated as unset (safer default)."""
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "   ")
    client = _make_client(workspace, monkeypatch)
    response = client.post("/connections/test")
    assert response.status_code == 200

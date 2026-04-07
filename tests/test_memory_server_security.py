from __future__ import annotations

import asyncio
import sys

import pytest


def test_is_local_bind_host():
    from omicsclaw.memory.server import _is_local_bind_host

    assert _is_local_bind_host("127.0.0.1") is True
    assert _is_local_bind_host("localhost") is True
    assert _is_local_bind_host("::1") is True
    assert _is_local_bind_host("0.0.0.0") is False
    assert _is_local_bind_host("192.168.1.8") is False


def test_validate_server_security_rejects_remote_without_token():
    from omicsclaw.memory.server import _validate_server_security

    with pytest.raises(SystemExit, match="OMICSCLAW_MEMORY_API_TOKEN"):
        _validate_server_security("0.0.0.0", "")


def test_validate_server_security_allows_local_without_token():
    from omicsclaw.memory.server import _validate_server_security

    _validate_server_security("127.0.0.1", "")


def test_memory_server_main_reports_missing_uvicorn(monkeypatch, capsys):
    pytest.importorskip("fastapi")

    from omicsclaw.memory import server

    monkeypatch.setitem(sys.modules, "uvicorn", None)

    with pytest.raises(SystemExit) as excinfo:
        server.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "uvicorn is not installed" in captured.out
    assert 'pip install -e ".[memory]"' in captured.out


def test_memory_server_docs_and_openapi_require_auth_when_token_set(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import omicsclaw.memory as memory
    from omicsclaw.memory.server import _build_app

    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_DB_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'memory-security.db'}",
    )
    monkeypatch.setenv("OMICSCLAW_MEMORY_API_TOKEN", "secret-token")
    asyncio.run(memory.close_db())

    app = _build_app()
    assert app is not None

    with TestClient(app) as client:
        docs_unauth = client.get("/docs")
        openapi_unauth = client.get("/openapi.json")
        health_unauth = client.get("/health")
        docs_auth = client.get(
            "/docs",
            headers={"Authorization": "Bearer secret-token"},
        )
        openapi_auth = client.get(
            "/openapi.json",
            headers={"Authorization": "Bearer secret-token"},
        )

    asyncio.run(memory.close_db())

    assert docs_unauth.status_code == 401
    assert openapi_unauth.status_code == 401
    assert health_unauth.status_code != 401
    assert docs_auth.status_code == 200
    assert openapi_auth.status_code == 200

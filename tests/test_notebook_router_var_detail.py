"""Router-level tests for /notebook/var_detail and /notebook/adata_slot.

These tests exercise the FastAPI layer end-to-end (model parsing,
workspace/file_path resolution, script generation, payload plumbing)
but stub out the actual kernel call via ``run_stdout_script`` so we
don't need a live Jupyter kernel to verify the request pipeline.

Assertions focus on:

* The endpoints take the single ``workspace + file_path`` locator the
  whole router uses now — no legacy ``notebook_id`` track.
* Missing-locator / invalid-variable-name bodies fail with 400.
* The script produced by ``var_inspector.build_*`` is what ends up in
  ``run_stdout_script``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.app.notebook import var_inspector
from omicsclaw.app.notebook.router import router

# The package __init__ re-exports ``router`` (the APIRouter object), which
# shadows the submodule name at the package level. Grab the actual module
# out of sys.modules so monkeypatch targets the real ``get_kernel_manager``
# symbol the route handlers reference.
notebook_router_module = sys.modules["omicsclaw.app.notebook.router"]


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/notebook")
    return TestClient(app)


def _make_payload(payload: dict[str, Any]) -> str:
    return (
        var_inspector.PAYLOAD_BEGIN
        + json.dumps(payload)
        + var_inspector.PAYLOAD_END
    )


class _FakeManager:
    """Stand-in for ``NotebookKernelManager`` capturing calls."""

    def __init__(self, stdout_payload: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stdout_payload = stdout_payload

    async def run_stdout_script(
        self,
        notebook_id: str,
        script: str,
        file_path: str | None = None,
    ) -> tuple[str, str]:
        self.calls.append(
            {
                "notebook_id": notebook_id,
                "script": script,
                "file_path": file_path,
            }
        )
        return _make_payload(self._stdout_payload), "idle"


@pytest.fixture
def fake_manager(monkeypatch: pytest.MonkeyPatch) -> _FakeManager:
    manager = _FakeManager(
        stdout_payload={
            "type": "scalar",
            "name": "x",
            "content": "42",
            "py_type": "int",
        }
    )
    monkeypatch.setattr(
        notebook_router_module, "get_kernel_manager", lambda: manager
    )
    return manager


@pytest.fixture
def workspace_notebook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Create a real ipynb file inside a workspace and trust the workspace."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    notebook = workspace / "analysis.ipynb"
    notebook.write_text("{}")  # content irrelevant; only path is resolved
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    return str(workspace), str(notebook)


# ---------------------------------------------------------------------------
# /notebook/var_detail
# ---------------------------------------------------------------------------


class TestVarDetailRoute:
    def test_accepts_workspace_file_path(
        self, fake_manager: _FakeManager, workspace_notebook: tuple[str, str]
    ) -> None:
        workspace, file_path = workspace_notebook
        client = _make_client()

        resp = client.post(
            "/notebook/var_detail",
            json={
                "workspace": workspace,
                "file_path": file_path,
                "name": "x",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["payload"]["type"] == "scalar"
        assert body["payload"]["content"] == "42"
        assert body["kernel_status"] == "idle"

        # The manager must see the derived notebook_id + resolved file_path.
        assert len(fake_manager.calls) == 1
        call = fake_manager.calls[0]
        assert call["notebook_id"].startswith("nbk_")
        assert call["file_path"] == file_path
        # Script embeds the variable name as a Python string literal.
        assert "'x'" in call["script"]

    def test_missing_file_path_returns_400(
        self, fake_manager: _FakeManager
    ) -> None:
        client = _make_client()

        resp = client.post("/notebook/var_detail", json={"name": "x"})

        assert resp.status_code == 400
        assert "file_path" in resp.json()["detail"]
        assert fake_manager.calls == []

    def test_invalid_variable_name_returns_400(
        self,
        fake_manager: _FakeManager,
        workspace_notebook: tuple[str, str],
    ) -> None:
        workspace, file_path = workspace_notebook
        client = _make_client()

        resp = client.post(
            "/notebook/var_detail",
            json={
                "workspace": workspace,
                "file_path": file_path,
                "name": "__import__('os').system('rm')",
            },
        )

        assert resp.status_code == 400
        assert fake_manager.calls == []


# ---------------------------------------------------------------------------
# /notebook/adata_slot
# ---------------------------------------------------------------------------


class TestAdataSlotRoute:
    def test_accepts_workspace_file_path(
        self, fake_manager: _FakeManager, workspace_notebook: tuple[str, str]
    ) -> None:
        workspace, file_path = workspace_notebook
        client = _make_client()

        resp = client.post(
            "/notebook/adata_slot",
            json={
                "workspace": workspace,
                "file_path": file_path,
                "var_name": "adata",
                "slot": "obs",
                "key": "cluster",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["payload"]["type"] == "scalar"  # from the stub
        assert body["kernel_status"] == "idle"

        call = fake_manager.calls[0]
        assert call["file_path"] == file_path
        assert "'obs'" in call["script"]
        assert "'cluster'" in call["script"]

    def test_unsupported_slot_returns_400(
        self,
        fake_manager: _FakeManager,
        workspace_notebook: tuple[str, str],
    ) -> None:
        workspace, file_path = workspace_notebook
        client = _make_client()

        resp = client.post(
            "/notebook/adata_slot",
            json={
                "workspace": workspace,
                "file_path": file_path,
                "var_name": "adata",
                "slot": "not_a_slot",
                "key": "cluster",
            },
        )

        assert resp.status_code == 400
        assert fake_manager.calls == []

    def test_missing_file_path_returns_400(
        self, fake_manager: _FakeManager
    ) -> None:
        client = _make_client()

        resp = client.post(
            "/notebook/adata_slot",
            json={"var_name": "adata", "slot": "obs", "key": ""},
        )

        assert resp.status_code == 400
        assert fake_manager.calls == []

    def test_key_may_be_empty(
        self,
        fake_manager: _FakeManager,
        workspace_notebook: tuple[str, str],
    ) -> None:
        workspace, file_path = workspace_notebook
        client = _make_client()

        resp = client.post(
            "/notebook/adata_slot",
            json={
                "workspace": workspace,
                "file_path": file_path,
                "var_name": "adata",
                "slot": "obs",
                "key": "",
            },
        )

        assert resp.status_code == 200
        assert fake_manager.calls[0]["notebook_id"].startswith("nbk_")
        assert fake_manager.calls[0]["file_path"] == file_path

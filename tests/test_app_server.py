from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import bot.core as bot_core


ROOT = Path(__file__).resolve().parent.parent


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location("omicsclaw_main_app_server_test", ROOT / "omicsclaw.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _read_streaming_response(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


def _parse_sse_events(payload: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in payload.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        data = event.get("data")
        if isinstance(data, str):
            try:
                parsed_data = json.loads(data)
            except json.JSONDecodeError:
                parsed_data = data
        else:
            parsed_data = data
        events.append({"type": event.get("type"), "data": parsed_data})
    return events


async def _setup_memory_review_runtime(monkeypatch, tmp_path: Path):
    from omicsclaw import memory as memory_pkg
    from omicsclaw.app import server
    from omicsclaw.memory.snapshot import ChangesetStore

    db_path = (tmp_path / "memory.db").resolve()
    monkeypatch.setenv("OMICSCLAW_MEMORY_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    await memory_pkg.close_db()
    db = memory_pkg.get_db_manager()
    await db.init_db()

    store = ChangesetStore(snapshot_dir=str((tmp_path / "snapshots").resolve()))
    monkeypatch.setattr(server, "_get_changeset_store", lambda: store, raising=False)
    # The first tuple element is the legacy ``BrowseHelpers`` instance —
    # tests use it as a thin DB-shaped fixture to seed paths/memories
    # without going through the namespace-aware MemoryClient layer.
    from omicsclaw.memory.api._browse_helpers import BrowseHelpers
    helpers = BrowseHelpers(memory_pkg.get_db_manager(), memory_pkg.get_search_indexer())
    return helpers, store, memory_pkg


def test_app_server_main_uses_default_contract(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured: dict[str, object] = {}
    fake_uvicorn = SimpleNamespace(
        run=lambda app_ref, **kwargs: captured.update({"app_ref": app_ref, **kwargs})
    )
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("OMICSCLAW_APP_HOST", raising=False)
    monkeypatch.delenv("OMICSCLAW_APP_PORT", raising=False)
    monkeypatch.delenv("OMICSCLAW_APP_RELOAD", raising=False)

    server.main([])

    assert captured["app_ref"] == "omicsclaw.app.server:app"
    assert captured["host"] == server.DEFAULT_APP_API_HOST
    assert captured["port"] == server.DEFAULT_APP_API_PORT
    assert captured["reload"] is False


def test_app_server_main_exports_effective_port_to_env(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured: dict[str, object] = {}
    fake_uvicorn = SimpleNamespace(
        run=lambda app_ref, **kwargs: captured.update({"app_ref": app_ref, **kwargs})
    )
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("OMICSCLAW_APP_PORT", raising=False)
    monkeypatch.delenv("OMICSCLAW_APP_HOST", raising=False)

    server.main(["--host", "127.0.0.1", "--port", "9000"])

    assert captured["port"] == 9000
    assert os.environ["OMICSCLAW_APP_PORT"] == "9000"
    assert os.environ["OMICSCLAW_APP_HOST"] == "127.0.0.1"


def test_app_server_main_reports_missing_uvicorn(monkeypatch, capsys):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    monkeypatch.setitem(sys.modules, "uvicorn", None)

    with pytest.raises(SystemExit) as excinfo:
        server.main([])

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "uvicorn is not installed" in captured.err
    assert 'pip install -e ".[desktop]"' in captured.err


@pytest.mark.asyncio
async def test_app_server_lifespan_allows_startup_without_llm_credentials(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured: dict[str, object] = {}

    def fake_init(**kwargs):
        captured.update(kwargs)
        if kwargs.get("allow_missing_credentials") is not True:
            raise AssertionError("app-server startup must not require an LLM API key")

    for key in (
        "LLM_PROVIDER",
        "OMICSCLAW_PROVIDER",
        "LLM_API_KEY",
        "OMICSCLAW_API_KEY",
        "LLM_BASE_URL",
        "OMICSCLAW_BASE_URL",
        "OMICSCLAW_MODEL",
        "LLM_AUTH_MODE",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bot_core, "init", fake_init)
    monkeypatch.setattr(bot_core, "LLM_PROVIDER_NAME", "openai")
    monkeypatch.setattr(bot_core, "OMICSCLAW_MODEL", "gpt-5.5")
    monkeypatch.setattr(server, "_core", None)
    monkeypatch.setattr(server, "_NOTEBOOK_AVAILABLE", False)
    monkeypatch.setattr(server, "_memory_client", None)

    async with server.lifespan(server.app):
        pass

    assert captured["allow_missing_credentials"] is True
    assert captured["strict_oauth"] is False
    assert captured["provider"] == ""
    assert captured["api_key"] == ""


def test_app_server_mounts_native_notebook_routes():
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    route_paths = {getattr(route, "path", "") for route in server.app.routes}

    assert "/notebook/kernel/start" in route_paths
    assert "/notebook/kernel/stop" in route_paths
    assert "/notebook/kernel/interrupt" in route_paths
    assert "/notebook/kernel/status" in route_paths
    assert "/notebook/execute" in route_paths
    assert "/notebook/complete" in route_paths
    assert "/notebook/inspect" in route_paths
    assert "/notebook/list" in route_paths
    assert "/notebook/open" in route_paths
    assert "/notebook/create" in route_paths
    assert "/notebook/save" in route_paths
    assert "/notebook/delete" in route_paths
    assert "/notebook/rename" in route_paths
    assert "/notebook/var_detail" in route_paths
    assert "/notebook/adata_slot" in route_paths
    assert "/notebook/files/upload" in route_paths
    # /files/list and /files/open were removed along with the legacy
    # root+filename contract — only /files/upload (bytes → JSON) remains.
    assert "/notebook/files/list" not in route_paths
    assert "/notebook/files/open" not in route_paths


def test_register_optional_kg_router_mounts_embedded_routes(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server

    kg_root = ModuleType("omicsclaw_kg")
    kg_config = ModuleType("omicsclaw_kg.config")
    kg_http_api = ModuleType("omicsclaw_kg.http_api")

    def resolve(path):
        return {"workspace": str(Path(path).resolve())}

    def get_kg_config():
        raise AssertionError("dependency override should supply KG config")

    router = APIRouter()

    @router.get("/status")
    def status(config=Depends(get_kg_config)):
        return {"workspace": config["workspace"]}

    kg_config.resolve = resolve
    kg_http_api.build_router = lambda enable_writes=True: router
    kg_http_api.get_kg_config = get_kg_config
    kg_root.config = kg_config

    monkeypatch.setitem(sys.modules, "omicsclaw_kg", kg_root)
    monkeypatch.setitem(sys.modules, "omicsclaw_kg.config", kg_config)
    monkeypatch.setitem(sys.modules, "omicsclaw_kg.http_api", kg_http_api)

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "omicsclaw_kg":
            return object()
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    app = FastAPI()
    server._register_optional_kg_router(app)
    client = TestClient(app)

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    response = client.get("/kg/status", headers={"X-OmicsClaw-Workspace": str(workspace_root)})
    assert response.status_code == 200
    assert response.json() == {
        "workspace": str((workspace_root / ".omicsclaw" / "knowledge").resolve())
    }


def test_notebook_file_routes_round_trip_through_backend_router(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server
    from omicsclaw.app.notebook.router import router as notebook_router

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    app = FastAPI()
    app.include_router(notebook_router, prefix="/notebook")
    client = TestClient(app)

    create_response = client.post("/notebook/create", json={"workspace": str(workspace)})
    assert create_response.status_code == 200
    created_path = create_response.json()["path"]

    list_response = client.get("/notebook/list", params={"workspace": str(workspace)})
    assert list_response.status_code == 200
    listed_paths = {entry["path"] for entry in list_response.json()["notebooks"]}
    assert created_path in listed_paths

    open_response = client.get("/notebook/open", params={"path": created_path})
    assert open_response.status_code == 200
    opened_payload = open_response.json()
    assert opened_payload["path"] == created_path
    assert opened_payload["workspace"] == str(workspace.resolve())
    assert isinstance(opened_payload["notebook"]["cells"], list)

    save_response = client.post(
        "/notebook/save",
        json={
            "workspace": str(workspace),
            "path": created_path,
            "notebook": {
                **opened_payload["notebook"],
                "cells": [],
            },
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["path"] == created_path

    delete_response = client.post(
        "/notebook/delete",
        json={"workspace": str(workspace), "path": created_path},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["path"] == created_path

    list_after_delete = client.get("/notebook/list", params={"workspace": str(workspace)})
    assert list_after_delete.status_code == 200
    listed_after_delete = {entry["path"] for entry in list_after_delete.json()["notebooks"]}
    assert created_path not in listed_after_delete


def test_notebook_open_rejects_untrusted_absolute_path_when_workspace_is_omitted(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server
    from omicsclaw.app.notebook.router import router as notebook_router

    trusted_workspace = tmp_path / "trusted"
    trusted_workspace.mkdir()
    rogue_dir = tmp_path / "rogue"
    rogue_dir.mkdir()
    rogue_path = rogue_dir / "rogue.ipynb"
    rogue_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[trusted_workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(trusted_workspace))

    app = FastAPI()
    app.include_router(notebook_router, prefix="/notebook")
    client = TestClient(app)

    response = client.get("/notebook/open", params={"path": str(rogue_path)})

    assert response.status_code == 400
    assert "trusted scope" in response.json()["detail"]


def test_notebook_delete_rejects_live_pipeline_notebook(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    import importlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server
    from omicsclaw.app.notebook.router import router as notebook_router

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notebook_path = workspace / "analysis.ipynb"
    notebook_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")
    seen: dict[str, bool] = {"stop_called": False}

    class DummyManager:
        async def status(self, notebook_id, file_path=None):
            return {"running": True, "source": "live", "kernel_status": "busy"}

        async def stop(self, notebook_id, file_path=None):
            seen["stop_called"] = True
            return True

    monkeypatch.setattr(notebook_router_module, "get_kernel_manager", lambda: DummyManager())

    app = FastAPI()
    app.include_router(notebook_router, prefix="/notebook")
    client = TestClient(app)

    response = client.post(
        "/notebook/delete",
        json={"workspace": str(workspace), "path": str(notebook_path)},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "cannot delete a live pipeline notebook"
    assert notebook_path.exists()
    assert seen["stop_called"] is False


def test_notebook_delete_route_rejects_live_pipeline_notebook(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notebook_path = workspace / "analysis.ipynb"
    notebook_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    seen = {"stop_calls": 0}

    class DummyManager:
        async def status(self, notebook_id, file_path=None):
            return {
                "notebook_id": notebook_id,
                "file_path": file_path,
                "source": "live",
                "running": True,
                "kernel_status": "busy",
            }

        async def stop(self, notebook_id, file_path=None):
            seen["stop_calls"] += 1
            return True

    monkeypatch.setattr(
        notebook_router_module,
        "get_kernel_manager",
        lambda: DummyManager(),
    )

    app = FastAPI()
    app.include_router(notebook_router_module.router, prefix="/notebook")
    client = TestClient(app)

    response = client.post(
        "/notebook/delete",
        json={"workspace": str(workspace), "path": str(notebook_path)},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "cannot delete a live pipeline notebook"
    assert notebook_path.exists()
    assert seen["stop_calls"] == 0


def test_notebook_kernel_routes_accept_workspace_file_contract(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import importlib

    from omicsclaw.app import server
    from omicsclaw.app.notebook import nb_files

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notebook_path = workspace / "analysis.ipynb"
    notebook_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )
    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    seen: dict[str, dict[str, object]] = {}

    class DummyManager:
        async def start(self, notebook_id, cwd=None, file_path=None):
            seen["start"] = {
                "notebook_id": notebook_id,
                "cwd": cwd,
                "file_path": file_path,
            }
            return {"notebook_id": notebook_id, "running": True, "cwd": cwd}

        async def status(self, notebook_id, file_path=None):
            seen["status"] = {
                "notebook_id": notebook_id,
                "file_path": file_path,
            }
            return {"notebook_id": notebook_id, "running": False, "kernel_status": "missing"}

    monkeypatch.setattr(
        notebook_router_module,
        "get_kernel_manager",
        lambda: DummyManager(),
    )

    app = FastAPI()
    app.include_router(notebook_router_module.router, prefix="/notebook")
    client = TestClient(app)

    expected_id = nb_files.derive_notebook_id(str(notebook_path))
    expected_path = str(notebook_path.resolve())
    expected_cwd = str(workspace.resolve())

    start_response = client.post(
        "/notebook/kernel/start",
        json={"workspace": str(workspace), "file_path": str(notebook_path)},
    )
    assert start_response.status_code == 200
    assert seen["start"] == {
        "notebook_id": expected_id,
        "cwd": expected_cwd,
        "file_path": expected_path,
    }

    status_response = client.get(
        "/notebook/kernel/status",
        params={"workspace": str(workspace), "file_path": str(notebook_path)},
    )
    assert status_response.status_code == 200
    assert seen["status"] == {
        "notebook_id": expected_id,
        "file_path": expected_path,
    }


def test_notebook_kernel_interrupt_route_forwards_to_manager(monkeypatch, tmp_path):
    """End-to-end HTTP → manager.interrupt() pin.

    If the Stop button in the UI hits this endpoint, the backend must
    (a) accept the workspace+file_path locator shape, (b) derive the
    right notebook_id, (c) call manager.interrupt() with that id, and
    (d) surface the "no kernel" case as HTTP 404 so the frontend can
    react instead of silently swallowing it.
    """
    pytest.importorskip("fastapi")

    import importlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server
    from omicsclaw.app.notebook import nb_files

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notebook_path = workspace / "analysis.ipynb"
    notebook_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        server,
        "_core",
        SimpleNamespace(TRUSTED_DATA_DIRS=[workspace]),
        raising=False,
    )
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    seen: dict[str, object] = {}

    class DummyManager:
        def __init__(self) -> None:
            self.should_succeed = True

        async def interrupt(self, notebook_id, file_path=None):
            seen["notebook_id"] = notebook_id
            seen["file_path"] = file_path
            return self.should_succeed

    dummy = DummyManager()
    monkeypatch.setattr(
        notebook_router_module,
        "get_kernel_manager",
        lambda: dummy,
    )

    app = FastAPI()
    app.include_router(notebook_router_module.router, prefix="/notebook")
    client = TestClient(app)

    expected_id = nb_files.derive_notebook_id(str(notebook_path))
    expected_path = str(notebook_path.resolve())

    # Happy path: kernel exists, manager reports True → HTTP 200.
    response = client.post(
        "/notebook/kernel/interrupt",
        json={"workspace": str(workspace), "file_path": str(notebook_path)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["interrupted"] is True
    assert body["notebook_id"] == expected_id
    assert seen == {
        "notebook_id": expected_id,
        "file_path": expected_path,
    }

    # Missing-kernel path: manager.interrupt() returns False → HTTP 404.
    dummy.should_succeed = False
    response_missing = client.post(
        "/notebook/kernel/interrupt",
        json={"workspace": str(workspace), "file_path": str(notebook_path)},
    )
    assert response_missing.status_code == 404
    assert "no kernel" in response_missing.json()["detail"]


def test_notebook_execute_route_accepts_workspace_file_contract(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import importlib

    from omicsclaw.app import server
    from omicsclaw.app.notebook import nb_files

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notebook_path = workspace / "analysis.ipynb"
    notebook_path.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )
    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace])
    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    seen: dict[str, object] = {}

    class DummyManager:
        async def execute_stream(self, notebook_id, cell_id, code, cwd=None, file_path=None):
            seen.update({
                "notebook_id": notebook_id,
                "cell_id": cell_id,
                "code": code,
                "cwd": cwd,
                "file_path": file_path,
            })
            yield {
                "type": "execute_reply",
                "data": {
                    "cell_id": cell_id,
                    "status": "ok",
                    "execution_count": 1,
                },
            }

    monkeypatch.setattr(
        notebook_router_module,
        "get_kernel_manager",
        lambda: DummyManager(),
    )

    app = FastAPI()
    app.include_router(notebook_router_module.router, prefix="/notebook")
    client = TestClient(app)

    expected_id = nb_files.derive_notebook_id(str(notebook_path))
    expected_path = str(notebook_path.resolve())
    expected_cwd = str(workspace.resolve())

    response = client.post(
        "/notebook/execute",
        json={
            "workspace": str(workspace),
            "file_path": str(notebook_path),
            "cell_id": "cell-1",
            "code": "print('hi')",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "execute_reply"' in response.text
    assert seen == {
        "notebook_id": expected_id,
        "cell_id": "cell-1",
        "code": "print('hi')",
        "cwd": expected_cwd,
        "file_path": expected_path,
    }


def test_notebook_execute_route_rejects_untrusted_workspace_before_streaming(
    monkeypatch, tmp_path
):
    """Regression: if the workspace/file_path resolve fails, the client
    must see a real HTTP 4xx with the validator's message — not an SSE
    stream that mysteriously "ends early"."""
    pytest.importorskip("fastapi")

    import importlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omicsclaw.app import server

    notebook_router_module = importlib.import_module("omicsclaw.app.notebook.router")

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    rogue = tmp_path / "rogue"
    rogue.mkdir()
    rogue_nb = rogue / "evil.ipynb"
    rogue_nb.write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        server,
        "_core",
        SimpleNamespace(TRUSTED_DATA_DIRS=[trusted]),
        raising=False,
    )
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(trusted))

    class ExplodingManager:
        async def execute_stream(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("execute_stream must not be reached")
            yield  # make this an async generator

    monkeypatch.setattr(
        notebook_router_module,
        "get_kernel_manager",
        lambda: ExplodingManager(),
    )

    app = FastAPI()
    app.include_router(notebook_router_module.router, prefix="/notebook")
    client = TestClient(app)

    response = client.post(
        "/notebook/execute",
        json={
            "workspace": str(rogue),
            "file_path": str(rogue_nb),
            "cell_id": "cell-1",
            "code": "print('hi')",
        },
    )

    # Real HTTP error with the real message — not a 200 SSE body.
    assert response.status_code == 400
    body = response.json()
    assert "trusted scope" in body["detail"]


def test_resolve_backend_init_config_prefers_documented_llm_namespace(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    monkeypatch.setenv("LLM_PROVIDER", "siliconflow")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("OMICSCLAW_PROVIDER", "openai")
    monkeypatch.setenv("OMICSCLAW_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("OMICSCLAW_API_KEY", "legacy-key")
    monkeypatch.setenv("OMICSCLAW_MODEL", "deepseek-ai/DeepSeek-V3")

    assert server._resolve_backend_init_config() == {
        "provider": "siliconflow",
        "api_key": "llm-key",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "auth_mode": "api_key",
        "ccproxy_port": "11435",
    }


def test_app_server_cli_dispatches(monkeypatch):
    oc = _load_omicsclaw_script()
    fake_server = ModuleType("omicsclaw.app.server")
    captured: dict[str, object] = {}

    def fake_main(argv=None):
        captured["argv"] = argv

    fake_server.main = fake_main
    monkeypatch.setitem(sys.modules, "omicsclaw.app.server", fake_server)
    monkeypatch.setattr(oc, "_ensure_server_dependencies", lambda **_: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["omicsclaw.py", "app-server", "--host", "0.0.0.0", "--port", "9123", "--reload"],
    )

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 0
    assert captured["argv"] == ["--host", "0.0.0.0", "--port", "9123", "--reload"]


def test_app_server_cli_fails_fast_when_uvicorn_missing(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    monkeypatch.setattr(oc, "_module_available", lambda name: name != "uvicorn")
    monkeypatch.setattr(sys, "argv", ["omicsclaw.py", "app-server"])

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "`app-server` requires optional dependencies" in captured.err
    assert "uvicorn" in captured.err
    assert 'pip install -e ".[desktop]"' in captured.err


def test_memory_server_cli_fails_fast_when_uvicorn_missing(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    monkeypatch.setattr(oc, "_module_available", lambda name: name != "uvicorn")
    monkeypatch.setattr(sys, "argv", ["omicsclaw.py", "memory-server"])

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "`memory-server` requires optional dependencies" in captured.err
    assert "uvicorn" in captured.err
    assert 'pip install -e ".[memory]"' in captured.err


@pytest.mark.asyncio
async def test_set_workspace_updates_workspace_env_and_persistence(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[], OUTPUT_DIR=tmp_path / "old-output")
    captured_updates: dict[str, str] = {}
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_get_omicsclaw_env_path", lambda: tmp_path / ".env", raising=False)
    monkeypatch.setattr(
        server,
        "_update_env_file",
        lambda env_path, updates: captured_updates.update(updates),
        raising=False,
    )
    monkeypatch.delenv("OMICSCLAW_DATA_DIRS", raising=False)
    monkeypatch.delenv("OMICSCLAW_WORKSPACE", raising=False)
    monkeypatch.delenv("OMICSCLAW_OUTPUT_DIR", raising=False)

    result = await server.set_workspace(server.WorkspaceRequest(workspace=str(workspace_dir)))

    expected_output_dir = workspace_dir / "output"

    assert result["ok"] is True
    assert result["workspace"] == str(workspace_dir)
    assert result["workspace_env"] == str(workspace_dir)
    assert result["output_dir"] == str(expected_output_dir)
    assert os.environ["OMICSCLAW_WORKSPACE"] == str(workspace_dir)
    assert os.environ["OMICSCLAW_DATA_DIRS"] == str(workspace_dir)
    assert os.environ["OMICSCLAW_OUTPUT_DIR"] == str(expected_output_dir)
    assert captured_updates == {
        "OMICSCLAW_DATA_DIRS": str(workspace_dir),
        "OMICSCLAW_WORKSPACE": str(workspace_dir),
        "OMICSCLAW_OUTPUT_DIR": str(expected_output_dir),
    }
    assert fake_core.TRUSTED_DATA_DIRS == [workspace_dir]
    assert fake_core.OUTPUT_DIR == expected_output_dir
    assert expected_output_dir.is_dir()


@pytest.mark.asyncio
async def test_chat_stream_request_workspace_updates_output_dir_before_tool_loop(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    expected_output_dir = workspace_dir / "output"
    captured: dict[str, object] = {}

    class FakeCore:
        TRUSTED_DATA_DIRS: list[Path] = []
        OUTPUT_DIR = tmp_path / "old-output"
        LLM_PROVIDER_NAME = "test"
        OMICSCLAW_MODEL = "test-model"
        received_files: list[object] = []

        @staticmethod
        def _skill_registry():
            return SimpleNamespace(skills={})

        @staticmethod
        def get_tool_executors():
            return {}

        @staticmethod
        async def llm_tool_loop(**kwargs):
            captured["workspace"] = kwargs["workspace"]
            captured["output_dir"] = FakeCore.OUTPUT_DIR
            return "done"

    monkeypatch.setattr(server, "_core", FakeCore, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)
    monkeypatch.delenv("OMICSCLAW_DATA_DIRS", raising=False)
    monkeypatch.delenv("OMICSCLAW_WORKSPACE", raising=False)
    monkeypatch.delenv("OMICSCLAW_OUTPUT_DIR", raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-output-dir",
            content="run analysis",
            workspace=str(workspace_dir),
        )
    )
    payload = await _read_streaming_response(response)

    assert '"done"' in payload
    assert captured["workspace"] == str(workspace_dir)
    assert captured["output_dir"] == expected_output_dir
    assert os.environ["OMICSCLAW_WORKSPACE"] == str(workspace_dir)
    assert os.environ["OMICSCLAW_OUTPUT_DIR"] == str(expected_output_dir)
    assert FakeCore.TRUSTED_DATA_DIRS == [workspace_dir]
    assert expected_output_dir.is_dir()


@pytest.mark.asyncio
async def test_outputs_latest_marks_stale_incomplete_run_failed(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    output_dir = tmp_path / "output"
    stale_run = output_dir / "spatial-domains__graphst__20260504_010203__stale001"
    stale_run.mkdir(parents=True)
    stdout_log = stale_run / "stdout.log"
    stdout_log.write_text("started\n", encoding="utf-8")
    old_timestamp = 1_700_000_000
    os.utime(stdout_log, (old_timestamp, old_timestamp))
    os.utime(stale_run, (old_timestamp, old_timestamp))

    fake_core = SimpleNamespace(OUTPUT_DIR=output_dir)
    monkeypatch.setattr(server, "_core", fake_core, raising=False)

    result = await server.outputs_latest(limit=10)

    assert result["total"] == 1
    assert result["runs"][0]["id"] == stale_run.name
    assert result["runs"][0]["status"] == "failed"
    assert "stale" in result["runs"][0]["summary"].lower()


@pytest.mark.asyncio
async def test_files_tree_returns_remote_files_and_directories(tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    root = tmp_path / "workspace"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "notes.md").write_text("# notes\n", encoding="utf-8")
    (nested / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    result = await server.files_tree(path=str(root), depth=2)

    assert result["root"] == str(root.resolve())
    by_name = {entry["name"]: entry for entry in result["tree"]}
    assert by_name["nested"]["type"] == "directory"
    assert by_name["nested"]["children"][0]["name"] == "table.csv"
    assert by_name["nested"]["children"][0]["type"] == "file"
    assert by_name["notes.md"]["type"] == "file"
    assert by_name["notes.md"]["extension"] == ".md"
    assert by_name["notes.md"]["size"] > 0


@pytest.mark.asyncio
async def test_files_serve_returns_trusted_workspace_file(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    workspace = tmp_path / "workspace"
    figure = workspace / "output" / "run-1" / "figures" / "spatial.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"PNGDATA")

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace], OUTPUT_DIR=workspace / "output")
    monkeypatch.setattr(server, "_core", fake_core, raising=False)

    response = await server.files_serve(path=str(figure))

    assert response.status_code == 200
    assert response.media_type == "image/png"
    assert response.path == str(figure.resolve())


@pytest.mark.asyncio
async def test_files_serve_rejects_untrusted_path(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"PNGDATA")

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[workspace], OUTPUT_DIR=workspace / "output")
    monkeypatch.setattr(server, "_core", fake_core, raising=False)

    with pytest.raises(server.HTTPException) as exc:
        await server.files_serve(path=str(outside))

    assert exc.value.status_code == 403


def test_resolve_scoped_memory_workspace_prefers_explicit_then_env_then_data_dir(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    monkeypatch.setattr(
        server,
        "_core",
        SimpleNamespace(DATA_DIR=Path("/tmp/core-data")),
        raising=False,
    )
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", "/tmp/env-workspace")

    assert server._resolve_scoped_memory_workspace("/tmp/explicit-workspace") == "/tmp/explicit-workspace"
    assert server._resolve_scoped_memory_workspace("") == "/tmp/env-workspace"

    monkeypatch.delenv("OMICSCLAW_WORKSPACE", raising=False)
    assert server._resolve_scoped_memory_workspace("") == "/tmp/core-data"


@pytest.mark.asyncio
async def test_health_reports_runtime_python_and_dependency_status(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    fake_core = SimpleNamespace(
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        _primary_skill_count=lambda: 42,
        get_skill_runner_python=lambda: "/opt/analysis/bin/python",
        OMICSCLAW_DIR=Path("/tmp/omicsclaw-project"),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(
        server,
        "_module_available",
        lambda name: name == "cellcharter",
        raising=False,
    )

    payload = await server.health()

    assert payload["status"] == "ok"
    assert payload["provider"] == "env"
    assert payload["model"] == "gpt-test"
    assert payload["skills_count"] == 42
    assert payload["python_executable"] == sys.executable
    assert payload["python_version"]
    assert payload["skill_python_executable"] == "/opt/analysis/bin/python"
    assert payload["omicsclaw_dir"] == "/tmp/omicsclaw-project"
    assert payload["launch_id"] == ""
    assert payload["dependencies"] == {
        "cellcharter": True,
        "squidpy": False,
    }


def test_health_echoes_desktop_launch_id(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    fake_core = SimpleNamespace(
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        _primary_skill_count=lambda: 42,
        get_skill_runner_python=lambda: sys.executable,
        OMICSCLAW_DIR=ROOT,
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setenv("OMICSCLAW_DESKTOP_LAUNCH_ID", "launch-123")

    payload = asyncio.run(server.health())

    assert payload["launch_id"] == "launch-123"


@pytest.mark.asyncio
async def test_chat_stream_emits_protocol_events_and_usage(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_kwargs: dict[str, object] = {}

    async def fake_llm_tool_loop(**kwargs):
        captured_kwargs.update(kwargs)
        kwargs["usage_accumulator"](
            SimpleNamespace(
                prompt_tokens=9,
                completion_tokens=3,
                total_tokens=12,
                prompt_tokens_details=SimpleNamespace(
                    cached_tokens=0,
                    cache_creation_tokens=0,
                ),
            )
        )
        await kwargs["on_stream_reasoning"]("reasoning delta")
        await kwargs["on_tool_call"]("task_update", {"task_id": "t1", "status": "in_progress"})
        await kwargs["on_tool_result"]("task_update", "updated")
        await kwargs["on_stream_content"]("streamed output")
        return "streamed output"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(
            skills={
                "spatial-preprocess": {
                    "alias": "spatial-preprocess",
                    "description": "Spatial preprocessing",
                }
            }
        ),
        get_tool_executors=lambda: {"task_update": object(), "inspect_data": object()},
        _accumulate_usage=lambda response_usage: {
            "prompt_tokens": int(getattr(response_usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(response_usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(response_usage, "total_tokens", 0) or 0),
        },
        _get_token_price=lambda model: (1.0, 2.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-1",
            content="hello",
            mode="plan",
            permission_profile="full_access",
        )
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)
    event_types = [event["type"] for event in events]

    assert "init" not in event_types
    assert "status" in event_types
    assert "mode_changed" in event_types
    assert "thinking" in event_types
    assert "tool_use" in event_types
    assert "tool_output" in event_types
    assert "tool_result" in event_types
    assert "task_update" in event_types
    assert "result" in event_types
    assert event_types[-1] == "done"

    status_event = next(event for event in events if event["type"] == "status")
    assert status_event["data"]["session_id"] == "session-1"
    assert status_event["data"]["permission_profile"] == "full_access"
    assert next(event for event in events if event["type"] == "mode_changed")["data"] == "plan"
    result_event = next(event for event in events if event["type"] == "result")
    assert result_event["data"]["usage"] == {
        "input_tokens": 9,
        "output_tokens": 3,
        "cost_usd": 0.000015,
    }
    assert captured_kwargs["policy_state"]["trusted"] is True
    assert captured_kwargs["policy_state"]["auto_approve_ask"] is True


@pytest.mark.asyncio
async def test_chat_stream_emits_preflight_pending_event_for_omicsclaw_tool(monkeypatch):
    """Desktop regression: when an omicsclaw tool result carries the
    ``preflight_pending`` metadata marker, the server must:

      - keep the ``tool_result`` event with ``is_error=False`` so the
        frontend renders the guidance content (otherwise the user only
        sees a collapsed error tile, as in the original sc-preprocessing
        bug report)
      - additionally emit a dedicated ``preflight_pending`` SSE event
        with the structured payload so the frontend can light up a
        confirmation prompt without parsing free-form text
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    payload = {
        "kind": "preflight",
        "status": "needs_user_input",
        "skill_name": "sc-preprocessing",
        "confirmations": ["Confirm defaults are acceptable"],
        "pending_fields": [],
    }

    async def fake_llm_tool_loop(**kwargs):
        await kwargs["on_tool_call"](
            "omicsclaw", {"skill": "preprocess", "file_path": "/tmp/x.h5ad"}
        )
        await kwargs["on_tool_result"](
            "omicsclaw",
            "USER_GUIDANCE: confirm defaults",
            {
                "success": False,
                "is_error": False,
                "preflight_pending": True,
                "preflight_payload": payload,
            },
        )
        await kwargs["on_stream_content"]("waiting on your confirm")
        return "waiting on your confirm"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"omicsclaw": object()},
        _accumulate_usage=lambda response_usage: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-preflight",
            content="please preprocess",
            mode="plan",
            permission_profile="full_access",
        )
    )
    payload_str = await _read_streaming_response(response)
    events = _parse_sse_events(payload_str)
    event_types = [event["type"] for event in events]

    assert "tool_result" in event_types
    assert "preflight_pending" in event_types, (
        "desktop must emit a dedicated preflight_pending SSE event so the "
        "frontend can render a confirmation UI instead of relying on the LLM "
        "to verbalise the structured guidance"
    )

    tool_result_event = next(e for e in events if e["type"] == "tool_result")
    # is_error MUST NOT be set for a preflight-pending result — that's
    # what was hiding the guidance in the original bug report.
    assert "is_error" not in tool_result_event["data"] or tool_result_event["data"]["is_error"] is False

    preflight_event = next(e for e in events if e["type"] == "preflight_pending")
    pf_data = preflight_event["data"]
    assert pf_data["tool_name"] == "omicsclaw"
    assert pf_data["session_id"] == "session-preflight"
    assert pf_data["payload"]["skill_name"] == "sc-preprocessing"
    assert pf_data["payload"]["status"] == "needs_user_input"


@pytest.mark.asyncio
async def test_chat_stream_updates_bound_remote_chat_job_lifecycle(monkeypatch, tmp_path: Path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.remote.schemas import Job
    from omicsclaw.remote.storage import jobs_root, utc_now_iso

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    job_dir = jobs_root(workspace) / "job-chat-1"
    job_dir.mkdir(parents=True, exist_ok=True)
    queued = Job(
        job_id="job-chat-1",
        session_id="session-chat-1",
        skill="chat",
        status="queued",
        workspace=str(workspace),
        inputs={},
        params={"job_kind": "chat_stream", "display_name": "chat turn"},
        created_at=utc_now_iso(),
    )
    (job_dir / "job.json").write_text(queued.model_dump_json(), encoding="utf-8")

    async def fake_llm_tool_loop(**kwargs):
        await kwargs["on_tool_call"]("task_update", {"task_id": "t1", "status": "in_progress"})
        await kwargs["on_tool_result"]("task_update", "updated")
        await kwargs["on_stream_content"]("remote chat output")
        return "remote chat output"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"task_update": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-chat-1",
            content="hello",
            workspace=str(workspace),
            job_id="job-chat-1",
        )
    )
    await _read_streaming_response(response)

    final_job = Job.model_validate_json((job_dir / "job.json").read_text(encoding="utf-8"))
    assert final_job.status == "succeeded"
    assert final_job.started_at
    assert final_job.finished_at
    stdout_text = (job_dir / "stdout.log").read_text(encoding="utf-8")
    assert "Starting task_update" in stdout_text
    assert "Completed task_update" in stdout_text


@pytest.mark.asyncio
async def test_chat_stream_cost_uses_requested_model_override(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    async def fake_llm_tool_loop(**kwargs):
        kwargs["usage_accumulator"](
            SimpleNamespace(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        )
        await kwargs["on_stream_content"]("priced response")
        return "priced response"

    def fake_get_token_price(model: str):
        if model == "priced-model":
            return (10.0, 20.0)
        return (0.0, 0.0)

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="unpriced-default",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {},
        _accumulate_usage=lambda response_usage: {
            "prompt_tokens": int(getattr(response_usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(response_usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(response_usage, "total_tokens", 0) or 0),
        },
        _get_token_price=fake_get_token_price,
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-priced-model",
            content="hello",
            model="priced-model",
        )
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)
    result_event = next(event for event in events if event["type"] == "result")

    assert result_event["data"]["usage"] == {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.02,
    }


@pytest.mark.asyncio
async def test_chat_stream_delivers_pending_media_as_tool_result_media(monkeypatch, tmp_path: Path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    image_path = tmp_path / "spatial_domains.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    pending_media: dict[str, list[dict[str, str]]] = {}

    async def fake_llm_tool_loop(**kwargs):
        pending_media["session-media"] = [
            {"type": "photo", "path": str(image_path)},
        ]
        await kwargs["on_tool_call"]("omicsclaw", {"skill": "spatial-domains"})
        await kwargs["on_tool_result"](
            "omicsclaw",
            (
                "spatial domain 图 以及其他可视化文件（域纯度直方图、PCA、"
                "邻近混合图等）正在自动传送中。"
            ),
        )
        return "analysis complete"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        pending_media=pending_media,
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"omicsclaw": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(session_id="session-media", content="show the plot")
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)
    tool_result = next(event for event in events if event["type"] == "tool_result")

    assert tool_result["data"]["media"] == [
        {
            "type": "image",
            "mimeType": "image/png",
            "localPath": str(image_path),
        }
    ]
    assert fake_core.pending_media == {}


@pytest.mark.asyncio
async def test_chat_stream_merges_pending_media_without_duplicates(monkeypatch, tmp_path: Path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    image_path = tmp_path / "spatial_domains.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    extra_path = tmp_path / "domain_sizes.png"
    extra_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    pending_media: dict[str, list[dict[str, str]]] = {}

    async def fake_llm_tool_loop(**kwargs):
        pending_media["session-media-merge"] = [
            {"type": "photo", "path": str(image_path)},
            {"type": "photo", "path": str(extra_path)},
        ]
        await kwargs["on_tool_call"]("omicsclaw", {"skill": "spatial-domains"})
        await kwargs["on_tool_result"](
            "omicsclaw",
            json.dumps({"plot_path": str(image_path)}),
        )
        return "analysis complete"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        pending_media=pending_media,
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"omicsclaw": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(session_id="session-media-merge", content="show plots")
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)
    tool_result = next(event for event in events if event["type"] == "tool_result")

    assert tool_result["data"]["media"] == [
        {
            "type": "image",
            "mimeType": "image/png",
            "localPath": str(image_path),
        },
        {
            "type": "image",
            "mimeType": "image/png",
            "localPath": str(extra_path),
        },
    ]
    assert fake_core.pending_media == {}


@pytest.mark.asyncio
async def test_chat_stream_delivers_pending_documents_as_file_media(monkeypatch, tmp_path: Path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    table_path = tmp_path / "domain_purity.csv"
    table_path.write_text("domain,purity\n1,0.92\n", encoding="utf-8")
    pending_media: dict[str, list[dict[str, str]]] = {}

    async def fake_llm_tool_loop(**kwargs):
        pending_media["session-document-media"] = [
            {"type": "document", "path": str(table_path)},
        ]
        await kwargs["on_tool_call"]("omicsclaw", {"skill": "spatial-domains"})
        await kwargs["on_tool_result"](
            "omicsclaw",
            "analysis files are being delivered automatically.",
        )
        return "analysis complete"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        pending_media=pending_media,
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"omicsclaw": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(session_id="session-document-media", content="show files")
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)
    tool_result = next(event for event in events if event["type"] == "tool_result")

    assert tool_result["data"]["media"] == [
        {
            "type": "file",
            "mimeType": "text/csv",
            "localPath": str(table_path),
        }
    ]
    assert fake_core.pending_media == {}


@pytest.mark.asyncio
async def test_chat_stream_rejects_bind_when_job_already_canceled(monkeypatch, tmp_path: Path):
    """Regression: ``bind_chat_stream_job`` intentionally passes canceled jobs
    through so the cancel handler can finalize them without clobbering state.
    Before this guard, ``chat_stream`` discarded that return value and marched
    on into the tool loop, executing a full chat turn whose job row was
    permanently ``canceled`` — backend state and actual execution forked.
    The handler must bail with 409 instead.
    """
    pytest.importorskip("fastapi")

    from fastapi import HTTPException

    from omicsclaw.app import server
    from omicsclaw.remote.schemas import Job
    from omicsclaw.remote.storage import jobs_root, utc_now_iso

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    job_dir = jobs_root(workspace) / "job-chat-canceled"
    job_dir.mkdir(parents=True, exist_ok=True)
    canceled = Job(
        job_id="job-chat-canceled",
        session_id="session-chat-canceled",
        skill="chat",
        status="canceled",
        workspace=str(workspace),
        inputs={},
        params={"job_kind": "chat_stream", "display_name": "chat turn"},
        created_at=utc_now_iso(),
        finished_at=utc_now_iso(),
    )
    (job_dir / "job.json").write_text(canceled.model_dump_json(), encoding="utf-8")

    tool_loop_ran = False

    async def fake_llm_tool_loop(**kwargs):
        nonlocal tool_loop_ran
        tool_loop_ran = True
        return ""

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    with pytest.raises(HTTPException) as excinfo:
        await server.chat_stream(
            server.ChatRequest(
                session_id="session-chat-canceled",
                content="hello",
                workspace=str(workspace),
                job_id="job-chat-canceled",
            )
        )

    assert excinfo.value.status_code == 409
    assert "canceled" in str(excinfo.value.detail).lower()
    assert not tool_loop_ran, "tool loop must not run for a pre-canceled job"

    # Job row must remain canceled — the guard explicitly avoids clobbering.
    final_job = Job.model_validate_json((job_dir / "job.json").read_text(encoding="utf-8"))
    assert final_job.status == "canceled"


@pytest.mark.asyncio
async def test_chat_stream_surfaces_provider_switch_failure(monkeypatch):
    """When provider switch fails, chat_stream must raise HTTPException instead
    of silently falling back to the previous provider. Without this the UI
    shows a ``status`` event naming the old provider — the user thinks the
    switch succeeded while the chat actually runs against the previous model.
    """
    pytest.importorskip("fastapi")

    from fastapi import HTTPException

    from omicsclaw.app import server

    class FailingCore:
        LLM_PROVIDER_NAME = "anthropic"
        OMICSCLAW_MODEL = "claude-sonnet-4-6"

        def init(self, **kwargs):
            raise RuntimeError("deepseek unreachable: connection refused")

        _skill_registry = staticmethod(lambda: SimpleNamespace(skills={}))
        get_tool_executors = staticmethod(lambda: {})
        _accumulate_usage = staticmethod(lambda response_usage: {})
        _get_token_price = staticmethod(lambda model: (0.0, 0.0))

    monkeypatch.setattr(server, "_core", FailingCore(), raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    with pytest.raises(HTTPException) as excinfo:
        await server.chat_stream(
            server.ChatRequest(
                session_id="session-switch-fail",
                content="hello",
                provider_id="deepseek",
            )
        )

    assert excinfo.value.status_code == 400
    detail = str(excinfo.value.detail)
    assert "deepseek" in detail
    assert "connection refused" in detail


@pytest.mark.asyncio
async def test_chat_stream_reapplies_provider_when_model_changes(monkeypatch):
    """Custom Endpoint keeps the same provider id while users edit model names.

    The chat request must still reinitialise the runtime when the model differs;
    otherwise the status event claims the requested model while the underlying
    AsyncOpenAI client still points at the previous model/provider runtime.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured: dict[str, object] = {}

    class FakeCore:
        LLM_PROVIDER_NAME = "custom"
        OMICSCLAW_MODEL = "old-model"
        received_files: list[object] = []

        def init(self, **kwargs):
            captured["init"] = kwargs
            self.LLM_PROVIDER_NAME = kwargs.get("provider") or self.LLM_PROVIDER_NAME
            self.OMICSCLAW_MODEL = kwargs.get("model") or self.OMICSCLAW_MODEL

        _skill_registry = staticmethod(lambda: SimpleNamespace(skills={}))
        get_tool_executors = staticmethod(lambda: {})
        _accumulate_usage = staticmethod(lambda response_usage: {})

        async def llm_tool_loop(self, **kwargs):
            captured["model_override"] = kwargs.get("model_override")
            return "ok"

    monkeypatch.setattr(server, "_core", FakeCore(), raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)
    monkeypatch.setattr(server, "_get_omicsclaw_env_path", lambda: None, raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-custom-model-change",
            content="hello",
            provider_id="custom",
            model="new-model",
        )
    )
    payload = await _read_streaming_response(response)

    assert '"ok"' in payload
    assert captured["init"] == {
        "provider": "custom",
        "model": "new-model",
        "base_url": "https://api.example.com/v1",
    }
    assert captured["model_override"] == "new-model"


@pytest.mark.asyncio
async def test_chat_stream_provider_config_preserves_custom_env_base_url(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured: dict[str, object] = {}

    class FakeCore:
        LLM_PROVIDER_NAME = "deepseek"
        OMICSCLAW_MODEL = "deepseek-v4-flash"
        received_files: list[object] = []

        def init(self, **kwargs):
            captured["init"] = kwargs
            self.LLM_PROVIDER_NAME = kwargs.get("provider") or self.LLM_PROVIDER_NAME
            self.OMICSCLAW_MODEL = kwargs.get("model") or self.OMICSCLAW_MODEL

        _skill_registry = staticmethod(lambda: SimpleNamespace(skills={}))
        get_tool_executors = staticmethod(lambda: {})
        _accumulate_usage = staticmethod(lambda response_usage: {})

        async def llm_tool_loop(self, **kwargs):
            return "ok"

    monkeypatch.setattr(server, "_core", FakeCore(), raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)
    monkeypatch.setattr(server, "_get_omicsclaw_env_path", lambda: None, raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-custom-provider-config",
            content="hello",
            provider_config=server.ProviderConfig(
                provider="custom",
                model="custom-model",
            ),
        )
    )
    payload = await _read_streaming_response(response)

    assert '"ok"' in payload
    assert captured["init"] == {
        "api_key": "",
        "base_url": "https://api.example.com/v1",
        "model": "custom-model",
        "provider": "custom",
    }


@pytest.mark.asyncio
async def test_chat_stream_provider_config_rejects_incomplete_custom_endpoint(monkeypatch):
    pytest.importorskip("fastapi")

    from fastapi import HTTPException

    from omicsclaw.app import server

    class FakeCore:
        LLM_PROVIDER_NAME = "deepseek"
        OMICSCLAW_MODEL = "deepseek-v4-flash"

        def init(self, **kwargs):
            raise AssertionError("incomplete custom provider should fail before core.init")

    monkeypatch.setattr(server, "_core", FakeCore(), raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")

    with pytest.raises(HTTPException) as excinfo:
        await server.chat_stream(
            server.ChatRequest(
                session_id="session-custom-provider-config-invalid",
                content="hello",
                provider_config=server.ProviderConfig(provider="custom"),
            )
        )

    assert excinfo.value.status_code == 400
    assert "model" in str(excinfo.value.detail).lower()


@pytest.mark.asyncio
async def test_switch_provider_clears_legacy_base_url_alias(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_remove_keys: set[str] = set()

    class FakeCore:
        LLM_PROVIDER_NAME = "openai"
        OMICSCLAW_MODEL = "gpt-5.5"

        def init(self, **kwargs):
            self.LLM_PROVIDER_NAME = kwargs.get("provider") or self.LLM_PROVIDER_NAME
            self.OMICSCLAW_MODEL = kwargs.get("model") or self.OMICSCLAW_MODEL

    def fake_update_env_file(env_path, updates, *, remove_keys=None):
        captured_remove_keys.update(remove_keys or set())

    monkeypatch.setattr(server, "_get_core", lambda: FakeCore())
    monkeypatch.setattr(server, "_get_omicsclaw_env_path", lambda: Path("/tmp/.env"))
    monkeypatch.setattr(server, "_update_env_file", fake_update_env_file)

    await server.switch_provider(
        server.ProviderSwitchRequest(
            provider="openai",
            api_key="sk-test",
            model="gpt-5.5",
        )
    )

    assert "LLM_BASE_URL" in captured_remove_keys
    assert "OMICSCLAW_BASE_URL" in captured_remove_keys


def test_apply_chat_provider_switch_clears_legacy_base_url_alias(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_remove_keys: set[str] = set()

    class FakeCore:
        LLM_PROVIDER_NAME = "custom"
        OMICSCLAW_MODEL = "custom-model"

        def init(self, **kwargs):
            self.LLM_PROVIDER_NAME = kwargs.get("provider") or self.LLM_PROVIDER_NAME
            self.OMICSCLAW_MODEL = kwargs.get("model") or self.OMICSCLAW_MODEL

    def fake_update_env_file(env_path, updates, *, remove_keys=None):
        captured_remove_keys.update(remove_keys or set())

    monkeypatch.setattr(server, "_get_omicsclaw_env_path", lambda: Path("/tmp/.env"))
    monkeypatch.setattr(server, "_update_env_file", fake_update_env_file)

    server._apply_chat_provider_switch(FakeCore(), "openai", "gpt-5.5")

    assert "LLM_BASE_URL" in captured_remove_keys
    assert "OMICSCLAW_BASE_URL" in captured_remove_keys


@pytest.mark.asyncio
async def test_switch_provider_rejects_incomplete_custom_endpoint(monkeypatch):
    pytest.importorskip("fastapi")

    from fastapi import HTTPException

    from omicsclaw.app import server

    class FakeCore:
        LLM_PROVIDER_NAME = "deepseek"
        OMICSCLAW_MODEL = "deepseek-v4-flash"

        def init(self, **kwargs):
            raise AssertionError("incomplete custom provider should fail before core.init")

    monkeypatch.setattr(server, "_get_core", lambda: FakeCore())

    with pytest.raises(HTTPException) as excinfo:
        await server.switch_provider(
            server.ProviderSwitchRequest(
                provider="custom",
                api_key="sk-test",
                base_url="https://api.example.com/v1",
                model="",
            )
        )

    assert excinfo.value.status_code == 400
    assert "model" in str(excinfo.value.detail).lower()


@pytest.mark.asyncio
async def test_list_providers_reflects_active_custom_endpoint(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    class FakeCore:
        LLM_PROVIDER_NAME = "custom"
        OMICSCLAW_MODEL = "qwen-plus"

    monkeypatch.setattr(server, "_core", FakeCore, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    payload = await server.list_providers()
    custom = next(item for item in payload["providers"] if item["name"] == "custom")

    assert custom["active"] is True
    assert custom["configured"] is True
    assert custom["base_url"] == "https://api.example.com/v1"
    assert custom["default_model"] == "qwen-plus"
    assert payload["current_model"] == "qwen-plus"


@pytest.mark.asyncio
async def test_provider_test_closes_async_openai_client(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    clients: list[object] = []
    fail_request = False

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )
            clients.append(self)

        async def _create(self, **kwargs):
            if fail_request:
                raise RuntimeError("provider unreachable")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="OK"),
                    )
                ]
            )

        async def close(self):
            self.closed = True

    class FakeCore:
        LLM_PROVIDER_NAME = ""
        OMICSCLAW_MODEL = ""

    monkeypatch.setattr(server, "_get_core", lambda: FakeCore())
    monkeypatch.setattr(server, "AsyncOpenAI", FakeAsyncOpenAI)

    result = await server.test_provider(
        server.ProviderTestRequest(
            provider="custom",
            model="qwen-plus",
            base_url="https://api.example.com/v1",
            api_key="sk-test",
        )
    )

    assert result["ok"] is True
    assert len(clients) == 1
    assert clients[0].closed is True

    fail_request = True
    result = await server.test_provider(
        server.ProviderTestRequest(
            provider="custom",
            model="qwen-plus",
            base_url="https://api.example.com/v1",
            api_key="sk-test",
        )
    )

    assert result["ok"] is False
    assert "provider unreachable" in result["message"]
    assert len(clients) == 2
    assert clients[1].closed is True


@pytest.mark.asyncio
async def test_chat_stream_omits_adaptive_thinking_for_siliconflow(monkeypatch):
    """SiliconFlow gateway rejects non-standard thinking types — adaptive must omit."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_kwargs: dict[str, object] = {}

    async def fake_llm_tool_loop(**kwargs):
        captured_kwargs.update(kwargs)
        await kwargs["on_stream_content"]("ok")
        return "ok"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="siliconflow",
        OMICSCLAW_MODEL="deepseek-ai/DeepSeek-V3",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-thinking-adaptive",
            content="hello",
            thinking={"type": "adaptive"},
        )
    )
    await _read_streaming_response(response)

    assert captured_kwargs["extra_api_params"] is None


@pytest.mark.asyncio
async def test_chat_stream_enables_adaptive_thinking_for_deepseek(monkeypatch):
    """DeepSeek native API supports thinking — adaptive must enable it."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_kwargs: dict[str, object] = {}

    async def fake_llm_tool_loop(**kwargs):
        captured_kwargs.update(kwargs)
        await kwargs["on_stream_content"]("ok")
        return "ok"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="deepseek",
        OMICSCLAW_MODEL="deepseek-chat",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(
            session_id="session-thinking-deepseek",
            content="hello",
            thinking={"type": "adaptive"},
        )
    )
    await _read_streaming_response(response)

    extra = captured_kwargs["extra_api_params"]
    assert extra is not None
    assert extra["extra_body"]["thinking"] == {
        "type": "enabled",
        "budget_tokens": 10000,
    }


def test_build_thinking_extra_body_explicit_enabled_and_disabled():
    """Explicit enabled/disabled are always honoured regardless of provider."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    # enabled — any provider
    assert server._build_thinking_extra_body(
        {"type": "enabled", "budgetTokens": 123},
        provider="siliconflow",
    ) == {"type": "enabled", "budget_tokens": 123}

    assert server._build_thinking_extra_body(
        {"type": "enabled", "budgetTokens": 500},
        provider="deepseek",
    ) == {"type": "enabled", "budget_tokens": 500}

    # disabled — any provider
    assert server._build_thinking_extra_body(
        {"type": "disabled"}, provider="deepseek",
    ) == {"type": "disabled"}


def test_build_thinking_extra_body_adaptive_per_provider():
    """Adaptive mode enables thinking only for supported providers/models."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    adaptive = {"type": "adaptive"}

    # Native provider → enabled
    result = server._build_thinking_extra_body(adaptive, provider="deepseek")
    assert result == {"type": "enabled", "budget_tokens": 10000}

    # Incompatible provider → omit
    assert server._build_thinking_extra_body(adaptive, provider="siliconflow") is None

    # Gateway with thinking-capable model → enabled
    result = server._build_thinking_extra_body(
        adaptive, provider="openrouter", model="deepseek/deepseek-chat-v3-0324",
    )
    assert result == {"type": "enabled", "budget_tokens": 10000}

    result = server._build_thinking_extra_body(
        adaptive, provider="openrouter", model="deepseek/deepseek-v4-pro",
    )
    assert result == {"type": "enabled", "budget_tokens": 10000}

    result = server._build_thinking_extra_body(
        adaptive, provider="nvidia", model="deepseek-ai/deepseek-r1",
    )
    assert result == {"type": "enabled", "budget_tokens": 10000}

    # Gateway with non-thinking model → omit
    assert server._build_thinking_extra_body(
        adaptive, provider="openrouter", model="anthropic/claude-3-opus",
    ) is None

    # Unknown provider, unknown model → omit
    assert server._build_thinking_extra_body(adaptive, provider="ollama", model="llama3") is None

    # No provider, no model → omit (safe default)
    assert server._build_thinking_extra_body(adaptive) is None

    # Custom budget with adaptive on native provider
    result = server._build_thinking_extra_body(
        {"type": "adaptive", "budgetTokens": 5000}, provider="deepseek",
    )
    assert result == {"type": "enabled", "budget_tokens": 5000}


def test_build_thinking_extra_body_invalid_inputs():
    """Non-dict / empty inputs return None."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    assert server._build_thinking_extra_body(None) is None
    assert server._build_thinking_extra_body("enabled") is None
    assert server._build_thinking_extra_body(42) is None
    assert server._build_thinking_extra_body({}) is None


@pytest.mark.asyncio
async def test_chat_stream_emits_structured_tool_timeout_events(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    async def fake_llm_tool_loop(**kwargs):
        await kwargs["on_tool_call"]("notebook_add_execute", {"source": "sleep(999)"})
        await kwargs["on_tool_result"](
            "notebook_add_execute",
            "Cell execution timed out after 91s",
            {
                "success": False,
                "is_error": True,
                "timed_out": True,
                "elapsed_seconds": 91,
            },
        )
        return ""

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"notebook_add_execute": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(session_id="session-timeout", content="run cell")
    )
    payload = await _read_streaming_response(response)
    events = _parse_sse_events(payload)

    tool_result = next(event for event in events if event["type"] == "tool_result")
    tool_timeout = next(event for event in events if event["type"] == "tool_timeout")

    assert any(
        event["type"] == "tool_output"
        and event["data"] == "notebook_add_execute timed out after 91s"
        for event in events
    )
    assert tool_result["data"]["is_error"] is True
    assert tool_timeout["data"] == {
        "tool_name": "notebook_add_execute",
        "elapsed_seconds": 91,
    }


@pytest.mark.asyncio
async def test_chat_permission_endpoint_resumes_pending_request(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    captured_decision: dict[str, object] = {}
    permission_event = asyncio.Event()
    permission_id_holder: dict[str, str] = {}

    async def fake_llm_tool_loop(**kwargs):
        await kwargs["on_tool_call"]("remove_file", {"path": "/tmp/data.txt"})
        decision = await kwargs["request_tool_approval"](
            SimpleNamespace(
                name="remove_file",
                arguments={"path": "/tmp/data.txt"},
                spec=SimpleNamespace(description="Delete a file"),
            ),
            SimpleNamespace(policy_decision=SimpleNamespace(reason="Needs approval")),
        )
        captured_decision.update(decision)
        await kwargs["on_tool_result"]("remove_file", "deleted")
        await kwargs["on_stream_content"]("done")
        return "done"

    fake_core = SimpleNamespace(
        init=lambda **kwargs: None,
        llm_tool_loop=fake_llm_tool_loop,
        LLM_PROVIDER_NAME="env",
        OMICSCLAW_MODEL="gpt-test",
        OUTPUT_DIR=ROOT / "output",
        _skill_registry=lambda: SimpleNamespace(skills={}),
        get_tool_executors=lambda: {"remove_file": object()},
        _accumulate_usage=lambda response_usage: {},
        _get_token_price=lambda model: (0.0, 0.0),
    )

    monkeypatch.setattr(server, "_core", fake_core, raising=False)
    monkeypatch.setattr(server, "_mcp_load_fn", None, raising=False)

    response = await server.chat_stream(
        server.ChatRequest(session_id="session-2", content="delete the file")
    )

    async def consume_stream() -> str:
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
            chunks.append(text)
            for event in _parse_sse_events(text):
                if event["type"] == "permission_request":
                    permission_id_holder["id"] = event["data"]["permissionRequestId"]
                    permission_event.set()
        return "".join(chunks)

    consumer = asyncio.create_task(consume_stream())
    await asyncio.wait_for(permission_event.wait(), timeout=2)

    permission_response = await server.chat_permission(
        server.PermissionResponseRequest(
            permissionRequestId=permission_id_holder["id"],
            decision={"behavior": "allow"},
        )
    )
    payload = await consumer
    events = _parse_sse_events(payload)

    assert permission_response["ok"] is True
    assert captured_decision["behavior"] == "allow"
    assert captured_decision["policy_state"]["approved_tool_names"] == ["remove_file"]
    assert any(event["type"] == "permission_request" for event in events)
    assert any(event["type"] == "tool_result" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_mcp_sync_reconciles_removed_servers_and_preserves_tools(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.interactive import _mcp

    added: list[dict[str, object]] = []
    removed: list[str] = []

    def fake_add_mcp_server(
        name,
        target,
        *,
        extra_args=None,
        transport=None,
        env=None,
        headers=None,
        enabled=None,
        tools=None,
    ):
        added.append(
            {
                "name": name,
                "target": target,
                "transport": transport,
                "extra_args": extra_args,
                "env": env,
                "headers": headers,
                "enabled": enabled,
                "tools": tools,
            }
        )

    monkeypatch.setattr(_mcp, "add_mcp_server", fake_add_mcp_server)
    monkeypatch.setattr(
        _mcp,
        "list_mcp_servers",
        lambda: [
            {"name": "fresh-server", "transport": "sse", "url": "https://old.example/sse"},
            {"name": "stale-server", "transport": "http", "url": "https://stale.example/mcp"},
        ],
    )
    monkeypatch.setattr(
        _mcp,
        "remove_mcp_server",
        lambda name: removed.append(name) or True,
    )

    class DummyRequest:
        async def json(self):
            return {
                "mcpServers": {
                    "fresh-server": {
                        "type": "sse",
                        "url": "https://mcp.example/sse",
                        "headers": {
                            "Authorization": "Bearer token",
                            "X-Workspace": "omics",
                        },
                        "enabled": False,
                        "tools": ["allowed_tool"],
                    }
                }
            }

    result = await server.mcp_sync_from_frontend(DummyRequest())

    assert result == {"ok": True, "synced": 1, "removed": 1}
    assert removed == ["stale-server"]
    assert added == [
        {
            "name": "fresh-server",
            "target": "https://mcp.example/sse",
            "transport": "sse",
            "extra_args": None,
            "env": None,
            "headers": {
                "Authorization": "Bearer token",
                "X-Workspace": "omics",
            },
            "enabled": False,
            "tools": ["allowed_tool"],
        }
    ]


@pytest.mark.asyncio
async def test_mcp_sync_empty_payload_removes_all_existing_servers(monkeypatch):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.interactive import _mcp

    added: list[dict[str, object]] = []
    removed: list[str] = []

    monkeypatch.setattr(_mcp, "add_mcp_server", lambda *args, **kwargs: added.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(
        _mcp,
        "list_mcp_servers",
        lambda: [
            {"name": "stale-a", "transport": "stdio", "command": "npx"},
            {"name": "stale-b", "transport": "sse", "url": "https://stale.example/sse"},
        ],
    )
    monkeypatch.setattr(
        _mcp,
        "remove_mcp_server",
        lambda name: removed.append(name) or True,
    )

    class DummyRequest:
        async def json(self):
            return {"mcpServers": {}}

    result = await server.mcp_sync_from_frontend(DummyRequest())

    assert result == {"ok": True, "synced": 0, "removed": 2}
    assert added == []
    assert removed == ["stale-a", "stale-b"]


# ---------------------------------------------------------------------------
# T2 S2 — /memory/browse recall falls back to __shared__
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_browse_endpoint_falls_back_to_shared(monkeypatch, tmp_path):
    """GET /memory/browse for a URI that lives only in __shared__ must
    surface the shared content to the desktop client via read fallback.
    Pins the engine.recall(fallback_to_shared=True) contract at the
    HTTP boundary."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        # core://agent/* routes to __shared__ via namespace_policy.
        await desktop_client.remember("core://agent/style", "concise replies")

        # Sanity: the row really lives only in __shared__.
        assert (
            await engine.recall(
                "core://agent/style",
                namespace="app/desktop_user",
                fallback_to_shared=False,
            )
        ) is None

        result = await server.memory_browse(path="agent/style", domain="core")
        assert result["node"] is not None, (
            "browse returned no node — read fallback to __shared__ broken"
        )
        assert result["node"]["content"] == "concise replies"
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# /memory/browse — is_versioned flag drives the desktop "Show history" button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_browse_marks_versioned_uri(monkeypatch, tmp_path):
    """A versioned URI (per ``namespace_policy.should_version``) must
    surface ``is_versioned=True`` in the /memory/browse response so the
    desktop UI can decide whether to render the History/rollback button.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("core://my_user/note", "v1")

        result = await server.memory_browse(path="my_user/note", domain="core")
        assert result["is_versioned"] is True, (
            f"core://my_user/note is in VERSIONED_PREFIXES; expected "
            f"is_versioned=True, got {result.get('is_versioned')!r}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_browse_marks_overwrite_uri(monkeypatch, tmp_path):
    """An overwrite-only URI (``dataset://``, ``analysis://``) must
    surface ``is_versioned=False`` so the UI hides the History button —
    these URIs structurally have no version chain."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("dataset://x.h5ad", "data x")

        result = await server.memory_browse(path="x.h5ad", domain="dataset")
        assert result["is_versioned"] is False, (
            f"dataset:// is overwrite-only; expected is_versioned=False, "
            f"got {result.get('is_versioned')!r}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_browse_is_versioned_present_on_root_browse(
    monkeypatch, tmp_path
):
    """Root browse (``path=""``, ``domain="core"``) must still include
    the ``is_versioned`` field. ``core://`` itself is not versioned, so
    the value is False — but the field's presence is the contract the
    front-end relies on, not just the value.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        result = await server.memory_browse(path="", domain="core")
        assert "is_versioned" in result
        assert result["is_versioned"] is False
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_browse_children_have_rich_shape(monkeypatch, tmp_path):
    """Each /memory/browse child must carry the desktop-tree fields
    (``name``, ``path``, ``domain``, ``approx_children_count``) so
    MemoryTree.tsx and MemoryContent.tsx can render labels and decide
    whether the entry is a directory. The sparse ``MemoryRef`` shape
    (``memory_id``/``node_uuid``/``namespace``/``uri`` only) leaves the
    UI showing blank rows, which is the regression this guards.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("core://parent/child_a", "leaf a")
        await desktop_client.remember("core://parent/child_b/grandchild", "leaf b")

        result = await server.memory_browse(path="parent", domain="core")
        children = result["children"]
        assert len(children) >= 2, (
            f"expected ≥2 children under core://parent, got {len(children)}"
        )

        required = {"name", "path", "domain", "approx_children_count"}
        for child in children:
            missing = required - set(child)
            assert not missing, (
                f"child {child!r} missing rich-shape fields: {missing}. "
                f"This means /memory/browse is returning the sparse "
                f"MemoryRef list_children shape instead of "
                f"list_children_rich, and the desktop UI shows blank rows."
            )

        by_name = {c["name"]: c for c in children}
        assert "child_a" in by_name, f"missing 'child_a'; got {list(by_name)}"
        assert "child_b" in by_name, f"missing 'child_b'; got {list(by_name)}"
        assert by_name["child_a"]["approx_children_count"] == 0
        assert by_name["child_b"]["approx_children_count"] >= 1, (
            "child_b has a grandchild; approx_children_count should be ≥1 "
            "so the UI marks it as a directory"
        )
        assert by_name["child_a"]["domain"] == "core"
        assert by_name["child_a"]["path"] == "parent/child_a"
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# /memory/browse + /memory/children — derived display label for analysis://*
# (see docs/adr/0002-derived-display-label-for-analysis-memory.md)
# ---------------------------------------------------------------------------


def _seed_analysis_payload(*, status: str, dataset_path: str, executed_at: str):
    """Build a Pydantic-compatible AnalysisMemory JSON for seeding."""
    import json as _json

    return _json.dumps({
        "memory_id": "any-uuid-fake",
        "memory_type": "analysis",
        "created_at": executed_at,
        "source_dataset_id": "ds-uuid",
        "parent_analysis_id": None,
        "skill": "sc-preprocessing",
        "method": "default",
        "parameters": {"input": dataset_path},
        "output_path": "",
        "status": status,
        "executed_at": executed_at,
        "duration_seconds": 0.0,
    })


@pytest.mark.asyncio
async def test_memory_browse_decorates_analysis_children_with_derived_title(
    monkeypatch, tmp_path
):
    """For ``analysis://*`` parents, ``/memory/browse`` must surface
    ``<basename> · <time> · <status>`` in each child's ``name`` field,
    not the URI's UUID-style last segment. The desktop tree currently
    renders ``name`` directly so the user sees identifiable rows
    instead of opaque hex.
    """
    import os as _os
    import time as _time

    # Pin the test process to UTC so the time-of-day rendered by
    # ``_analysis_content_to_title`` is deterministic regardless of the
    # CI runner's locale.
    _os.environ["TZ"] = "UTC"
    _time.tzset()

    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        # Two analysis runs under the same skill, different datasets and
        # statuses. URI last-segments are intentionally unreadable to
        # mimic the production UUID-hex pattern this fix exists for.
        await desktop_client.remember(
            "analysis://sc-preprocessing/3c7a182ee7ab498ea4454a2f8465063c",
            _seed_analysis_payload(
                status="completed",
                dataset_path="/data/work/pbmc3k_raw.h5ad",
                executed_at="2026-05-05T12:43:00Z",
            ),
        )
        await desktop_client.remember(
            "analysis://sc-preprocessing/9c71d3252e4c4fc3ae51468db124d5cc",
            _seed_analysis_payload(
                status="failed",
                dataset_path="/data/work/visium_brain.h5ad",
                executed_at="2026-05-05T08:15:00Z",
            ),
        )

        result = await server.memory_browse(
            path="sc-preprocessing", domain="analysis"
        )
        children = result["children"]
        assert len(children) == 2, (
            f"seeded 2 children, got {len(children)}: {children!r}"
        )

        names = {c["name"] for c in children}

        # Both children should have the derived title in ``name``. We
        # don't pin exact strings on the time portion (older-than-today
        # vs today depends on the test's wall clock) — assert the two
        # invariant pieces: dataset basename and status.
        for c in children:
            assert "·" in c["name"], (
                f"expected derived title with separator in name, got "
                f"{c['name']!r} — looks like raw UUID, decoration didn't fire"
            )
            assert (
                "pbmc3k_raw.h5ad" in c["name"]
                or "visium_brain.h5ad" in c["name"]
            ), f"name {c['name']!r} missing dataset basename"
            assert (
                c["name"].endswith(" · completed")
                or c["name"].endswith(" · failed")
            ), f"name {c['name']!r} missing status suffix"

        # The original UUID is preserved in ``path`` so the frontend
        # can still link to / inspect / delete the row.
        paths = {c["path"] for c in children}
        assert (
            "sc-preprocessing/3c7a182ee7ab498ea4454a2f8465063c" in paths
        ), f"path {paths!r} should keep UUID"

        # Negative: bare UUID hex must NOT appear as a name (that was
        # the pre-fix behaviour).
        assert (
            "3c7a182ee7ab498ea4454a2f8465063c" not in names
        ), f"name set still contains raw UUID: {names!r}"
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_children_endpoint_decorates_analysis_too(
    monkeypatch, tmp_path
):
    """The ``/memory/children`` endpoint shares the decoration. The
    desktop graph view loads children through this endpoint after the
    initial ``/memory/browse`` so both paths must produce the same
    label or the UI would flicker between hex and title."""
    import os as _os
    import time as _time

    _os.environ["TZ"] = "UTC"
    _time.tzset()

    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember(
            "analysis://sc-preprocessing/abc123fakeuuid",
            _seed_analysis_payload(
                status="completed",
                dataset_path="/x/pbmc3k_raw.h5ad",
                executed_at="2026-05-05T12:43:00Z",
            ),
        )

        result = await server.memory_children(
            node_uuid="", domain="analysis", path="sc-preprocessing"
        )
        children = result["children"]
        assert len(children) == 1, f"got {children!r}"
        assert "·" in children[0]["name"]
        assert "pbmc3k_raw.h5ad" in children[0]["name"]
        assert children[0]["name"].endswith(" · completed")
        assert children[0]["path"] == "sc-preprocessing/abc123fakeuuid", (
            "path must preserve the raw URI segment"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_browse_does_not_decorate_non_analysis_domains(
    monkeypatch, tmp_path
):
    """The decoration is scoped to ``analysis://*``. Other domains —
    here ``core://`` — keep their existing ``edge.name`` (URI's last
    path segment) so the fix doesn't perturb dataset / preference /
    session / core listings."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    _, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("core://my_user/note", "v1")

        result = await server.memory_browse(path="my_user", domain="core")
        children = result["children"]
        assert len(children) == 1
        assert children[0]["name"] == "note", (
            f"core domain should keep edge.name; got {children[0]['name']!r}. "
            f"Decoration must be scoped to analysis://* only."
        )
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# T2 S3 — /memory/search namespace-scoped (caller + __shared__ only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_search_endpoint_excludes_other_namespaces(
    monkeypatch, tmp_path
):
    """GET /memory/search must scope FTS hits to the desktop's namespace
    plus __shared__. Bystander namespaces' content matching the query
    must not leak — the production guarantee for multi-tenant DBs."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        bystander_client = MemoryClient(engine=engine, namespace="telegram/bob")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        # Three rows, all containing "mito" — one per namespace.
        await desktop_client.remember(
            "analysis://desktop/qc-report", "mito 18% in pbmc"
        )
        await desktop_client.remember(
            "core://agent/style", "concise replies about mito"
        )  # → __shared__
        await bystander_client.remember(
            "analysis://bob/qc", "mito 22% (bob's secret)"
        )

        result = await server.memory_search(q="mito", limit=20, domain=None)
        namespaces = {r.get("namespace") for r in result["results"]}
        contents = " ".join(
            (r.get("content_snippet") or "") for r in result["results"]
        )

        assert "app/desktop_user" in namespaces, (
            f"Desktop's own row missing from FTS: {result['results']}"
        )
        assert "telegram/bob" not in namespaces, (
            f"Bystander telegram/bob leaked into desktop FTS: {result['results']}"
        )
        assert "bob's secret" not in contents, (
            f"Bystander content leaked through search snippets: {contents!r}"
        )
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# T2 S4 — /memory/{children,domains,recent} desktop-UI mode (include_shared)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_children_endpoint_surfaces_shared_and_excludes_others(
    monkeypatch, tmp_path
):
    """GET /memory/children for the desktop client returns children in
    its own namespace AND in __shared__ (PR #137's include_shared=True
    UI mode), but never children that live only in another bot user's
    namespace.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        other_client = MemoryClient(engine=engine, namespace="telegram/bob")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        # Desktop's own write
        await desktop_client.remember("dataset://desktop_only.h5ad", "desk")
        # A shared-prefix write (lands in __shared__ via namespace_policy)
        await desktop_client.remember("core://agent/style", "concise")
        # Bystander's own write — must NOT show in desktop tree
        await other_client.remember("dataset://bob_secret.h5ad", "bob")

        children = await server.memory_children(
            node_uuid="", domain="dataset"
        )
        paths = {c["path"] for c in children["children"]}
        assert "desktop_only.h5ad" in paths, (
            f"Desktop's own dataset missing from tree: {paths}"
        )
        assert "bob_secret.h5ad" not in paths, (
            f"Bystander telegram/bob's dataset leaked into desktop tree: {paths}"
        )

        core_children = await server.memory_children(
            node_uuid="", domain="core"
        )
        core_paths = {c["path"] for c in core_children["children"]}
        assert any("agent" in p for p in core_paths), (
            f"Shared core://agent/* missing from desktop tree (include_shared "
            f"contract broken): {core_paths}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_recent_endpoint_excludes_other_namespaces(
    monkeypatch, tmp_path
):
    """GET /memory/recent for the desktop client must include the
    desktop's own writes AND __shared__ rows (the desktop-UI mode), but
    never another user's per-namespace writes."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        other_client = MemoryClient(engine=engine, namespace="telegram/bob")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("dataset://desktop_only.h5ad", "desk")
        await desktop_client.remember("core://agent/style", "concise")
        await other_client.remember("dataset://bob_secret.h5ad", "bob")

        result = await server.memory_recent(limit=20)
        uris = {r["uri"] for r in result["results"]}
        assert "dataset://desktop_only.h5ad" in uris
        assert "core://agent/style" in uris, (
            "include_shared contract: desktop /memory/recent should surface "
            f"user's __shared__ writes; got {uris}"
        )
        assert "dataset://bob_secret.h5ad" not in uris, (
            f"Bystander row leaked into desktop's /memory/recent: {uris}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_domains_endpoint_counts_user_plus_shared_only(
    monkeypatch, tmp_path
):
    """GET /memory/domains counts paths the desktop user can address —
    own namespace + __shared__ — never sibling namespaces. The legacy
    unscoped count was a privacy/correctness leak."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        other_client = MemoryClient(engine=engine, namespace="telegram/bob")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("dataset://d1.h5ad", "d1")
        await desktop_client.remember("analysis://a1/run", "a1")
        await desktop_client.remember("core://agent/style", "concise")
        # Three rows for telegram/bob — must not influence desktop's counts
        await other_client.remember("dataset://b1.h5ad", "b1")
        await other_client.remember("dataset://b2.h5ad", "b2")
        await other_client.remember("analysis://b/run", "b3")

        result = await server.memory_domains()
        domain_counts = {d["domain"]: d["node_count"] for d in result["domains"]}

        assert "dataset" in domain_counts and domain_counts["dataset"] >= 1
        assert "analysis" in domain_counts and domain_counts["analysis"] >= 1
        # Desktop has 1 dataset; bystander has 2 — total under unscoped
        # would be 3. Scoped count must show 1 (just the desktop's).
        assert domain_counts["dataset"] == 1, (
            f"Domain count leaked telegram/bob's datasets: "
            f"got {domain_counts['dataset']}, expected 1 (desktop only). "
            f"Full counts: {domain_counts}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_domains_endpoint_admin_view_aggregates_all_namespaces(
    monkeypatch, tmp_path
):
    """``/memory/domains?namespace=`` (empty value) is the admin view: it
    sums every partition's paths, including ones the current desktop
    user cannot otherwise reach. Used when an operator needs to find
    data stranded under a legacy namespace."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop = MemoryClient(engine=engine, namespace="app/desktop_user")
        legacy = MemoryClient(engine=engine, namespace="app/legacy-launch-uuid")
        monkeypatch.setattr(server, "_memory_client", desktop)

        await desktop.remember("dataset://now.h5ad", "current")
        await legacy.remember("dataset://stranded.h5ad", "stranded")
        await legacy.remember("analysis://a/run", "stranded too")

        result = await server.memory_domains(namespace="")
        counts = {d["domain"]: d["node_count"] for d in result["domains"]}

        # Both partitions visible: 2 datasets, 2 analysis paths (the
        # parent ``analysis://a`` container is auto-created alongside
        # the ``analysis://a/run`` leaf).
        assert counts["dataset"] == 2, (
            f"Admin view missed a partition's data: {counts}"
        )
        assert counts.get("analysis", 0) >= 1
        # Default-scoped (no namespace param) sees only the desktop's
        # row — assert the admin view sees strictly more.
        default = await server.memory_domains()
        default_total = default["total_nodes"]
        assert result["total_nodes"] > default_total, (
            f"Admin view {result['total_nodes']} did not exceed default "
            f"{default_total} — namespace override is not taking effect."
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_namespaces_endpoint_lists_partitions_and_current(
    monkeypatch, tmp_path,
):
    """``/memory/namespaces`` powers the admin UI dropdown: every partition
    holding at least one path is listed, and the response identifies which
    one the desktop client is currently bound to so the UI can preselect it."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop = MemoryClient(engine=engine, namespace="app/desktop_user")
        legacy = MemoryClient(engine=engine, namespace="app/old-launch-uuid")
        monkeypatch.setattr(server, "_memory_client", desktop)

        await desktop.remember("dataset://d.h5ad", "d")
        await legacy.remember("dataset://stranded.h5ad", "s")
        await desktop.remember_shared("core://agent/style", "shared")

        result = await server.memory_namespaces()
        assert "namespaces" in result
        names = result["namespaces"]
        assert "app/desktop_user" in names
        assert "app/old-launch-uuid" in names
        assert "__shared__" in names
        # Current namespace is exposed so the UI can preselect it.
        assert result["current"] == "app/desktop_user"
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_domains_endpoint_explicit_namespace_scopes_query(
    monkeypatch, tmp_path
):
    """``/memory/domains?namespace=app/foo`` lets an operator inspect a
    specific partition without spinning up that client. Returns just
    that namespace + shared, dedupe on collision."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop = MemoryClient(engine=engine, namespace="app/desktop_user")
        target = MemoryClient(engine=engine, namespace="app/target")
        monkeypatch.setattr(server, "_memory_client", desktop)

        await desktop.remember("dataset://desktop.h5ad", "d")
        await target.remember("dataset://target.h5ad", "t")
        await target.remember("dataset://shared.h5ad", "t-collision")
        await desktop.remember_shared("dataset://shared.h5ad", "shared-copy")

        result = await server.memory_domains(namespace="app/target")
        uris = {d["domain"] for d in result["domains"]}

        # target sees its own row + shared row (deduped); desktop's
        # private row is NOT visible.
        assert result["total_nodes"] == 2, (
            f"Explicit-namespace query leaked or missed: {result}"
        )
        assert "dataset" in uris
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# T2 S6 — /memory/delete is namespace-scoped (no cross-namespace blast)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_delete_endpoint_does_not_cross_namespace(monkeypatch, tmp_path):
    """DELETE /memory/delete must remove only the desktop client's row.
    Two namespaces holding the same ``(domain, path)`` URI must not be
    collapsed by the delete — that would be the PR #131-class data-loss
    pattern PR #137 closed for the legacy GraphService path.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        bystander_client = MemoryClient(engine=engine, namespace="telegram/bob")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        await desktop_client.remember("dataset://pbmc.h5ad", "desktop's pbmc")
        await bystander_client.remember("dataset://pbmc.h5ad", "bob's pbmc")

        # Act
        result = await server.memory_delete(path="pbmc.h5ad", domain="dataset")
        assert result["ok"] is True

        # Assert: desktop row gone; bystander row intact
        desktop_after = await engine.recall(
            "dataset://pbmc.h5ad",
            namespace="app/desktop_user",
            fallback_to_shared=False,
        )
        bystander_after = await engine.recall(
            "dataset://pbmc.h5ad",
            namespace="telegram/bob",
            fallback_to_shared=False,
        )
        assert desktop_after is None, (
            f"Desktop row survived its own delete: {desktop_after!r}"
        )
        assert bystander_after is not None, (
            "telegram/bob's same-URI row was deleted by desktop's "
            "/memory/delete — PR #137 cross-namespace safety broken"
        )
        assert bystander_after.content == "bob's pbmc"
    finally:
        await memory_pkg.close_db()


# ---------------------------------------------------------------------------
# T2 S5 — /memory/update writes to the desktop client's namespace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_update_endpoint_writes_to_desktop_namespace(monkeypatch, tmp_path):
    """POST /memory/update must update the row in the desktop's namespace
    (``_memory_client.namespace``), not the legacy ``__shared__``-only
    target. PR #137 fixed the GraphService shim that hardcoded
    ``Path.namespace == SHARED_NAMESPACE``; without that fix a desktop
    user's per-namespace memory was unreachable through this endpoint.
    """
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.app.server import MemoryUpdateRequest
    from omicsclaw.memory.memory_client import MemoryClient

    graph, _, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        # Bind the server's _memory_client to a non-shared namespace so we
        # can prove updates land there (not in __shared__).
        engine = memory_pkg.get_memory_engine()
        desktop_client = MemoryClient(engine=engine, namespace="app/desktop_user")
        monkeypatch.setattr(server, "_memory_client", desktop_client)

        # Seed a row at app/desktop_user — note core://test/* is NOT in
        # SHARED_PREFIXES, so MemoryClient.remember writes to the caller's
        # namespace as expected.
        await desktop_client.remember("core://test/key", "v1")

        # Act: hit the endpoint function (the public HTTP surface).
        result = await server.memory_update(
            MemoryUpdateRequest(
                path="test/key", domain="core", content="v2",
            )
        )
        assert result["ok"] is True

        # Assert: the desktop namespace row updated; nothing in __shared__.
        record = await engine.recall(
            "core://test/key",
            namespace="app/desktop_user",
            fallback_to_shared=False,
        )
        assert record is not None, "Update vaporized the desktop row"
        assert record.content == "v2", (
            f"Expected v2 in app/desktop_user, got {record.content!r}"
        )

        shared_record = await engine.recall(
            "core://test/key",
            namespace="__shared__",
            fallback_to_shared=False,
        )
        assert shared_record is None, (
            f"/memory/update leaked into __shared__: {shared_record!r}"
        )
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_clear_discards_pending_memory_create(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    graph, store, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        create_result = await graph.create_memory(
            parent_path="",
            content="draft content",
            priority=0,
            title="draft-note",
            domain="core",
        )
        store.record_many(
            before_state=create_result.get("rows_before", {}),
            after_state=create_result.get("rows_after", {}),
        )

        assert store.get_change_count() == 4
        assert await graph.get_memory_by_path("draft-note", domain="core") is not None

        cleared = await server.memory_review_clear()

        assert cleared["ok"] is True
        assert cleared["discarded"] == 4
        assert store.get_change_count() == 0
        assert await graph.get_memory_by_path("draft-note", domain="core") is None
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_clear_restores_previous_memory_content(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    graph, store, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)

    try:
        create_result = await graph.create_memory(
            parent_path="",
            content="original content",
            priority=0,
            title="persistent-note",
            domain="core",
        )
        store.record_many(
            before_state=create_result.get("rows_before", {}),
            after_state=create_result.get("rows_after", {}),
        )
        assert store.clear_all() == 4

        update_result = await graph.update_memory(
            path="persistent-note",
            content="updated by AI",
            domain="core",
        )
        store.record_many(
            before_state=update_result.get("rows_before", {}),
            after_state=update_result.get("rows_after", {}),
        )

        current = await graph.get_memory_by_path("persistent-note", domain="core")
        assert current is not None
        assert current["id"] == update_result["new_memory_id"]
        assert current["node_uuid"] == update_result["node_uuid"]
        assert current["content"] == "updated by AI"
        assert store.get_change_count() == 2

        cleared = await server.memory_review_clear()
        restored = await graph.get_memory_by_path("persistent-note", domain="core")

        assert cleared["ok"] is True
        assert cleared["discarded"] == 2
        assert store.get_change_count() == 0
        assert restored is not None
        assert restored["id"] == update_result["old_memory_id"]
        assert restored["content"] == "original content"
        assert restored["node_uuid"] == update_result["node_uuid"]
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_integrate_accepts_selected_keys(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.memory.api import review

    graph, store, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(review, "get_changeset_store", lambda: store)

    try:
        create_result = await graph.create_memory(
            parent_path="",
            content="draft content",
            priority=0,
            title="draft-note",
            domain="core",
        )
        store.record_many(
            before_state=create_result.get("rows_before", {}),
            after_state=create_result.get("rows_after", {}),
        )

        keys = sorted(store.get_all_rows_dict())
        result = await review.integrate_changes(review.IntegrateRequest(keys=[keys[0]]))

        assert result["integrated"] == [keys[0]]
        assert result["errors"] == []
        assert result["remaining"] == len(keys) - 1
        assert keys[0] not in store.get_all_rows_dict()
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_integrate_reports_missing_keys(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")

    from omicsclaw.memory.api import review

    graph, store, memory_pkg = await _setup_memory_review_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(review, "get_changeset_store", lambda: store)

    try:
        create_result = await graph.create_memory(
            parent_path="",
            content="draft content",
            priority=0,
            title="draft-note",
            domain="core",
        )
        store.record_many(
            before_state=create_result.get("rows_before", {}),
            after_state=create_result.get("rows_after", {}),
        )

        keys = sorted(store.get_all_rows_dict())
        result = await review.integrate_changes(
            review.IntegrateRequest(keys=[keys[0], "missing:key"])
        )

        assert result["integrated"] == [keys[0]]
        assert result["errors"] == [{"key": "missing:key", "error": "Not found"}]
        assert result["remaining"] == len(keys) - 1
    finally:
        await memory_pkg.close_db()


# ----------------------------------------------------------------------
# PR #5 — review routes wired to ReviewLog
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_review_rollback_uses_reviewlog(monkeypatch, tmp_path):
    """POST /memory/review/rollback now routes through ReviewLog with the
    desktop's launch-derived namespace. Older active versions roll back
    cleanly; idempotent when already active."""
    pytest.importorskip("fastapi")

    from omicsclaw.app import server
    from omicsclaw.app.server import MemoryRollbackRequest

    graph, _, memory_pkg = await _setup_memory_review_runtime(
        monkeypatch, tmp_path
    )

    try:
        # GraphService.create_memory + update_memory go to __shared__,
        # so ensure the desktop namespace is __shared__ for this test.
        monkeypatch.delenv("OMICSCLAW_DESKTOP_LAUNCH_ID", raising=False)
        monkeypatch.setattr(
            "omicsclaw.memory.desktop_namespace", lambda: "__shared__"
        )
        monkeypatch.setattr(server, "_memory_client", object())

        await graph.create_memory(
            parent_path="",
            content="v1",
            priority=0,
            title="rollback-target",
            domain="core",
        )
        update_result = await graph.update_memory(
            path="rollback-target",
            content="v2",
            domain="core",
        )

        old_id = update_result["old_memory_id"]
        new_id = update_result["new_memory_id"]
        assert old_id != new_id

        result = await server.memory_review_rollback(
            MemoryRollbackRequest(target_memory_id=old_id)
        )

        assert result["ok"] is True
        assert result["result"]["restored_memory_id"] == old_id
        assert result["result"]["was_already_active"] is False

        # Re-rolling should be a no-op.
        again = await server.memory_review_rollback(
            MemoryRollbackRequest(target_memory_id=old_id)
        )
        assert again["result"]["was_already_active"] is True
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_orphans_endpoint_returns_dataclass_dicts(
    monkeypatch, tmp_path
):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    graph, _, memory_pkg = await _setup_memory_review_runtime(
        monkeypatch, tmp_path
    )

    try:
        monkeypatch.setattr(server, "_memory_client", object())

        # No orphans yet — endpoint should return an empty list cleanly.
        result = await server.memory_review_orphans(namespace="")
        assert result["count"] == 0
        assert result["orphans"] == []
        assert result["namespace"] is None
    finally:
        await memory_pkg.close_db()


@pytest.mark.asyncio
async def test_memory_review_version_chain_endpoint_rejects_overwrite_uri(
    monkeypatch, tmp_path
):
    pytest.importorskip("fastapi")

    from omicsclaw.app import server

    _, _, memory_pkg = await _setup_memory_review_runtime(
        monkeypatch, tmp_path
    )

    try:
        monkeypatch.setattr(server, "_memory_client", object())
        monkeypatch.setattr(
            "omicsclaw.memory.desktop_namespace", lambda: "__shared__"
        )

        # ``dataset://`` is overwrite-only — endpoint should 400.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            await server.memory_review_version_chain(
                uri="dataset://x.h5ad",
                namespace=None,
            )
        assert ei.value.status_code == 400
    finally:
        await memory_pkg.close_db()

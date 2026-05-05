from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


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
    return memory_pkg.get_graph_service(), store, memory_pkg


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

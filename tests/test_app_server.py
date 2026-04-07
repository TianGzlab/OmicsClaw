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

    fake_core = SimpleNamespace(TRUSTED_DATA_DIRS=[])
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

    result = await server.set_workspace(server.WorkspaceRequest(workspace=str(workspace_dir)))

    assert result["ok"] is True
    assert result["workspace"] == str(workspace_dir)
    assert result["workspace_env"] == str(workspace_dir)
    assert os.environ["OMICSCLAW_WORKSPACE"] == str(workspace_dir)
    assert os.environ["OMICSCLAW_DATA_DIRS"] == str(workspace_dir)
    assert captured_updates == {
        "OMICSCLAW_DATA_DIRS": str(workspace_dir),
        "OMICSCLAW_WORKSPACE": str(workspace_dir),
    }
    assert fake_core.TRUSTED_DATA_DIRS == [workspace_dir]


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
    assert payload["dependencies"] == {
        "cellcharter": True,
        "squidpy": False,
    }


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

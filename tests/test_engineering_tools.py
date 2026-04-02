import asyncio
import json
from pathlib import Path

from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs
from omicsclaw.runtime.engineering_tools import (
    build_engineering_tool_executors,
    build_engineering_tool_specs,
)


def _build_executors(tmp_path: Path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    (repo_root / "examples").mkdir(parents=True, exist_ok=True)
    (repo_root / "output").mkdir(parents=True, exist_ok=True)
    return build_engineering_tool_executors(
        omicsclaw_dir=repo_root,
        state_root=tmp_path / "state",
        tool_specs_supplier=build_engineering_tool_specs,
    )


def test_build_bot_tool_specs_includes_curated_engineering_tools():
    specs = build_bot_tool_specs(
        BotToolContext(
            skill_names=("auto",),
            skill_desc_text="auto (auto route)",
        )
    )
    names = {spec.name for spec in specs}

    assert "tool_search" in names
    assert "file_read" in names
    assert "file_write" in names
    assert "file_edit" in names
    assert "glob_files" in names
    assert "grep_files" in names
    assert "task_create" in names
    assert "task_list" in names
    assert "todo_write" in names
    assert "web_fetch" in names
    assert "web_search" in names
    assert "mcp_list" in names


def test_tool_search_reports_engineering_and_existing_tools(tmp_path: Path):
    executors = _build_executors(tmp_path)

    result = asyncio.run(
        executors["tool_search"](
            {
                "query": "task planning",
                "include_schema": True,
            }
        )
    )
    payload = json.loads(result)
    tool_names = {item["name"] for item in payload["tools"]}

    assert "task_create" in tool_names
    assert "task_list" in tool_names
    assert "todo_write" in tool_names
    assert any("parameters" in item for item in payload["tools"])


def test_file_tools_follow_workspace_and_safe_surface_defaults(tmp_path: Path):
    executors = _build_executors(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    write_result = asyncio.run(
        executors["file_write"](
            {"path": "notes/plan.txt", "content": "alpha\nbeta\n"},
            surface="interactive",
            workspace=str(workspace),
        )
    )
    assert str(workspace / "notes" / "plan.txt") in write_result

    read_result = asyncio.run(
        executors["file_read"](
            {"path": "notes/plan.txt", "start_line": 2, "end_line": 2},
            surface="interactive",
            workspace=str(workspace),
        )
    )
    assert "2: beta" in read_result

    edit_result = asyncio.run(
        executors["file_edit"](
            {
                "path": "notes/plan.txt",
                "old_text": "beta",
                "new_text": "gamma",
            },
            surface="interactive",
            workspace=str(workspace),
        )
    )
    assert "replaced 1 occurrence" in edit_result
    assert (workspace / "notes" / "plan.txt").read_text(encoding="utf-8") == "alpha\ngamma\n"

    safe_default_result = asyncio.run(
        executors["file_write"](
            {"path": "remote.txt", "content": "safe"},
            surface="telegram",
        )
    )
    assert str(tmp_path / "repo" / "output" / "engineering" / "remote.txt") in safe_default_result


def test_task_tools_persist_state_for_session(tmp_path: Path):
    executors = _build_executors(tmp_path)

    create_payload = json.loads(
        asyncio.run(
            executors["task_create"](
                {
                    "title": "Draft integration plan",
                    "description": "Capture the curated tool rollout.",
                },
                session_id="interactive:user:chat-1",
                chat_id="chat-1",
                surface="interactive",
                workspace=str(tmp_path / "workspace"),
            )
        )
    )
    task_id = create_payload["task"]["id"]

    update_payload = json.loads(
        asyncio.run(
            executors["task_update"](
                {
                    "task_id": task_id,
                    "status": "in_progress",
                    "summary": "Shared runtime module drafted.",
                    "artifact_ref": "omicsclaw/runtime/engineering_tools.py",
                },
                session_id="interactive:user:chat-1",
                chat_id="chat-1",
                surface="interactive",
                workspace=str(tmp_path / "workspace"),
            )
        )
    )
    assert update_payload["task"]["status"] == "in_progress"
    assert update_payload["task"]["metadata"]["summary"] == "Shared runtime module drafted."

    list_payload = json.loads(
        asyncio.run(
            executors["task_list"](
                {"status": "in_progress"},
                session_id="interactive:user:chat-1",
                chat_id="chat-1",
                surface="interactive",
                workspace=str(tmp_path / "workspace"),
            )
        )
    )
    assert [task["id"] for task in list_payload["tasks"]] == [task_id]
    assert list_payload["metadata"]["workspace"] == str(tmp_path / "workspace")

    todo_payload = json.loads(
        asyncio.run(
            executors["todo_write"](
                {
                    "items": [
                        {"title": "Inspect registry"},
                        {"title": "Wire executors", "status": "completed"},
                    ]
                },
                session_id="interactive:user:chat-1",
                chat_id="chat-1",
                surface="interactive",
            )
        )
    )
    assert todo_payload["task_count"] == 2
    assert {task["status"] for task in todo_payload["tasks"]} == {"pending", "completed"}


def test_web_fetch_uses_shared_fetcher_and_truncates(monkeypatch, tmp_path: Path):
    executors = _build_executors(tmp_path)
    import omicsclaw.research.web_search as web_search

    async def fake_fetch(url: str, timeout: float = 10.0) -> str:
        assert url == "https://example.org"
        return "0123456789" * 10

    monkeypatch.setattr(web_search, "_fetch_webpage", fake_fetch)

    result = asyncio.run(
        executors["web_fetch"](
            {"url": "https://example.org", "max_chars": 25}
        )
    )
    assert result.startswith("URL: https://example.org")
    assert "... [truncated]" in result


def test_mcp_list_sanitizes_environment_values(monkeypatch, tmp_path: Path):
    executors = _build_executors(tmp_path)
    config_root = tmp_path / "config"
    (config_root / "omicsclaw").mkdir(parents=True, exist_ok=True)
    (config_root / "omicsclaw" / "mcp.yaml").write_text(
        "demo:\n"
        "  transport: stdio\n"
        "  command: npx\n"
        "  args:\n"
        "    - -y\n"
        "    - demo-server\n"
        "  env:\n"
        "    API_KEY: secret-value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))

    payload = json.loads(asyncio.run(executors["mcp_list"]({})))
    assert payload["servers"] == [
        {
            "name": "demo",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "demo-server"],
            "env_keys": ["API_KEY"],
        }
    ]

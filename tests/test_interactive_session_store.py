import sqlite3

import pytest

from omicsclaw.interactive import _session as session_store


@pytest.mark.asyncio
async def test_save_and_load_session_with_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    await session_store.save_session(
        "sess-1",
        [{"role": "user", "content": "hello"}],
        model="test-model",
        workspace="/tmp/workspace",
        metadata={
            "pipeline_workspace": "/tmp/pipeline",
            "tag": "test",
            "active_style": "scientific-brief",
        },
    )

    loaded = await session_store.load_session("sess-1")

    assert loaded is not None
    assert loaded["workspace"] == "/tmp/workspace"
    assert loaded["metadata"]["pipeline_workspace"] == "/tmp/pipeline"
    assert loaded["metadata"]["tag"] == "test"
    assert loaded["metadata"]["active_style"] == "scientific-brief"
    assert loaded["transcript"] == [{"role": "user", "content": "hello"}]
    assert loaded["messages"] == loaded["transcript"]

    sessions = await session_store.list_sessions(limit=10)
    assert sessions
    assert sessions[0]["metadata"]["pipeline_workspace"] == "/tmp/pipeline"
    assert sessions[0]["metadata"]["active_style"] == "scientific-brief"


@pytest.mark.asyncio
async def test_save_session_migrates_old_schema_without_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    db_path = session_store.get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL DEFAULT 'OmicsClaw',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                model TEXT,
                workspace TEXT,
                messages TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    await session_store.save_session(
        "sess-legacy",
        [{"role": "user", "content": "legacy"}],
        metadata={"pipeline_workspace": "/tmp/legacy-pipeline"},
    )

    loaded = await session_store.load_session("sess-legacy")

    assert loaded is not None
    assert loaded["metadata"]["pipeline_workspace"] == "/tmp/legacy-pipeline"

    conn = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
    finally:
        conn.close()

    assert "metadata" in columns
    assert "transcript" in columns
    assert "transcript_summary" in columns


@pytest.mark.asyncio
async def test_session_store_sanitizes_incomplete_tool_bundles_on_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    await session_store.save_session(
        "sess-tools",
        [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function"}],
            },
            {"role": "assistant", "content": "final answer"},
        ],
    )

    loaded = await session_store.load_session("sess-tools")
    sessions = await session_store.list_sessions(limit=10)

    assert loaded is not None
    assert loaded["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final answer"},
    ]
    assert sessions[0]["message_count"] == 2
    assert sessions[0]["preview"] == "hello"


@pytest.mark.asyncio
async def test_session_store_prefers_transcript_column_over_legacy_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    await session_store.save_session(
        "sess-transcript",
        [{"role": "user", "content": "fresh transcript"}],
    )

    db_path = session_store.get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET transcript = ?, messages = ? WHERE session_id = ?",
            (
                '[{"role": "user", "content": "structured transcript"}]',
                '[{"role": "user", "content": "legacy projection"}]',
                "sess-transcript",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded = await session_store.load_session("sess-transcript")
    sessions = await session_store.list_sessions(limit=10)

    assert loaded is not None
    assert loaded["transcript"] == [{"role": "user", "content": "structured transcript"}]
    assert loaded["messages"] == [{"role": "user", "content": "structured transcript"}]
    assert sessions[0]["preview"] == "structured transcript"
    assert sessions[0]["message_count"] == 1


@pytest.mark.asyncio
async def test_session_store_exposes_compacted_tool_result_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    await session_store.save_session(
        "sess-artifacts",
        [
            {"role": "user", "content": "inspect this"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function"}],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": (
                    "[tool result compacted]\n"
                    "tool: inspect_data\n"
                    "bytes: 2048\n"
                    f"full_result_path: {tmp_path / 'tool_results' / 'result.txt'}\n"
                    "preview:\n"
                    "first lines"
                ),
            },
            {"role": "assistant", "content": "done"},
        ],
    )

    loaded = await session_store.load_session("sess-artifacts")
    sessions = await session_store.list_sessions(limit=10)

    assert loaded is not None
    assert loaded["compacted_tool_results"] == [
        {
            "tool_call_id": "call-1",
            "tool_name": "inspect_data",
            "storage_path": str(tmp_path / "tool_results" / "result.txt"),
            "output_bytes": 2048,
        }
    ]
    assert sessions[0]["compacted_tool_result_count"] == 1


@pytest.mark.asyncio
async def test_session_store_exposes_plan_references_and_advisory_events(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    workspace = tmp_path / "pipeline"
    workspace.mkdir()
    (workspace / "plan.md").write_text("# plan\n", encoding="utf-8")

    await session_store.save_session(
        "sess-summary",
        [
            {"role": "user", "content": "run pipeline"},
            {"role": "assistant", "content": "💡 Advice:\nValidate QC thresholds before rerun."},
        ],
        workspace=str(workspace),
        metadata={"pipeline_workspace": str(workspace)},
    )

    loaded = await session_store.load_session("sess-summary")
    sessions = await session_store.list_sessions(limit=10)

    assert loaded is not None
    assert loaded["plan_references"] == [
        {
            "path": str((workspace / "plan.md").resolve()),
            "workspace": str(workspace.resolve()),
            "exists": True,
        }
    ]
    assert loaded["advisory_events"] == [
        {
            "message": "💡 Advice:\nValidate QC thresholds before rerun.",
            "role": "assistant",
            "index": 1,
            "kind": "advisory",
        }
    ]
    assert sessions[0]["plan_reference_count"] == 1
    assert sessions[0]["advisory_event_count"] == 1

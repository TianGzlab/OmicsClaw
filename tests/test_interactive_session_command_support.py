from pathlib import Path
from types import SimpleNamespace

import pytest

from omicsclaw.interactive._session_command_support import (
    build_clear_conversation_command_view,
    build_current_session_command_view,
    build_delete_session_command_view,
    build_export_session_command_view,
    build_new_session_command_view,
    build_resume_session_command_view,
    build_session_metadata,
    build_session_list_view,
    build_session_tag_command_view,
    build_session_title_command_view,
    enrich_session_metadata,
    format_session_list_plain,
    normalize_session_metadata,
    resolve_active_output_style,
    resolve_active_pipeline_workspace,
    SessionListEntry,
    SessionListView,
)


@pytest.mark.asyncio
async def test_build_session_list_view_uses_session_rows(monkeypatch):
    async def _list_sessions(limit: int = 20):
        assert limit == 5
        return [
            {
                "session_id": "abc12345",
                "preview": "run spatial-preprocess",
                "message_count": 3,
                "compacted_tool_result_count": 1,
                "plan_reference_count": 1,
                "advisory_event_count": 1,
                "model": "gpt-test",
                "updated_at": "2026-03-31T00:00:00+00:00",
            }
        ]

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.list_sessions",
        _list_sessions,
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.format_relative_time",
        lambda _: "2h ago",
    )

    view = await build_session_list_view(limit=5)

    assert view.entries == [
        SessionListEntry(
            session_id="abc12345",
            preview="run spatial-preprocess",
            title="run spatial-preprocess",
            workspace_kind="conversation",
            message_count=3,
            compacted_tool_result_count=1,
            plan_reference_count=1,
            advisory_event_count=1,
            model="gpt-test",
            updated_at="2026-03-31T00:00:00+00:00",
            updated_label="2h ago",
        )
    ]


def test_format_session_list_plain_renders_entries_and_hint():
    text = format_session_list_plain(
        SessionListView(
            entries=[
                SessionListEntry(
                    session_id="abc12345",
                    preview="run spatial-preprocess",
                    title="Brain Visium",
                    state_summary="research-pipeline · pipeline-operator · tag=brain",
                    message_count=3,
                    compacted_tool_result_count=1,
                    plan_reference_count=1,
                    advisory_event_count=1,
                )
            ]
        ),
        hint_text="Use /resume <id>",
    )

    assert "Recent sessions (newest first):" in text
    assert "  [abc12345]  Brain Visium  (3 msgs) · 1 compacted · 1 plan · 1 advisory" in text
    assert "     research-pipeline · pipeline-operator · tag=brain" in text
    assert "Use /resume <id>" in text


def test_build_new_session_command_view_sets_reset_flags():
    view = build_new_session_command_view("abc12345")

    assert view.output_text == "New session: abc12345"
    assert view.session_id == "abc12345"
    assert view.session_metadata == {}
    assert view.replace_session_metadata is True
    assert view.clear_messages is True
    assert view.clear_pipeline_workspace is True
    assert view.reset_session_runtime is True


def test_build_clear_conversation_command_view_sets_clear_flag():
    view = build_clear_conversation_command_view()

    assert view.output_text == "Conversation history cleared."
    assert view.clear_messages is True
    assert view.clear_pipeline_workspace is False


def test_build_export_session_command_view_exports_markdown(tmp_path):
    view = build_export_session_command_view(
        "abc12345",
        [
            {"role": "user", "content": "hello"},
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
                    "bytes: 1024\n"
                    "full_result_path: /tmp/tool_results/result.txt\n"
                    "preview:\n"
                    "first lines"
                ),
            },
            {"role": "assistant", "content": "done"},
        ],
        workspace_dir=tmp_path,
    )

    assert view.success is True
    assert view.export_path == str(tmp_path / "exports" / "omicsclaw_session_abc12345.md")
    assert Path(view.export_path).exists()
    exported = Path(view.export_path).read_text(encoding="utf-8")
    assert "## Compacted Tool Results" in exported
    assert "`/tmp/tool_results/result.txt`" in exported
    assert "Session exported to:" in view.output_text


def test_build_export_session_command_view_reports_failure(monkeypatch, tmp_path):
    def _fail(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.export_conversation_to_markdown",
        _fail,
    )

    view = build_export_session_command_view(
        "abc12345",
        [{"role": "user", "content": "hello"}],
        workspace_dir=tmp_path,
    )

    assert view.success is False
    assert view.output_text == "Export failed: disk full"


def test_normalize_session_metadata_and_resolve_pipeline_workspace():
    metadata = normalize_session_metadata(
        {
            "title": "  Brain spatial follow-up  ",
            "tag": "  visium  ",
            "pipeline_workspace": "  /tmp/pipeline  ",
            "active_style": " Scientific_Brief ",
            "active_workflow": " research-pipeline ",
            "plan_slug": " Brain Follow Up ",
            "dataset_refs": ["data/sample.h5ad", "data/sample.h5ad"],
            "enabled_extension_refs": ["lab-style", "lab-style"],
            "last_active_task_id": " review-results ",
            "workspace_kind": " analysis_run ",
            "domain": " Spatial ",
            "foo": "bar",
        }
    )

    assert metadata == {
        "title": "Brain spatial follow-up",
        "tag": "visium",
        "pipeline_workspace": "/tmp/pipeline",
        "active_pipeline_workspace": "/tmp/pipeline",
        "active_style": "scientific-brief",
        "active_workflow": "research-pipeline",
        "plan_slug": "brain-follow-up",
        "dataset_refs": ["data/sample.h5ad"],
        "enabled_extension_refs": ["lab-style"],
        "last_active_task_id": "review-results",
        "workspace_kind": "analysis_run",
        "domain": "spatial",
        "foo": "bar",
    }
    assert build_session_metadata(metadata, pipeline_workspace=None) == {
        "title": "Brain spatial follow-up",
        "tag": "visium",
        "active_style": "scientific-brief",
        "active_workflow": "research-pipeline",
        "plan_slug": "brain-follow-up",
        "dataset_refs": ["data/sample.h5ad"],
        "enabled_extension_refs": ["lab-style"],
        "last_active_task_id": "review-results",
        "workspace_kind": "analysis_run",
        "domain": "spatial",
        "foo": "bar",
    }
    assert resolve_active_pipeline_workspace("", metadata) == "/tmp/pipeline"
    assert resolve_active_output_style(metadata) == "scientific-brief"


def test_session_title_and_tag_command_views_update_metadata():
    title_view = build_session_title_command_view(
        "Brain Visium rerun",
        session_metadata={"tag": "visium"},
    )
    tag_view = build_session_tag_command_view(
        "priority",
        session_metadata=title_view.session_metadata,
    )

    assert title_view.success is True
    assert title_view.replace_session_metadata is True
    assert title_view.session_metadata["title"] == "Brain Visium rerun"
    assert tag_view.session_metadata["tag"] == "priority"


def test_enrich_session_metadata_derives_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.resolve_pipeline_workspace",
        lambda _arg, workspace: Path(workspace),
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.load_pipeline_workspace_snapshot",
        lambda workspace: SimpleNamespace(
            has_pipeline_state=True,
            workspace=Path(workspace),
            current_stage="review",
        ),
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.list_installed_extensions",
        lambda _root: [
            SimpleNamespace(
                state=SimpleNamespace(enabled=True),
                record=SimpleNamespace(extension_name="lab-style"),
                path=tmp_path / "lab-style",
            )
        ],
    )

    metadata = enrich_session_metadata(
        {"pipeline_workspace": str(tmp_path / "pipeline"), "active_style": "teaching"},
        messages=[{"role": "user", "content": "Analyze data/sample.h5ad in spatial mode"}],
        workspace_dir=str(tmp_path / "workspace"),
        omicsclaw_dir=str(tmp_path),
    )

    assert metadata["active_pipeline_workspace"] == str(tmp_path / "pipeline")
    assert metadata["active_workflow"] == "research-pipeline"
    assert metadata["last_active_task_id"] == "review"
    assert metadata["workspace_kind"] == "analysis_run"
    assert metadata["dataset_refs"] == ["data/sample.h5ad"]
    assert metadata["enabled_extension_refs"] == ["lab-style"]
    assert metadata["domain"] == "spatial"


@pytest.mark.asyncio
async def test_build_resume_session_command_view_loads_and_formats_history(monkeypatch):
    async def _load_session(target_id: str):
        assert target_id == "abc12345"
        return {
            "session_id": "abc12345",
            "workspace": "/tmp/workspace",
            "metadata": {
                "title": "Spatial transcript follow-up",
                "tag": "visium",
                "pipeline_workspace": " /tmp/pipeline ",
                "active_style": " scientific-brief ",
                "interactive_plan": {
                    "request": "Analyze data carefully",
                    "plan_kind": "generic_analysis",
                    "status": "approved",
                    "active_task_id": "execute-analysis",
                    "task_store": {
                        "kind": "interactive_plan",
                        "metadata": {},
                        "tasks": [
                            {
                                "id": "execute-analysis",
                                "title": "Execute analysis",
                                "description": "Run the workflow",
                                "status": "in_progress",
                            }
                        ],
                    },
                },
            },
            "transcript": [
                {"role": "user", "content": "run spatial-transcript-first"},
                {"role": "assistant", "content": "💡 Advice:\nworking from transcript"},
            ],
            "transcript_summary": {
                "compacted_tool_results": [
                    {
                        "tool_call_id": "call-1",
                        "tool_name": "inspect_data",
                        "storage_path": "/tmp/tool_results/result.txt",
                        "output_bytes": 1024,
                    }
                ],
                "plan_references": [
                    {
                        "path": "/tmp/pipeline/plan.md",
                        "workspace": "/tmp/pipeline",
                        "exists": True,
                    }
                ],
                "advisory_events": [
                    {
                        "message": "💡 Advice:\nworking from transcript",
                        "role": "assistant",
                        "index": 1,
                        "kind": "advisory",
                    }
                ],
            },
            "messages": [
                {"role": "user", "content": "legacy projection should be ignored"},
            ],
        }

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.load_session",
        _load_session,
    )

    view = await build_resume_session_command_view("abc12345")

    assert view.success is True
    assert view.render_as_markup is True
    assert view.session_id == "abc12345"
    assert view.workspace_dir == "/tmp/workspace"
    assert view.session_metadata["pipeline_workspace"] == "/tmp/pipeline"
    assert view.session_metadata["active_style"] == "scientific-brief"
    assert view.session_metadata["title"] == "Spatial transcript follow-up"
    assert view.session_metadata["tag"] == "visium"
    assert "interactive_plan" in view.session_metadata
    assert view.replace_session_metadata is True
    assert view.replace_messages is True
    assert "Resumed session:" in view.output_text
    assert "Title:" in view.output_text
    assert "Tag:" in view.output_text
    assert "Pipeline Workspace:" in view.output_text
    assert "Style:" in view.output_text
    assert "Workspace Kind:" in view.output_text
    assert "Interactive Plan:" in view.output_text
    assert "Interactive Task:" in view.output_text
    assert "Compacted Results:" in view.output_text
    assert "Plan References:" in view.output_text
    assert "Advisory Events:" in view.output_text
    assert "Conversation history" in view.output_text
    assert "run spatial-transcript-first" in view.output_text
    assert "legacy projection should be ignored" not in view.output_text


@pytest.mark.asyncio
async def test_build_resume_session_command_view_reports_missing_session(monkeypatch):
    async def _load_session(target_id: str):
        assert target_id == "missing"
        return None

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.load_session",
        _load_session,
    )

    view = await build_resume_session_command_view("missing")

    assert view.success is False
    assert view.output_text == "Session 'missing' not found."


def test_build_current_session_command_view_includes_pipeline_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.resolve_pipeline_workspace",
        lambda _arg, workspace: Path(workspace),
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.load_pipeline_workspace_snapshot",
        lambda workspace: SimpleNamespace(
            has_pipeline_state=True,
            workspace=workspace,
            current_stage="review",
        ),
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.build_pipeline_display_from_snapshot",
        lambda snapshot: SimpleNamespace(
            current_stage="review",
            plan=SimpleNamespace(status="pending_approval"),
        ),
    )

    view = build_current_session_command_view(
        session_id="abc12345",
        workspace_dir=str(tmp_path),
        model="gpt-test",
        provider="openai",
        messages=[
            {"role": "user", "content": "hello"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": (
                    "[tool result compacted]\n"
                    "tool: inspect_data\n"
                    "bytes: 1024\n"
                    "full_result_path: /tmp/tool_results/result.txt\n"
                    "preview:\n"
                    "first lines"
                ),
            },
            {"role": "assistant", "content": "💡 Advice:\nworld"},
        ],
        session_metadata={
            "title": "Pipeline review",
            "tag": "priority",
            "pipeline_workspace": str(tmp_path / "pipeline"),
            "active_style": "pipeline-operator",
        },
    )

    assert view.render_as_markup is True
    assert "Session:" in view.output_text
    assert "Title:" in view.output_text
    assert "Tag:" in view.output_text
    assert "Pipeline Workspace:" in view.output_text
    assert "Style:" in view.output_text
    assert "Workflow:" in view.output_text
    assert "Messages:[/dim]  2" in view.output_text
    assert "Compacted:[/dim] 1 tool result artifact(s)" in view.output_text
    assert "Plan Refs:[/dim] 1 linked plan artifact(s)" in view.output_text
    assert "Advisories:[/dim] 1 recorded hint(s)" in view.output_text
    assert "Pipeline Stage:[/dim] [cyan]review[/cyan]" in view.output_text
    assert "Plan Status:[/dim] [cyan]pending_approval[/cyan]" in view.output_text


def test_build_current_session_command_view_includes_interactive_plan_summary():
    view = build_current_session_command_view(
        session_id="sess-2",
        workspace_dir="/tmp/workspace",
        model="gpt-test",
        provider="openai",
        messages=[{"role": "user", "content": "hello"}],
        session_metadata={
            "interactive_plan": {
                "request": "Analyze sample.h5ad",
                "plan_kind": "generic_analysis",
                "status": "pending_approval",
                "active_task_id": "define-objective",
                "task_store": {
                    "kind": "interactive_plan",
                    "metadata": {},
                    "tasks": [
                        {
                            "id": "define-objective",
                            "title": "Define objective",
                            "description": "Scope the work",
                            "status": "pending",
                        }
                    ],
                },
            }
        },
    )

    assert "Interactive Plan:" in view.output_text
    assert "Interactive Task:" in view.output_text


@pytest.mark.asyncio
async def test_build_session_list_view_filters_by_metadata_query(monkeypatch):
    async def _list_sessions(limit: int = 20):
        assert limit == 0
        return [
            {
                "session_id": "visium1",
                "preview": "run spatial-preprocess",
                "workspace": "/tmp/w1",
                "metadata": {
                    "title": "Brain Visium",
                    "tag": "visium",
                    "domain": "spatial",
                    "pipeline_workspace": "/tmp/pipeline1",
                    "active_style": "scientific-brief",
                    "last_active_task_id": "review",
                },
            },
            {
                "session_id": "scrna1",
                "preview": "run sc-qc",
                "workspace": "/tmp/w2",
                "metadata": {
                    "title": "PBMC QC",
                    "tag": "singlecell",
                    "domain": "singlecell",
                },
            },
        ]

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.list_sessions",
        _list_sessions,
    )

    view = await build_session_list_view(limit=5, query="tag:visium domain:spatial")

    assert [entry.session_id for entry in view.entries] == ["visium1"]
    assert view.query == "tag:visium domain:spatial"


@pytest.mark.asyncio
async def test_build_delete_session_command_view_rejects_current_session():
    view = await build_delete_session_command_view(
        "abc12345",
        current_session_id="abc12345",
    )

    assert view.success is False
    assert view.output_text == "Cannot delete the current active session."


@pytest.mark.asyncio
async def test_build_delete_session_command_view_deletes_loaded_session(monkeypatch):
    async def _load_session(target_id: str):
        assert target_id == "abc"
        return {"session_id": "abc12345"}

    async def _delete_session(session_id: str):
        assert session_id == "abc12345"
        return True

    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.load_session",
        _load_session,
    )
    monkeypatch.setattr(
        "omicsclaw.interactive._session_command_support.delete_session",
        _delete_session,
    )

    view = await build_delete_session_command_view(
        "abc",
        current_session_id="current",
    )

    assert view.success is True
    assert view.output_text == "Deleted session abc12345."

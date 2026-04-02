from pathlib import Path

import pytest

from omicsclaw.agents.plan_state import PLAN_STATE_METADATA_KEY
from omicsclaw.agents.pipeline_result import normalize_pipeline_result
from omicsclaw.agents.pipeline import PipelineState
from omicsclaw.interactive._pipeline_support import (
    approve_pipeline_plan,
    build_approve_plan_command_view,
    build_resume_research_command,
    build_resume_task_command,
    build_pipeline_display_from_result,
    build_pipeline_display_from_snapshot,
    build_pipeline_tasks_command_view,
    build_plan_preview_command_view,
    build_research_history_messages,
    format_pipeline_tasks,
    format_plan_preview,
    format_research_result_summary,
    format_research_start_summary,
    load_pipeline_workspace_snapshot,
    parse_approve_plan_command,
    parse_research_command,
    parse_resume_task_command,
    ResearchCommandArgs,
    resolve_pipeline_workspace,
    resolve_research_workspace,
)

_VALID_PLAN_MD = """# Research Context & Scope

Scoped objective.

## Data Acquisition Strategy

Use local data.

## Analysis Stages

### Stage 1
- Goal: preprocess data
- OmicsClaw skill(s): spatial-preprocessing
- Parameters: min_genes=20, max_mt_pct=25
- Success signals: QC metrics are acceptable
- Expected artifacts: qc.csv, qc.png
- Fallback: use MAD-based thresholds if needed

## Dependencies

- scanpy

## Iteration Triggers

- Repeat if QC fails

## Evaluation Protocol

- Compare baseline and control outputs
"""


def test_parse_research_command_supports_stage_controls():
    command = parse_research_command(
        'paper.pdf --idea "test idea" --h5ad data.h5ad '
        '--from-stage analyze --skip research,review --output ./workspace --plan-only'
    )

    assert command.pdf_path == "paper.pdf"
    assert command.idea == "test idea"
    assert command.h5ad_path == "data.h5ad"
    assert command.from_stage == "analyze"
    assert command.skip_stages == ["research", "review"]
    assert command.output_dir == "./workspace"
    assert command.plan_only is True


def test_parse_resume_task_command_sets_from_stage():
    command = parse_resume_task_command(
        'write paper.pdf --idea "retry write" --workspace ./workspace'
    )

    assert command.from_stage == "write"
    assert command.pdf_path == "paper.pdf"
    assert command.idea == "retry write"
    assert command.output_dir == "./workspace"


def test_parse_approve_plan_command_supports_notes_and_approver():
    command = parse_approve_plan_command(
        './workspace --notes "looks good" --by reviewer'
    )

    assert command.workspace == "./workspace"
    assert command.notes == "looks good"
    assert command.approver == "reviewer"


def test_resolve_research_workspace_reuses_pipeline_workspace(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="idea-only")
    state.checkpoint(tmp_path)

    assert resolve_research_workspace(None, str(tmp_path)) == tmp_path.resolve()


def test_resolve_pipeline_workspace_prefers_nested_research_workspace(tmp_path):
    nested = tmp_path / "research_workspace"
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.checkpoint(nested)

    resolved = resolve_pipeline_workspace(None, str(tmp_path))

    assert resolved == nested.resolve()


def test_pipeline_workspace_snapshot_and_renderers(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared", artifact_ref="paper/02_methodology.md")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")

    snapshot = load_pipeline_workspace_snapshot(tmp_path)
    tasks_view = format_pipeline_tasks(snapshot)
    plan_view = format_plan_preview(snapshot)

    assert snapshot.has_pipeline_state
    assert "Current stage: plan" in tasks_view
    assert "summary: drafting plan" in tasks_view
    assert "paper/02_methodology.md" in tasks_view
    assert "Plan file:" in plan_view
    assert "# Plan" in plan_view


def test_build_pipeline_display_from_snapshot_exposes_unified_status(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_completed("plan", summary="Generated plan", artifact_ref=str(tmp_path / "plan.md"))
    state.task_store.metadata[PLAN_STATE_METADATA_KEY] = {"status": "pending_approval"}
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")
    state.checkpoint(tmp_path)

    snapshot = load_pipeline_workspace_snapshot(tmp_path)
    view = build_pipeline_display_from_snapshot(snapshot)

    assert view.workspace == str(tmp_path)
    assert view.mode == "A"
    assert view.paper_flag == "yes"
    assert view.current_stage == "plan"
    assert view.plan.status == "pending_approval"
    assert view.plan.validation_valid is True
    assert view.plan.validation_stage_count == 1
    assert view.plan.next_action == "review plan.md, then run /approve-plan"


def test_build_pipeline_display_from_result_matches_plan_runtime_shape(tmp_path):
    result = normalize_pipeline_result(
        {
            "success": True,
            "workspace": str(tmp_path),
            "intake": {"mode": "A"},
            "completed_stages": ["intake", "plan"],
            "review_iterations": 1,
            "warnings": ["final report missing"],
            "plan": {
                "status": "pending_approval",
                "awaiting_approval": True,
                "validation": {
                    "available": True,
                    "valid": False,
                    "errors": ["Missing required section: dependencies."],
                    "warnings": ["No fallback strategy detected for failed stages."],
                    "detected_sections": ["analysis_stages"],
                    "stage_count": 1,
                },
            },
        }
    )

    view = build_pipeline_display_from_result(result)

    assert view.workspace == str(tmp_path)
    assert view.mode == "A"
    assert view.paper_flag == "yes"
    assert view.current_stage == "plan"
    assert view.review_iterations == 1
    assert view.plan.status == "pending_approval"
    assert view.plan.awaiting_approval is True
    assert view.plan.validation_valid is False
    assert view.plan.validation_errors == ["Missing required section: dependencies."]
    assert view.plan.validation_warnings == ["No fallback strategy detected for failed stages."]
    assert view.plan.validation_stage_count == 1
    assert view.plan.next_action == "review plan.md, then run /approve-plan"
    assert view.warnings == ["final report missing"]


def test_research_command_helpers_render_resume_commands(tmp_path):
    workspace = tmp_path / "research_workspace"

    assert build_resume_task_command(workspace) == (
        f"/resume-task research --output {workspace.resolve()}"
    )
    assert build_resume_research_command(workspace, idea="retry write-up") == (
        f"/research --resume --output {workspace.resolve()} --idea 'retry write-up'"
    )


def test_format_research_start_summary_reuses_snapshot_view(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.task_store.metadata[PLAN_STATE_METADATA_KEY] = {"status": "pending_approval"}
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")
    state.checkpoint(tmp_path)
    snapshot = load_pipeline_workspace_snapshot(tmp_path)

    summary = format_research_start_summary(
        ResearchCommandArgs(
            pdf_path="paper.pdf",
            idea="test idea",
            output_dir=str(tmp_path),
            plan_only=True,
        ),
        tmp_path,
        snapshot,
        mode="A",
    )

    assert "Starting Research Pipeline in Plan-Only Mode" in summary
    assert f"Workspace:[/dim] {tmp_path.resolve()}" in summary
    assert "Completed:[/dim] intake" in summary
    assert "Current:[/dim]   plan" in summary
    assert "Plan:[/dim]      pending_approval" in summary


def test_format_research_result_summary_renders_pending_approval_actions(tmp_path):
    summary = format_research_result_summary(
        normalize_pipeline_result(
            {
                "success": True,
                "workspace": str(tmp_path),
                "plan": {
                    "status": "pending_approval",
                    "awaiting_approval": True,
                    "validation": {
                        "available": True,
                        "valid": False,
                        "errors": ["Missing required section: dependencies."],
                        "warnings": ["No fallback strategy detected for failed stages."],
                        "detected_sections": ["analysis_stages"],
                        "stage_count": 1,
                    },
                },
            }
        ),
        workspace_fallback=tmp_path,
        idea="test idea",
    )

    assert "Plan generated and awaiting approval" in summary
    assert "Plan Status:[/dim] pending_approval" in summary
    assert "Approve:[/dim]   /approve-plan" in summary
    assert (
        f"Continue:[/dim]  /resume-task research --output {tmp_path.resolve()}"
        in summary
    )


def test_build_research_history_messages_capture_pending_approval_context(tmp_path):
    messages = build_research_history_messages(
        ResearchCommandArgs(
            pdf_path="paper.pdf",
            idea="test idea",
            output_dir=str(tmp_path),
            plan_only=True,
        ),
        normalize_pipeline_result(
            {
                "success": True,
                "workspace": str(tmp_path),
                "plan": {
                    "status": "pending_approval",
                    "awaiting_approval": True,
                    "validation": {
                        "available": True,
                        "valid": True,
                        "errors": [],
                        "warnings": [],
                        "detected_sections": ["analysis_stages"],
                        "stage_count": 1,
                    },
                },
            }
        ),
        mode="A",
        workspace_fallback=tmp_path,
    )

    assert messages[0]["role"] == "user"
    assert "[Research pipeline Mode A]" in messages[0]["content"]
    assert "Idea: test idea" in messages[0]["content"]
    assert "PDF: paper.pdf" in messages[0]["content"]
    assert "plan_only: true" in messages[0]["content"]
    assert f"workspace: {tmp_path}" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert "Research pipeline awaiting approval." in messages[1]["content"]
    assert "Plan status: pending_approval" in messages[1]["content"]


def test_build_research_history_messages_capture_failure_context(tmp_path):
    messages = build_research_history_messages(
        ResearchCommandArgs(
            idea="retry analysis",
            output_dir=str(tmp_path),
            resume=True,
            skip_stages=["review"],
        ),
        normalize_pipeline_result(
            {
                "success": False,
                "workspace": str(tmp_path),
                "completed_stages": ["intake", "plan"],
                "plan": {
                    "status": "approved",
                    "awaiting_approval": False,
                    "validation": {
                        "available": True,
                        "valid": True,
                        "errors": [],
                        "warnings": [],
                        "detected_sections": ["analysis_stages"],
                        "stage_count": 1,
                    },
                },
                "error": "tool failed",
            }
        ),
        mode="C",
        workspace_fallback=tmp_path,
    )

    assert "resume: true" in messages[0]["content"]
    assert "skip: review" in messages[0]["content"]
    assert "Research pipeline failed." in messages[1]["content"]
    assert "Workspace: " in messages[1]["content"]
    assert "Plan status: approved" in messages[1]["content"]
    assert "Error: tool failed" in messages[1]["content"]


def test_pipeline_workspace_snapshot_revalidates_when_plan_changes_after_checkpoint(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text("# Plan\n", encoding="utf-8")

    snapshot = load_pipeline_workspace_snapshot(tmp_path)
    validation = snapshot.plan_validation()

    assert validation.valid is False
    assert "Missing required section: data acquisition strategy." in validation.errors


def test_approve_pipeline_plan_updates_task_store_metadata(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")

    snapshot = approve_pipeline_plan(
        tmp_path,
        approver="reviewer",
        notes="Proceed to execution",
    )

    assert snapshot.plan_status == "approved"
    assert snapshot.plan_approved_by == "reviewer"
    assert snapshot.plan_approval_notes == "Proceed to execution"
    assert snapshot.state.is_stage_done("plan")
    assert str(snapshot.plan_path) in snapshot.task_store.require("plan").artifact_refs
    assert snapshot.task_store.metadata[PLAN_STATE_METADATA_KEY]["status"] == "approved"


def test_format_pipeline_tasks_shows_next_action_for_pending_approval(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_completed("plan", summary="Generated plan", artifact_ref=str(tmp_path / "plan.md"))
    state.task_store.metadata[PLAN_STATE_METADATA_KEY] = {"status": "pending_approval"}
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")

    snapshot = load_pipeline_workspace_snapshot(tmp_path)

    assert "Next action: review plan.md, then run /approve-plan" in format_pipeline_tasks(snapshot)


def test_build_pipeline_tasks_command_view_exposes_active_workspace(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.checkpoint(tmp_path)

    view = build_pipeline_tasks_command_view(
        None,
        workspace_fallback=tmp_path,
    )

    assert view.active_workspace == str(tmp_path.resolve())
    assert "Pipeline workspace:" in view.output_text
    assert "Current stage:" in view.output_text


def test_build_plan_preview_command_view_exposes_active_workspace(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")

    view = build_plan_preview_command_view(
        None,
        workspace_fallback=tmp_path,
    )

    assert view.active_workspace == str(tmp_path.resolve())
    assert "Plan file:" in view.output_text
    assert "Plan validation: passed" in view.output_text


def test_build_approve_plan_command_view_sets_persist_and_continue_command(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text(_VALID_PLAN_MD, encoding="utf-8")

    view = build_approve_plan_command_view(
        "",
        workspace_fallback=tmp_path,
    )

    assert view.persist_session is True
    assert view.active_workspace == str(tmp_path.resolve())
    assert f"Plan approved for: {tmp_path.resolve()}" in view.output_text
    assert (
        f"Continue with: /resume-task research --output {tmp_path.resolve()}"
        in view.output_text
    )


def test_approve_pipeline_plan_rejects_invalid_plan(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.checkpoint(tmp_path)
    (tmp_path / "plan.md").write_text("# Plan\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Plan validation failed"):
        approve_pipeline_plan(tmp_path)


def test_format_plan_preview_handles_missing_workspace(tmp_path):
    missing = tmp_path / "missing"
    snapshot = load_pipeline_workspace_snapshot(Path(missing))

    assert "Workspace does not exist." in format_plan_preview(snapshot)

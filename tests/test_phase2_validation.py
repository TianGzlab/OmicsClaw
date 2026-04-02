import json
from pathlib import Path

from omicsclaw.agents.intake import IntakeResult
from omicsclaw.agents.plan_state import PLAN_STATE_METADATA_KEY
from omicsclaw.agents.pipeline import (
    PIPELINE_TASK_STORE_FILENAME,
    PipelineState,
    _generate_todos,
)


def test_pipeline_state_basic_operations():
    state = PipelineState()

    state.mark_stage_completed("intake", summary="prepared")

    assert state.is_stage_done("intake")
    assert not state.is_stage_done("plan")
    assert not state.should_stop_review()

    state.review_iterations = 3
    assert state.should_stop_review()


def test_checkpoint_roundtrip_preserves_task_store(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="paper.md", artifact_ref="paper.md")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    state.review_iterations = 1
    state.checkpoint(tmp_path)

    loaded = PipelineState.load_checkpoint(tmp_path)

    assert loaded is not None
    assert loaded.completed_stages == ["intake"]
    assert loaded.current_stage == "plan"
    assert loaded.review_iterations == 1
    assert loaded.task_store.require("intake").artifact_refs == ["paper.md"]
    assert loaded.task_store.require("plan").status == "in_progress"


def test_checkpoint_persists_plan_validation_metadata(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="paper.md", artifact_ref="paper.md")
    state.mark_stage_in_progress("plan", summary="drafting plan")
    (tmp_path / "plan.md").write_text(
        """# Research Context & Scope

Test scope.

## Data Acquisition Strategy

Use the available dataset.

## Analysis Stages

### Stage 1
- Goal: establish a baseline
- OmicsClaw skill(s): spatial-preprocessing
- Parameters: min_genes=20, max_mt_pct=25
- Success signals: QC metrics are stable
- Expected artifacts: qc_report.csv, qc_plot.png
- Fallback: use data-driven thresholds if the first pass fails

## Dependencies

- scanpy

## Iteration Triggers

- Revisit parameters if QC fails

## Evaluation Protocol

- Compare against baseline and control metrics
""",
        encoding="utf-8",
    )

    state.checkpoint(tmp_path)
    loaded = PipelineState.load_checkpoint(tmp_path)

    assert loaded is not None
    validation = loaded.task_store.metadata[PLAN_STATE_METADATA_KEY]["validation"]
    assert validation["valid"] is True
    assert validation["stage_count"] == 1
    assert validation["path"] == str((tmp_path / "plan.md").resolve())
    assert validation["sha256"]


def test_checkpoint_clears_stale_plan_validation_metadata_when_plan_is_removed(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    (tmp_path / "plan.md").write_text(
        "# Research Context & Scope\n\nok\n\n## Data Acquisition Strategy\n\nok\n\n## Analysis Stages\n\n### Stage 1\n- Goal: a\n- OmicsClaw skill(s): b\n- Parameters: min_genes=1\n- Success signals: c\n- Expected artifacts: d\n- Fallback: e\n\n## Dependencies\n\n- x\n\n## Iteration Triggers\n\n- y\n\n## Evaluation Protocol\n\n- baseline\n",
        encoding="utf-8",
    )
    state.checkpoint(tmp_path)

    (tmp_path / "plan.md").unlink()
    state.checkpoint(tmp_path)
    loaded = PipelineState.load_checkpoint(tmp_path)

    assert loaded is not None
    assert PLAN_STATE_METADATA_KEY not in loaded.task_store.metadata


def test_generate_todos_projects_task_store(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="A", has_pdf=True)
    state.mark_stage_completed("intake", summary="Prepared intake context")

    store = _generate_todos(
        tmp_path,
        mode="A",
        has_pdf=True,
        task_store=state.task_store,
    )

    todos = tmp_path / "todos.md"
    store_path = tmp_path / PIPELINE_TASK_STORE_FILENAME

    assert todos.exists()
    assert store_path.exists()
    content = todos.read_text(encoding="utf-8")
    assert "Intake" in content
    assert "Plan" in content
    assert "in progress" not in content


def test_load_checkpoint_converts_legacy_checkpoint(tmp_path):
    legacy_checkpoint = {
        "current_stage": "plan",
        "completed_stages": ["intake"],
        "stage_outputs": {"intake": "paper.md", "plan": "drafting"},
        "review_iterations": 2,
    }
    (tmp_path / ".pipeline_checkpoint.json").write_text(
        json.dumps(legacy_checkpoint),
        encoding="utf-8",
    )

    loaded = PipelineState.load_checkpoint(tmp_path)

    assert loaded is not None
    assert loaded.completed_stages == ["intake"]
    assert loaded.current_stage == "plan"
    assert loaded.task_store.require("intake").status == "completed"
    assert loaded.task_store.require("plan").status == "in_progress"
    assert loaded.review_iterations == 2


def test_load_checkpoint_recovers_from_task_store_only(tmp_path):
    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="idea-only")
    state.task_store.save(tmp_path / PIPELINE_TASK_STORE_FILENAME)

    loaded = PipelineState.load_checkpoint(tmp_path)

    assert loaded is not None
    assert loaded.completed_stages == ["intake"]
    assert loaded.task_store.metadata["mode"] == "C"


def test_intake_from_workspace_mode_a(tmp_path):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "01_abstract_conclusion.md").write_text(
        "# My Paper Title\nAbstract content...",
        encoding="utf-8",
    )
    (paper_dir / "02_methodology.md").write_text(
        "Methods section...",
        encoding="utf-8",
    )

    result = IntakeResult.from_workspace(str(tmp_path), idea="test idea")

    assert result.input_mode == "A"
    assert result.paper_title == "My Paper Title"
    assert "methodology" in result.paper_md_path.lower()


def test_intake_from_workspace_mode_c(tmp_path):
    result = IntakeResult.from_workspace(str(tmp_path), idea="pure idea")

    assert result.input_mode == "C"
    assert result.paper_title == ""


def test_load_checkpoint_with_corrupted_file_returns_none(tmp_path):
    (tmp_path / ".pipeline_checkpoint.json").write_text(
        "not valid json!",
        encoding="utf-8",
    )

    assert PipelineState.load_checkpoint(tmp_path) is None


def test_load_checkpoint_with_no_files_returns_none(tmp_path):
    assert PipelineState.load_checkpoint(Path(tmp_path)) is None

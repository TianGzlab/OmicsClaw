from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.agents.plan_state import PLAN_STATE_METADATA_KEY
from omicsclaw.agents.pipeline import (
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
    PipelineState,
    ResearchPipeline,
)


_VALID_PLAN_MD = """# Research Context & Scope

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
"""


class _PlanOnlyAgent:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def astream_events(self, *_args, **_kwargs):
        yield {
            "event": "on_tool_start",
            "name": "task",
            "data": {
                "input": {
                    "subagent": "planner-agent",
                    "task_description": "Draft the experiment plan",
                }
            },
        }
        plan_path = self.workspace / "plan.md"
        yield {
            "event": "on_tool_start",
            "name": "write_file",
            "data": {"input": {"file_path": str(plan_path)}},
        }
        plan_path.write_text(_VALID_PLAN_MD, encoding="utf-8")
        yield {
            "event": "on_tool_end",
            "name": "write_file",
            "data": {"output": "ok"},
        }


class _NoOpAgent:
    async def astream_events(self, *_args, **_kwargs):
        if False:
            yield {}


@pytest.mark.asyncio
async def test_pipeline_plan_only_stops_after_plan_and_requires_approval(tmp_path, monkeypatch):
    pipeline = ResearchPipeline(workspace_dir=str(tmp_path))
    monkeypatch.setattr(pipeline, "_build_agent", lambda: _PlanOnlyAgent(tmp_path))

    result = await pipeline.run(
        idea="test plan-only gate",
        plan_only=True,
    )

    assert result["success"] is True
    assert result["awaiting_plan_approval"] is True
    assert result["plan_status"] == PLAN_STATUS_PENDING_APPROVAL
    assert result["plan"]["status"] == PLAN_STATUS_PENDING_APPROVAL
    assert result["plan"]["awaiting_approval"] is True
    assert result["plan"]["validation"]["valid"] is True
    assert result["warnings"] == []
    assert Path(result["manifest_path"]).exists()
    assert Path(result["completion_report_path"]).exists()
    assert result["completion"]["status"] == "awaiting_approval"
    assert result["completion"]["completed"] is False
    assert (tmp_path / "plan.md").exists()
    assert pipeline.state.is_stage_done("plan")
    assert (
        pipeline.state.task_store.metadata[PLAN_STATE_METADATA_KEY]["status"]
        == PLAN_STATUS_PENDING_APPROVAL
    )


@pytest.mark.asyncio
async def test_pipeline_resume_blocks_when_plan_not_approved(tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(_VALID_PLAN_MD, encoding="utf-8")

    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_completed("plan", summary="Generated plan.md", artifact_ref=str(plan_path))
    state.task_store.metadata[PLAN_STATE_METADATA_KEY] = {
        "status": PLAN_STATUS_PENDING_APPROVAL
    }
    state.checkpoint(tmp_path)

    pipeline = ResearchPipeline(workspace_dir=str(tmp_path))
    result = await pipeline.run(
        idea="resume after plan",
        resume=True,
    )

    assert result["success"] is False
    assert "Plan approval required" in result["error"]


@pytest.mark.asyncio
async def test_pipeline_resume_after_approval_is_allowed(tmp_path, monkeypatch):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(_VALID_PLAN_MD, encoding="utf-8")

    state = PipelineState()
    state.configure_pipeline(mode="C", has_pdf=False)
    state.mark_stage_completed("intake", summary="prepared")
    state.mark_stage_completed("plan", summary="Approved plan", artifact_ref=str(plan_path))
    state.task_store.metadata[PLAN_STATE_METADATA_KEY] = {
        "status": PLAN_STATUS_APPROVED
    }
    state.checkpoint(tmp_path)

    pipeline = ResearchPipeline(workspace_dir=str(tmp_path))
    monkeypatch.setattr(pipeline, "_build_agent", lambda: _NoOpAgent())

    result = await pipeline.run(
        idea="resume after approval",
        resume=True,
    )

    assert result["success"] is True
    assert result["awaiting_plan_approval"] is False
    assert result["plan_status"] == PLAN_STATUS_APPROVED
    assert result["plan"]["status"] == PLAN_STATUS_APPROVED
    assert result["plan"]["awaiting_approval"] is False
    assert Path(result["manifest_path"]).exists()
    assert Path(result["completion_report_path"]).exists()
    assert result["completion"]["status"] == "incomplete"
    assert result["completion"]["completed"] is False

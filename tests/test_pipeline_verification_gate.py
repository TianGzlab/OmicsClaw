from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.agents.pipeline import ResearchPipeline


_VALID_PLAN_MD = """# Research Context & Scope

Test scope.

## Data Acquisition Strategy

Use local data.

## Analysis Stages

### Stage 1
- Goal: preprocess data
- OmicsClaw skill(s): spatial-preprocessing
- Parameters: min_genes=20, max_mt_pct=25
- Success signals: QC metrics are stable
- Expected artifacts: qc.csv, qc.png
- Fallback: use robust defaults if needed

## Dependencies

- scanpy

## Iteration Triggers

- Repeat if QC fails

## Evaluation Protocol

- Compare baseline and control outputs
"""


class _CompleteRunAgent:
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

        (self.workspace / "analysis.ipynb").write_text("{}", encoding="utf-8")
        (self.workspace / "final_report.md").write_text("# Final Report\n", encoding="utf-8")
        (self.workspace / "review_report.json").write_text(
            json.dumps(
                {
                    "overall_assessment": "accept",
                    "score": 9,
                    "strengths": ["complete artifact set"],
                    "weaknesses": [],
                    "critical_issues": [],
                    "minor_issues": [],
                    "citation_check": [],
                    "artifact_checks": [],
                    "reproducibility_score": 9,
                    "revision_required": False,
                }
            ),
            encoding="utf-8",
        )
        (self.workspace / "artifacts").mkdir(parents=True, exist_ok=True)


@pytest.mark.asyncio
async def test_pipeline_completion_gate_marks_complete_when_artifacts_exist(tmp_path, monkeypatch):
    pipeline = ResearchPipeline(workspace_dir=str(tmp_path))
    monkeypatch.setattr(pipeline, "_build_agent", lambda: _CompleteRunAgent(tmp_path))

    result = await pipeline.run(idea="run the full pipeline")

    assert result["success"] is True
    assert Path(result["manifest_path"]).exists()
    assert Path(result["completion_report_path"]).exists()
    assert result["completion"]["status"] == "complete"
    assert result["completion"]["completed"] is True
    assert result["completion"]["missing_required_artifacts"] == []

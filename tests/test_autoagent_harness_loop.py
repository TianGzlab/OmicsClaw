"""Tests for omicsclaw.autoagent.harness_loop.

Uses mocked LLM calls and skill execution to verify the loop logic
without running real bioinformatics pipelines.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest

from omicsclaw.autoagent.edit_surface import EditSurface
from omicsclaw.autoagent.evaluator import EvaluationResult, Evaluator
from omicsclaw.autoagent.harness_loop import HarnessLoop, HarnessResult
from omicsclaw.autoagent.metrics_registry import MetricDef
from omicsclaw.autoagent.runner import TrialExecution
from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_surface(tmp_path: Path) -> EditSurface:
    """Create a test surface with a simple editable file."""
    skill_dir = tmp_path / "project" / "skills" / "test"
    skill_dir.mkdir(parents=True)
    (skill_dir / "test.py").write_text(
        "def filter_cells(adata, min_genes=200):\n"
        "    return adata[adata.obs['n_genes'] >= min_genes]\n"
    )
    (skill_dir / "SKILL.md").write_text("# Test Skill\nmin_genes: 200\n")
    return EditSurface(
        max_level=2,
        project_root=tmp_path / "project",
        explicit_files=[
            "skills/test/test.py",
            "skills/test/SKILL.md",
        ],
    )


def _make_search_space() -> SearchSpace:
    return SearchSpace(
        skill_name="test-skill",
        method="scanpy",
        tunable=[
            ParameterDef(
                name="min_genes", param_type="int",
                default=200, low=50, high=1000,
                cli_flag="--min-genes",
            ),
        ],
        fixed={},
    )


def _make_evaluator() -> Evaluator:
    metrics = {
        "quality": MetricDef(
            source="result.json:summary.quality",
            direction="maximize",
            weight=1.0,
        ),
    }
    return Evaluator(metrics, skill_name="test-skill")


def _make_trial_execution(
    output_dir: Path,
    success: bool = True,
    score: float = 0.5,
) -> TrialExecution:
    """Create a fake TrialExecution with result.json on disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if success:
        result = {
            "skill": "test-skill",
            "summary": {"quality": score, "n_cells": 100, "n_genes": 50},
            "data": {"effective_params": {"min_genes": 200}},
        }
        (output_dir / "result.json").write_text(json.dumps(result))
    return TrialExecution(
        success=success,
        output_dir=str(output_dir),
        duration_seconds=5.0,
        exit_code=0 if success else 1,
        stderr="" if success else "Error occurred",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHarnessLoopBaseline:
    """Tests for baseline execution."""

    def test_baseline_crash_stops(self, tmp_path):
        """If baseline crashes, loop stops immediately."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=5,
        )

        # Mock execute_trial to crash
        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            return _make_trial_execution(Path(od), success=False)

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ):
            result = loop.run()

        assert not result.success
        assert "Baseline crashed" in result.error_message

    def test_baseline_nonfinite_score_stops(self, tmp_path):
        """If baseline has no readable metrics, loop stops."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
        )

        # Mock execute_trial to succeed but produce no metrics
        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            od = Path(od)
            od.mkdir(parents=True, exist_ok=True)
            # result.json without the expected metric
            (od / "result.json").write_text(json.dumps({
                "summary": {"unrelated": 42},
            }))
            return TrialExecution(
                success=True, output_dir=str(od),
                duration_seconds=1.0, exit_code=0,
            )

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ):
            result = loop.run()

        assert not result.success
        assert "metrics" in result.error_message.lower()


class TestHarnessLoopEvolution:
    """Tests for the evolution iterations."""

    def test_trials_run_in_isolated_worktree(self, tmp_path):
        """Patched trials execute in a sandbox while the source tree stays clean."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=1,
            auto_promote=True,
        )

        source_file = tmp_path / "project" / "skills" / "test" / "test.py"
        observed = {"sandbox_checked": False}
        call_count = [0]

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_trial_execution(Path(od), success=True, score=0.5)

            sandbox_root = Path(kwargs["project_root"])
            sandbox_file = sandbox_root / "skills" / "test" / "test.py"
            assert sandbox_root != surface.project_root
            assert "min_genes=200" in source_file.read_text()
            assert "min_genes=300" in sandbox_file.read_text()
            observed["sandbox_checked"] = True
            return _make_trial_execution(Path(od), success=True, score=0.8)

        llm_response = json.dumps({
            "patch_plan": {
                "target_files": ["skills/test/test.py"],
                "description": "Improve threshold",
            },
            "diffs": [{
                "file": "skills/test/test.py",
                "hunks": [{
                    "old_code": "min_genes=200",
                    "new_code": "min_genes=300",
                }],
            }],
            "reasoning": "Higher threshold for better filtering.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=llm_response):
            result = loop.run()

        assert result.success
        assert observed["sandbox_checked"] is True
        assert "min_genes=300" in source_file.read_text()
        assert result.promotion["status"] == "applied"

    def test_accepts_improving_patch(self, tmp_path):
        """A patch that improves quality is accepted."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=2,
            auto_promote=True,
        )

        call_count = [0]

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            call_count[0] += 1
            # Baseline score=0.5, patched score=0.8
            score = 0.5 if call_count[0] == 1 else 0.8
            return _make_trial_execution(Path(od), success=True, score=score)

        # LLM returns a valid patch
        llm_response = json.dumps({
            "patch_plan": {
                "target_files": ["skills/test/test.py"],
                "description": "Improve threshold",
            },
            "diffs": [{
                "file": "skills/test/test.py",
                "hunks": [{
                    "old_code": "min_genes=200",
                    "new_code": "min_genes=300",
                }],
            }],
            "reasoning": "Higher threshold for better filtering.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=llm_response):
            result = loop.run()

        assert result.success
        assert result.patches_accepted >= 1
        assert result.improvement_pct > 0
        assert result.accepted_patches
        accepted = result.accepted_patches[0]
        assert accepted.commit_hash
        assert Path(accepted.artifact_path).exists()
        assert Path(accepted.manifest_path).exists()
        assert result.best_trial.code_state["commit_hash"] == accepted.commit_hash
        summary = json.loads((output_root / "harness_summary.json").read_text())
        assert summary["accepted_patch_commits"] == [accepted.commit_hash]
        assert summary["promotion"]["status"] == "applied"

    def test_reverts_failing_patch(self, tmp_path):
        """A patch that crashes is reverted and recorded in failure bank."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=2,
        )

        call_count = [0]

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_trial_execution(Path(od), success=True, score=0.5)
            # Patched version crashes
            return _make_trial_execution(Path(od), success=False)

        llm_response = json.dumps({
            "patch_plan": {"target_files": ["skills/test/test.py"]},
            "diffs": [{
                "file": "skills/test/test.py",
                "hunks": [{
                    "old_code": "min_genes=200",
                    "new_code": "min_genes=-1",
                }],
            }],
            "reasoning": "Try negative threshold.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=llm_response):
            result = loop.run()

        assert result.patches_rejected >= 1
        # File should be reverted
        content = (
            tmp_path / "project" / "skills" / "test" / "test.py"
        ).read_text()
        assert "min_genes=200" in content

        # Failure recorded
        assert len(loop.failure_bank) >= 1

    def test_convergence_signal(self, tmp_path):
        """LLM can signal convergence to stop the loop."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=5,
        )

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            return _make_trial_execution(Path(od), success=True, score=0.5)

        converge_response = json.dumps({
            "converged": True,
            "reasoning": "No further improvements possible.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(
            loop, "_call_llm", return_value=converge_response,
        ):
            result = loop.run()

        assert result.success
        assert result.converged

    def test_validation_failure_recorded(self, tmp_path):
        """Invalid patches emit terminal discard events instead of hanging."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=2,
        )

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            return _make_trial_execution(Path(od), success=True, score=0.5)

        # Patch targets a file outside the surface
        bad_patch = json.dumps({
            "patch_plan": {"target_files": ["omicsclaw/runtime/tool_executor.py"]},
            "diffs": [{
                "file": "omicsclaw/runtime/tool_executor.py",
                "hunks": [{"old_code": "x", "new_code": "y"}],
            }],
            "reasoning": "Try to modify frozen file.",
        })
        events: list[tuple[str, dict[str, object]]] = []

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=bad_patch):
            result = loop.run(
                on_event=lambda event_type, data: events.append((event_type, data))
            )

        assert result.patches_rejected >= 1
        assert len(loop.failure_bank) >= 1
        assert len(loop.ledger.all_trials()) == 3

        rejected_complete = [
            data
            for event_type, data in events
            if event_type == "trial_complete" and int(data["trial_id"]) > 0
        ]
        assert len(rejected_complete) == 2
        assert all(data["status"] == "discard" for data in rejected_complete)
        assert all(data["stage"] == "validation" for data in rejected_complete)
        assert all("cannot be edited" in str(data["error"]) for data in rejected_complete)

        rejected_judgment = [
            data
            for event_type, data in events
            if event_type == "trial_judgment" and int(data["trial_id"]) > 0
        ]
        assert len(rejected_judgment) == 2
        assert all(data["decision"] == "discard" for data in rejected_judgment)
        assert all(data["stage"] == "validation" for data in rejected_judgment)

    def test_validation_failure_limit_returns_error(self, tmp_path):
        """Three consecutive validation failures terminate the run as an error."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=3,
        )

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            return _make_trial_execution(Path(od), success=True, score=0.5)

        bad_patch = json.dumps({
            "patch_plan": {"target_files": ["skills/not-real/file.py"]},
            "diffs": [{
                "file": "skills/not-real/file.py",
                "hunks": [{"old_code": "x", "new_code": "y"}],
            }],
            "reasoning": "Target a path that does not exist.",
        })

        events: list[tuple[str, dict[str, object]]] = []

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=bad_patch):
            result = loop.run(
                on_event=lambda event_type, data: events.append((event_type, data))
            )

        assert result.success is False
        assert result.error_message == "3 consecutive patch validation failures."
        assert len(loop.ledger.all_trials()) == 4
        assert [event_type for event_type, _data in events].count("error") == 1

    def test_harness_summary_written(self, tmp_path):
        """harness_summary.json is written to output_root."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=1,
        )

        converge = json.dumps({"converged": True, "reasoning": "done"})

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            return _make_trial_execution(Path(od), success=True, score=0.5)

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=converge):
            result = loop.run()

        summary_path = output_root / "harness_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["success"] is True
        assert summary["skill"] == "test-skill"

    def test_emits_frontend_compatible_progress_and_trial_ids(self, tmp_path):
        """Harness SSE payloads include the legacy optimize UI fields."""
        surface = _make_surface(tmp_path)
        output_root = tmp_path / "output"

        loop = HarnessLoop(
            skill_name="test-skill",
            method="scanpy",
            input_path="",
            output_root=output_root,
            surface=surface,
            evaluator=_make_evaluator(),
            search_space=_make_search_space(),
            demo=True,
            max_iterations=2,
        )

        call_count = [0]

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            call_count[0] += 1
            score = 0.5 if call_count[0] == 1 else 0.8
            return _make_trial_execution(Path(od), success=True, score=score)

        llm_response = json.dumps({
            "patch_plan": {
                "target_files": ["skills/test/test.py"],
                "description": "Improve threshold",
            },
            "diffs": [{
                "file": "skills/test/test.py",
                "hunks": [{
                    "old_code": "min_genes=200",
                    "new_code": "min_genes=300",
                }],
            }],
            "reasoning": "Higher threshold for better filtering.",
        })

        events: list[tuple[str, dict[str, object]]] = []

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=llm_response):
            result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

        assert result.success

        progress_events = [data for event_type, data in events if event_type == "progress"]
        assert [int(data["completed"]) for data in progress_events[:3]] == [0, 1, 1]
        assert [int(data["total"]) for data in progress_events[:3]] == [2, 2, 2]

        trial_start = next(data for event_type, data in events if event_type == "trial_start")
        assert trial_start["trial_id"] == 1
        assert trial_start["iteration"] == 1

        trial_complete_events = [data for event_type, data in events if event_type == "trial_complete"]
        assert trial_complete_events[0]["trial_id"] == 0
        assert trial_complete_events[1]["trial_id"] == 1

        trial_judgment = next(data for event_type, data in events if event_type == "trial_judgment")
        assert trial_judgment["trial_id"] == 1

        done_event = next(data for event_type, data in events if event_type == "done")
        assert int(done_event["total_trials"]) >= 1
        assert done_event["best_trial"]["trial_id"] == 1

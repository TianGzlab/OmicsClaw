"""Integration tests for the harness evolution MVP.

Verifies the full chain: run_harness_evolution → HarnessLoop →
surface/trace/gates/patch/failure_memory with mocked LLM + runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch as mock_patch

import pytest

from omicsclaw.autoagent import run_harness_evolution
from omicsclaw.autoagent.edit_surface import build_sc_preprocessing_surface
from omicsclaw.autoagent.evaluator import Evaluator
from omicsclaw.autoagent.harness_loop import HarnessLoop, HarnessResult
from omicsclaw.autoagent.metrics_registry import (
    SC_PREPROCESSING_METRICS,
    get_metrics_for_skill,
    register_metrics,
)
from omicsclaw.autoagent.runner import TrialExecution
from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace
from omicsclaw.autoagent.trace import clear_result_json_cache


# ---------------------------------------------------------------------------
# Metric registration tests
# ---------------------------------------------------------------------------


class TestPreprocessingMetrics:
    def test_metrics_registered(self):
        metrics = get_metrics_for_skill("sc-preprocessing")
        assert metrics is not None
        assert "cell_retention" in metrics
        assert "n_hvgs" in metrics
        assert "n_genes_after" in metrics

    def test_metric_directions(self):
        metrics = get_metrics_for_skill("sc-preprocessing")
        for name, m in metrics.items():
            assert m.direction == "maximize"
            assert m.weight > 0


# ---------------------------------------------------------------------------
# MVP surface tests
# ---------------------------------------------------------------------------


class TestMVPSurface:
    def test_build_for_real_project(self):
        """Verify the MVP surface matches real project structure."""
        project_root = Path(__file__).resolve().parents[1]
        surface = build_sc_preprocessing_surface(project_root)

        # All three MVP files should be on the explicit list
        assert "skills/singlecell/scrna/sc-preprocessing/SKILL.md" in surface.explicit_files
        assert "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py" in surface.explicit_files
        assert "skills/singlecell/_lib/qc.py" in surface.explicit_files

        # These files should exist on disk
        for f in surface.explicit_files:
            assert surface.file_exists(f), f"Expected {f} to exist"

    def test_read_real_qc_py(self):
        """Verify we can read the real qc.py and it has the expected code."""
        project_root = Path(__file__).resolve().parents[1]
        surface = build_sc_preprocessing_surface(project_root)

        content = surface.read_file("skills/singlecell/_lib/qc.py")
        # The plan's key observation: qc.py has both fixed and MAD filtering
        assert "apply_threshold_filtering" in content
        assert "batch_mad_outlier_detection" in content

    def test_read_real_sc_preprocess(self):
        """Verify sc_preprocess.py uses fixed thresholds (the problem to fix)."""
        project_root = Path(__file__).resolve().parents[1]
        surface = build_sc_preprocessing_surface(project_root)

        content = surface.read_file(
            "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py"
        )
        # The structural tension: fixed defaults despite MAD being available
        assert "min_genes" in content
        assert "200" in content  # default fixed threshold


# ---------------------------------------------------------------------------
# Harness loop integration with mock LLM
# ---------------------------------------------------------------------------


def _make_result_json(output_dir: Path, score_data: dict) -> None:
    """Write a result.json (and dummy processed.h5ad) with given metrics."""
    result = {
        "skill": "sc-preprocessing",
        "summary": score_data,
        "data": {
            "effective_params": {
                "method": "scanpy",
                "min_genes": 200,
            },
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(json.dumps(result))
    # Hard gate requires processed.h5ad for adata-producing skills
    (output_dir / "processed.h5ad").write_bytes(b"")


class TestHarnessLoopIntegration:
    """End-to-end test of the harness loop with mocked execution."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        clear_result_json_cache()
        yield
        clear_result_json_cache()

    def _setup_loop(self, tmp_path: Path) -> HarnessLoop:
        """Build a HarnessLoop with a test surface."""
        # Create test editable files
        proj = tmp_path / "project"
        skill_dir = proj / "skills" / "singlecell" / "scrna" / "sc-preprocessing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# SC Preprocessing\nmin_genes: 200")
        (skill_dir / "sc_preprocess.py").write_text(
            "def main():\n"
            "    min_genes = 200  # fixed threshold\n"
            "    pass\n"
        )

        lib_dir = proj / "skills" / "singlecell" / "_lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "qc.py").write_text(
            "def apply_threshold_filtering(adata, min_genes=200):\n"
            "    return adata\n\n"
            "def batch_mad_outlier_detection(adata):\n"
            "    return adata\n"
        )

        from omicsclaw.autoagent.edit_surface import EditSurface

        surface = EditSurface(
            max_level=2,
            project_root=proj,
            explicit_files=[
                "skills/singlecell/scrna/sc-preprocessing/SKILL.md",
                "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
                "skills/singlecell/_lib/qc.py",
            ],
        )

        metrics = get_metrics_for_skill("sc-preprocessing")
        evaluator = Evaluator(metrics, skill_name="sc-preprocessing", method="scanpy")
        search_space = SearchSpace(
            skill_name="sc-preprocessing",
            method="scanpy",
            tunable=[
                ParameterDef(
                    name="min_genes", param_type="int",
                    default=200, low=50, high=1000,
                    cli_flag="--min-genes",
                ),
            ],
        )

        return HarnessLoop(
            skill_name="sc-preprocessing",
            method="scanpy",
            input_path="",
            output_root=tmp_path / "output",
            surface=surface,
            evaluator=evaluator,
            search_space=search_space,
            max_iterations=3,
            evolution_goal=(
                "Upgrade QC from fixed thresholds to data-driven MAD-based "
                "adaptive filtering strategy."
            ),
            auto_promote=True,
            demo=True,
        )

    def test_full_evolution_cycle(self, tmp_path):
        """Test: baseline → LLM patch → accept → summary written."""
        loop = self._setup_loop(tmp_path)
        call_count = [0]

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            od = Path(od)
            call_count[0] += 1
            if call_count[0] == 1:
                # Baseline
                _make_result_json(od, {
                    "n_hvg": 2000,
                    "n_genes": 18000,
                    "n_cells_before_filter": 5000,
                    "n_genes_before_filter": 20000,
                    "cells_retained_pct": 85.0,
                    "n_cells": 4250,
                })
            else:
                # Improved after patch
                _make_result_json(od, {
                    "n_hvg": 2200,
                    "n_genes": 19000,
                    "n_cells_before_filter": 5000,
                    "n_genes_before_filter": 20000,
                    "cells_retained_pct": 92.0,
                    "n_cells": 4600,
                })
            return TrialExecution(
                success=True, output_dir=str(od),
                duration_seconds=5.0, exit_code=0,
            )

        # LLM returns a patch that adds MAD strategy option
        llm_patch = json.dumps({
            "patch_plan": {
                "target_files": [
                    "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
                ],
                "description": "Add MAD-based filtering strategy option",
                "expected_improvements": [
                    "Better cell retention through data-driven thresholds",
                ],
                "rollback_conditions": [
                    "Cell retention drops below 5%",
                ],
            },
            "diffs": [{
                "file": "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
                "hunks": [{
                    "old_code": "    min_genes = 200  # fixed threshold",
                    "new_code": "    min_genes = 200  # data-driven threshold via MAD",
                }],
            }],
            "reasoning": (
                "The planner requires data-driven QC, but the skill uses "
                "fixed thresholds. Adding MAD-based strategy."
            ),
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=llm_patch):
            result = loop.run()

        # Verify result
        assert result.success
        assert result.patches_accepted >= 1
        assert result.improvement_pct > 0

        # Verify summary file
        summary_path = tmp_path / "output" / "harness_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["success"] is True
        assert summary["patches_accepted"] >= 1
        assert summary["evolution_goal"].startswith("Upgrade QC")
        assert summary["accepted_patch_commits"]
        assert summary["accepted_patch_artifacts"]
        assert summary["promotion"]["status"] == "applied"

        # Verify traces were saved
        traces = list((tmp_path / "output").glob("trial_*/run_trace.json"))
        assert len(traces) >= 1

    def test_failure_memory_accumulates(self, tmp_path):
        """Test: failed patches are recorded in failure_bank.jsonl."""
        loop = self._setup_loop(tmp_path)

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            od = Path(od)
            _make_result_json(od, {
                "n_hvg": 2000,
                "n_genes": 18000,
                "n_cells_before_filter": 5000,
                "n_genes_before_filter": 20000,
                "cells_retained_pct": 85.0,
            })
            return TrialExecution(
                success=True, output_dir=str(od),
                duration_seconds=5.0, exit_code=0,
            )

        # LLM returns an invalid patch (targets wrong file)
        bad_patch = json.dumps({
            "patch_plan": {"target_files": ["nonexistent.py"]},
            "diffs": [{
                "file": "nonexistent.py",
                "hunks": [{"old_code": "x", "new_code": "y"}],
            }],
            "reasoning": "Bad patch targeting wrong file.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=bad_patch):
            result = loop.run()

        # Failure bank should have entries
        bank_path = tmp_path / "output" / "failure_bank.jsonl"
        assert bank_path.exists()
        failures = [
            json.loads(line)
            for line in bank_path.read_text().strip().splitlines()
        ]
        assert len(failures) >= 1
        assert "validation" in failures[0].get("gate_failures", [])

    def test_events_emitted(self, tmp_path):
        """Test: events are emitted during the loop."""
        loop = self._setup_loop(tmp_path)
        events: list[tuple[str, dict]] = []

        def capture_event(event_type, data):
            events.append((event_type, data))

        def mock_execute(*args, **kwargs):
            od = kwargs.get("output_dir") or args[2]
            od = Path(od)
            _make_result_json(od, {
                "n_hvg": 2000,
                "n_genes": 18000,
                "n_cells_before_filter": 5000,
                "n_genes_before_filter": 20000,
                "cells_retained_pct": 85.0,
            })
            return TrialExecution(
                success=True, output_dir=str(od),
                duration_seconds=5.0, exit_code=0,
            )

        converge = json.dumps({
            "converged": True,
            "reasoning": "Looks good already.",
        })

        with mock_patch(
            "omicsclaw.autoagent.harness_loop.execute_trial", mock_execute,
        ), mock_patch.object(loop, "_call_llm", return_value=converge):
            loop.run(on_event=capture_event)

        event_types = [e[0] for e in events]
        assert "progress" in event_types
        assert "trial_complete" in event_types
        assert "done" in event_types


class TestHarnessEvolutionEntryPoint:
    def test_spatial_domains_uses_explicit_surface(self, monkeypatch, tmp_path):
        captured: dict[str, object] = {}

        fake_registry = MagicMock()
        fake_registry.skills = {
            "spatial-domains": {
                "param_hints": {
                    "cellcharter": {
                        "params": ["n_domains", "auto_k", "n_layers"],
                        "defaults": {
                            "n_domains": 7,
                            "auto_k": False,
                            "n_layers": 3,
                        },
                    }
                }
            }
        }
        fake_registry.load_all = lambda: None

        class FakeLoop:
            def __init__(self, *args, **kwargs):
                captured["surface"] = kwargs["surface"]
                captured["output_root"] = kwargs["output_root"]

            def run(self, on_event=None):
                return HarnessResult(
                    success=True,
                    total_iterations=1,
                )

        monkeypatch.setattr(
            "omicsclaw.autoagent.metrics_registry.get_metrics_for_skill",
            lambda *_args, **_kwargs: SC_PREPROCESSING_METRICS,
        )
        monkeypatch.setattr("omicsclaw.core.registry.registry", fake_registry)
        monkeypatch.setattr("omicsclaw.autoagent.harness_loop.HarnessLoop", FakeLoop)

        result = run_harness_evolution(
            skill_name="spatial-domains",
            method="cellcharter",
            cwd=str(tmp_path),
        )

        assert result["success"] is True
        surface = captured["surface"]
        assert surface.explicit_files == [
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "skills/spatial/_lib/domains.py",
        ]

    def test_rejects_explicit_files_that_escape_project_root(self):
        fake_registry = MagicMock()
        fake_registry.skills = {
            "test-skill": {
                "param_hints": {
                    "scanpy": {
                        "params": [],
                        "defaults": {},
                        "tips": [],
                    }
                }
            }
        }

        with mock_patch(
            "omicsclaw.autoagent.metrics_registry.get_metrics_for_skill",
            return_value={},
        ), mock_patch(
            "omicsclaw.core.registry.registry",
            fake_registry,
        ):
            result = run_harness_evolution(
                skill_name="test-skill",
                method="scanpy",
                explicit_files=["../outside.py"],
            )

        assert result["success"] is False
        assert "escapes project root" in result["error"]

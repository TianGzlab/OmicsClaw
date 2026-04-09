"""Tests for omicsclaw.autoagent.harness_directive."""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.autoagent.edit_surface import EditSurface
from omicsclaw.autoagent.hard_gates import GateResult, HardGateVerdict
from omicsclaw.autoagent.harness_directive import build_harness_directive
from omicsclaw.autoagent.trace import (
    DataShapeTrace,
    ExecutionTrace,
    MethodTrace,
    ParameterTrace,
    RunTrace,
)


@pytest.fixture
def surface_with_files(tmp_path):
    """Create a surface with real files on disk."""
    skill_dir = tmp_path / "skills" / "singlecell" / "scrna" / "sc-preprocessing"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# SC Preprocessing\nparam_hints: ...")
    (skill_dir / "sc_preprocess.py").write_text("def main():\n    pass\n")

    lib_dir = tmp_path / "skills" / "singlecell" / "_lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "qc.py").write_text("def apply_threshold_filtering():\n    pass\n")

    return EditSurface(
        max_level=2,
        project_root=tmp_path,
        explicit_files=[
            "skills/singlecell/scrna/sc-preprocessing/SKILL.md",
            "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
            "skills/singlecell/_lib/qc.py",
        ],
    )


@pytest.fixture
def sample_trace():
    return RunTrace(
        trial_id=0,
        skill_name="sc-preprocessing",
        method="scanpy",
        execution=ExecutionTrace(exit_code=0, duration_seconds=25.0),
        data_shape=DataShapeTrace(
            n_obs_before=5000,
            n_obs_after=4500,
            cell_retention_rate=0.9,
            embedding_keys=["X_pca"],
        ),
        parameters=ParameterTrace(
            skill_defaults={"min_genes": 200, "max_mt_pct": 20.0},
            effective_params={"min_genes": 200, "max_mt_pct": 20.0},
        ),
    )


@pytest.fixture
def spatial_domains_surface(tmp_path):
    skill_dir = tmp_path / "skills" / "spatial" / "spatial-domains"
    skill_dir.mkdir(parents=True)
    lib_dir = tmp_path / "skills" / "spatial" / "_lib"
    lib_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """### STAGATE
STAGATE docs.

### CellCharter
CellCharter docs.
oc run spatial-domains --method cellcharter
""",
        encoding="utf-8",
    )
    (skill_dir / "spatial_domains.py").write_text(
        """def main():
    parser.add_argument("--method")
    # CellCharter params
    parser.add_argument("--auto-k")
    param_tips = {
        "stagate": "gpu",
        "cellcharter": "auto_k",
    }
    if args.method == "cellcharter":
        current_params["auto_k"] = args.auto_k
    summary = dispatch_method(args.method, adata)
""",
        encoding="utf-8",
    )
    (lib_dir / "domains.py").write_text(
        """def identify_domains_stagate(adata):
    marker = "stagate"
    return marker


def identify_domains_cellcharter(adata):
    marker = "cellcharter"
    return marker


def _cluster_fixed_k():
    return "fixed"


def _cluster_auto_k():
    return "auto"


def dispatch_method(method, adata):
    return method
""",
        encoding="utf-8",
    )

    return EditSurface(
        max_level=2,
        project_root=tmp_path,
        explicit_files=[
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "skills/spatial/_lib/domains.py",
        ],
        prompt_views={
            "skills/spatial/spatial-domains/SKILL.md": "### CellCharter\nCellCharter docs.",
            "skills/spatial/spatial-domains/spatial_domains.py": (
                "if args.method == \"cellcharter\":\n"
                "    current_params[\"auto_k\"] = args.auto_k\n"
                "summary = dispatch_method(args.method, adata)"
            ),
            "skills/spatial/_lib/domains.py": (
                "def identify_domains_cellcharter(adata):\n"
                "    marker = \"cellcharter\"\n"
                "    return marker\n\n"
                "def _cluster_fixed_k():\n"
                "    return \"fixed\"\n\n"
                "def _cluster_auto_k():\n"
                "    return \"auto\"\n\n"
                "def dispatch_method(method, adata):\n"
                "    return method"
            ),
        },
        metadata={
            "method_focus": {
                "method": "cellcharter",
                "focus_targets": {
                    "skills/spatial/_lib/domains.py": [
                        "identify_domains_cellcharter",
                        "_cluster_fixed_k",
                        "_cluster_auto_k",
                        "dispatch_method",
                    ],
                },
            }
        },
    )


class TestBuildHarnessDirective:
    def test_basic_structure(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
        )
        # All required sections present
        assert "## Role" in directive
        assert "## Editable Surface" in directive
        assert "## Current Source Code" in directive
        assert "## Trial Diagnostics" in directive
        assert "## Constraints" in directive
        assert "## Output Format" in directive
        assert "## Budget" in directive

    def test_includes_source_code(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
        )
        assert "def main():" in directive
        assert "def apply_threshold_filtering():" in directive
        assert "# SC Preprocessing" in directive

    def test_includes_trace_diagnostics(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
        )
        assert "5000 cells" in directive
        assert "4500 cells" in directive
        assert "retention=90.0%" in directive

    def test_no_traces(self, surface_with_files):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[],
        )
        assert "No trials have been run yet" in directive

    def test_with_hard_gates(self, surface_with_files, sample_trace):
        verdict = HardGateVerdict(
            all_passed=False,
            results=[
                GateResult("no_crash", True, "OK"),
                GateResult("cell_retention", False, "Collapsed to 1%"),
            ],
        )
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
            gate_verdict=verdict,
        )
        assert "## Hard Gate Results" in directive
        assert "FAIL" in directive
        assert "cell_retention" in directive

    def test_with_failure_history(self, surface_with_files, sample_trace):
        failures = [
            {
                "reasoning": "Tried to use batch_mad for all datasets",
                "gate_failures": ["cell_retention"],
                "error_summary": "Retention dropped to 2%",
            }
        ]
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
            failure_history=failures,
        )
        assert "## Failure History" in directive
        assert "batch_mad" in directive
        assert "Do NOT repeat" in directive

    def test_custom_evolution_goal(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
            evolution_goal="Upgrade QC from fixed thresholds to MAD-based filtering.",
        )
        assert "MAD-based" in directive

    def test_budget_section(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
            iteration=3,
            max_iterations=10,
        )
        assert "Iteration: 3 / 10" in directive
        assert "Remaining: 7" in directive

    def test_output_format_includes_patch_schema(
        self, surface_with_files, sample_trace,
    ):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
        )
        assert "patch_plan" in directive
        assert "diffs" in directive
        assert "old_code" in directive
        assert "new_code" in directive
        assert "converged" in directive

    def test_preserves_frozen_warning(self, surface_with_files, sample_trace):
        directive = build_harness_directive(
            skill_name="sc-preprocessing",
            method="scanpy",
            surface=surface_with_files,
            traces=[sample_trace],
        )
        assert "frozen" in directive.lower()

    def test_multiple_traces_shown(self, surface_with_files):
        traces = [
            RunTrace(trial_id=i, skill_name="test", method="scanpy",
                     execution=ExecutionTrace(exit_code=0, duration_seconds=i * 10.0))
            for i in range(5)
        ]
        directive = build_harness_directive(
            skill_name="test",
            method="scanpy",
            surface=surface_with_files,
            traces=traces,
        )
        # Should show at most 3 recent traces
        assert "Trial #4" in directive
        assert "Trial #3" in directive
        assert "Trial #2" in directive

    def test_method_focused_excerpt_hides_unrelated_algorithms(
        self,
        spatial_domains_surface,
    ):
        directive = build_harness_directive(
            skill_name="spatial-domains",
            method="cellcharter",
            surface=spatial_domains_surface,
            traces=[],
        )
        assert "## Method Scope" in directive
        assert "identify_domains_cellcharter" in directive
        assert "identify_domains_stagate" not in directive
        assert "Method-focused excerpt" in directive

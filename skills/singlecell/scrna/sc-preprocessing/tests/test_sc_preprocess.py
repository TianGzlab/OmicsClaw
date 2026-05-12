"""Tests for the sc-preprocessing skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_preprocess.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_preprocess_out"


def test_demo_mode(tmp_output):
    """sc-preprocessing --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "preprocess_summary.csv").exists()
    assert (tmp_output / "tables" / "qc_metrics_per_cell.csv").exists()
    assert (tmp_output / "tables" / "pca_embedding.csv").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert not (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()
    assert (tmp_output / "reproducibility" / "requirements.txt").exists()
    assert not (tmp_output / "reproducibility" / "environment.txt").exists()


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Preprocessing" in report or "preprocessing" in report
    assert "Default Gallery" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-preprocessing"
    assert "summary" in data
    assert data["data"]["params"]["method"] == "scanpy"
    assert data["data"]["effective_params"]["method"] == "scanpy"
    assert data["data"]["effective_params"]["scanpy_hvg_flavor"] == "seurat"
    assert data["data"]["effective_params"]["normalization_target_sum"] == 10000.0
    assert data["data"]["effective_params"]["raw_available"] is True
    assert data["data"]["visualization"]["recipe_id"] == "standard-sc-preprocessing-gallery"
    assert "pca_embedding" in data["data"]["visualization"]["available_figure_data"]
    command_text = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--method scanpy" in command_text


def test_seurat_backend_function_is_defined():
    """R-backed Seurat method should be wired in the Python entrypoint."""
    spec = importlib.util.spec_from_file_location("sc_preprocess", SKILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "run_seurat_preprocessing")


def _has_seurat_r_stack() -> bool:
    """Return True when the minimal R Seurat preprocessing stack is available."""
    try:
        result = subprocess.run(
            [
                "Rscript",
                "-e",
                (
                    "cat("
                    "requireNamespace('Seurat', quietly=TRUE) && "
                    "requireNamespace('SingleCellExperiment', quietly=TRUE) && "
                    "requireNamespace('zellkonverter', quietly=TRUE)"
                    ")"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "TRUE"


@pytest.mark.skipif(not _has_seurat_r_stack(), reason="R Seurat preprocessing stack not installed")
def test_demo_mode_seurat(tmp_output):
    """sc-preprocessing --method seurat should run when the R stack is available."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--method",
            "seurat",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    if result.returncode != 0:
        bootstrap_markers = [
            "Couldn't connect to server",
            "trying URL",
            "Miniforge",
            "basilisk",
        ]
        if any(marker in result.stderr for marker in bootstrap_markers):
            pytest.skip("R Seurat stack requires basilisk bootstrap that is unavailable in this environment")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["method"] == "seurat"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-preprocessing-gallery"

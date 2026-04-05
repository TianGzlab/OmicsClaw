"""Tests for the sc-velocity skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

VELOCITY_PREP_SCRIPT = Path(__file__).resolve().parents[2] / "sc-velocity-prep" / "sc_velocity_prep.py"
SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_velocity.py"


def _has_scvelo() -> bool:
    return importlib.util.find_spec("scvelo") is not None


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_velocity_out"


@pytest.fixture
def velocity_ready_input(tmp_path):
    prep_out = tmp_path / "prep"
    result = subprocess.run(
        [sys.executable, str(VELOCITY_PREP_SCRIPT), "--demo", "--output", str(prep_out)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(VELOCITY_PREP_SCRIPT.parent),
    )
    assert result.returncode == 0, f"prep stderr: {result.stderr}"
    return prep_out / "processed.h5ad"


@pytest.mark.skipif(not _has_scvelo(), reason="scvelo not installed in current test environment")
def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "adata_with_velocity.h5ad").exists()
    assert (tmp_output / "figures" / "velocity_stream.png").exists()
    assert (tmp_output / "figures" / "velocity_magnitude_umap.png").exists()
    assert (tmp_output / "figures" / "velocity_magnitude_distribution.png").exists()
    assert (tmp_output / "figures" / "velocity_top_genes.png").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "tables" / "velocity_summary.csv").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


@pytest.mark.skipif(not _has_scvelo(), reason="scvelo not installed in current test environment")
def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-velocity"
    assert payload["data"]["output_h5ad"] == "processed.h5ad"
    assert payload["data"]["matrix_contract"]["X"] == "normalized_expression"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-velocity-gallery"


@pytest.mark.skipif(not _has_scvelo(), reason="scvelo not installed in current test environment")
def test_velocity_from_velocity_prep_output(tmp_output, velocity_ready_input):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--input", str(velocity_ready_input), "--method", "scvelo_stochastic", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["n_cells"] > 0
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-velocity-gallery"
    assert (tmp_output / "adata_with_velocity.h5ad").exists()

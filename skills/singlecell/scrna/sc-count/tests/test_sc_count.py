"""Tests for the sc-count skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_count.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_count_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "standardized_input.h5ad").exists()
    assert (tmp_output / "figures" / "barcode_rank.png").exists()
    assert (tmp_output / "figures" / "count_distributions.png").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-count"
    assert payload["summary"]["n_cells"] > 0
    assert payload["data"]["input_contract"]["standardized"] is True


@pytest.mark.parametrize("method", ["simpleaf", "kb_python"])
def test_demo_mode_accepts_pseudoalign_methods(tmp_output, method):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", method, "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["method"] == "demo"

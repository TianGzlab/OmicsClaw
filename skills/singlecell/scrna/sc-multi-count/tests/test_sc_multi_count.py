"""Tests for the sc-multi-count skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_multi_count.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_multi_count_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "multimodal_standardized_input.h5ad").exists()
    assert (tmp_output / "rna_standardized_input.h5ad").exists()
    assert (tmp_output / "figures" / "feature_type_totals.png").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-multi-count"
    assert payload["summary"]["n_rna_genes"] > 0
    assert payload["data"]["multimodal_input_contract"]["standardized"] is True

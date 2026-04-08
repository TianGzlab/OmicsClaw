"""Tests for the sc-pathway-scoring skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from omicsclaw.core.r_script_runner import RScriptRunner

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_pathway_scoring.py"
R_SCRIPTS_DIR = SKILL_SCRIPT.parent / "rscripts"


def _aucell_stack_available() -> bool:
    if importlib.util.find_spec("scanpy") is None:
        return False
    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=10, verbose=False)
    if not runner.check_r_available():
        return False
    return not runner.get_missing_packages(["AUCell", "GSEABase"])


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_pathway_scoring_out"


def test_score_genes_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", "score_genes_py", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "tables" / "enrichment_scores.csv").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


@pytest.mark.skipif(not _aucell_stack_available(), reason="AUCell R stack unavailable")
def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "tables" / "enrichment_scores.csv").exists()
    assert (tmp_output / "tables" / "top_pathways.csv").exists()


@pytest.mark.skipif(not _aucell_stack_available(), reason="AUCell R stack unavailable")
def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-pathway-scoring"
    assert data["summary"]["method"] == "aucell_r"
    assert "score_columns" in data["summary"]

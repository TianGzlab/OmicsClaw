"""Tests for the sc-clustering skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_cluster.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_cluster_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "cluster_summary.csv").exists()
    assert (tmp_output / "tables" / "embedding_points.csv").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-clustering"
    assert data["data"]["visualization"]["recipe_id"] == "standard-sc-clustering-gallery"
    assert data["data"]["visualization"]["cluster_column"] == "leiden"
    assert data["data"]["visualization"]["embedding_method"] == "umap"
    assert data["data"]["visualization"]["embedding_key"] == "X_umap"

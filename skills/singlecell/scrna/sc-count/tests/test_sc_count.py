"""Tests for the sc-count skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import gzip

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_count.py"
DEMO_H5AD = Path(__file__).resolve().parents[5] / "data" / "pbmc3k_raw.h5ad"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_count_out"


@pytest.fixture
def tiny_fastq_dir(tmp_path):
    root = tmp_path / "fastqs"
    root.mkdir()
    r1 = root / "mini_S1_L001_R1_001.fastq.gz"
    r2 = root / "mini_S1_L001_R2_001.fastq.gz"
    with gzip.open(r1, "wt", encoding="utf-8") as handle:
        handle.write("@r1\nACGTACGTACGTACGT\n+\nFFFFFFFFFFFFFFFF\n")
    with gzip.open(r2, "wt", encoding="utf-8") as handle:
        handle.write("@r1\nGATTACAGATTACAGA\n+\nFFFFFFFFFFFFFFFF\n")
    return root


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
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "standardized_input.h5ad").exists()
    assert (tmp_output / "figures" / "barcode_rank.png").exists()
    assert (tmp_output / "figures" / "count_distributions.png").exists()
    assert (tmp_output / "figures" / "count_complexity_scatter.png").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
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
    assert payload["data"]["output_h5ad"] == "processed.h5ad"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-count-gallery"


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


@pytest.mark.parametrize("method", ["simpleaf", "kb_python"])
def test_import_existing_h5ad_for_pseudoalign_methods(tmp_output, method):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--input", str(DEMO_H5AD), "--method", method, "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["method"] == method
    assert payload["data"]["artifacts"]["method"] == method


def test_starsolo_missing_reference_message(tmp_output, tiny_fastq_dir):
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(tiny_fastq_dir),
            "--method",
            "starsolo",
            "--chemistry",
            "10xv3",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode != 0
    stderr = result.stderr
    assert "resources/singlecell/references/starsolo" in stderr
    assert "STARsolo docs" in stderr
    assert "genomeGenerate" in stderr


def test_starsolo_missing_whitelist_message(tmp_output, tiny_fastq_dir, tmp_path):
    fake_reference = tmp_path / "star_index"
    fake_reference.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(tiny_fastq_dir),
            "--method",
            "starsolo",
            "--reference",
            str(fake_reference),
            "--chemistry",
            "10xv3",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode != 0
    stderr = result.stderr
    assert "resources/singlecell/references/whitelists" in stderr
    assert "3M-february-2018" in stderr
    assert "curl -L -o" in stderr

"""Tests for the sc-fastq-qc skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import gzip

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_fastq_qc.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_fastq_qc_out"


@pytest.fixture
def tiny_fastq_pair(tmp_path):
    r1 = tmp_path / "tiny_R1.fastq.gz"
    r2 = tmp_path / "tiny_R2.fastq.gz"
    with gzip.open(r1, "wt", encoding="utf-8") as handle:
        handle.write("@read1\nACGTACGTACGT\n+\nFFFFFFFFFFFF\n")
        handle.write("@read2\nTGCATGCATGCA\n+\nFFFFFFFFFFFF\n")
    with gzip.open(r2, "wt", encoding="utf-8") as handle:
        handle.write("@read1\nGATTACAGATTA\n+\nFFFFFFFFFFFF\n")
        handle.write("@read2\nCCTGAACCTGAA\n+\nFFFFFFFFFFFF\n")
    return r1, r2


def test_demo_mode(tmp_output):
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
    assert (tmp_output / "figures" / "fastq_q30_summary.png").exists()
    assert (tmp_output / "figures" / "per_base_quality.png").exists()
    assert (tmp_output / "figures" / "fastq_file_quality.png").exists()
    assert (tmp_output / "figures" / "fastq_read_structure.png").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "fastq_per_sample_summary.csv").exists()
    assert not (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-fastq-qc"
    assert payload["summary"]["method"] == "fastqc"
    assert payload["summary"]["n_samples"] == 1
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-fastq-qc-gallery"
    assert "fastq_per_sample_summary" in payload["data"]["visualization"]["available_figure_data"]


def test_real_fastq_fallback_mode(tmp_output, tiny_fastq_pair):
    r1, r2 = tiny_fastq_pair
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--input", str(r1), "--read2", str(r2), "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["n_fastq_files"] == 2
    assert payload["data"]["external_tools"]["fastqc_available"] in {True, False}

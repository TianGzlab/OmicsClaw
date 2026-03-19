"""Tests for all 13 bulk RNA-seq skills.

Each skill is tested in --demo mode to verify:
1. Exit code == 0 (no crash)
2. Core output files generated (report.md, result.json)
3. Report contains expected content
4. result.json has correct structure
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BULKRNA_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BULKRNA_DIR.parent.parent


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_skill(script: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """Run a skill script and return the completed process."""
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(script.parent),
    )


# =========================================================================
# 1. bulkrna-qc
# =========================================================================

class TestBulkrnaQC:
    SCRIPT = BULKRNA_DIR / "bulkrna-qc" / "bulkrna_qc.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "qc_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        """bulkrna-qc --demo should run without error."""
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()
        assert (output / "figures").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "QC" in report or "Quality" in report
        assert "Library" in report or "library" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-qc"
        assert "summary" in data
        assert data["summary"]["n_genes"] > 0
        assert data["summary"]["n_samples"] > 0


# =========================================================================
# 2. bulkrna-de
# =========================================================================

class TestBulkrnaDE:
    SCRIPT = BULKRNA_DIR / "bulkrna-de" / "bulkrna_de.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "de_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()
        assert (output / "figures").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Differential" in report or "DE" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-de"
        assert "summary" in data


# =========================================================================
# 3. bulkrna-splicing
# =========================================================================

class TestBulkrnaSplicing:
    SCRIPT = BULKRNA_DIR / "bulkrna-splicing" / "bulkrna_splicing.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "splicing_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Splicing" in report or "splicing" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-splicing"
        assert "summary" in data


# =========================================================================
# 4. bulkrna-enrichment
# =========================================================================

class TestBulkrnaEnrichment:
    SCRIPT = BULKRNA_DIR / "bulkrna-enrichment" / "bulkrna_enrichment.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "enrichment_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Enrichment" in report or "enrichment" in report or "Pathway" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-enrichment"
        assert "summary" in data


# =========================================================================
# 5. bulkrna-deconvolution
# =========================================================================

class TestBulkrnaDeconvolution:
    SCRIPT = BULKRNA_DIR / "bulkrna-deconvolution" / "bulkrna_deconvolution.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "deconv_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Deconvolution" in report or "deconvolution" in report or "Cell" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-deconvolution"
        assert "summary" in data


# =========================================================================
# 6. bulkrna-coexpression
# =========================================================================

class TestBulkrnaCoexpression:
    SCRIPT = BULKRNA_DIR / "bulkrna-coexpression" / "bulkrna_coexpression.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "coexp_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Co-expression" in report or "coexpression" in report or "WGCNA" in report or "Module" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-coexpression"
        assert "summary" in data


# =========================================================================
# 7. bulkrna-batch-correction
# =========================================================================

class TestBulkrnaBatchCorrection:
    SCRIPT = BULKRNA_DIR / "bulkrna-batch-correction" / "bulkrna_batch_correction.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "batch_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Batch" in report or "batch" in report or "ComBat" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-batch-correction"
        assert "summary" in data


# =========================================================================
# 8. bulkrna-geneid-mapping
# =========================================================================

class TestBulkrnaGeneidMapping:
    SCRIPT = BULKRNA_DIR / "bulkrna-geneid-mapping" / "bulkrna_geneid_mapping.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "geneid_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Gene" in report or "gene" in report or "Mapping" in report or "mapping" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-geneid-mapping"
        assert "summary" in data


# =========================================================================
# 9. bulkrna-ppi-network
# =========================================================================

class TestBulkrnaPPINetwork:
    SCRIPT = BULKRNA_DIR / "bulkrna-ppi-network" / "bulkrna_ppi_network.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "ppi_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "PPI" in report or "Network" in report or "network" in report or "STRING" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-ppi-network"
        assert "summary" in data


# =========================================================================
# 10. bulkrna-survival
# =========================================================================

class TestBulkrnaSurvival:
    SCRIPT = BULKRNA_DIR / "bulkrna-survival" / "bulkrna_survival.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "survival_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Survival" in report or "survival" in report or "Kaplan" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-survival"
        assert "summary" in data


# =========================================================================
# 11. bulkrna-read-qc
# =========================================================================

class TestBulkrnaReadQC:
    SCRIPT = BULKRNA_DIR / "bulkrna-read-qc" / "bulkrna_read_qc.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "readqc_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()
        assert (output / "figures").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "FASTQ" in report or "Quality" in report or "Phred" in report or "Q20" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-read-qc"
        assert "summary" in data


# =========================================================================
# 12. bulkrna-read-alignment
# =========================================================================

class TestBulkrnaReadAlignment:
    SCRIPT = BULKRNA_DIR / "bulkrna-read-alignment" / "bulkrna_read_alignment.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "readalign_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Alignment" in report or "alignment" in report or "Mapping" in report or "STAR" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-read-alignment"
        assert "summary" in data


# =========================================================================
# 13. bulkrna-trajblend
# =========================================================================

class TestBulkrnaTrajblend:
    SCRIPT = BULKRNA_DIR / "bulkrna-trajblend" / "bulkrna_trajblend.py"

    @pytest.fixture
    def output(self, tmp_path):
        out = tmp_path / "trajblend_out"
        result = run_skill(self.SCRIPT, ["--demo", "--output", str(out)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return out

    def test_demo_runs(self, output):
        assert output.exists()

    def test_output_files(self, output):
        assert (output / "report.md").exists()
        assert (output / "result.json").exists()

    def test_report_content(self, output):
        report = (output / "report.md").read_text()
        assert "Trajectory" in report or "trajectory" in report or "Interpolation" in report or "TrajBlend" in report

    def test_result_json(self, output):
        data = json.loads((output / "result.json").read_text())
        assert data["skill"] == "bulkrna-trajblend"
        assert "summary" in data


# =========================================================================
# Cross-cutting: SKILL.md existence check
# =========================================================================

EXPECTED_SKILLS = [
    "bulkrna-qc",
    "bulkrna-de",
    "bulkrna-splicing",
    "bulkrna-enrichment",
    "bulkrna-deconvolution",
    "bulkrna-coexpression",
    "bulkrna-batch-correction",
    "bulkrna-geneid-mapping",
    "bulkrna-ppi-network",
    "bulkrna-survival",
    "bulkrna-read-qc",
    "bulkrna-read-alignment",
    "bulkrna-trajblend",
]


class TestSkillStructure:
    """Verify all 13 skills have required files."""

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_skill_md_exists(self, skill):
        skill_md = BULKRNA_DIR / skill / "SKILL.md"
        assert skill_md.exists(), f"Missing SKILL.md for {skill}"

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_python_script_exists(self, skill):
        script_name = skill.replace("-", "_") + ".py"
        script = BULKRNA_DIR / skill / script_name
        assert script.exists(), f"Missing script {script_name} for {skill}"

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_skill_md_has_frontmatter(self, skill):
        skill_md = BULKRNA_DIR / skill / "SKILL.md"
        content = skill_md.read_text()
        assert content.startswith("---"), f"SKILL.md for {skill} missing YAML frontmatter"
        # Verify frontmatter closes
        second_marker = content.index("---", 3)
        assert second_marker > 3, f"SKILL.md for {skill} has malformed frontmatter"

    def test_total_skill_count(self):
        """Verify we have exactly 13 bulkrna skills."""
        actual = sorted([
            d.name for d in BULKRNA_DIR.iterdir()
            if d.is_dir() and d.name.startswith("bulkrna-")
        ])
        assert len(actual) == 13, f"Expected 13 skills, got {len(actual)}: {actual}"

    def test_no_alignment_dir_exists(self):
        """Verify old bulkrna-alignment directory does not exist."""
        assert not (BULKRNA_DIR / "bulkrna-alignment").exists(), \
            "Old bulkrna-alignment directory should not exist"

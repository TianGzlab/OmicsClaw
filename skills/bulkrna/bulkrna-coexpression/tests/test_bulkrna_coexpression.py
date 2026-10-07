"""Tests for the bulkrna-coexpression skill.

Requires R with WGCNA package installed. Tests are skipped if R/WGCNA is unavailable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.cli_subprocess

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "bulkrna_coexpression.py"


def _r_wgcna_available() -> bool:
    """Check if R and WGCNA package are available."""
    try:
        from skills._sdk.deps import validate_r_environment
        validate_r_environment(required_r_packages=["WGCNA", "Matrix"])
        return True
    except (RuntimeError, ImportError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


_skip_no_wgcna = pytest.mark.skipif(
    not _r_wgcna_available(),
    reason="R WGCNA package not available",
)


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "coexpr_out"


@_skip_no_wgcna
def test_demo_mode(tmp_output):
    """bulkrna-coexpression --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures").exists()
    assert (tmp_output / "tables" / "module_assignments.csv").exists()


@_skip_no_wgcna
def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Co-expression" in report or "Coexpression" in report
    assert "Disclaimer" in report


@_skip_no_wgcna
def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "bulkrna-coexpression"
    assert "summary" in data
    assert data["summary"]["n_modules"] > 0

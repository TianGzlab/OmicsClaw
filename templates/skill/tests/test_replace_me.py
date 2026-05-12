"""Tests for the REPLACE_SKILL_NAME skill scaffold.

Rename this file when copying the template (`mv test_replace_me.py
test_<my_skill>.py`) and adjust the SKILL_SCRIPT import accordingly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "replace_me.py"


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "replace_me_out"


def test_demo_mode(tmp_output: Path) -> None:
    """`--demo` must run without error and produce report.md + result.json."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "tables" / "replace_me.csv").exists()


def test_demo_result_envelope(tmp_output: Path) -> None:
    """`result.json` should be a well-formed envelope with summary + data."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        check=True,
        capture_output=True,
        timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert "summary" in payload
    assert "data" in payload
    assert payload["summary"]["method"] == "default"
    assert payload["summary"]["n_rows"] == 5

"""Tests for the sc-markers skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / 'sc_markers.py'


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / 'sc_markers_out'


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), '--demo', '--output', str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_output / 'processed.h5ad').exists()
    assert (tmp_output / 'report.md').exists()
    assert (tmp_output / 'result.json').exists()
    assert (tmp_output / 'tables' / 'markers_all.csv').exists()
    assert (tmp_output / 'figure_data' / 'manifest.json').exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), '--demo', '--output', str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
        check=True,
    )
    data = json.loads((tmp_output / 'result.json').read_text())
    assert data['skill'] == 'sc-markers'
    assert data['summary']['n_clusters'] >= 1
    assert 'visualization' in data['data']
    assert 'matrix_contract' in data['data']

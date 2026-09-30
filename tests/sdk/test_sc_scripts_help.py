"""The ten single-cell scripts broken by ``omicsclaw/core`` answer ``--help`` again.

Plan 0062 case 13 (F10). Slow: each probe starts the skill interpreter.
``OMICSCLAW_TEST_BASE_PYTHON`` names that interpreter (the ``OmicsClaw``
conda env, Python 3.11). It exists only for this test and is not a
configuration option; unset or missing, the test is skipped and says why.
The probe runs from an unrelated directory with ``-B`` and
``PYTHONDONTWRITEBYTECODE=1`` and without ``PYTHONPATH``, so it writes
nothing into the repository and relies only on the script's own bootstrap.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.sdk._scan import REPO_ROOT

pytestmark = pytest.mark.slow

SCRNA = REPO_ROOT / "skills" / "singlecell" / "scrna"
SCRIPTS = [
    "sc-ambient-removal/sc_ambient.py",
    "sc-batch-integration/sc_integrate.py",
    "sc-cell-annotation/sc_annotate.py",
    "sc-cell-communication/sc_cell_communication.py",
    "sc-de/sc_de.py",
    "sc-doublet-detection/sc_doublet.py",
    "sc-enrichment/sc_enrichment.py",
    "sc-pathway-scoring/sc_pathway_scoring.py",
    "sc-preprocessing/sc_preprocess.py",
    "sc-pseudotime/sc_pseudotime.py",
]


def base_python() -> str:
    python = os.environ.get("OMICSCLAW_TEST_BASE_PYTHON", "")
    if not python or not Path(python).is_file():
        pytest.skip("OMICSCLAW_TEST_BASE_PYTHON is unset or not an interpreter")
    return python


def run_help(python: str, script: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [python, "-B", str(script), "--help"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_help_exits_zero(script, tmp_path):
    proc = run_help(base_python(), SCRNA / script, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]

"""The scoring half runs under the skill interpreter, which may be Python 3.11.

The agent runs on a newer Python; trials and scoring run under whatever the
skills need (``OmicsClaw`` here, Python 3.11). This test imports the scoring
half under that interpreter and checks it did not drag agent-side modules
along — an eager import of ``tool`` from the package ``__init__`` would load
the whole tool layer inside every scoring subprocess — and byte-compiles the
supervisor and the panels there, which catches 3.12-only syntax.

The interpreter is ``$OMICSCLAW_SKILL_PYTHON`` or the ``OmicsClaw`` conda
environment's; when neither exists the test is skipped, and says so.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL_PYTHON = os.environ.get("OMICSCLAW_SKILL_PYTHON", "/opt/conda/envs/OmicsClaw/bin/python")

pytestmark = pytest.mark.skipif(
    not Path(SKILL_PYTHON).exists(), reason=f"skill interpreter {SKILL_PYTHON} is not installed"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [SKILL_PYTHON, *args], capture_output=True, text=True, cwd=REPO, timeout=300,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_the_scoring_half_imports_without_the_agent_side():
    done = _run(
        "-c",
        "import sys, omicsclaw.ensemble, omicsclaw.ensemble.metrics.score\n"
        "bad = [m for m in ('omicsclaw.tools', 'omicsclaw.skills', 'omicsclaw.ensemble.tool',"
        " 'omicsclaw.ensemble.runner') if m in sys.modules]\n"
        "print(sys.version_info[:2], bad)",
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("[]"), done.stdout


def test_the_supervisor_and_panels_compile_under_it(tmp_path):
    files = [REPO / "omicsclaw" / "ensemble" / "_supervise.py", *sorted((REPO / "omicsclaw" / "ensemble" / "metrics").glob("*.py"))]
    code = (
        "import py_compile, sys\n"
        f"for path in {[str(f) for f in files]!r}:\n"
        f"    py_compile.compile(path, cfile={str(tmp_path / 'x.pyc')!r}, doraise=True)\n"
        "print('ok')"
    )
    done = _run("-c", code)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_the_tuning_subprocess_modules_import_under_it():
    done = _run(
        "-c",
        "import sys\n"
        "import omicsclaw.ensemble.tuning.subsample, omicsclaw.ensemble.tuning.stability\n"
        "import omicsclaw.ensemble.tuning.markers, omicsclaw.ensemble.tuning.inspect\n"
        "bad = [m for m in ('omicsclaw.tools', 'omicsclaw.skills', 'omicsclaw.ensemble.runner',"
        " 'omicsclaw.ensemble.tuning.pipeline') if m in sys.modules]\n"
        "print(sys.version_info[:2], bad)",
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("[]"), done.stdout

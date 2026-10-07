"""Each function library's ``examples/example_step.py`` runs through the step runner on demo data.

Marked ``skill_example`` and excluded by default: it needs the skills' own
dependencies (scanpy, leidenalg, igraph) and the demo datasets. The kernel
runs this interpreter, so run it where those are installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skills._sdk.notebook import _ledger

pytestmark = pytest.mark.skill_example

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / "skills" / "_sdk" / "notebook" / "run.py"
EXAMPLES = sorted(
    p for p in (REPO / "skills").rglob("examples/example_step.py")
    if (p.parent.parent / "_api.py").is_file()
)
EXAMPLES = [
    pytest.param(example, marks=pytest.mark.skill_example_extended, id=example.parent.parent.name)
    if example.parent.parent.name == "sc-perturb" else pytest.param(example, id=example.parent.parent.name)
    for example in EXAMPLES
]


@pytest.mark.parametrize("example", EXAMPLES)
def test_the_example_step_runs(example, tmp_path):
    skill = example.parent.parent.name
    root = tmp_path / "project"
    root.mkdir()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("OMICSCLAW_SKILL_STUBS", None)
    env.pop("NUMBA_DISABLE_JIT", None)  # set by tests/conftest.py for unit tests; UMAP needs the JIT
    new = subprocess.run([sys.executable, str(RUN), "new", "demo"], cwd=root, env=env,
                         capture_output=True, text=True, timeout=120)
    assert new.returncode == 0, new.stdout + new.stderr
    step = root / "analysis" / "01_demo" / f"01_{skill.replace('-', '_')}.py"
    shutil.copy2(example, step)
    run = subprocess.run([sys.executable, str(RUN), "run", "analysis/01_demo"], cwd=root, env=env,
                         capture_output=True, text=True, timeout=1800)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-4000:]
    assert (root / "results" / "01_demo" / "notebooks" / f"{step.stem}.ipynb").is_file()
    runs = _ledger.runs_of(root / "results" / "01_demo" / "provenance" / "runs", step.stem)
    calls = [c for c in runs[-1].skill_calls if c["skill"] == skill]
    assert calls, f"the example made no recorded call to {skill}"
    assert runs[-1].skill_loads[0]["stub"] is False


def test_velocity_example_rejects_reversed_kinetics(tmp_path):
    """A fitted but sign-reversed result must fail the known-direction check."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("OMICSCLAW_SKILL_STUBS", None)
    env.pop("NUMBA_DISABLE_JIT", None)
    new = subprocess.run([sys.executable, str(RUN), "new", "velocity_mutation"], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=120)
    assert new.returncode == 0, new.stdout + new.stderr
    source = REPO / "skills/singlecell/scrna/sc-velocity/examples/example_step.py"
    text = source.read_text()
    anchor = "sc.tl.umap(adata, random_state=0)"
    assert text.count(anchor) == 1
    mutant = text.replace(anchor, 'adata.layers["velocity"] *= -1\n' + anchor)
    (tmp_path / "analysis/01_velocity_mutation/01_reversed.py").write_text(mutant)
    run = subprocess.run([sys.executable, str(RUN), "run", "analysis/01_velocity_mutation"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=180)
    assert run.returncode != 0, "the example accepted reversed simulated velocities"
    assert "simulation kinetics: velocity direction is wrong" in run.stdout + run.stderr

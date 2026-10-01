"""The pilot skills' CLIs and function libraries still give the recorded results.

For every recorded case: the CLI, now a thin shell over ``_api.py``, is run and
its snapshot compared value by value with the one recorded from the old CLI;
then the library is called directly in this interpreter and the tables and
labels it returns are compared with the matching recorded ones. Cases without a
recorded snapshot are skipped (snapshots are not committed). Record with
``python -m tests.parity.snapshot record <skill> --case <case>`` in the same
environment, before changing the skill.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.parity import snapshot

pytestmark = pytest.mark.slow

CASES = [(skill, case) for skill, cases in snapshot.CASES.items() for case in cases]


def _require_golden(skill: str, case: str) -> Path:
    golden = snapshot.golden_dir(skill, case)
    if not (golden / "summary.json").is_file():
        pytest.skip(f"no recorded snapshot for {skill} {case}")
    return golden


@pytest.mark.parametrize(("skill", "case"), CASES, ids=[f"{s}-{c}" for s, c in CASES])
def test_the_cli_reproduces_the_recorded_snapshot(skill, case, tmp_path):
    _require_golden(skill, case)
    output = tmp_path / "out"
    proc = snapshot.run_cli(skill, case, output)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert snapshot.compare_output(skill, case, output) == []


def compare_api(skill: str, case: str, produced: Path) -> list[str]:
    """Differences between what the library returned (saved in *produced*) and the recorded snapshot."""
    import pandas as pd

    golden = snapshot.golden_dir(skill, case)
    problems: list[str] = []
    for path in sorted((produced / "tables").glob("*.csv")):
        recorded = golden / "tables" / path.name
        if not recorded.is_file():
            problems.append(f"tables/{path.name}: not in the recorded snapshot")
            continue
        problems += snapshot.compare_frames(pd.read_csv(recorded), pd.read_csv(path), f"api tables/{path.name}")
    for path in sorted((produced / "obs_labels").glob("*.csv")) if (produced / "obs_labels").is_dir() else []:
        recorded = golden / "obs_labels" / path.name
        if recorded.is_file():
            problems += snapshot.compare_labels(
                pd.read_csv(recorded).set_index("obs_name")["label"],
                pd.read_csv(path).set_index("obs_name")["label"],
                f"api obs_labels/{path.name}",
            )
    numeric = produced / "obs_numeric.csv"
    if numeric.is_file() and (golden / "obs_numeric.csv").is_file():
        recorded = pd.read_csv(golden / "obs_numeric.csv")
        actual = pd.read_csv(numeric)
        shared = [c for c in recorded.columns if c in actual.columns]
        problems += snapshot.compare_frames(recorded.loc[:, shared], actual.loc[:, shared], "api obs_numeric.csv")
    return problems


@pytest.mark.parametrize(("skill", "case"), CASES, ids=[f"{s}-{c}" for s, c in CASES])
def test_the_library_reproduces_the_recorded_tables_and_labels(skill, case, tmp_path):
    _require_golden(skill, case)
    from tests.parity import api_runs

    if skill not in api_runs.API_RUNNERS:
        pytest.skip(f"{skill} has no function library yet")
    proc = subprocess.run(
        [sys.executable, "-m", "tests.parity.api_runs", skill, case, str(tmp_path / "api")],
        cwd=snapshot.REPO, env=snapshot.child_env(), capture_output=True, text=True, timeout=3600,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert compare_api(skill, case, tmp_path / "api") == []

"""Registered skills' CLIs and function libraries still give the recorded results.

For every recorded case: the CLI, now a thin shell over ``_api.py``, is run and
its snapshot compared value by value with the one recorded from the old CLI;
then the library is called in a separate subprocess and the tables and
labels it returns are compared with the matching recorded ones. Cases without a
recorded snapshot are skipped (snapshots are not committed). Record with
``python -m tests.parity.snapshot record <skill> --case <case>`` in the same
environment, before changing the skill.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.parity import snapshot

pytestmark = pytest.mark.slow

CASES = [(skill, case) for skill, entry in snapshot.REGISTRY.items() for case in entry.cases]


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


def _api_column_rtol(skill: str, case: str, relative: str) -> dict[str, float]:
    """DPT's legacy CLI disables JIT; its API intentionally does not.

    Two JIT runs agreed. Against the no-JIT golden, max absolute drift was
    6e-7 and max relative drift 2.329e-5. No-JIT API output passes 1e-6.
    Only these three float columns use 3e-5, still with zero absolute tolerance.
    """
    if (skill, case) != ("sc-pseudotime", "default"):
        return {}
    if relative == "tables/pseudotime_cells.csv":
        return {"pseudotime": 3e-5}
    if relative == "obs_numeric.csv":
        return {"dpt_pseudotime": 3e-5, "pseudotime": 3e-5}
    return {}


def compare_api(skill: str, case: str, produced: Path) -> list[str]:
    """Differences between what the library returned (saved in *produced*) and the recorded snapshot."""
    import pandas as pd

    golden = snapshot.golden_dir(skill, case)
    problems: list[str] = []
    compared = 0
    options = snapshot.comparison_options(skill, case)
    exclude = options["exclude"]
    structure_only = options["structure_only"]
    for path in sorted((produced / "tables").glob("*.csv")):
        relative = f"tables/{path.name}"
        if skill == "sc-in-silico-perturbation" and relative == "tables/diff_regulation.csv":
            # Its fake p-value columns were removed; retain the actual score comparison.
            columns = ["dr_score", "wt_ko_corr"]
            expected = pd.read_csv(golden / relative).set_index("gene")[columns].sort_index().reset_index()
            actual = pd.read_csv(path).set_index("gene")[columns].sort_index().reset_index()
            problems += snapshot.compare_frames(expected, actual, f"api {relative}")
            compared += 1
            continue
        if relative in exclude:
            continue
        recorded = golden / "tables" / path.name
        if not recorded.is_file():
            problems.append(f"tables/{path.name}: not in the recorded snapshot")
            continue
        columns = [key.split(":", 1)[1] for key in exclude if key.startswith(f"{relative}:")]
        compared += 1
        problems += snapshot.compare_frames(
            pd.read_csv(recorded).drop(columns=columns, errors="ignore"),
            pd.read_csv(path).drop(columns=columns, errors="ignore"), f"api {relative}",
            structure_only=structure_only,
            column_rtol=_api_column_rtol(skill, case, relative),
        )
    for path in sorted((produced / "obs_labels").glob("*.csv")) if (produced / "obs_labels").is_dir() else []:
        if f"obs_labels/{path.name}" in exclude:
            continue
        recorded = golden / "obs_labels" / path.name
        if recorded.is_file():
            compared += 1
            problems += snapshot.compare_labels(
                pd.read_csv(recorded).set_index("obs_name")["label"],
                pd.read_csv(path).set_index("obs_name")["label"],
                f"api obs_labels/{path.name}",
                structure_only=structure_only,
            )
        else:
            problems.append(f"obs_labels/{path.name}: not in the recorded snapshot")
    numeric = produced / "obs_numeric.csv"
    if numeric.is_file() and "obs_numeric.csv" not in exclude:
        if not (golden / "obs_numeric.csv").is_file():
            problems.append("obs_numeric.csv: not in the recorded snapshot")
            return problems
        recorded = pd.read_csv(golden / "obs_numeric.csv")
        actual = pd.read_csv(numeric)
        shared = [c for c in recorded.columns if c in actual.columns and f"obs_numeric.csv:{c}" not in exclude]
        if any(c != "obs_name" for c in shared):
            compared += 1
        problems += snapshot.compare_frames(recorded.loc[:, shared], actual.loc[:, shared], "api obs_numeric.csv",
                                            structure_only=structure_only,
                                            column_rtol=_api_column_rtol(skill, case, "obs_numeric.csv"))
    summary = produced / "summary.json"
    if summary.is_file():
        actual = json.loads(summary.read_text())
        recorded = json.loads((golden / "summary.json").read_text())
        expected = {key: recorded[key] for key in actual if key in recorded}
        problems += snapshot.compare_values(expected, actual, "api summary.json")
        if actual:
            compared += 1
    if not compared:
        problems.append("no comparable API outputs")
    return problems


@pytest.mark.parametrize(("skill", "case"), CASES, ids=[f"{s}-{c}" for s, c in CASES])
def test_the_library_reproduces_the_recorded_tables_and_labels(skill, case, tmp_path):
    _require_golden(skill, case)
    if snapshot.REGISTRY[skill].api_runner is None:
        pytest.skip(f"{skill} has no function library yet")
    proc = subprocess.run(
        [sys.executable, "-m", "tests.parity.api_runs", skill, case, str(tmp_path / "api")],
        cwd=snapshot.REPO, env=snapshot.case_env(skill, case), capture_output=True, text=True, timeout=3600,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert compare_api(skill, case, tmp_path / "api") == []

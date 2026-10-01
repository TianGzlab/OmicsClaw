"""Record what a pilot skill's CLI produces, and compare later runs with it value by value.

A snapshot keeps the values that matter, not the bytes: every CSV under
``tables/``, each categorical ``obs`` column of ``processed.h5ad`` as
``obs_name,label``, the numeric ``obs`` columns, the ``obsm`` keys with their
shapes, the ``summary`` of ``result.json`` without times and paths, and the
names of the files under ``figures/``.

Snapshots live in ``tests/parity/golden/<skill>/<case>/``, which is not
committed: they only mean something on the machine and in the environment
that recorded them.

    python -m tests.parity.snapshot record sc-clustering --case default
    python -m tests.parity.snapshot compare sc-clustering --case default --output <dir>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden"
RTOL = 1e-6

SCRIPTS = {
    "sc-qc": "skills/singlecell/scrna/sc-qc/sc_qc.py",
    "sc-preprocessing": "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
    "sc-clustering": "skills/singlecell/scrna/sc-clustering/sc_cluster.py",
    "sc-cell-annotation": "skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py",
    "sc-de": "skills/singlecell/scrna/sc-de/sc_de.py",
}

CASES = {
    "sc-qc": {"default": ["--demo"], "mouse": ["--demo", "--species", "mouse"]},
    "sc-preprocessing": {"default": ["--demo"], "pearson": ["--demo", "--method", "pearson_residuals"]},
    "sc-clustering": {"default": ["--demo"], "louvain": ["--demo", "--cluster-method", "louvain"]},
    "sc-cell-annotation": {"default": ["--demo"], "knnpredict": ["--demo", "--method", "knnpredict"]},
    "sc-de": {"default": ["--demo"], "ttest": ["--demo", "--method", "t-test"]},
}
"""Each pilot skill's demo defaults plus one Python-method variant."""

_DROPPED_SUMMARY_KEYS = {"completed_at", "elapsed_seconds", "runtime_seconds", "output_dir", "output_h5ad",
                         "input_file", "standardized_at"}


def golden_dir(skill: str, case: str) -> Path:
    return GOLDEN / skill / case


def child_env() -> dict[str, str]:
    """The environment for a CLI or library run: this one, without the test-only numba switch.

    ``tests/conftest.py`` sets ``NUMBA_DISABLE_JIT=1`` to speed up unit tests;
    a UMAP run without JIT is slow and need not match a snapshot recorded with it.
    """
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_DISABLE_JIT"}
    env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
    return env


def run_cli(skill: str, case: str, output: Path, *, python: str | None = None) -> subprocess.CompletedProcess:
    """Run *skill*'s CLI for *case* into *output* with the given interpreter (default: this one)."""
    env = child_env()
    return subprocess.run(
        [python or sys.executable, str(REPO / SCRIPTS[skill]), *CASES[skill][case], "--output", str(output)],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=3600,
    )


def _clean_summary(value):
    if isinstance(value, dict):
        return {k: _clean_summary(v) for k, v in value.items() if k not in _DROPPED_SUMMARY_KEYS}
    if isinstance(value, list):
        return [_clean_summary(v) for v in value]
    if isinstance(value, str) and (value.startswith("/") or value.startswith(str(REPO))):
        return "<path>"
    return value


def obs_frames(adata):
    """The categorical and numeric ``obs`` columns of *adata*, keyed by ``obs_name``."""
    import pandas as pd
    from pandas.api import types

    labels: dict[str, pd.Series] = {}
    numeric = pd.DataFrame(index=adata.obs_names.astype(str))
    for column in adata.obs.columns:
        series = adata.obs[column]
        if types.is_bool_dtype(series) or not types.is_numeric_dtype(series):
            labels[str(column)] = series.astype(str).set_axis(adata.obs_names.astype(str))
        else:
            numeric[str(column)] = series.to_numpy()
    numeric.index.name = "obs_name"
    return labels, numeric


def extract(output: Path, target: Path) -> None:
    """Write the snapshot of the CLI output in *output* to *target*."""
    import anndata

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    tables = output / "tables"
    if tables.is_dir():
        for csv in sorted(tables.rglob("*.csv")):
            destination = target / "tables" / csv.relative_to(tables)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv, destination)
    h5ad = output / "processed.h5ad"
    if h5ad.is_file():
        adata = anndata.read_h5ad(h5ad)
        labels, numeric = obs_frames(adata)
        for column, series in labels.items():
            path = target / "obs_labels" / f"{column}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            series.rename("label").rename_axis("obs_name").to_csv(path)
        numeric.to_csv(target / "obs_numeric.csv")
        (target / "obsm.json").write_text(
            json.dumps({str(k): list(v.shape) for k, v in adata.obsm.items()}, indent=2, sort_keys=True) + "\n"
        )
    result = json.loads((output / "result.json").read_text())
    (target / "summary.json").write_text(
        json.dumps(_clean_summary(result.get("summary", {})), indent=2, sort_keys=True, default=str) + "\n"
    )
    figures = output / "figures"
    names = sorted(p.relative_to(figures).as_posix() for p in figures.rglob("*") if p.is_file()) if figures.is_dir() else []
    (target / "figures.json").write_text(json.dumps(names, indent=2) + "\n")


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=RTOL, abs_tol=0.0) or a == b
    return a == b


def compare_values(expected, actual, where: str) -> list[str]:
    """Differences between two JSON-like values, floats compared within ``RTOL``."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        problems = []
        if set(expected) != set(actual):
            problems.append(f"{where}: keys differ: missing {sorted(set(expected) - set(actual))}, "
                            f"extra {sorted(set(actual) - set(expected))}")
        for key in sorted(set(expected) & set(actual)):
            problems += compare_values(expected[key], actual[key], f"{where}.{key}")
        return problems
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{where}: length {len(expected)} != {len(actual)}"]
        problems = []
        for index, (e, a) in enumerate(zip(expected, actual)):
            problems += compare_values(e, a, f"{where}[{index}]")
        return problems
    return [] if _close(expected, actual) else [f"{where}: {expected!r} != {actual!r}"]


def compare_frames(expected, actual, where: str) -> list[str]:
    """Value-by-value differences between two tables: same columns and rows, floats within ``RTOL``."""
    import numpy as np
    from pandas.api import types

    if list(expected.columns) != list(actual.columns):
        return [f"{where}: columns {list(expected.columns)} != {list(actual.columns)}"]
    if expected.shape != actual.shape:
        return [f"{where}: shape {expected.shape} != {actual.shape}"]
    problems = []
    for column in expected.columns:
        left, right = expected[column], actual[column]
        if types.is_float_dtype(left) or types.is_float_dtype(right):
            if not (types.is_numeric_dtype(left) and types.is_numeric_dtype(right)):
                problems.append(f"{where}.{column}: numeric and non-numeric")
                continue
            if not np.allclose(left.to_numpy(float), right.to_numpy(float), rtol=RTOL, atol=0.0, equal_nan=True):
                bad = int((~np.isclose(left.to_numpy(float), right.to_numpy(float), rtol=RTOL, atol=0.0,
                                       equal_nan=True)).sum())
                problems.append(f"{where}.{column}: {bad} values differ beyond rtol {RTOL}")
        elif not (left.astype(str).to_numpy() == right.astype(str).to_numpy()).all():
            bad = int((left.astype(str).to_numpy() != right.astype(str).to_numpy()).sum())
            problems.append(f"{where}.{column}: {bad} values differ")
    return problems


def compare_labels(expected, actual, where: str) -> list[str]:
    """Differences between two ``obs_name -> label`` series."""
    if set(expected.index) != set(actual.index):
        return [f"{where}: cells differ ({len(set(expected.index) ^ set(actual.index))} not shared)"]
    actual = actual.reindex(expected.index)
    bad = int((expected.astype(str).to_numpy() != actual.astype(str).to_numpy()).sum())
    return [f"{where}: {bad} labels differ"] if bad else []


def compare(golden: Path, snapshot: Path) -> list[str]:
    """Every difference between a recorded snapshot and a new one."""
    import pandas as pd

    problems: list[str] = []
    for name in ("summary.json", "figures.json", "obsm.json"):
        left, right = golden / name, snapshot / name
        if left.exists() != right.exists():
            problems.append(f"{name}: present in only one snapshot")
        elif left.exists():
            problems += compare_values(json.loads(left.read_text()), json.loads(right.read_text()), name)
    for folder in ("tables", "obs_labels"):
        expected = {p.relative_to(golden / folder).as_posix() for p in (golden / folder).rglob("*.csv")} \
            if (golden / folder).is_dir() else set()
        actual = {p.relative_to(snapshot / folder).as_posix() for p in (snapshot / folder).rglob("*.csv")} \
            if (snapshot / folder).is_dir() else set()
        if expected != actual:
            problems.append(f"{folder}: files differ: missing {sorted(expected - actual)}, extra {sorted(actual - expected)}")
        for relative in sorted(expected & actual):
            left = pd.read_csv(golden / folder / relative)
            right = pd.read_csv(snapshot / folder / relative)
            if folder == "obs_labels":
                problems += compare_labels(left.set_index("obs_name")["label"], right.set_index("obs_name")["label"],
                                           f"{folder}/{relative}")
            else:
                problems += compare_frames(left, right, f"{folder}/{relative}")
    left, right = golden / "obs_numeric.csv", snapshot / "obs_numeric.csv"
    if left.exists() and right.exists():
        problems += compare_frames(pd.read_csv(left), pd.read_csv(right), "obs_numeric.csv")
    elif left.exists() != right.exists():
        problems.append("obs_numeric.csv: present in only one snapshot")
    return problems


def compare_output(skill: str, case: str, output: Path) -> list[str]:
    """Differences between the recorded snapshot of *case* and the CLI output in *output*."""
    with tempfile.TemporaryDirectory(prefix="parity-") as scratch:
        snapshot = Path(scratch) / "snapshot"
        extract(output, snapshot)
        return compare(golden_dir(skill, case), snapshot)


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def record(skill: str, case: str) -> Path:
    """Run the CLI for *case* and store its snapshot in the golden folder."""
    with tempfile.TemporaryDirectory(prefix=f"parity-{skill}-") as scratch:
        output = Path(scratch) / "out"
        proc = run_cli(skill, case, output)
        if proc.returncode != 0:
            raise SystemExit(f"{skill} {case} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
        target = golden_dir(skill, case)
        extract(output, target)
    from importlib.metadata import version

    meta = {
        "skill": skill, "case": case, "args": CASES[skill][case], "python": sys.executable,
        "python_version": platform.python_version(), "git_commit": _git_commit(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in ("scanpy", "anndata", "numpy", "pandas")},
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.parity.snapshot")
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record")
    rec.add_argument("skill", choices=sorted(CASES))
    rec.add_argument("--case", required=True)
    cmp_ = commands.add_parser("compare")
    cmp_.add_argument("skill", choices=sorted(CASES))
    cmp_.add_argument("--case", required=True)
    cmp_.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.case not in CASES[args.skill]:
        parser.error(f"{args.skill} has cases {sorted(CASES[args.skill])}")
    if args.command == "record":
        print(record(args.skill, args.case))
        return 0
    problems = compare_output(args.skill, args.case, args.output)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

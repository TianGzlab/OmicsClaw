"""The validate checks in ``skills._sdk.notebook.checks``."""

from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import _ledger
from skills._sdk.notebook.checks import (
    as_labels,
    check_between,
    check_columns,
    check_counts,
    check_files,
    check_rows,
    check_same_labels,
)

REPO = Path(__file__).resolve().parents[3]

SUMMARY_CSV = "cluster,n_cells,proportion_pct\n0,3,60.0\n1,2,40.0\n"
MATRIX_CSV = "leiden,B cell,T cell\n0,0.0,1.0\n1,1.0,0.0\n"


def _labels():
    return pd.Series(pd.Categorical(["0", "0", "1", "0", "1"]))


def test_a_cluster_table_read_back_from_csv_breaks_a_string_lookup():
    """iterrows turns a row of ints and floats into floats, so the key becomes '0.0'."""
    summary = pd.read_csv(io.StringIO(SUMMARY_CSV))
    counts = _labels().value_counts()
    _, row = next(summary.iterrows())
    with pytest.raises(KeyError, match="0.0"):
        counts[str(row["cluster"])]


def test_check_counts_matches_a_csv_cluster_table_to_categorical_labels():
    check_counts(_labels(), pd.read_csv(io.StringIO(SUMMARY_CSV)), key="cluster", count="n_cells")


def test_as_labels_looks_rows_up_across_a_csv_and_the_labels():
    """A CSV gives an integer index; the labels in obs are strings."""
    matrix = pd.read_csv(io.StringIO(MATRIX_CSV))
    with pytest.raises(KeyError):
        matrix.set_index("leiden").loc["0"]
    label_columns = [c for c in matrix.columns if c != "leiden"]
    per_cluster = dict(zip(as_labels(matrix["leiden"]), matrix[label_columns].idxmax(axis=1)))
    assert per_cluster[as_labels(_labels())[0]] == "T cell"


def test_as_labels_turns_equal_labels_into_one_string():
    values = [0, 0.0, np.int64(0), "0", np.float64(2.5), 7.0, True, np.bool_(False), "B cell"]
    assert as_labels(values) == ["0", "0", "0", "0", "2.5", "7", "True", "False", "B cell"]
    assert as_labels(np.array([1, 2])) == ["1", "2"]


@pytest.mark.parametrize("missing", [None, float("nan"), np.nan, pd.NA])
def test_as_labels_reports_a_missing_value_and_where(missing):
    with pytest.raises(AssertionError, match="label 1 is missing"):
        as_labels(["a", missing])


def test_as_labels_refuses_a_single_string():
    with pytest.raises(TypeError, match="not one string"):
        as_labels("leiden")


def test_check_counts_lists_what_differs():
    labels = ["0", "0", "1", "2"]
    table = pd.DataFrame({"cluster": [0, 1, 3], "n_cells": [2, 2, 0]})
    with pytest.raises(AssertionError) as caught:
        check_counts(labels, table, key="cluster", count="n_cells")
    message = str(caught.value)
    assert "'1': the table says 2, the labels hold 1" in message
    assert "'2': 1 in the labels, not in the table" in message
    assert "'3'" not in message  # a listed label with a count of 0 may be absent


def test_check_counts_refuses_a_label_listed_twice_and_a_fractional_count():
    with pytest.raises(AssertionError, match="listed twice"):
        check_counts(["a", "a"], {"k": ["a", "a"], "n": [2, 2]}, key="k", count="n")
    with pytest.raises(AssertionError, match="not a whole number"):
        check_counts(["a"], {"k": ["a"], "n": [0.5]}, key="k", count="n")


def test_check_counts_needs_both_columns():
    with pytest.raises(AssertionError, match="missing column"):
        check_counts(["a"], pd.DataFrame({"cluster": ["a"]}), key="cluster", count="n_cells")


def test_check_columns_names_the_missing_and_the_present_columns():
    table = pd.DataFrame({"cluster": [0], "n_cells": [1]})
    check_columns(table, ["cluster", "n_cells"])
    check_columns(table, "cluster")
    check_columns({"a": [1], "b": [2]}, ["a"])
    with pytest.raises(AssertionError, match="missing column.*proportion_pct; the table has cluster, n_cells"):
        check_columns(table, ["cluster", "proportion_pct"])


def test_check_rows_by_default_wants_a_row():
    check_rows(pd.DataFrame({"a": [1]}))
    with pytest.raises(AssertionError, match="at least 1 rows, the table has 0"):
        check_rows(pd.DataFrame({"a": []}))
    check_rows(pd.DataFrame({"a": [1, 2, 3]}), exactly=3)
    with pytest.raises(AssertionError, match="expected 4 rows"):
        check_rows(pd.DataFrame({"a": [1, 2, 3]}), exactly=4)
    with pytest.raises(AssertionError, match="at most 2"):
        check_rows([1, 2, 3], at_most=2)
    check_rows({"a": [1, 2], "b": [3, 4]}, exactly=2)


def test_check_between_takes_a_number_or_a_column():
    check_between(9, 5, 15)
    check_between(pd.Series([0.0, 0.5, 1.0]), 0, 1)
    check_between([3, 4], low=0)
    with pytest.raises(AssertionError, match=r"1 of 3 values outside \[0, 1\]: 1.5 at position 2"):
        check_between([0.1, 0.2, 1.5], 0, 1)
    with pytest.raises(AssertionError, match="nan at position 1"):
        check_between([0.1, float("nan")], 0, 1)
    with pytest.raises(ValueError):
        check_between([1])


def test_check_same_labels_compares_through_as_labels():
    check_same_labels([0, 1, 2], ["0", "1", "2"])
    check_same_labels([0.0, 1.0], pd.Series(pd.Categorical(["0", "1"])))
    with pytest.raises(AssertionError, match="position 1: '1' vs '2'"):
        check_same_labels([0, 1], ["0", "2"])
    with pytest.raises(AssertionError, match="have 2 and 3 labels"):
        check_same_labels([0, 1], [0, 1, 1])
    check_same_labels(["b", "a", "a"], ["a", "b", "a"], ignore_order=True)
    with pytest.raises(AssertionError, match="'a': 2 on the left, 1 on the right"):
        check_same_labels(["a", "a", "b"], ["a", "b", "b"], ignore_order=True)


def test_a_check_still_fails_under_python_O():
    code = "from skills._sdk.notebook.checks import check_rows; check_rows([])"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    done = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True, env=env)
    assert done.returncode == 1
    assert "AssertionError: expected at least 1 rows" in done.stderr


@pytest.fixture
def step(tmp_path, monkeypatch):
    """The environment the runner gives step ``02_validate.py`` of module ``02_mod``."""
    root = tmp_path / "proj"
    (root / "analysis" / "02_mod").mkdir(parents=True)
    results = root / "results" / "02_mod"
    (results / "figures").mkdir(parents=True)
    step_file = root / "analysis" / "02_mod" / "02_validate.py"
    step_file.write_text("")
    ledger = results / "provenance" / "runs" / "02_validate" / "r.jsonl"
    monkeypatch.setenv("OMICSCLAW_STEP_FILE", str(step_file))
    monkeypatch.setenv("OMICSCLAW_STEP_LEDGER", str(ledger))
    return results, ledger


def test_check_files_records_each_checked_output_as_an_input(step):
    results, ledger = step
    (results / "figures" / "a.png").write_bytes(b"png")
    (results / "figures" / "b.png").write_bytes(b"png!")
    found = check_files("figures/a.png", "figures/b.png")
    assert found == [results / "figures" / "a.png", results / "figures" / "b.png"]
    inputs = [e for e in _ledger.read_events(ledger) if e["event"] == "input"]
    assert [(e["path"], e["via"], e["bytes"]) for e in inputs] == [
        ("results/02_mod/figures/a.png", "check_files", 3),
        ("results/02_mod/figures/b.png", "check_files", 4),
    ]


def test_check_files_names_every_missing_or_empty_output(step):
    results, ledger = step
    (results / "figures" / "empty.png").write_bytes(b"")
    with pytest.raises(AssertionError) as caught:
        check_files("figures/empty.png", "figures/gone.png")
    assert "figures/empty.png is empty" in str(caught.value)
    assert "figures/gone.png does not exist" in str(caught.value)
    assert not ledger.exists()


def test_check_files_takes_only_paths_in_the_output_folders(step):
    with pytest.raises(ValueError, match="first folder must be one of"):
        check_files("provenance/manifest.json")
    with pytest.raises(ValueError):
        check_files("../01_other/figures/a.png")
    with pytest.raises(ValueError):
        check_files()


def test_check_files_needs_a_step(monkeypatch, tmp_path):
    monkeypatch.delenv("OMICSCLAW_STEP_FILE", raising=False)
    monkeypatch.delenv("OMICSCLAW_STEP_LEDGER", raising=False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "loose.py")])
    with pytest.raises(RuntimeError, match="cannot check outputs"):
        check_files("figures/a.png")


def test_the_checks_import_only_the_standard_library_and_the_runner():
    tree = ast.parse((REPO / "skills" / "_sdk" / "notebook" / "checks.py").read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("skills._sdk.notebook"):
                continue
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)

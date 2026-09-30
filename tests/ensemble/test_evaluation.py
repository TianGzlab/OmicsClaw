"""Ground-truth metrics are aligned by observation id and skip missing truth.

A benchmark's truth table rarely covers every observation (unannotated beads,
filtered cells), and aligning by position would silently pair the wrong rows.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from omicsclaw.ensemble.evaluation import ari, evaluate, nmi


def test_identical_partitions_score_one_whatever_the_names():
    labels = {"a": "0", "b": "0", "c": "1", "d": "1"}
    truth = {"d": "y", "c": "y", "b": "x", "a": "x"}
    assert ari(labels, truth) == pytest.approx(1.0)
    assert nmi(labels, truth) == pytest.approx(1.0)


def test_missing_truth_is_ignored():
    labels = {"a": "0", "b": "0", "c": "1", "d": "1", "e": "1"}
    truth = {"a": "x", "b": "x", "c": "y", "d": "y", "e": None}
    result = evaluate(labels, truth)
    assert result["ari"] == pytest.approx(1.0)
    assert result["n_evaluated"] == 4


def test_no_overlap_is_an_error():
    with pytest.raises(ValueError, match="no observation"):
        ari({"a": "0"}, {"b": "x"})

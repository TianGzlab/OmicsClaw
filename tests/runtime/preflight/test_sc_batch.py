"""Unit tests for ``omicsclaw.runtime.preflight.sc_batch``.

The module owns sc-batch-integration's batch-key detection + workflow
plan logic — single-cell domain business logic carved out of bot.core
per ADR 0001. These tests construct small AnnData fixtures so we can
drive the candidate scorer, the readiness inspector, and the
clarification renderer without touching a real h5ad file from disk.

The auto-prepare async chain (``_auto_prepare_sc_batch_integration``)
is exercised through the higher-level eval suite + integration tests,
not here — too much indirect orchestration to mock cleanly without
testing implementation details.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Pure helpers — no AnnData / disk
# ---------------------------------------------------------------------------


def test_normalize_obs_key_collapses_punctuation_and_lowers():
    from omicsclaw.runtime.preflight.sc_batch import _normalize_obs_key

    assert _normalize_obs_key("Sample_ID") == "sample id"
    assert _normalize_obs_key("orig.ident") == "orig ident"
    assert _normalize_obs_key("  Batch--01  ") == "batch 01"


def test_resolve_requested_batch_key_prefers_direct_arg_over_extra_flag():
    """When ``args["batch_key"]`` is set, it wins over a ``--batch-key``
    flag in extra_args. This pin the precedence rule."""
    from omicsclaw.runtime.preflight.sc_batch import _resolve_requested_batch_key

    args = {"batch_key": "sample", "extra_args": ["--batch-key", "donor"]}
    assert _resolve_requested_batch_key(args) == "sample"


def test_resolve_requested_batch_key_falls_back_to_extra_flag():
    """When ``args["batch_key"]`` is missing, parse ``--batch-key`` /
    ``--batch-key=…`` from ``extra_args``."""
    from omicsclaw.runtime.preflight.sc_batch import _resolve_requested_batch_key

    assert _resolve_requested_batch_key({"extra_args": ["--batch-key", "donor"]}) == "donor"
    assert _resolve_requested_batch_key({"extra_args": ["--batch-key=patient"]}) == "patient"
    assert _resolve_requested_batch_key({}) is None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@pytest.fixture
def pandas_module():
    return pytest.importorskip("pandas")


def test_score_batch_candidate_rejects_excluded_columns(pandas_module):
    """Cluster / annotation / QC columns must never score as batch keys —
    even if their cardinality looks right, they're scientifically wrong."""
    from omicsclaw.runtime.preflight.sc_batch import _score_batch_key_candidate

    series = pandas_module.Series(["A", "B", "C", "A", "B", "C"] * 5)
    for excluded in ("leiden", "cluster", "cell_type", "doublet_score", "barcode"):
        assert _score_batch_key_candidate(excluded, series, n_obs=30) is None


def test_score_batch_candidate_high_score_for_exact_preference_match(pandas_module):
    """A column literally named ``sample`` with a sensible group count
    must score high — that's the canonical happy path."""
    from omicsclaw.runtime.preflight.sc_batch import _score_batch_key_candidate

    series = pandas_module.Series(["S1", "S2", "S3", "S4"] * 10)
    result = _score_batch_key_candidate("sample", series, n_obs=40)

    assert result is not None
    assert result["column"] == "sample"
    assert result["nunique"] == 4
    assert result["score"] >= 120
    assert "sample" not in result["reasons"][0] or "common" in result["reasons"][0]


def test_score_batch_candidate_rejects_singleton_or_unique_per_cell(pandas_module):
    """``nunique == 1`` (constant) or ``nunique >= n_obs`` (cell-id-like)
    are not batch columns."""
    from omicsclaw.runtime.preflight.sc_batch import _score_batch_key_candidate

    constant = pandas_module.Series(["only"] * 50)
    cell_ids = pandas_module.Series([f"cell_{i}" for i in range(50)])

    assert _score_batch_key_candidate("batch", constant, n_obs=50) is None
    assert _score_batch_key_candidate("batch", cell_ids, n_obs=50) is None


def test_score_batch_candidate_includes_preview_examples(pandas_module):
    """Preview is the first ~5 unique values — used in the clarification
    message so the user sees what they'd be choosing."""
    from omicsclaw.runtime.preflight.sc_batch import _score_batch_key_candidate

    series = pandas_module.Series(["donor_1", "donor_2", "donor_3", "donor_1"] * 10)
    result = _score_batch_key_candidate("donor", series, n_obs=40)

    assert result is not None
    assert "donor_1" in result["preview"]
    assert "donor_2" in result["preview"]


# ---------------------------------------------------------------------------
# Clarification rendering — no I/O, just template
# ---------------------------------------------------------------------------


def test_format_batch_key_clarification_lists_candidates_when_available():
    from omicsclaw.runtime.preflight.sc_batch import _format_batch_key_clarification

    text = _format_batch_key_clarification(
        file_path=Path("/tmp/sample.h5ad"),
        requested_batch_key=None,
        preflight={
            "obs_columns": ["sample", "leiden", "n_genes_by_counts"],
            "candidates": [
                {
                    "column": "sample",
                    "nunique": 4,
                    "preview": ["S1", "S2", "S3", "S4"],
                    "score": 120,
                    "reasons": ["name matches a common batch/sample column"],
                }
            ],
        },
    )

    assert "sample.h5ad" in text
    assert "`sample`" in text
    assert "4 groups" in text
    assert "S1, S2, S3, S4" in text
    assert "no `batch_key` was provided" in text


def test_format_batch_key_clarification_explains_when_requested_key_not_found():
    """When the user passed a ``batch_key`` but it doesn't exist in
    ``adata.obs``, the message must say so explicitly."""
    from omicsclaw.runtime.preflight.sc_batch import _format_batch_key_clarification

    text = _format_batch_key_clarification(
        file_path=Path("/tmp/x.h5ad"),
        requested_batch_key="nonexistent_column",
        preflight={"obs_columns": ["sample", "leiden"], "candidates": []},
    )

    assert "Requested `batch_key`: `nonexistent_column`" in text
    assert "not found" in text

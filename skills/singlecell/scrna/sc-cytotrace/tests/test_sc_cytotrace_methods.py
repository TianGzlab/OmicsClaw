"""Tests for sc-cytotrace skill."""

import os
import sys
from pathlib import Path

import numpy as np
import pytest
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _load_script(name: str, path: Path):
    """Import the skill script at *path* under *name*; its directory name has hyphens."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_cytotrace = _load_script("sc_cytotrace", Path(__file__).resolve().parent.parent / "sc_cytotrace.py")
run_cytotrace_simple = _cytotrace.run_cytotrace_simple
_compute_gene_counts = _cytotrace._compute_gene_counts
_knn_smooth = _cytotrace._knn_smooth
POTENCY_LABELS = _cytotrace.POTENCY_LABELS


@pytest.fixture
def small_adata():
    """Create a small synthetic AnnData for testing."""
    rng = np.random.RandomState(42)
    n_cells, n_genes = 200, 500
    # Make some cells express more genes (stem-like) and some fewer (differentiated)
    X = np.zeros((n_cells, n_genes))
    for i in range(n_cells):
        n_detected = int(50 + 400 * (i / n_cells))  # gradient of complexity
        detected_genes = rng.choice(n_genes, n_detected, replace=False)
        X[i, detected_genes] = rng.lognormal(0, 1, n_detected)

    adata = sc.AnnData(X=X)
    adata.var_names = [f"Gene_{i}" for i in range(n_genes)]
    adata.obs_names = [f"Cell_{i}" for i in range(n_cells)]
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)
    sc.tl.umap(adata)
    return adata


class TestComputeGeneCounts:
    def test_basic(self, small_adata):
        counts = _compute_gene_counts(small_adata)
        assert counts.shape == (small_adata.n_obs,)
        assert counts.min() >= 0
        assert counts.max() <= small_adata.n_vars

    def test_sparse_input(self, small_adata):
        from scipy import sparse
        small_adata.X = sparse.csr_matrix(small_adata.X)
        counts = _compute_gene_counts(small_adata)
        assert counts.shape == (small_adata.n_obs,)


class TestKnnSmooth:
    def test_smoothing_reduces_variance(self, small_adata):
        rng = np.random.RandomState(0)
        values = rng.rand(small_adata.n_obs)
        smoothed = _knn_smooth(values, small_adata, n_neighbors=15)
        assert smoothed.shape == values.shape
        # Smoothing should reduce variance
        assert np.std(smoothed) <= np.std(values) + 0.01  # small tolerance


class TestRunCytotraceSimple:
    def test_basic_run(self, small_adata):
        summary = run_cytotrace_simple(small_adata, n_neighbors=15)
        assert "cytotrace_score" in small_adata.obs.columns
        assert "cytotrace_potency" in small_adata.obs.columns
        assert "cytotrace_gene_count" in small_adata.obs.columns
        assert summary["n_cells"] == small_adata.n_obs
        assert summary["method"] == "cytotrace_simple"
        assert 0.0 <= summary["score_min"] <= summary["score_max"] <= 1.0

    def test_potency_categories(self, small_adata):
        run_cytotrace_simple(small_adata)
        categories = small_adata.obs["cytotrace_potency"].cat.categories.tolist()
        for cat in categories:
            assert cat in POTENCY_LABELS

    def test_not_degenerate(self, small_adata):
        summary = run_cytotrace_simple(small_adata)
        assert summary["n_potency_categories"] > 1
        assert not summary["degenerate"]

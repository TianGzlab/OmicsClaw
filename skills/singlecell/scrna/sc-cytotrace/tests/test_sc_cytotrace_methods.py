"""Tests for sc-cytotrace skill."""

import numpy as np
import pytest
import scanpy as sc
from skills._sdk.notebook import load_skill

_cytotrace = load_skill("sc-cytotrace")
POTENCY_LABELS = ["Differentiated", "Unipotent", "Oligopotent", "Multipotent", "Pluripotent", "Totipotent"]


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
        counts = _cytotrace.cytotrace(small_adata).obs["cytotrace_gene_count"]
        assert counts.shape == (small_adata.n_obs,)
        assert counts.min() >= 0
        assert counts.max() <= small_adata.n_vars

    def test_sparse_input(self, small_adata):
        from scipy import sparse
        small_adata.X = sparse.csr_matrix(small_adata.X)
        counts = _cytotrace.cytotrace(small_adata).obs["cytotrace_gene_count"]
        assert counts.shape == (small_adata.n_obs,)


class TestKnnSmooth:
    def test_smoothed_scores_remain_finite_and_bounded(self, small_adata):
        scores = _cytotrace.cytotrace(small_adata, n_neighbors=15).obs["cytotrace_score"]
        assert np.isfinite(scores).all()
        assert scores.between(0, 1).all()


class TestRunCytotraceSimple:
    def test_basic_run(self, small_adata):
        _cytotrace.cytotrace(small_adata, n_neighbors=15)
        summary = _cytotrace.run_info(small_adata)
        assert "cytotrace_score" in small_adata.obs.columns
        assert "cytotrace_potency" in small_adata.obs.columns
        assert "cytotrace_gene_count" in small_adata.obs.columns
        assert summary["n_cells"] == small_adata.n_obs
        assert summary["method"] == "cytotrace_simple"
        assert 0.0 <= summary["score_min"] <= summary["score_max"] <= 1.0

    def test_potency_categories(self, small_adata):
        _cytotrace.cytotrace(small_adata)
        categories = small_adata.obs["cytotrace_potency"].cat.categories.tolist()
        for cat in categories:
            assert cat in POTENCY_LABELS

    def test_not_degenerate(self, small_adata):
        _cytotrace.cytotrace(small_adata)
        summary = _cytotrace.run_info(small_adata)
        assert summary["n_potency_categories"] > 1
        assert not summary["degenerate"]

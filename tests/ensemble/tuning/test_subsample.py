"""Subsampled inputs keep 80% of the observations and get a fresh expression graph.

PCA is not recomputed on the subset (a deliberate simplification): the
subsample tests the clustering's stability under losing observations, and
recomputing PCA would add a second source of change.
"""

from __future__ import annotations

import numpy as np
import pytest

anndata = pytest.importorskip("anndata")
pytest.importorskip("scanpy")

from omicsclaw.ensemble.tuning.subsample import draw, write_subsamples  # noqa: E402


def _input(path, n=200):
    rng = np.random.default_rng(0)
    adata = anndata.AnnData(X=rng.poisson(1.0, size=(n, 20)).astype(np.float32))
    adata.obs_names = [f"c{i}" for i in range(n)]
    adata.obsm["X_pca"] = rng.normal(size=(n, 10))
    adata.obsm["spatial"] = rng.uniform(size=(n, 2))
    adata.uns["neighbors"] = {"params": {"n_neighbors": 12, "n_pcs": 8, "random_state": 0}}
    adata.write_h5ad(path)
    return adata


def test_draw_is_reproducible_and_sized():
    first = draw(100, 0.8, 5701)
    assert first.size == 80 and np.all(np.diff(first) > 0)
    assert np.array_equal(first, draw(100, 0.8, 5701))
    assert not np.array_equal(first, draw(100, 0.8, 5702))


def test_subsamples_are_written_with_a_new_graph(tmp_path):
    original = _input(tmp_path / "in.h5ad")
    files = write_subsamples(tmp_path / "in.h5ad", tmp_path / "subs", [5701, 5702], 0.8)
    assert [f["n_obs"] for f in files] == [160, 160]
    assert files[0]["path"].endswith("sub01.h5ad")
    sub = anndata.read_h5ad(files[0]["path"])
    assert sub.obsp["connectivities"].shape == (160, 160)
    assert sub.uns["neighbors"]["params"]["n_neighbors"] == 12
    kept = draw(200, 0.8, 5701)
    assert list(sub.obs_names) == [original.obs_names[i] for i in kept]
    assert np.allclose(sub.obsm["X_pca"], original.obsm["X_pca"][kept])


def test_an_input_without_x_pca_is_refused(tmp_path):
    adata = anndata.AnnData(X=np.zeros((10, 2), dtype=np.float32))
    adata.write_h5ad(tmp_path / "in.h5ad")
    with pytest.raises(ValueError, match="X_pca"):
        write_subsamples(tmp_path / "in.h5ad", tmp_path / "subs", [1], 0.8)

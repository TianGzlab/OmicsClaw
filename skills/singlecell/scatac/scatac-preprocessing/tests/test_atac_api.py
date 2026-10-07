"""The ATAC library preserves counts and makes its filtering explicit."""

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse
import pytest

from skills._sdk.notebook import load_skill


def test_preprocess_returns_filtered_counts_lsi_and_named_tables_without_mutating_input():
    library = load_skill("scatac-preprocessing")
    rng = np.random.default_rng(2)
    counts = rng.poisson(2, size=(24, 40)).astype(np.float32)
    counts[0] = 0
    adata = ad.AnnData(sparse.csr_matrix(counts), obs=pd.DataFrame(index=[f"cell{i}" for i in range(24)]),
                      var=pd.DataFrame(index=[f"peak{i}" for i in range(40)]))
    result = library.preprocess(adata, min_peaks=2, min_cells=2, n_top_peaks=20, n_lsi=4, n_neighbors=5)
    assert result.shape == (23, 20)
    assert result.obsm["X_lsi"].shape == (23, 4)
    assert result.obsm["X_umap"].shape == (23, 2)
    assert "leiden" in result.obs
    np.testing.assert_array_equal(result.layers["counts"].toarray(), adata[result.obs_names, result.var_names].X.toarray())
    assert adata.shape == (24, 40) and not adata.obs.columns.size and not adata.layers
    assert library.qc_metrics_table(result).shape == (23, 4)
    assert len(library.lsi_variance_table(result)) == 4
    assert library.cluster_summary(result)["n_cells"].sum() == 23
    assert set(library.peak_summary(result)["peak"]) == set(result.var_names)
    assert library.run_info(result)["random_state"] == 0


def test_10x_reader_retains_peaks_from_a_multiome_h5(tmp_path):
    import h5py

    path = tmp_path / "multiome.h5"
    with h5py.File(path, "w") as handle:
        matrix = handle.create_group("matrix")
        matrix["data"] = np.array([1, 3, 5, 2, 4, 6], dtype=np.int32)
        matrix["indices"] = np.array([0, 1, 2, 0, 1, 2], dtype=np.int32)
        matrix["indptr"] = np.array([0, 3, 6], dtype=np.int32)
        matrix["shape"] = np.array([3, 2], dtype=np.int64)
        matrix["barcodes"] = np.array([b"bc1", b"bc2"])
        features = matrix.create_group("features")
        features["id"] = np.array([b"gene", b"peak1", b"peak2"])
        features["name"] = np.array([b"GENE", b"chr1:1-10", b"chr1:11-20"])
        features["feature_type"] = np.array([b"Gene Expression", b"Peaks", b"Peaks"])
        features["genome"] = np.array([b"GRCh38"] * 3)
        features["_all_tag_keys"] = np.array([b"genome"])
    adata = load_skill("scatac-preprocessing").read_10x_peaks(path)
    assert adata.shape == (2, 2)
    assert list(adata.var_names) == ["chr1:1-10", "chr1:11-20"]
    np.testing.assert_array_equal(adata.X.toarray(), [[3, 5], [4, 6]])


@pytest.mark.parametrize("values,message", [([[-1, 2], [1, 3]], "non-negative"),
                                          ([[0, 1], [1, 0]], "All cells")])
def test_invalid_or_overfiltered_atac_fails_without_changing_input(values, message):
    adata = ad.AnnData(sparse.csr_matrix(np.array(values, dtype=float)))
    with pytest.raises((ValueError, RuntimeError), match=message):
        load_skill("scatac-preprocessing").preprocess(adata)
    assert not adata.obs.columns.size

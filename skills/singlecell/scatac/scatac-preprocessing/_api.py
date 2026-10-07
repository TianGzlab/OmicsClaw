"""TF-IDF and LSI preprocessing of cell-by-peak accessibility counts."""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler

__all__ = ["preprocess", "read_10x_peaks", "qc_metrics_table", "peak_summary",
           "lsi_variance_table", "cluster_summary", "umap_figure", "run_info"]

logger = logging.getLogger(__name__)


def _qc(adata):
    counts = adata.X
    adata.obs["total_counts"] = np.asarray(counts.sum(axis=1)).ravel().astype(float)
    adata.obs["n_peaks_by_counts"] = np.asarray((counts > 0).sum(axis=1)).ravel().astype(int)
    adata.obs["fraction_accessible"] = adata.obs["n_peaks_by_counts"] / max(adata.n_vars, 1)


def preprocess(adata, *, min_peaks=200, min_cells=5, n_top_peaks=10000,
               tfidf_scale_factor=1e4, n_lsi=30, n_neighbors=15,
               leiden_resolution=0.8, random_state=0):
    """Return a filtered copy of .X accessibility counts with TF-IDF, LSI and Leiden.

    Cells need min_peaks detected peaks; peaks need min_cells cells. Keep at
    most n_top_peaks, ranked by total counts. Counts remain in layers['counts']
    and .raw on retained peaks; .X becomes log1p TF-IDF. LSI uses scaled SVD
    components, excluding the first component from the neighbor graph. UMAP
    and Leiden use that graph. All stochastic operations use random_state.
    No file is written and the input is not modified.
    """
    if adata.X is None:
        raise ValueError("Input AnnData has no matrix in `adata.X`.")
    data = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).ravel()
    if not data.size:
        raise ValueError("Input matrix is empty.")
    if np.any(data < 0):
        raise ValueError("scATAC preprocessing requires a non-negative accessibility matrix.")
    if np.any(np.abs(data - np.round(data)) > 1e-6):
        logger.warning("Input contains non-integer values; TF-IDF + LSI expects count-like accessibility.")
    result = adata.copy()
    _qc(result)
    keep = result.obs["n_peaks_by_counts"] >= min_peaks
    if not keep.any():
        raise RuntimeError("All cells were removed by `min_peaks`. Lower the threshold.")
    result = result[keep.to_numpy()].copy()
    keep = np.asarray((result.X > 0).sum(axis=0)).ravel() >= min_cells
    if not keep.any():
        raise RuntimeError("All peaks were removed by `min_cells`. Lower the threshold.")
    result = result[:, keep].copy()
    _qc(result)
    result.var["total_counts"] = np.asarray(result.X.sum(axis=0)).ravel().astype(float)
    result.var["n_cells_by_counts"] = np.asarray((result.X > 0).sum(axis=0)).ravel().astype(int)
    peaks_after_filter = result.n_vars
    if n_top_peaks < result.n_vars:
        order = np.argsort(-result.var["total_counts"].to_numpy(), kind="mergesort")
        result = result[:, np.sort(order[:n_top_peaks])].copy()
    result.var["selected_for_lsi"] = True
    result.uns["scatac_preprocess"] = {"n_peaks_after_filter": peaks_after_filter, "n_selected_peaks": result.n_vars}
    result.layers["counts"] = result.X.copy()
    result.raw = result.copy()
    matrix = sparse.csr_matrix(result.X, dtype=np.float32)
    cell_sums = np.asarray(matrix.sum(axis=1)).ravel()
    cell_sums[cell_sums == 0] = 1.0
    tf = matrix.multiply((1.0 / cell_sums)[:, None])
    presence = np.asarray((matrix > 0).sum(axis=0)).ravel().astype(np.float32)
    presence[presence == 0] = 1.0
    tfidf = tf.multiply(matrix.shape[0] / presence)
    if tfidf_scale_factor != 1.0:
        tfidf = tfidf.multiply(tfidf_scale_factor)
    tfidf.data = np.log1p(tfidf.data)
    result.X = tfidf.tocsr()
    components = min(int(n_lsi), result.n_obs - 1, result.n_vars - 1)
    if components < 2:
        raise RuntimeError("Not enough cells or peaks remain to compute a stable LSI embedding.")
    svd = TruncatedSVD(n_components=components, random_state=random_state)
    result.obsm["X_lsi"] = StandardScaler().fit_transform(svd.fit_transform(result.X))
    result.varm["LSI"] = svd.components_.T
    result.obsm["X_lsi_graph"] = result.obsm["X_lsi"][:, 1:]
    result.uns["lsi"] = {
        "variance_ratio": np.asarray(svd.explained_variance_ratio_, dtype=float),
        "singular_values": np.asarray(svd.singular_values_, dtype=float),
        "skip_first_component": True, "graph_component_start": 2,
        "graph_component_count": components - 1,
    }
    sc.pp.neighbors(result, use_rep="X_lsi_graph", n_neighbors=n_neighbors, random_state=random_state)
    sc.tl.umap(result, random_state=random_state)
    sc.tl.leiden(result, resolution=leiden_resolution, key_added="leiden", flavor="igraph",
                 directed=False, n_iterations=2, random_state=random_state)
    result.obs["leiden"] = result.obs["leiden"].astype(str).astype("category")
    result.obs["preprocess_method"] = "tfidf_lsi"
    result.uns["scatac_run"] = json.dumps({
        "requested_method": "tfidf_lsi", "executed_method": "tfidf_lsi", "fallback_reason": None,
        "random_state": random_state, "min_peaks": min_peaks, "min_cells": min_cells,
        "n_top_peaks": n_top_peaks, "tfidf_scale_factor": tfidf_scale_factor, "n_lsi": n_lsi,
        "n_neighbors": n_neighbors, "leiden_resolution": leiden_resolution,
    })
    return result


def read_10x_peaks(path):
    """Read 10x H5 or MTX peak counts; pass it as reader= to read_input.

    Use gex_only=False, then keep Peaks when feature_types is present. No
    gene-expression filtering is applied to a peak-only matrix lacking it.
    """
    from pathlib import Path

    path = Path(path)
    adata = sc.read_10x_mtx(path, gex_only=False) if path.is_dir() else sc.read_10x_h5(path, gex_only=False)
    if "feature_types" in adata.var:
        adata = adata[:, adata.var["feature_types"].eq("Peaks").to_numpy()].copy()
    if not adata.n_vars:
        raise ValueError("10x input contains no Peaks features")
    return adata


def qc_metrics_table(adata):
    """Return cell identifiers and the QC metrics computed before top-peak selection."""
    columns = [name for name in ("n_peaks_by_counts", "total_counts", "fraction_accessible") if name in adata.obs]
    table = adata.obs[columns].copy()
    table.insert(0, "cell_id", adata.obs_names.astype(str))
    return table.reset_index(drop=True)


def peak_summary(adata, *, n_top=50):
    """Return retained peaks ranked by total counts and number of cells."""
    if "total_counts" not in adata.var:
        return pd.DataFrame(columns=["peak", "total_counts", "n_cells_by_counts"])
    table = adata.var.copy()
    table["peak"] = table.index.astype(str)
    return table.sort_values(["total_counts", "n_cells_by_counts", "peak"], ascending=[False, False, True])[
        ["peak", "total_counts", "n_cells_by_counts"]
    ].head(n_top).reset_index(drop=True)


def lsi_variance_table(adata):
    """Return variance ratios and their cumulative sum for every fitted LSI component."""
    ratios = np.asarray(adata.uns.get("lsi", {}).get("variance_ratio", []), dtype=float)
    return pd.DataFrame({"component": np.arange(1, len(ratios) + 1), "variance_ratio": ratios,
                         "cumulative_variance_ratio": np.cumsum(ratios)})


def cluster_summary(adata, *, cluster_key="leiden"):
    """Return cell counts and percentages for labels in obs[cluster_key]."""
    counts = adata.obs[cluster_key].astype(str).value_counts()
    table = pd.DataFrame({"cluster": counts.index.astype(str), "n_cells": counts.to_numpy(),
                          "proportion_pct": [round(int(value) / max(adata.n_obs, 1) * 100, 2) for value in counts]})
    return table.sort_values(["n_cells", "cluster"], ascending=[False, True]).reset_index(drop=True)


def umap_figure(adata, *, cluster_key="leiden"):
    """Return a cluster-colored Figure from obsm['X_umap']; do not write a file."""
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6, 5))
    coordinates = np.asarray(adata.obsm["X_umap"])
    labels = adata.obs[cluster_key].astype(str)
    for label in sorted(labels.unique()):
        chosen = labels.eq(label).to_numpy()
        axis.scatter(*coordinates[chosen].T, s=8, label=label)
    axis.set(xlabel="UMAP1", ylabel="UMAP2")
    axis.legend(title=cluster_key)
    figure.tight_layout()
    return figure


def run_info(adata):
    """Return the TF-IDF/LSI parameters recorded on the output AnnData."""
    return json.loads(adata.uns.get("scatac_run", "{}"))

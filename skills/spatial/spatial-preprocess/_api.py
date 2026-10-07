"""Spatial QC, normalization, embeddings and clustering on raw counts."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from skills.spatial._lib.preprocessing import TISSUE_PRESETS, preprocess as _preprocess

__all__ = ["preprocess", "run_info", "cluster_summary", "qc_metrics_table", "pca_variance_table", "spatial_figure"]

_RUN_KEY = "omicsclaw_spatial_preprocess_run"


def preprocess(
    adata, *, min_genes: int = 0, min_cells: int = 0,
    max_mt_pct: float = 20.0, max_genes: int = 0,
    n_top_hvg: int = 2000, n_pcs: int = 30, n_neighbors: int = 15,
    leiden_resolution: float = 0.5, resolutions: list[float] | None = None,
    tissue: str | None = None, species: str = "human", random_state: int = 0,
):
    """Filter raw spatial counts and return a processed copy without changing the input.

    Reads raw counts from ``X``. The returned ``X`` is total-normalized to
    10,000 and log1p-transformed; ``layers['counts']`` and ``raw`` retain the
    filtered counts. Adds QC metrics, HVGs, PCA, neighbors, UMAP and Leiden.
    Coordinates are preserved but do not enter the expression neighbor graph.

    :param adata: AnnData with raw counts in ``X`` and optional spatial coordinates.
    :param min_genes: Minimum detected genes per spot; 0 disables this filter.
    :param min_cells: Minimum spots per gene; 0 disables this filter.
    :param max_mt_pct: Keep spots strictly below this percentage; 20 by default,
        100 disables the filter. Adjust for tissue and assay quality.
    :param max_genes: Keep spots strictly below this detected-gene count;
        0 disables the upper bound.
    :param n_top_hvg: Select up to 2000 HVGs from counts with Seurat v3 by default.
    :param n_pcs: Request 30 PCs by default; clipped below both dimensions.
        Neighbors use at most 30 of the computed PCs.
    :param n_neighbors: Graph neighborhood size, 15 by default.
    :param leiden_resolution: Primary Leiden resolution, 0.5 by default.
    :param resolutions: Optional positive resolutions for extra
        ``obs['leiden_res_<value>']`` columns; None skips the sweep.
    :param tissue: Optional QC preset such as brain or pbmc. Values equal to
        the defaults (0, 20, 0) for min_genes, max_mt_pct and max_genes are
        replaced by the preset, even when passed explicitly. None uses no preset.
    :param species: Human (default, ``MT-``) or mouse (``mt-``) mitochondrial prefix.
    :param random_state: Seed for PCA, neighbors, UMAP and Leiden; default 0
        matches the original CLI. Change it to assess seed sensitivity.
    :returns: A new AnnData with counts, embeddings, labels and JSON diagnostics.
    :raises ValueError: Invalid thresholds or too few spots, genes or HVGs remain.
    :raises ImportError: A backend is missing; use install_skill_deps for
        scikit-misc (HVGs), igraph (Leiden) or umap-learn (embedding).
    """
    for name, value in (("min_genes", min_genes), ("min_cells", min_cells), ("max_genes", max_genes)):
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and >= 0")
    for name, value in (("n_top_hvg", n_top_hvg), ("n_pcs", n_pcs),
                        ("n_neighbors", n_neighbors), ("leiden_resolution", leiden_resolution)):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and > 0")
    if not 0 <= max_mt_pct <= 100:
        raise ValueError("max_mt_pct must be in [0, 100]")
    if tissue and tissue.lower() not in TISSUE_PRESETS:
        raise ValueError(f"Unknown tissue {tissue!r}; choose from {sorted(TISSUE_PRESETS)}")
    if resolutions is not None and any(not np.isfinite(value) or value <= 0 for value in resolutions):
        raise ValueError("All resolutions must be finite and > 0")
    try:
        from skmisc.loess import loess  # noqa: F401
        import igraph  # noqa: F401
        import umap  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "spatial-preprocess needs scikit-misc, igraph and umap-learn; "
            "use install_skill_deps(skill='spatial-preprocess', "
            "packages=['scikit-misc', 'igraph', 'umap-learn']). "
            f"Backend import failed: {exc}"
        ) from exc
    processed, summary = _preprocess(
        adata.copy(), min_genes=min_genes, min_cells=min_cells,
        max_mt_pct=max_mt_pct, max_genes=max_genes, n_top_hvg=n_top_hvg,
        n_pcs=n_pcs, n_neighbors=n_neighbors, leiden_resolution=leiden_resolution,
        resolutions=resolutions, tissue=tissue, species=species, random_state=random_state,
    )
    summary["random_state"] = random_state
    processed.uns[_RUN_KEY] = json.dumps(summary, default=lambda value: value.item())
    return processed


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the QC counts, cluster sizes and effective parameters of the last run.

    :param adata: AnnData returned by preprocess.
    :param keep: True retains diagnostics; False removes them before CLI serialization.
    :returns: A dict including random_state, effective_params and optional
        multi_resolution, or an empty dict if no record remains.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def cluster_summary(adata) -> pd.DataFrame:
    """Count spots in each Leiden cluster, sorted by size then label.

    :param adata: Processed AnnData with ``obs['leiden']``.
    :returns: Columns cluster (string) and n_cells (spot count).
    :raises KeyError: Leiden clustering has not been run.
    """
    counts = adata.obs["leiden"].value_counts()
    table = pd.DataFrame({"cluster": counts.index.astype(str), "n_cells": counts.to_numpy()})
    return table.sort_values(["n_cells", "cluster"], ascending=[False, True], kind="mergesort").reset_index(drop=True)


def qc_metrics_table(adata) -> pd.DataFrame:
    """Return available spot QC metrics and Leiden labels in observation order.

    :param adata: AnnData after preprocessing or QC metric calculation.
    :returns: observation followed by available n_genes_by_counts, total_counts,
        pct_counts_mt and leiden columns, matching the CLI's QC distribution table.
    """
    columns = [key for key in ("n_genes_by_counts", "total_counts", "pct_counts_mt", "leiden") if key in adata.obs]
    table = adata.obs.loc[:, columns].copy()
    table.insert(0, "observation", adata.obs_names.astype(str))
    return table.reset_index(drop=True)


def pca_variance_table(adata) -> pd.DataFrame:
    """Return explained and cumulative variance for each computed PC.

    :param adata: Processed AnnData with PCA information in ``uns['pca']``.
    :returns: Columns pc, variance_ratio, cumulative_variance_ratio and variance;
        an empty table before PCA, with NaN variance if only ratios are available.
    """
    pca = adata.uns.get("pca", {})
    ratio = np.asarray(pca.get("variance_ratio", []), dtype=float)
    return pd.DataFrame({
        "pc": np.arange(1, len(ratio) + 1), "variance_ratio": ratio,
        "cumulative_variance_ratio": np.cumsum(ratio),
        "variance": np.asarray(pca.get("variance", np.full(len(ratio), np.nan)), dtype=float),
    })


def spatial_figure(adata, *, color: str = "leiden"):
    """Plot spot coordinates colored by an observation annotation, without saving.

    :param adata: AnnData with ``obsm['spatial']`` or ``obsm['X_spatial']``.
    :param color: Observation column; default leiden shows the expression clusters.
        A numeric column such as total_counts shows a continuous color scale.
    :returns: A matplotlib Figure; the caller saves and closes it.
    :raises ValueError: No spatial coordinates are available.
    :raises KeyError: The color column is absent from obs.
    """
    import matplotlib.pyplot as plt
    from skills.spatial._lib.adata_utils import get_spatial_key

    key = get_spatial_key(adata)
    if key is None:
        raise ValueError("spatial_figure needs obsm['spatial'] or obsm['X_spatial']")
    coords = np.asarray(adata.obsm[key])
    values = adata.obs[color]
    categorical = not pd.api.types.is_numeric_dtype(values)
    labels = pd.Categorical(values) if categorical else None
    fig, ax = plt.subplots(figsize=(6, 5))
    points = ax.scatter(coords[:, 0], coords[:, 1], c=labels.codes if categorical else values,
                        cmap="tab20" if categorical else "viridis", s=16)
    if categorical:
        from matplotlib.lines import Line2D

        handles = [Line2D([], [], linestyle="", marker="o", color=points.cmap(points.norm(i)), label=str(label))
                   for i, label in enumerate(labels.categories)]
        ax.legend(handles=handles, title=color, bbox_to_anchor=(1.02, 1), loc="upper left")
    else:
        fig.colorbar(points, ax=ax, label=color)
    ax.set(xlabel="Spatial x", ylabel="Spatial y", title=color, aspect="equal")
    ax.invert_yaxis()
    fig.tight_layout()
    return fig

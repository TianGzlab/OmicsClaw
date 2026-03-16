"""Normalization and highly variable gene selection for single-cell analysis.

Adapted from validated reference scripts (normalize_data.py, find_variable_genes.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Union

import numpy as np

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def run_standard_normalization(
    adata: AnnData,
    target_sum: float = 1e4,
    exclude_highly_expressed: bool = False,
    max_fraction: float = 0.05,
    log_transform: bool = True,
    inplace: bool = True,
) -> AnnData:
    """Normalize total counts per cell and optionally log-transform.

    Stores raw counts in ``adata.layers['counts']`` before normalization,
    then applies library-size normalization via :func:`scanpy.pp.normalize_total`
    and optionally :func:`scanpy.pp.log1p`.

    Parameters
    ----------
    adata
        AnnData with raw counts in ``X``.
    target_sum
        Target total counts per cell after normalization.
    exclude_highly_expressed
        Exclude highly expressed genes from the normalization factor.
    max_fraction
        If ``exclude_highly_expressed`` is ``True``, genes with more than
        this fraction of total counts are excluded.
    log_transform
        Apply ``log1p`` after normalization.
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData with normalized (and optionally log-transformed) ``X``.
    Raw counts are stored in ``adata.layers['counts']``.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    logger.info("Running standard normalization (target_sum=%.0f)", target_sum)

    # Store raw counts before normalization
    adata.layers["counts"] = adata.X.copy()
    logger.info("  Stored raw counts in adata.layers['counts']")

    # Library-size normalization
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed,
        max_fraction=max_fraction,
        inplace=True,
    )
    logger.info("  Library-size normalization complete")

    # Log-transform
    if log_transform:
        sc.pp.log1p(adata)
        logger.info("  Log1p transformation applied")

    # Summary statistics
    mean_counts = np.mean(adata.X.sum(axis=1) if not hasattr(adata.X, "toarray") else np.asarray(adata.X.sum(axis=1)).ravel())
    logger.info("  Mean total counts after normalization: %.2f", mean_counts)

    return adata


def run_pearson_residuals(
    adata: AnnData,
    theta: float = 100,
    clip: Optional[float] = None,
    check_values: bool = True,
    inplace: bool = True,
) -> AnnData:
    """Normalize using analytic Pearson residuals.

    Stores raw counts in ``adata.layers['counts']`` before normalization.
    Uses :func:`scanpy.experimental.pp.normalize_pearson_residuals`.

    Parameters
    ----------
    adata
        AnnData with raw counts in ``X``.
    theta
        The negative binomial overdispersion parameter ``theta`` for
        Pearson residuals. Higher values correspond to less overdispersion
        (``theta=np.inf`` corresponds to a Poisson model).
    clip
        Clip Pearson residuals to this value. If ``None``, residuals are
        clipped to ``sqrt(n_obs)``.
    check_values
        Check if ``X`` contains unnormalized count data.
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData with Pearson residuals in ``X``.
    Raw counts are stored in ``adata.layers['counts']``.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    logger.info("Running Pearson residual normalization (theta=%.1f)", theta)

    # Store raw counts before normalization
    adata.layers["counts"] = adata.X.copy()
    logger.info("  Stored raw counts in adata.layers['counts']")

    # Compute Pearson residuals
    sc.experimental.pp.normalize_pearson_residuals(
        adata,
        theta=theta,
        clip=clip,
        check_values=check_values,
    )
    logger.info("  Pearson residual normalization complete")

    # Summary statistics
    residual_mean = np.mean(adata.X) if not hasattr(adata.X, "toarray") else np.mean(adata.X.toarray())
    residual_std = np.std(adata.X) if not hasattr(adata.X, "toarray") else np.std(adata.X.toarray())
    logger.info("  Residual mean: %.4f, std: %.4f", residual_mean, residual_std)

    return adata


# ---------------------------------------------------------------------------
# Normalization visualization
# ---------------------------------------------------------------------------

def plot_normalization_comparison(
    adata: AnnData,
    gene_name: str,
    output_dir: Union[str, Path],
    figsize: Tuple[int, int] = (12, 4),
) -> None:
    """Plot comparison of raw vs. normalized expression for a single gene.

    Creates a 3-panel figure:
    1. Histogram of raw counts for *gene_name*
    2. Histogram of normalized expression for *gene_name*
    3. Scatter plot of raw vs. normalized expression

    Saves ``figures/normalization_comparison.png``.

    Parameters
    ----------
    adata
        AnnData with normalized ``X`` and raw counts in ``layers['counts']``.
    gene_name
        Gene to visualize.
    output_dir
        Directory for output figures.
    figsize
        Figure size ``(width, height)``.
    """
    from .viz_utils import save_figure

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)

    if gene_name not in adata.var_names:
        logger.warning("Gene '%s' not found in adata.var_names. Skipping plot.", gene_name)
        return

    if "counts" not in adata.layers:
        logger.warning("Raw counts layer 'counts' not found. Skipping plot.")
        return

    logger.info("Plotting normalization comparison for gene: %s", gene_name)

    gene_idx = list(adata.var_names).index(gene_name)

    # Extract raw and normalized values
    raw_vals = adata.layers["counts"][:, gene_idx]
    if hasattr(raw_vals, "toarray"):
        raw_vals = np.asarray(raw_vals.toarray()).ravel()
    else:
        raw_vals = np.asarray(raw_vals).ravel()

    norm_vals = adata.X[:, gene_idx]
    if hasattr(norm_vals, "toarray"):
        norm_vals = np.asarray(norm_vals.toarray()).ravel()
    else:
        norm_vals = np.asarray(norm_vals).ravel()

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    # Panel 1: Raw histogram
    axes[0].hist(raw_vals, bins=50, color="#8da0cb", alpha=0.7, edgecolor="black")
    axes[0].set_xlabel("Raw Counts")
    axes[0].set_ylabel("Number of Cells")
    axes[0].set_title(f"{gene_name} - Raw")
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)

    # Panel 2: Normalized histogram
    axes[1].hist(norm_vals, bins=50, color="#66c2a5", alpha=0.7, edgecolor="black")
    axes[1].set_xlabel("Normalized Expression")
    axes[1].set_ylabel("Number of Cells")
    axes[1].set_title(f"{gene_name} - Normalized")
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)

    # Panel 3: Scatter raw vs normalized
    axes[2].scatter(raw_vals, norm_vals, s=1, alpha=0.3, c="#fc8d62")
    axes[2].set_xlabel("Raw Counts")
    axes[2].set_ylabel("Normalized Expression")
    axes[2].set_title(f"{gene_name} - Raw vs Normalized")
    axes[2].spines["top"].set_visible(False)
    axes[2].spines["right"].set_visible(False)

    plt.tight_layout()
    save_figure(fig, output_dir, "normalization_comparison.png")


def plot_library_size_effect(
    adata: AnnData,
    output_dir: Union[str, Path],
    figsize: Tuple[int, int] = (8, 6),
) -> None:
    """Plot library size vs. mean expression before and after normalization.

    Creates a 2-panel figure showing the relationship between total counts
    per cell and mean gene expression, before and after normalization.

    Saves ``figures/library_size_effect.png``.

    Parameters
    ----------
    adata
        AnnData with normalized ``X`` and raw counts in ``layers['counts']``.
    output_dir
        Directory for output figures.
    figsize
        Figure size ``(width, height)``.
    """
    from .viz_utils import save_figure

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)

    if "counts" not in adata.layers:
        logger.warning("Raw counts layer 'counts' not found. Skipping plot.")
        return

    logger.info("Plotting library size effect ...")

    # Raw counts statistics per cell
    raw_X = adata.layers["counts"]
    if hasattr(raw_X, "toarray"):
        raw_lib_size = np.asarray(raw_X.sum(axis=1)).ravel()
        raw_mean_expr = np.asarray(raw_X.mean(axis=1)).ravel()
    else:
        raw_lib_size = np.asarray(raw_X.sum(axis=1)).ravel()
        raw_mean_expr = np.asarray(raw_X.mean(axis=1)).ravel()

    # Normalized statistics per cell
    norm_X = adata.X
    if hasattr(norm_X, "toarray"):
        norm_lib_size = np.asarray(norm_X.sum(axis=1)).ravel()
        norm_mean_expr = np.asarray(norm_X.mean(axis=1)).ravel()
    else:
        norm_lib_size = np.asarray(norm_X.sum(axis=1)).ravel()
        norm_mean_expr = np.asarray(norm_X.mean(axis=1)).ravel()

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Panel 1: Before normalization
    axes[0].scatter(raw_lib_size, raw_mean_expr, s=1, alpha=0.3, c="#8da0cb")
    axes[0].set_xlabel("Library Size (Total Counts)")
    axes[0].set_ylabel("Mean Expression")
    axes[0].set_title("Before Normalization")
    axes[0].set_xscale("log")
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)
    axes[0].grid(alpha=0.3)

    # Panel 2: After normalization
    axes[1].scatter(norm_lib_size, norm_mean_expr, s=1, alpha=0.3, c="#66c2a5")
    axes[1].set_xlabel("Library Size (Total Counts)")
    axes[1].set_ylabel("Mean Expression")
    axes[1].set_title("After Normalization")
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_dir, "library_size_effect.png")


# ---------------------------------------------------------------------------
# Highly variable gene selection
# ---------------------------------------------------------------------------

def find_highly_variable_genes(
    adata: AnnData,
    n_top_genes: int = 2000,
    flavor: str = "seurat",
    min_mean: float = 0.0125,
    max_mean: float = 3,
    min_disp: float = 0.5,
    subset: bool = False,
    inplace: bool = True,
) -> AnnData:
    """Identify highly variable genes (HVGs).

    Wraps :func:`scanpy.pp.highly_variable_genes` with support for
    ``seurat``, ``cell_ranger``, and ``seurat_v3`` flavors.

    Parameters
    ----------
    adata
        AnnData with normalized data in ``X`` (for ``seurat``/``cell_ranger``
        flavors) or raw counts (for ``seurat_v3``).
    n_top_genes
        Number of top variable genes to select.
    flavor
        Method for HVG selection. One of ``"seurat"``, ``"cell_ranger"``,
        ``"seurat_v3"``.
    min_mean
        Minimum mean expression threshold (``seurat``/``cell_ranger`` only).
    max_mean
        Maximum mean expression threshold (``seurat``/``cell_ranger`` only).
    min_disp
        Minimum dispersion threshold (``seurat``/``cell_ranger`` only).
    subset
        If ``True``, subset ``adata`` to only HVGs.
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData with ``adata.var['highly_variable']`` and related columns.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    valid_flavors = ("seurat", "cell_ranger", "seurat_v3")
    if flavor not in valid_flavors:
        raise ValueError(f"Unknown flavor '{flavor}'. Must be one of {valid_flavors}")

    logger.info("Finding highly variable genes (n_top=%d, flavor=%s)", n_top_genes, flavor)

    if flavor == "seurat_v3":
        # seurat_v3 expects raw counts — use counts layer if available
        if "counts" in adata.layers:
            logger.info("  Using 'counts' layer for seurat_v3 flavor")
            sc.pp.highly_variable_genes(
                adata,
                n_top_genes=n_top_genes,
                flavor="seurat_v3",
                subset=subset,
                layer="counts",
            )
        else:
            logger.info("  No 'counts' layer found; using X directly for seurat_v3")
            sc.pp.highly_variable_genes(
                adata,
                n_top_genes=n_top_genes,
                flavor="seurat_v3",
                subset=subset,
            )
    else:
        # seurat and cell_ranger flavors use normalized data
        sc.pp.highly_variable_genes(
            adata,
            n_top_genes=n_top_genes,
            flavor=flavor,
            min_mean=min_mean,
            max_mean=max_mean,
            min_disp=min_disp,
            subset=subset,
        )

    n_hvg = adata.var["highly_variable"].sum()
    logger.info("  Selected %d highly variable genes", n_hvg)

    # Log top HVGs by dispersion / variance
    if "dispersions_norm" in adata.var.columns:
        top_genes = adata.var.loc[adata.var["highly_variable"]].nlargest(10, "dispersions_norm")
        logger.info("  Top 10 HVGs by normalized dispersion:")
        for gene, row in top_genes.iterrows():
            logger.info("    %s (disp_norm=%.2f)", gene, row["dispersions_norm"])
    elif "variances_norm" in adata.var.columns:
        top_genes = adata.var.loc[adata.var["highly_variable"]].nlargest(10, "variances_norm")
        logger.info("  Top 10 HVGs by normalized variance:")
        for gene, row in top_genes.iterrows():
            logger.info("    %s (var_norm=%.2f)", gene, row["variances_norm"])

    return adata


# ---------------------------------------------------------------------------
# HVG visualization
# ---------------------------------------------------------------------------

def plot_variable_genes(
    adata: AnnData,
    output_dir: Union[str, Path],
    figsize: Tuple[int, int] = (8, 6),
    log: bool = True,
) -> None:
    """Plot highly variable genes using scanpy.

    Uses :func:`scanpy.pl.highly_variable_genes` to create a
    mean-variance/dispersion plot with HVGs highlighted.

    Saves ``figures/highly_variable_genes.png``.

    Parameters
    ----------
    adata
        AnnData with HVG annotations in ``adata.var``.
    output_dir
        Directory for output figures.
    figsize
        Figure size ``(width, height)``.
    log
        Use log scale for axes.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    if "highly_variable" not in adata.var.columns:
        logger.warning("HVG annotations not found. Run find_highly_variable_genes() first.")
        return

    logger.info("Plotting highly variable genes ...")

    sc.pl.highly_variable_genes(adata, log=log, show=False)
    fig = plt.gcf()
    fig.set_size_inches(figsize)

    save_figure(fig, output_dir, "highly_variable_genes.png")


# ---------------------------------------------------------------------------
# HVG filtering
# ---------------------------------------------------------------------------

def filter_to_hvgs(
    adata: AnnData,
    inplace: bool = False,
) -> AnnData:
    """Subset AnnData to only highly variable genes.

    Parameters
    ----------
    adata
        AnnData with ``adata.var['highly_variable']`` column.
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData subset to highly variable genes only.
    """
    if "highly_variable" not in adata.var.columns:
        raise ValueError(
            "No 'highly_variable' column found in adata.var. "
            "Run find_highly_variable_genes() first."
        )

    n_before = adata.n_vars
    n_hvg = adata.var["highly_variable"].sum()
    logger.info("Filtering to %d HVGs (from %d total genes)", n_hvg, n_before)

    if inplace:
        adata._inplace_subset_var(adata.var["highly_variable"])
        result = adata
    else:
        result = adata[:, adata.var["highly_variable"]].copy()

    logger.info("  Retained %d genes (%.1f%%)", result.n_vars, 100 * result.n_vars / n_before)
    return result

"""Marker gene discovery and visualization for single-cell analysis.

Adapted from validated reference script (sc_de.py / find_markers logic).
Provides cluster-vs-rest marker identification, per-cluster extraction,
export utilities, and publication-quality visualizations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Marker gene discovery
# ---------------------------------------------------------------------------

def find_all_cluster_markers(
    adata: AnnData,
    cluster_key: str = "leiden_0.8",
    method: str = "wilcoxon",
    n_genes: Optional[int] = None,
    min_in_group_fraction: float = 0.25,
    min_fold_change: float = 1.0,
    max_out_group_fraction: float = 0.5,
    use_raw: bool | None = None,
    layer: Optional[str] = None,
) -> pd.DataFrame:
    """Find marker genes for all clusters (one-vs-rest).

    Runs :func:`scanpy.tl.rank_genes_groups` followed by
    :func:`scanpy.tl.filter_rank_genes_groups` to produce a filtered
    marker table.

    Parameters
    ----------
    adata
        AnnData with log-normalized data in ``adata.raw`` or ``adata.X``.
    cluster_key
        Column in ``adata.obs`` containing cluster labels.
    method
        Statistical test: ``"wilcoxon"``, ``"t-test"``, ``"t-test_overestim_var"``,
        or ``"logreg"``.
    n_genes
        Number of top genes per group to retain. If ``None``, keeps all genes.
    min_in_group_fraction
        Minimum fraction of cells in the group expressing the gene.
    min_fold_change
        Minimum log fold change to keep a gene.
    max_out_group_fraction
        Maximum fraction of cells outside the group expressing the gene.
    use_raw
        Use ``adata.raw`` for the test.
    layer
        Layer to use instead of ``X``.

    Returns
    -------
    pd.DataFrame
        Combined marker table with columns: ``group``, ``names``, ``scores``,
        ``logfoldchanges``, ``pvals``, ``pvals_adj``, plus fraction columns
        when available.
    """
    import scanpy as sc

    if cluster_key not in adata.obs.columns:
        raise ValueError(
            f"Cluster key '{cluster_key}' not found in adata.obs. "
            f"Available columns: {list(adata.obs.columns)}"
        )

    n_clusters = adata.obs[cluster_key].nunique()
    logger.info(
        "Finding markers for %d clusters (key=%s, method=%s)",
        n_clusters, cluster_key, method,
    )

    # --- Run rank_genes_groups ---
    if use_raw is None:
        use_raw = adata.raw is not None and adata.raw.shape == adata.shape

    kwargs: dict = dict(
        groupby=cluster_key,
        method=method,
        pts=True,
        use_raw=use_raw,
    )
    if n_genes is not None:
        kwargs["n_genes"] = n_genes
    if layer is not None:
        kwargs["layer"] = layer

    sc.tl.rank_genes_groups(adata, **kwargs)
    logger.info("  rank_genes_groups complete")

    # --- Filter ---
    try:
        sc.tl.filter_rank_genes_groups(
            adata,
            min_in_group_fraction=min_in_group_fraction,
            min_fold_change=min_fold_change,
            max_out_group_fraction=max_out_group_fraction,
        )
        logger.info(
            "  Filtered: min_in_group=%.2f, min_fc=%.1f, max_out_group=%.2f",
            min_in_group_fraction, min_fold_change, max_out_group_fraction,
        )
        # Use filtered results if available
        result_key = "rank_genes_groups_filtered"
        if result_key in adata.uns:
            markers_df = sc.get.rank_genes_groups_df(adata, group=None, key=result_key)
            # Drop rows where gene name is NaN (filtered out)
            markers_df = markers_df.dropna(subset=["names"])
        else:
            markers_df = sc.get.rank_genes_groups_df(adata, group=None)
    except Exception as exc:
        logger.warning("filter_rank_genes_groups failed (%s), using unfiltered results", exc)
        markers_df = sc.get.rank_genes_groups_df(adata, group=None)

    # Add fraction columns from pts if available
    if "pts" in adata.uns.get("rank_genes_groups", {}):
        pts_df = adata.uns["rank_genes_groups"]["pts"]
        if isinstance(pts_df, pd.DataFrame):
            logger.info("  Percentage-of-cells data available")

    n_total = len(markers_df)
    n_per_cluster = markers_df.groupby("group").size()
    logger.info(
        "  Total markers: %d (per cluster: min=%d, max=%d, median=%d)",
        n_total,
        int(n_per_cluster.min()) if len(n_per_cluster) else 0,
        int(n_per_cluster.max()) if len(n_per_cluster) else 0,
        int(n_per_cluster.median()) if len(n_per_cluster) else 0,
    )

    return markers_df


def find_markers_for_cluster(
    adata: AnnData,
    cluster: str,
    cluster_key: str = "leiden_0.8",
    method: str = "wilcoxon",
    n_genes: int = 100,
) -> pd.DataFrame:
    """Find marker genes for a single cluster vs. all others.

    Parameters
    ----------
    adata
        AnnData with log-normalized data in ``adata.raw`` or ``adata.X``.
    cluster
        The specific cluster label to find markers for.
    cluster_key
        Column in ``adata.obs`` containing cluster labels.
    method
        Statistical test.
    n_genes
        Number of top genes to return.

    Returns
    -------
    pd.DataFrame
        Marker table for the specified cluster, sorted by score descending.
    """
    import scanpy as sc

    if cluster_key not in adata.obs.columns:
        raise ValueError(
            f"Cluster key '{cluster_key}' not found in adata.obs. "
            f"Available columns: {list(adata.obs.columns)}"
        )

    cluster_str = str(cluster)
    available = adata.obs[cluster_key].astype(str).unique()
    if cluster_str not in available:
        raise ValueError(
            f"Cluster '{cluster}' not found in '{cluster_key}'. "
            f"Available clusters: {sorted(available)}"
        )

    logger.info(
        "Finding markers for cluster '%s' (key=%s, method=%s, n_genes=%d)",
        cluster, cluster_key, method, n_genes,
    )

    sc.tl.rank_genes_groups(
        adata,
        groupby=cluster_key,
        groups=[cluster_str],
        reference="rest",
        method=method,
        n_genes=n_genes,
        pts=True,
    )

    markers_df = sc.get.rank_genes_groups_df(adata, group=cluster_str)
    logger.info("  Found %d marker genes for cluster '%s'", len(markers_df), cluster)

    return markers_df


# ---------------------------------------------------------------------------
# Export utilities
# ---------------------------------------------------------------------------

def export_marker_tables(
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    top_n: Optional[int] = None,
) -> None:
    """Save marker tables as CSV files.

    Creates:
    - ``tables/markers_all.csv`` — full marker table
    - ``tables/markers_top{N}.csv`` — top N markers per cluster (if *top_n* given)
    - ``tables/markers_cluster_{id}.csv`` — one file per cluster

    Parameters
    ----------
    markers
        DataFrame from :func:`find_all_cluster_markers`.
    output_dir
        Base output directory.
    top_n
        If given, also save a table with only the top *top_n* markers per cluster.
    """
    output_dir = Path(output_dir)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Full table
    full_path = tables_dir / "markers_all.csv"
    markers.to_csv(full_path, index=False)
    logger.info("Saved full marker table: %s (%d rows)", full_path, len(markers))

    # Top N per cluster
    if top_n is not None and top_n > 0:
        if "group" in markers.columns:
            top_df = markers.groupby("group").head(top_n)
        else:
            top_df = markers.head(top_n)
        top_path = tables_dir / f"markers_top{top_n}.csv"
        top_df.to_csv(top_path, index=False)
        logger.info("Saved top-%d marker table: %s (%d rows)", top_n, top_path, len(top_df))

    # Per-cluster tables
    if "group" in markers.columns:
        for cluster_id, cluster_df in markers.groupby("group"):
            safe_name = str(cluster_id).replace("/", "_").replace(" ", "_")
            cluster_path = tables_dir / f"markers_cluster_{safe_name}.csv"
            cluster_df.to_csv(cluster_path, index=False)
        logger.info("Saved per-cluster marker tables for %d clusters", markers["group"].nunique())


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_top_markers_heatmap(
    adata: AnnData,
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    n_top: int = 10,
    cluster_key: str = "leiden_0.8",
    figsize: tuple = (12, 8),
    use_raw: bool | None = None,
) -> None:
    """Plot a clustered heatmap of top marker genes using seaborn.

    For each cluster, selects the top *n_top* genes and creates a
    seaborn clustermap showing mean expression per cluster.

    Saves ``figures/markers_heatmap.png``.

    Parameters
    ----------
    adata
        AnnData with expression data.
    markers
        DataFrame from :func:`find_all_cluster_markers`.
    output_dir
        Base output directory.
    n_top
        Number of top markers per cluster.
    cluster_key
        Column in ``adata.obs`` with cluster labels.
    figsize
        Figure size ``(width, height)``.
    use_raw
        Use ``adata.raw`` for expression values.
    """
    from .viz_utils import save_figure

    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)

    if "group" not in markers.columns or "names" not in markers.columns:
        logger.warning("Markers DataFrame missing 'group' or 'names' column. Skipping heatmap.")
        return

    # Select top N genes per cluster
    top_genes_df = markers.groupby("group").head(n_top)
    gene_list = top_genes_df["names"].unique().tolist()

    # Filter to genes present in adata
    if use_raw and adata.raw is not None:
        available_genes = [g for g in gene_list if g in adata.raw.var_names]
    else:
        available_genes = [g for g in gene_list if g in adata.var_names]

    if len(available_genes) == 0:
        logger.warning("No marker genes found in adata. Skipping heatmap.")
        return

    logger.info("Creating marker heatmap with %d genes ...", len(available_genes))

    # Build mean expression matrix (clusters x genes)
    if cluster_key not in adata.obs.columns:
        logger.warning("Cluster key '%s' not found. Skipping heatmap.", cluster_key)
        return

    clusters = sorted(adata.obs[cluster_key].unique(), key=str)
    mean_expr = pd.DataFrame(index=clusters, columns=available_genes, dtype=float)

    for cluster in clusters:
        mask = adata.obs[cluster_key] == cluster
        if use_raw and adata.raw is not None:
            subset = adata.raw[mask, available_genes].X
        else:
            subset = adata[mask, available_genes].X

        if hasattr(subset, "toarray"):
            subset = subset.toarray()
        mean_expr.loc[cluster] = np.asarray(subset).mean(axis=0)

    mean_expr = mean_expr.astype(float)

    # Z-score normalize per gene for better visualization
    mean_expr_z = (mean_expr - mean_expr.mean()) / (mean_expr.std() + 1e-10)

    try:
        g = sns.clustermap(
            mean_expr_z.T,
            cmap="RdBu_r",
            center=0,
            figsize=figsize,
            row_cluster=True,
            col_cluster=True,
            xticklabels=True,
            yticklabels=True,
            linewidths=0.5,
            cbar_kws={"label": "Z-score"},
        )
        g.ax_heatmap.set_xlabel("Cluster")
        g.ax_heatmap.set_ylabel("Gene")
        g.fig.suptitle(f"Top {n_top} Marker Genes per Cluster", y=1.02, fontsize=14)

        save_figure(g.fig, output_dir, "markers_heatmap.png")
        logger.info("Saved marker heatmap")
    except Exception as exc:
        logger.warning("Heatmap generation failed: %s", exc)


def plot_markers_dotplot(
    adata: AnnData,
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    n_top: int = 5,
    cluster_key: str = "leiden_0.8",
    figsize: tuple = (12, 6),
) -> None:
    """Plot a dot plot of top marker genes per cluster.

    Uses :func:`scanpy.pl.dotplot` with the top *n_top* genes per cluster.

    Saves ``figures/markers_dotplot.png``.

    Parameters
    ----------
    adata
        AnnData with expression data.
    markers
        DataFrame from :func:`find_all_cluster_markers`.
    output_dir
        Base output directory.
    n_top
        Number of top markers per cluster for the dotplot.
    cluster_key
        Column in ``adata.obs`` with cluster labels.
    figsize
        Figure size ``(width, height)``.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    if "group" not in markers.columns or "names" not in markers.columns:
        logger.warning("Markers DataFrame missing 'group' or 'names' column. Skipping dotplot.")
        return

    if cluster_key not in adata.obs.columns:
        logger.warning("Cluster key '%s' not found. Skipping dotplot.", cluster_key)
        return

    # Build gene dict: {cluster: [gene1, gene2, ...]}
    top_genes_df = markers.groupby("group").head(n_top)
    gene_dict = {}
    for cluster_id, grp in top_genes_df.groupby("group"):
        genes = [g for g in grp["names"].tolist() if g in adata.var_names]
        if genes:
            gene_dict[str(cluster_id)] = genes

    if not gene_dict:
        logger.warning("No valid marker genes found in adata. Skipping dotplot.")
        return

    logger.info("Creating marker dotplot (%d clusters, %d top genes each) ...",
                len(gene_dict), n_top)

    try:
        dp = sc.pl.dotplot(
            adata,
            var_names=gene_dict,
            groupby=cluster_key,
            show=False,
            return_fig=True,
        )
        fig = plt.gcf()
        fig.set_size_inches(figsize)

        save_figure(fig, output_dir, "markers_dotplot.png")
        logger.info("Saved marker dotplot")
    except Exception as exc:
        logger.warning("Dotplot generation failed: %s", exc)
        plt.close("all")

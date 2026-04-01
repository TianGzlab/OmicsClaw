"""Cell type annotation utilities for single-cell analysis.

Adapted from validated reference script (sc_annotate.py / annotate_celltypes logic).
Provides manual cluster annotation, CellTypist integration with validation,
annotation visualization, summary statistics, and cross-method comparison.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import numpy as np
import pandas as pd
from anndata import AnnData

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manual annotation
# ---------------------------------------------------------------------------

def annotate_clusters_manual(
    adata: AnnData,
    annotations: Dict[str, str],
    cluster_key: str = "leiden_0.8",
    annotation_key: str = "cell_type",
    inplace: bool = True,
) -> AnnData:
    """Assign cell type labels to clusters using a user-provided dictionary.

    Unmapped clusters are filled with their original cluster ID so that
    no cells are left without a label.

    Parameters
    ----------
    adata
        AnnData with cluster labels in ``adata.obs[cluster_key]``.
    annotations
        Dictionary mapping cluster IDs to cell type names,
        e.g. ``{"0": "T cells", "1": "B cells"}``.
    cluster_key
        Column in ``adata.obs`` containing cluster labels.
    annotation_key
        Column name for the new annotation in ``adata.obs``.
    inplace
        Modify *adata* in place. If ``False``, operates on a copy.

    Returns
    -------
    AnnData with ``adata.obs[annotation_key]`` populated.
    """
    if not inplace:
        adata = adata.copy()

    if cluster_key not in adata.obs.columns:
        raise ValueError(
            f"Cluster key '{cluster_key}' not found in adata.obs. "
            f"Available columns: {list(adata.obs.columns)}"
        )

    clusters = adata.obs[cluster_key].astype(str)
    unique_clusters = set(clusters.unique())

    # Normalize annotation keys to string
    annotations_str = {str(k): v for k, v in annotations.items()}

    # Map annotations, fill unmapped with cluster ID
    mapped = clusters.map(annotations_str)
    unmapped_mask = mapped.isna()
    mapped[unmapped_mask] = clusters[unmapped_mask]

    adata.obs[annotation_key] = pd.Categorical(mapped)

    n_mapped = len(unique_clusters & set(annotations_str.keys()))
    n_unmapped = len(unique_clusters) - n_mapped
    logger.info(
        "Manual annotation: %d/%d clusters mapped to cell types",
        n_mapped, len(unique_clusters),
    )
    if n_unmapped > 0:
        unmapped_ids = unique_clusters - set(annotations_str.keys())
        logger.warning(
            "  %d clusters not in annotation dict (kept as cluster ID): %s",
            n_unmapped, sorted(unmapped_ids),
        )

    # Log distribution
    counts = adata.obs[annotation_key].value_counts()
    for ct, n in counts.items():
        logger.info("  %s: %d cells (%.1f%%)", ct, n, 100 * n / adata.n_obs)

    return adata


# ---------------------------------------------------------------------------
# CellTypist annotation
# ---------------------------------------------------------------------------

def annotate_with_celltypist(
    adata: AnnData,
    model: str = "Immune_All_Low.pkl",
    majority_voting: bool = False,
    annotation_key: str = "celltypist_annotation",
    inplace: bool = True,
) -> AnnData:
    """Annotate cells using CellTypist pre-trained models.

    Requires the ``celltypist`` package. Uses
    :func:`dependency_manager.require` to provide a clear install message
    if the package is missing.

    Parameters
    ----------
    adata
        AnnData with normalized, log-transformed data.
    model
        CellTypist model name or path (e.g. ``"Immune_All_Low.pkl"``).
    majority_voting
        Apply majority voting within clusters for label smoothing.
    annotation_key
        Column name for the annotation in ``adata.obs``.
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData with ``adata.obs[annotation_key]`` and optionally
    ``adata.obs[annotation_key + '_majority_voting']`` populated.
    """
    from . import dependency_manager as dm

    ct = dm.require("celltypist", feature="CellTypist cell type annotation")

    if not inplace:
        adata = adata.copy()

    logger.info("Running CellTypist annotation (model=%s, majority_voting=%s)",
                model, majority_voting)

    # Download models if needed
    try:
        ct.models.download_models(force_update=False)
    except Exception as exc:
        logger.warning("Model download check failed: %s", exc)

    # Load model
    ct_model = ct.models.Model.load(model=model)
    logger.info("  Loaded model: %s", model)

    # Run annotation
    predictions = ct.annotate(adata, model=ct_model, majority_voting=majority_voting)

    # Transfer labels
    pred_labels = predictions.predicted_labels
    adata.obs[annotation_key] = pred_labels["predicted_labels"].values

    if majority_voting and "majority_voting" in pred_labels.columns:
        mv_key = f"{annotation_key}_majority_voting"
        adata.obs[mv_key] = pred_labels["majority_voting"].values
        logger.info("  Majority voting labels stored in '%s'", mv_key)

    # Transfer probability matrix if available
    if hasattr(predictions, "probability_matrix"):
        prob_matrix = predictions.probability_matrix
        adata.obsm[f"{annotation_key}_prob"] = prob_matrix.values
        try:
            adata.obs[f"{annotation_key}_score"] = prob_matrix.max(axis=1).to_numpy()
        except Exception:
            pass

    # Summary
    n_types = adata.obs[annotation_key].nunique()
    logger.info("  CellTypist identified %d cell types", n_types)

    counts = adata.obs[annotation_key].value_counts()
    for ct_name, n in counts.head(10).items():
        logger.info("    %s: %d cells (%.1f%%)", ct_name, n, 100 * n / adata.n_obs)
    if n_types > 10:
        logger.info("    ... and %d more types", n_types - 10)

    # Validate annotations
    _validate_celltypist_annotations(adata, annotation_key)

    return adata


def validate_celltypist_input_matrix(adata: AnnData) -> tuple[bool, str]:
    """Heuristically validate official CellTypist AnnData input expectations."""
    matrix = adata.X
    n_obs = min(500, adata.n_obs)
    n_vars = min(500, adata.n_vars)
    if hasattr(matrix, "toarray"):
        matrix = matrix[:n_obs, :n_vars].toarray()
    else:
        matrix = np.asarray(matrix[:n_obs, :n_vars])

    if matrix.size == 0:
        return True, "empty matrix preview"
    if np.nanmin(matrix) < 0:
        return False, "CellTypist AnnData input should not contain negative expression values"

    frac_integer = float(np.mean(np.isclose(matrix, np.round(matrix), atol=1e-6)))
    max_value = float(np.nanmax(matrix))
    median_row_sum = float(np.nanmedian(matrix.sum(axis=1)))

    if frac_integer > 0.98 and max_value > 20 and median_row_sum > 50:
        return False, (
            "CellTypist official AnnData input expects log1p-normalized expression in X; "
            "the current matrix still looks count-like"
        )

    return True, "matrix is compatible with CellTypist AnnData input expectations"


def _validate_celltypist_annotations(
    adata: AnnData,
    annotation_key: str,
) -> None:
    """Run heuristic validation checks on CellTypist annotations.

    Emits warnings for:
    - Low-confidence annotations (if probability matrix is available)
    - Suspect rare cell type labels (ILC, HSC) in unexpected proportions
    - Potential RBC contamination
    - Low-complexity annotations (only 1-2 types in a large dataset)

    Parameters
    ----------
    adata
        AnnData with CellTypist annotations.
    annotation_key
        Column in ``adata.obs`` containing CellTypist labels.
    """
    if annotation_key not in adata.obs.columns:
        return

    labels = adata.obs[annotation_key]
    n_cells = adata.n_obs
    n_types = labels.nunique()
    counts = labels.value_counts()

    # --- Check 1: Low confidence ---
    prob_key = f"{annotation_key}_prob"
    if prob_key in adata.obsm:
        prob_matrix = adata.obsm[prob_key]
        if hasattr(prob_matrix, "max"):
            max_probs = prob_matrix.max(axis=1)
            if hasattr(max_probs, "values"):
                max_probs = max_probs.values
            low_conf_frac = (max_probs < 0.5).mean()
            if low_conf_frac > 0.2:
                logger.warning(
                    "CellTypist validation: %.1f%% of cells have max probability < 0.5. "
                    "Consider using a different model or checking data quality.",
                    100 * low_conf_frac,
                )

    # --- Check 2: Suspect rare labels ---
    suspect_labels = ["ILC", "HSC", "Innate lymphoid cell", "Hematopoietic stem cell"]
    for sl in suspect_labels:
        matching = [ct for ct in counts.index if sl.lower() in str(ct).lower()]
        for ct_name in matching:
            frac = counts[ct_name] / n_cells
            if frac > 0.15:
                logger.warning(
                    "CellTypist validation: '%s' accounts for %.1f%% of cells. "
                    "This is unusually high for a rare cell type — verify manually.",
                    ct_name, 100 * frac,
                )

    # --- Check 3: RBC contamination ---
    rbc_labels = ["Erythrocyte", "Red blood cell", "RBC"]
    for rl in rbc_labels:
        matching = [ct for ct in counts.index if rl.lower() in str(ct).lower()]
        for ct_name in matching:
            frac = counts[ct_name] / n_cells
            if frac > 0.05:
                logger.warning(
                    "CellTypist validation: '%s' detected at %.1f%%. "
                    "This may indicate insufficient QC filtering of red blood cells.",
                    ct_name, 100 * frac,
                )

    # --- Check 4: Low complexity ---
    if n_types <= 2 and n_cells > 1000:
        logger.warning(
            "CellTypist validation: Only %d cell types identified in %d cells. "
            "The model may be too coarse or the data may lack diversity. "
            "Consider trying a more granular model.",
            n_types, n_cells,
        )


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_annotated_umap(
    adata: AnnData,
    output_dir: Union[str, Path],
    annotation_key: str = "cell_type",
    figsize: tuple = (10, 8),
    palette: Optional[dict] = None,
) -> None:
    """Plot UMAP colored by cell type annotations.

    Saves ``figures/umap_{annotation_key}.png``.

    Parameters
    ----------
    adata
        AnnData with UMAP coordinates and annotations.
    output_dir
        Base output directory.
    annotation_key
        Column in ``adata.obs`` to color by.
    figsize
        Figure size ``(width, height)``.
    palette
        Optional dict mapping cell types to colors.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    if "X_umap" not in adata.obsm:
        logger.warning("UMAP coordinates not found. Computing UMAP ...")
        try:
            from .adata_utils import ensure_neighbors
            ensure_neighbors(adata)
            sc.tl.umap(adata)
        except Exception as exc:
            logger.warning("UMAP computation failed: %s. Skipping plot.", exc)
            return

    if annotation_key not in adata.obs.columns:
        logger.warning("Annotation key '%s' not found. Skipping UMAP plot.", annotation_key)
        return

    logger.info("Plotting annotated UMAP (color=%s) ...", annotation_key)

    n_types = adata.obs[annotation_key].nunique()

    # Adjust legend position for many cell types
    kwargs: dict = dict(
        color=annotation_key,
        show=False,
        frameon=False,
        title=annotation_key.replace("_", " ").title(),
    )
    if palette is not None:
        kwargs["palette"] = palette

    if n_types > 15:
        kwargs["legend_loc"] = "on data"
        kwargs["legend_fontsize"] = 6
        kwargs["legend_fontoutline"] = 2
    else:
        kwargs["legend_loc"] = "right margin"

    sc.pl.umap(adata, **kwargs)
    fig = plt.gcf()
    fig.set_size_inches(figsize)

    filename = f"umap_{annotation_key}.png"
    save_figure(fig, output_dir, filename)
    logger.info("Saved annotated UMAP: %s", filename)


# ---------------------------------------------------------------------------
# Annotation summary
# ---------------------------------------------------------------------------

def create_annotation_summary(
    adata: AnnData,
    output_dir: Union[str, Path],
    annotation_key: str = "cell_type",
    cluster_key: str = "leiden_0.8",
) -> pd.DataFrame:
    """Create a summary table of cell type annotations.

    Generates a table with cell type, count, percentage, associated clusters,
    and mean QC metrics per cell type. Saves to ``tables/annotation_summary.csv``.

    Parameters
    ----------
    adata
        AnnData with annotations.
    output_dir
        Base output directory.
    annotation_key
        Column in ``adata.obs`` with cell type labels.
    cluster_key
        Column in ``adata.obs`` with cluster labels.

    Returns
    -------
    pd.DataFrame
        Summary table with one row per cell type.
    """
    output_dir = Path(output_dir)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    if annotation_key not in adata.obs.columns:
        raise ValueError(
            f"Annotation key '{annotation_key}' not found in adata.obs. "
            f"Available columns: {list(adata.obs.columns)}"
        )

    logger.info("Creating annotation summary (key=%s) ...", annotation_key)

    records = []
    for ct in sorted(adata.obs[annotation_key].unique(), key=str):
        mask = adata.obs[annotation_key] == ct
        n_cells = int(mask.sum())
        pct = 100 * n_cells / adata.n_obs

        # Associated clusters
        if cluster_key in adata.obs.columns:
            clusters_in_type = sorted(
                adata.obs.loc[mask, cluster_key].unique(), key=str
            )
            clusters_str = ", ".join(str(c) for c in clusters_in_type)
        else:
            clusters_str = "N/A"

        # Mean QC metrics (if available)
        record: Dict[str, Any] = {
            "cell_type": ct,
            "n_cells": n_cells,
            "pct": round(pct, 2),
            "clusters": clusters_str,
        }

        for qc_col in ["n_genes_by_counts", "total_counts", "pct_counts_mt"]:
            if qc_col in adata.obs.columns:
                record[f"mean_{qc_col}"] = round(
                    float(adata.obs.loc[mask, qc_col].mean()), 2
                )

        records.append(record)

    summary_df = pd.DataFrame(records)
    summary_df = summary_df.sort_values("n_cells", ascending=False).reset_index(drop=True)

    summary_path = tables_dir / "annotation_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    logger.info("Saved annotation summary: %s (%d cell types)", summary_path, len(summary_df))

    return summary_df


# ---------------------------------------------------------------------------
# Sankey diagram
# ---------------------------------------------------------------------------

def plot_annotation_sankey(
    adata: AnnData,
    output_dir: Union[str, Path],
    cluster_key: str = "leiden_0.8",
    annotation_key: str = "cell_type",
    figsize: tuple = (12, 8),
) -> None:
    """Plot a Sankey diagram of cluster-to-annotation mapping.

    Uses :func:`scanpy.pl.sankey` to visualize how clusters map to
    cell type annotations.

    Saves ``figures/sankey_{cluster_key}_to_{annotation_key}.png``.

    Parameters
    ----------
    adata
        AnnData with both cluster and annotation columns.
    output_dir
        Base output directory.
    cluster_key
        Column in ``adata.obs`` with cluster labels (left side of Sankey).
    annotation_key
        Column in ``adata.obs`` with cell type labels (right side of Sankey).
    figsize
        Figure size ``(width, height)``.
    """
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    for key in [cluster_key, annotation_key]:
        if key not in adata.obs.columns:
            logger.warning("'%s' not found in adata.obs. Skipping Sankey plot.", key)
            return

    logger.info("Creating Sankey diagram (%s -> %s) ...", cluster_key, annotation_key)

    try:
        import scanpy as sc

        # Ensure categorical for scanpy sankey
        for key in [cluster_key, annotation_key]:
            if not isinstance(adata.obs[key].dtype, pd.CategoricalDtype):
                adata.obs[key] = pd.Categorical(adata.obs[key])

        sc.pl.sankey(
            adata,
            groupby=cluster_key,
            target=annotation_key,
            show=False,
        )
        fig = plt.gcf()
        fig.set_size_inches(figsize)

        filename = f"sankey_{cluster_key}_to_{annotation_key}.png"
        save_figure(fig, output_dir, filename)
        logger.info("Saved Sankey diagram: %s", filename)
    except ImportError:
        logger.warning(
            "scanpy.pl.sankey not available in this scanpy version. "
            "Falling back to confusion-matrix style visualization."
        )
        _plot_cluster_annotation_heatmap(adata, output_dir, cluster_key, annotation_key, figsize)
    except Exception as exc:
        logger.warning("Sankey plot failed: %s. Falling back to heatmap.", exc)
        _plot_cluster_annotation_heatmap(adata, output_dir, cluster_key, annotation_key, figsize)


def _plot_cluster_annotation_heatmap(
    adata: AnnData,
    output_dir: Union[str, Path],
    cluster_key: str,
    annotation_key: str,
    figsize: tuple = (12, 8),
) -> None:
    """Fallback heatmap showing cluster-to-annotation cell counts."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    ct = pd.crosstab(
        adata.obs[cluster_key],
        adata.obs[annotation_key],
        normalize="index",
    )

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        ct,
        annot=True,
        fmt=".2f",
        cmap="YlOrRd",
        ax=ax,
        linewidths=0.5,
        cbar_kws={"label": "Fraction of cells"},
    )
    ax.set_xlabel(annotation_key.replace("_", " ").title())
    ax.set_ylabel(cluster_key.replace("_", " ").title())
    ax.set_title(f"Cluster to Annotation Mapping")

    filename = f"heatmap_{cluster_key}_to_{annotation_key}.png"
    save_figure(fig, output_dir, filename)


# ---------------------------------------------------------------------------
# Cross-method comparison
# ---------------------------------------------------------------------------

def compare_annotations(
    adata: AnnData,
    output_dir: Union[str, Path],
    annotation_key1: str,
    annotation_key2: str,
) -> pd.DataFrame:
    """Compare two annotation columns via a row-normalized confusion matrix.

    Creates a confusion matrix where rows correspond to *annotation_key1*
    labels and columns to *annotation_key2* labels. Values represent the
    fraction of cells with a given label in *annotation_key1* that are
    assigned each label in *annotation_key2*.

    Saves ``tables/annotation_comparison_{key1}_vs_{key2}.csv`` and
    ``figures/annotation_comparison_{key1}_vs_{key2}.png``.

    Parameters
    ----------
    adata
        AnnData with both annotation columns.
    output_dir
        Base output directory.
    annotation_key1
        First annotation column (rows of confusion matrix).
    annotation_key2
        Second annotation column (columns of confusion matrix).

    Returns
    -------
    pd.DataFrame
        Row-normalized confusion matrix.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns
    from .viz_utils import save_figure

    output_dir = Path(output_dir)

    for key in [annotation_key1, annotation_key2]:
        if key not in adata.obs.columns:
            raise ValueError(
                f"Annotation key '{key}' not found in adata.obs. "
                f"Available columns: {list(adata.obs.columns)}"
            )

    logger.info("Comparing annotations: '%s' vs '%s'", annotation_key1, annotation_key2)

    # Build confusion matrix
    ct = pd.crosstab(
        adata.obs[annotation_key1],
        adata.obs[annotation_key2],
    )

    # Row-normalize (each row sums to 1)
    row_sums = ct.sum(axis=1)
    confusion_norm = ct.div(row_sums, axis=0)

    # Save table
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    safe1 = annotation_key1.replace("/", "_")
    safe2 = annotation_key2.replace("/", "_")
    table_path = tables_dir / f"annotation_comparison_{safe1}_vs_{safe2}.csv"
    confusion_norm.to_csv(table_path)
    logger.info("Saved comparison table: %s", table_path)

    # Also save raw counts
    raw_table_path = tables_dir / f"annotation_comparison_{safe1}_vs_{safe2}_counts.csv"
    ct.to_csv(raw_table_path)

    # Compute agreement statistics
    # Diagonal dominance = fraction of cells where both annotations agree
    # (only meaningful when labels overlap)
    common_labels = set(ct.index) & set(ct.columns)
    if common_labels:
        agree_cells = sum(ct.loc[lbl, lbl] for lbl in common_labels if lbl in ct.index and lbl in ct.columns)
        total_cells = ct.values.sum()
        agreement_pct = 100 * agree_cells / total_cells
        logger.info("  Label agreement (shared labels): %.1f%% (%d/%d cells)",
                    agreement_pct, agree_cells, total_cells)
    else:
        logger.info("  No overlapping labels between the two annotations")

    # Visualization
    fig_height = max(6, len(ct.index) * 0.4)
    fig_width = max(8, len(ct.columns) * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    sns.heatmap(
        confusion_norm,
        annot=True,
        fmt=".2f",
        cmap="YlOrRd",
        ax=ax,
        linewidths=0.5,
        cbar_kws={"label": "Fraction"},
        vmin=0,
        vmax=1,
    )
    ax.set_xlabel(annotation_key2.replace("_", " ").title())
    ax.set_ylabel(annotation_key1.replace("_", " ").title())
    ax.set_title(f"Annotation Comparison\n{annotation_key1} vs {annotation_key2}")
    plt.tight_layout()

    fig_path = f"annotation_comparison_{safe1}_vs_{safe2}.png"
    save_figure(fig, output_dir, fig_path)
    logger.info("Saved comparison heatmap: %s", fig_path)

    return confusion_norm



def build_celltypist_input_adata(adata: AnnData):
    """Return an AnnData view whose X matches CellTypist official input expectations."""
    if adata.raw is not None and adata.raw.shape == adata.shape:
        tmp = AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        tmp.obs_names = adata.obs_names.copy()
        tmp.var_names = adata.raw.var_names.copy()
        return tmp, "adata.raw"
    tmp = AnnData(X=adata.X.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    tmp.obs_names = adata.obs_names.copy()
    tmp.var_names = adata.var_names.copy()
    return tmp, "adata.X"

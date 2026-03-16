"""Pseudobulk differential expression analysis for single-cell data.

Aggregates single-cell counts to pseudobulk (sum per sample x cell type)
and runs DESeq2-based differential expression via rpy2 or pydeseq2.

Public API
----------
aggregate_to_pseudobulk
validate_pseudobulk_design
run_deseq2_analysis
export_de_results
plot_volcano
plot_ma
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np
import pandas as pd

from . import dependency_manager as dm

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pseudobulk aggregation
# ---------------------------------------------------------------------------


def aggregate_to_pseudobulk(
    adata: AnnData,
    sample_key: str,
    celltype_key: str,
    min_cells: int = 10,
    min_counts: int = 1000,
    layer: str | None = None,
) -> dict[str, Any]:
    """Aggregate single-cell counts to pseudobulk via SUM per sample x cell type.

    **Critical**: use raw counts, not normalised values.

    Parameters
    ----------
    adata : AnnData
        AnnData with raw counts.
    sample_key : str
        Column in ``adata.obs`` with sample/donor identifiers.
    celltype_key : str
        Column in ``adata.obs`` with cell-type labels.
    min_cells : int
        Minimum cells per sample-celltype combination (default 10).
    min_counts : int
        Minimum total counts per combination (default 1000).
    layer : str, optional
        Layer to aggregate (default ``None`` uses ``adata.X``).

    Returns
    -------
    dict
        ``counts`` -- genes x samples DataFrame, ``metadata`` -- sample-level
        DataFrame, ``n_cells`` -- cell counts per combination.
    """
    logger.info(
        "Aggregating to pseudobulk (sample=%s, celltype=%s) ...",
        sample_key,
        celltype_key,
    )

    if sample_key not in adata.obs.columns:
        raise ValueError(f"'{sample_key}' not found in adata.obs")
    if celltype_key not in adata.obs.columns:
        raise ValueError(f"'{celltype_key}' not found in adata.obs")

    # -- get counts -----------------------------------------------------------
    if layer is not None:
        counts = adata.layers[layer]
    else:
        counts = adata.X

    if hasattr(counts, "toarray"):
        counts = counts.toarray()

    # -- aggregate ------------------------------------------------------------
    pseudobulk_counts: dict[str, np.ndarray] = {}
    metadata_list: list[dict[str, Any]] = []

    samples = adata.obs[sample_key].unique()
    celltypes = adata.obs[celltype_key].unique()

    for sample in samples:
        for celltype in celltypes:
            mask = (adata.obs[sample_key] == sample) & (adata.obs[celltype_key] == celltype)
            n_cells = int(mask.sum())

            if n_cells < min_cells:
                continue

            summed = counts[mask.values, :].sum(axis=0)
            # ensure 1-d
            summed = np.asarray(summed).ravel()

            if summed.sum() < min_counts:
                continue

            sid = f"{sample}_{celltype}"
            pseudobulk_counts[sid] = summed
            metadata_list.append(
                {
                    "sample_celltype": sid,
                    "sample": sample,
                    "celltype": celltype,
                    "n_cells": n_cells,
                }
            )

    if not metadata_list:
        logger.warning("No sample-celltype combinations passed filters (min_cells=%d, min_counts=%d).", min_cells, min_counts)
        return {"counts": pd.DataFrame(), "metadata": pd.DataFrame(), "n_cells": pd.Series(dtype=int)}

    counts_df = pd.DataFrame(pseudobulk_counts, index=adata.var_names)
    metadata_df = pd.DataFrame(metadata_list).set_index("sample_celltype")

    logger.info(
        "Pseudobulk aggregation complete: %d combinations, %d genes, median %d cells/combination",
        counts_df.shape[1],
        counts_df.shape[0],
        int(metadata_df["n_cells"].median()),
    )

    return {
        "counts": counts_df,
        "metadata": metadata_df,
        "n_cells": metadata_df["n_cells"],
    }


# ---------------------------------------------------------------------------
# Design validation
# ---------------------------------------------------------------------------


def validate_pseudobulk_design(
    metadata: pd.DataFrame,
    contrast: list[str],
    min_replicates: int = 2,
) -> dict[str, Any]:
    """Validate experimental design for pseudobulk DE.

    Blocks on N=1 per condition (DESeq2 requires biological replicates to
    estimate dispersion) and warns when N < *min_replicates*.

    Parameters
    ----------
    metadata : DataFrame
        Sample-level metadata (must contain the contrast variable).
    contrast : list of str
        DESeq2-style contrast ``[variable, level1, level2]``.
    min_replicates : int
        Recommended minimum replicates per group (default 2).

    Returns
    -------
    dict
        ``valid`` (bool), ``condition_counts``, ``warnings``, ``errors``.
    """
    result: dict[str, Any] = {
        "valid": True,
        "condition_counts": {},
        "warnings": [],
        "errors": [],
    }

    contrast_var = contrast[0]
    if contrast_var not in metadata.columns:
        result["valid"] = False
        result["errors"].append(
            f"Contrast variable '{contrast_var}' not found in metadata.  "
            f"Available columns: {list(metadata.columns)}"
        )
        return result

    for level in contrast[1:]:
        level_mask = metadata[contrast_var] == level
        n_samples = (
            metadata.loc[level_mask, "sample"].nunique()
            if "sample" in metadata.columns
            else int(level_mask.sum())
        )
        result["condition_counts"][level] = n_samples

    for level, n in result["condition_counts"].items():
        if n < 1:
            result["valid"] = False
            result["errors"].append(f"Condition '{level}' has 0 samples.  Cannot run DE.")
        elif n == 1:
            result["valid"] = False
            result["errors"].append(
                f"Condition '{level}' has only 1 sample (N=1).  "
                "DESeq2 requires biological replicates to estimate dispersion.  "
                "Pseudobulk DE is not valid with N=1 in any group.  "
                "Options: (1) add more samples, (2) use cell-level Wilcoxon with "
                "caveats, (3) report descriptive statistics only."
            )
        elif n < min_replicates:
            result["warnings"].append(
                f"Condition '{level}' has only {n} samples.  "
                f"Minimum {min_replicates} recommended for reliable DE."
            )
        elif n < 3:
            result["warnings"].append(
                f"Condition '{level}' has {n} samples.  "
                "N>=3 per group recommended for adequate statistical power."
            )

    return result


# ---------------------------------------------------------------------------
# DESeq2 analysis
# ---------------------------------------------------------------------------


def _run_deseq2_rpy2(
    counts: pd.DataFrame,
    metadata: pd.DataFrame,
    formula: str,
    contrast: list[str],
) -> pd.DataFrame | None:
    """Run DESeq2 via rpy2 + R."""
    dm.require("rpy2", feature="DESeq2 via rpy2")

    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri as _p2r
    from rpy2.robjects.packages import importr as _importr

    _p2r.activate()
    try:
        _importr("DESeq2")
    except Exception as exc:
        raise ImportError(
            f"DESeq2 not found in R.  Install: BiocManager::install('DESeq2')\n{exc}"
        ) from exc

    r_counts = _p2r.py2rpy(counts.astype(int))
    r_metadata = _p2r.py2rpy(metadata)

    ro.globalenv["counts_matrix"] = r_counts
    ro.globalenv["col_data"] = r_metadata

    ro.r(
        f"""
    dds <- DESeqDataSetFromMatrix(
        countData = counts_matrix,
        colData = col_data,
        design = {formula}
    )
    keep <- rowSums(counts(dds) >= 10) >= 3
    dds <- dds[keep,]
    dds <- DESeq(dds, quiet=TRUE)
    """
    )

    contrast_str = f"c('{contrast[0]}', '{contrast[1]}', '{contrast[2]}')"
    ro.r(f"res <- results(dds, contrast={contrast_str})")
    ro.r(
        f"""
    res_shrunk <- lfcShrink(dds,
                            contrast={contrast_str},
                            res=res,
                            type="ashr",
                            quiet=TRUE)
    """
    )

    results_df: pd.DataFrame = _p2r.rpy2py(ro.r("as.data.frame(res_shrunk)"))
    results_df.index.name = "gene"
    results_df = results_df.reset_index()

    _p2r.deactivate()
    return results_df


def _run_deseq2_pydeseq2(
    counts: pd.DataFrame,
    metadata: pd.DataFrame,
    formula: str,
    contrast: list[str],
) -> pd.DataFrame | None:
    """Run DESeq2 via pydeseq2 (pure Python)."""
    dm.require("pydeseq2", feature="pseudobulk DE (Python)")
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    design_factors = [f.strip() for f in formula.replace("~", "").strip().split("+")]

    dds = DeseqDataSet(
        counts=counts.T.astype(int),
        metadata=metadata,
        design_factors=design_factors,
    )
    dds.deseq2()

    stat_res = DeseqStats(dds, contrast=contrast)
    stat_res.summary()

    results_df = stat_res.results_df
    results_df.index.name = "gene"
    results_df = results_df.reset_index()
    return results_df


def run_deseq2_analysis(
    pseudobulk: dict[str, pd.DataFrame],
    sample_metadata: pd.DataFrame,
    formula: str,
    contrast: list[str],
    celltype_key: str | None = None,
    output_dir: str | Path | None = None,
    use_rpy2: bool = True,
    min_replicates: int = 2,
) -> dict[str, pd.DataFrame]:
    """Run DESeq2 differential expression for each cell type.

    Validates experimental design **before** running: N=1 in any group causes
    the analysis to be aborted with an informative message.

    Parameters
    ----------
    pseudobulk : dict
        Output from :func:`aggregate_to_pseudobulk`.
    sample_metadata : DataFrame
        Sample-level metadata with a ``sample`` column matching pseudobulk
        sample identifiers, plus the contrast variable.
    formula : str
        DESeq2 design formula, e.g. ``"~ batch + condition"``.
    contrast : list of str
        ``[variable, numerator, denominator]``, e.g.
        ``["condition", "treated", "control"]``.
    celltype_key : str, optional
        Column name for cell types in pseudobulk metadata (default
        ``'celltype'``).
    output_dir : path-like, optional
        If given, results CSV files are written here.
    use_rpy2 : bool
        Use R DESeq2 via rpy2 (default ``True``).  If ``False``, uses
        pydeseq2 (pure Python).
    min_replicates : int
        Minimum biological replicates per condition (default 2).

    Returns
    -------
    dict
        Mapping cell type -> DESeq2 results DataFrame.  Empty if the design
        is invalid.
    """
    if celltype_key is None:
        celltype_key = "celltype"

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # -- design validation ----------------------------------------------------
    logger.info("Validating experimental design for pseudobulk DE ...")
    design_check = validate_pseudobulk_design(sample_metadata, contrast, min_replicates=min_replicates)

    for level, n in design_check["condition_counts"].items():
        logger.info("  %s='%s': %d sample(s)", contrast[0], level, n)
    for w in design_check["warnings"]:
        logger.warning("  %s", w)

    if not design_check["valid"]:
        for e in design_check["errors"]:
            logger.error("  %s", e)
        logger.error(
            "Pseudobulk DE aborted due to invalid design.  "
            "Use cell-level DE (Wilcoxon) for exploratory analysis with caveats."
        )
        return {}

    # -- per cell-type DE -----------------------------------------------------
    counts_df = pseudobulk["counts"]
    pb_metadata = pseudobulk["metadata"].copy()

    pb_metadata = pb_metadata.merge(sample_metadata, left_on="sample", right_on="sample", how="left")

    celltypes = pb_metadata[celltype_key].unique()
    logger.info("Running DESeq2 for %d cell types ...", len(celltypes))

    de_results: dict[str, pd.DataFrame] = {}
    contrast_var = contrast[0]

    for celltype in celltypes:
        logger.info("  Cell type: %s", celltype)
        ct_mask = pb_metadata[celltype_key] == celltype
        ct_samples = pb_metadata.index[ct_mask]
        # keep only columns present in counts_df
        ct_samples = [s for s in ct_samples if s in counts_df.columns]
        ct_counts = counts_df[ct_samples]
        ct_meta = pb_metadata.loc[ct_samples]

        n_total = ct_counts.shape[1]
        if n_total < 3:
            logger.info("    Skipping: <3 samples total")
            continue

        # per-condition check
        skip = False
        if contrast_var in ct_meta.columns:
            for level in contrast[1:]:
                n_level = int((ct_meta[contrast_var] == level).sum())
                if n_level < 2:
                    logger.info("    Skipping: '%s' has only %d sample(s) (need >=2)", level, n_level)
                    skip = True
                    break
        if skip:
            continue

        # -- run ---------------------------------------------------------------
        try:
            if use_rpy2:
                results_df = _run_deseq2_rpy2(ct_counts, ct_meta, formula, contrast)
            else:
                results_df = _run_deseq2_pydeseq2(ct_counts, ct_meta, formula, contrast)
        except Exception as exc:
            logger.error("    DESeq2 failed for %s: %s", celltype, exc)
            continue

        if results_df is not None:
            de_results[celltype] = results_df
            n_sig = int((results_df["padj"] < 0.05).sum()) if "padj" in results_df.columns else 0
            logger.info("    Significant genes (padj<0.05): %d", n_sig)

    return de_results


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_de_results(
    de_results: dict[str, pd.DataFrame],
    output_dir: str | Path,
    padj_threshold: float = 0.05,
    log2fc_threshold: float = 1.0,
) -> None:
    """Export DE results to CSV (all + significant per cell type).

    Parameters
    ----------
    de_results : dict
        Cell type -> results DataFrame.
    output_dir : path-like
        Output directory.
    padj_threshold : float
        Adjusted p-value cutoff (default 0.05).
    log2fc_threshold : float
        Absolute log2-fold-change cutoff (default 1.0).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting DE results to %s", output_dir)

    for celltype, results_df in de_results.items():
        # full results
        full_path = output_dir / f"{celltype}_deseq2_results.csv"
        results_df.to_csv(full_path, index=False)

        # significant subset
        fc_col = "log2FoldChange" if "log2FoldChange" in results_df.columns else "lfc"
        padj_col = "padj"
        if padj_col not in results_df.columns:
            logger.warning("  %s: 'padj' column missing -- skipping significance filter", celltype)
            continue

        sig_mask = (results_df[padj_col] < padj_threshold) & (results_df[fc_col].abs() > log2fc_threshold)
        sig_df = results_df[sig_mask].sort_values(padj_col)
        sig_path = output_dir / f"{celltype}_deseq2_sig.csv"
        sig_df.to_csv(sig_path, index=False)

        logger.info("  %s: %d significant genes", celltype, len(sig_df))


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_volcano(
    results_df: pd.DataFrame,
    celltype: str,
    output_dir: str | Path,
    padj_threshold: float = 0.05,
    log2fc_threshold: float = 1.0,
    top_genes: int = 10,
) -> None:
    """Create a volcano plot for DE results.

    Labels the *top_genes* most significant genes using ``adjustText`` when
    available.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    from .viz_utils import save_figure

    sns.set_style("ticks")
    output_dir = Path(output_dir)

    fc_col = "log2FoldChange" if "log2FoldChange" in results_df.columns else "lfc"

    plot_df = results_df.dropna(subset=["padj", fc_col]).copy()
    plot_df["-log10(padj)"] = -np.log10(plot_df["padj"].clip(lower=1e-300))

    plot_df["significance"] = "NS"
    sig_mask = (plot_df["padj"] < padj_threshold) & (plot_df[fc_col].abs() > log2fc_threshold)
    plot_df.loc[sig_mask, "significance"] = "Significant"

    top_df = plot_df.nsmallest(top_genes, "padj")

    fig, ax = plt.subplots(figsize=(8, 6))
    colour_map = {"NS": "#CCCCCC", "Significant": "#E31A1C"}
    for sig_type, colour in colour_map.items():
        mask = plot_df["significance"] == sig_type
        ax.scatter(
            plot_df.loc[mask, fc_col],
            plot_df.loc[mask, "-log10(padj)"],
            c=colour,
            alpha=0.5,
            s=10,
            label=sig_type,
            edgecolors="none",
        )

    ax.axhline(y=-np.log10(padj_threshold), ls="--", color="red", lw=0.8)
    ax.axvline(x=log2fc_threshold, ls="--", color="red", lw=0.8)
    ax.axvline(x=-log2fc_threshold, ls="--", color="red", lw=0.8)

    ax.set_xlabel("log2 Fold Change")
    ax.set_ylabel("-log10(adjusted p-value)")
    ax.set_title(f"Volcano Plot: {celltype}", fontweight="bold")
    ax.legend(frameon=False)
    sns.despine(ax=ax)

    # gene labels
    try:
        from adjustText import adjust_text

        gene_col = "gene" if "gene" in top_df.columns else top_df.index.name or "gene"
        texts = []
        for _, row in top_df.iterrows():
            label = row.get("gene", row.name) if "gene" in top_df.columns else row.name
            texts.append(ax.text(row[fc_col], row["-log10(padj)"], str(label), fontsize=8, alpha=0.9))
        adjust_text(
            texts,
            arrowprops=dict(arrowstyle="->", color="gray", lw=0.5, alpha=0.7),
            expand_points=(1.5, 1.5),
            force_text=(0.5, 0.5),
        )
    except ImportError:
        pass

    fig.tight_layout()
    save_figure(fig, output_dir, f"{celltype}_volcano.png")


def plot_ma(
    results_df: pd.DataFrame,
    celltype: str,
    output_dir: str | Path,
    padj_threshold: float = 0.05,
) -> None:
    """Create an MA plot for DE results."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    from .viz_utils import save_figure

    sns.set_style("ticks")
    output_dir = Path(output_dir)

    fc_col = "log2FoldChange" if "log2FoldChange" in results_df.columns else "lfc"

    plot_df = results_df.dropna(subset=["padj", fc_col, "baseMean"]).copy()
    plot_df["significance"] = "NS"
    plot_df.loc[plot_df["padj"] < padj_threshold, "significance"] = "Significant"

    fig, ax = plt.subplots(figsize=(8, 6))
    colour_map = {"NS": "#CCCCCC", "Significant": "#E31A1C"}
    for sig_type, colour in colour_map.items():
        mask = plot_df["significance"] == sig_type
        ax.scatter(
            plot_df.loc[mask, "baseMean"],
            plot_df.loc[mask, fc_col],
            c=colour,
            alpha=0.5,
            s=10,
            label=sig_type,
            edgecolors="none",
        )

    ax.axhline(y=0, ls="--", color="black", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("Mean Expression (log10)")
    ax.set_ylabel("log2 Fold Change")
    ax.set_title(f"MA Plot: {celltype}", fontweight="bold")
    ax.legend(frameon=False)
    sns.despine(ax=ax)

    fig.tight_layout()
    save_figure(fig, output_dir, f"{celltype}_ma.png")

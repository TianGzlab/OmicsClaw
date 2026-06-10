"""
DA.py — Bulk ChIP-seq Step 4: differential binding via pyDESeq2.

Consumes the consensus peak count matrix from ``bulkchip-peak-calling`` and runs
a two-condition contrast (pyDESeq2): size-factor normalization, dispersion fit,
Wald test, LFC, classification, IGV-ready BED tracks, and a volcano plot.

This mirrors ``bulkatac-DA`` — the featureCounts matrix schema is identical, so
the DESeq2 path is the same (binding intensity instead of accessibility). ChIP
peak-calling stops at the count matrix (annotation/enrichment is a separate
skill), so DA runs without an annotation merge.

Tools: pydeseq2, matplotlib (pure-Python; no subprocess).
References: DESeq2 (Love et al. 2014); pyDESeq2 https://github.com/owkin/PyDESeq2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ===========================================================================
# Result dataclass
# ===========================================================================

@dataclass
class DAResult:
    """Output of run_differential_binding()."""
    results_tsv:    Path
    up_bed:         Path | None = None
    down_bed:       Path | None = None
    all_bed:        Path | None = None
    volcano_png:    Path | None = None
    n_up:           int   = 0
    n_down:         int   = 0
    n_tested:       int   = 0
    contrast:       str   = ""
    padj_threshold: float = 0.05
    lfc_threshold:  float = 1.0


# ===========================================================================
# Differential binding (pyDESeq2)
# ===========================================================================

def run_differential_binding(
    counts_file: Path,
    sample_names: list[str],
    conditions: list[str],
    output_dir: Path,
    *,
    contrast_treat: str | None = None,
    contrast_control: str | None = None,
    annotation_tsv: Path | None = None,
    padj_threshold: float = 0.05,
    lfc_threshold: float = 1.0,
) -> DAResult:
    """
    Run differential binding analysis using pyDESeq2 on the consensus peak
    count matrix (peaks × ChIP samples).

    Parameters
    ----------
    counts_file      : featureCounts output (peaks × ChIP samples)
    sample_names     : ChIP sample names in count-matrix column order
    conditions       : condition labels matching sample_names order
    contrast_treat   : numerator condition (auto-detected if None)
    contrast_control : denominator condition (auto-detected if None)
    annotation_tsv   : optional peak annotation TSV to merge (usually None for ChIP)
    padj_threshold   : adjusted p-value threshold (default 0.05)
    lfc_threshold    : |log2FC| threshold for up/down calls (default 1.0)
    """
    try:
        import pandas as pd
        from pydeseq2.dds import DeseqDataSet
        from pydeseq2.ds import DeseqStats
    except ImportError:
        raise RuntimeError(
            "pyDESeq2 is required for differential binding. "
            "Install with:  pip install pydeseq2"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    counts, peak_info = _parse_featurecounts_with_info(counts_file)
    if counts is None:
        raise RuntimeError(f"Failed to parse count matrix: {counts_file}")

    if counts.shape[1] != len(sample_names):
        logger.warning(
            "Count matrix has %d sample columns but %d sample names provided. "
            "Check that sample order matches the featureCounts BAM input order.",
            counts.shape[1], len(sample_names),
        )

    n_peaks = counts.shape[0]
    peak_ids = [f"peak_{i+1}" for i in range(n_peaks)]

    count_df = pd.DataFrame(counts.astype(int), index=peak_ids, columns=sample_names)
    metadata = pd.DataFrame({"condition": conditions}, index=sample_names)

    unique_conds = sorted(set(conditions))
    if len(unique_conds) < 2:
        raise RuntimeError(f"DA requires >= 2 conditions, got: {unique_conds}")

    if contrast_treat is None or contrast_control is None:
        contrast_control = unique_conds[0]
        contrast_treat   = unique_conds[1]
        logger.info("Auto-detected contrast: %s vs %s", contrast_treat, contrast_control)

    contrast_name = f"{contrast_treat}_vs_{contrast_control}"

    results_tsv = output_dir / f"da_results_{contrast_name}.tsv"
    summary_csv = output_dir / f"da_summary_{contrast_name}.csv"
    up_bed_ck   = output_dir / f"da_peaks_up_{contrast_name}.bed"
    if (results_tsv.exists() and results_tsv.stat().st_size > 0
            and summary_csv.exists() and up_bed_ck.exists()):
        logger.info("DA checkpoint: %s — loading", results_tsv)
        return _load_da_checkpoint(results_tsv, output_dir, contrast_name,
                                   padj_threshold, lfc_threshold)

    logger.info("Running pyDESeq2: %s vs %s ...", contrast_treat, contrast_control)
    # pyDESeq2 renamed the design argument across versions: <0.5 takes
    # `design_factors`, >=0.5 takes an R-style `design` formula string.
    try:
        dds = DeseqDataSet(counts=count_df.T, metadata=metadata, design="~condition")
    except TypeError:
        dds = DeseqDataSet(counts=count_df.T, metadata=metadata,
                           design_factors="condition")
    dds.deseq2()

    stat_res = DeseqStats(dds, contrast=["condition", contrast_treat, contrast_control])
    stat_res.summary()

    res_df = stat_res.results_df.copy()
    res_df.index = peak_ids

    if peak_info is not None and len(peak_info) == n_peaks:
        res_df.insert(0, "chr",   [p[0] for p in peak_info])
        res_df.insert(1, "start", [p[1] for p in peak_info])
        res_df.insert(2, "end",   [p[2] for p in peak_info])

    if annotation_tsv and annotation_tsv.exists():
        logger.info("Merging DA results with annotation: %s", annotation_tsv)
        res_df = _merge_annotation(res_df, annotation_tsv)
    else:
        logger.info("No annotation merge (ChIP peak-calling stops at the count matrix)")

    res_df["direction"] = "ns"
    sig_mask = (res_df["padj"] < padj_threshold) & (res_df["log2FoldChange"].abs() >= lfc_threshold)
    res_df.loc[sig_mask & (res_df["log2FoldChange"] > 0), "direction"] = "up"
    res_df.loc[sig_mask & (res_df["log2FoldChange"] < 0), "direction"] = "down"

    n_up     = int((res_df["direction"] == "up").sum())
    n_down   = int((res_df["direction"] == "down").sum())
    n_tested = int(res_df["padj"].notna().sum())
    logger.info("  DA: %d up, %d down, %d tested (padj < %s, |log2FC| >= %s)",
                n_up, n_down, n_tested, padj_threshold, lfc_threshold)

    res_df.to_csv(results_tsv, sep="\t", float_format="%.6f")
    pd.DataFrame([{
        "contrast": contrast_name, "n_tested": n_tested, "n_up": n_up,
        "n_down": n_down, "n_ns": n_tested - n_up - n_down,
        "padj_threshold": padj_threshold, "lfc_threshold": lfc_threshold,
    }]).to_csv(summary_csv, index=False)

    up_bed = down_bed = all_bed = None
    if "chr" in res_df.columns:
        up_bed   = output_dir / f"da_peaks_up_{contrast_name}.bed"
        down_bed = output_dir / f"da_peaks_down_{contrast_name}.bed"
        all_bed  = output_dir / f"da_peaks_all_{contrast_name}.bed"
        _write_browser_bed(res_df[res_df["direction"] == "up"], up_bed,
                           contrast_name, direction="up", color="255,0,0")
        _write_browser_bed(res_df[res_df["direction"] == "down"], down_bed,
                           contrast_name, direction="down", color="0,0,255")
        _write_browser_bed_all(res_df[res_df["direction"] != "ns"], all_bed, contrast_name)

    return DAResult(
        results_tsv=results_tsv, up_bed=up_bed, down_bed=down_bed, all_bed=all_bed,
        n_up=n_up, n_down=n_down, n_tested=n_tested, contrast=contrast_name,
        padj_threshold=padj_threshold, lfc_threshold=lfc_threshold,
    )


# ===========================================================================
# Volcano plot
# ===========================================================================

def _setup_plot_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 300, "savefig.dpi": 300,
        "font.size": 10, "axes.titlesize": 12,
    })


def _save_figure(fig, name: str, output_dir: Path) -> Path:
    import matplotlib.pyplot as plt
    out_png = output_dir / f"{name}.png"
    for ext in ("pdf", "png"):
        fig.savefig(output_dir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    return out_png


def plot_volcano(da_result: DAResult, output_dir: Path) -> Path | None:
    """Volcano plot: log2FC vs -log10(padj). Significance by padj + lfc cutoff.

    padj==0 points (below DESeq2 precision) are drawn as triangles at the
    y-floor; padj==NaN (not tested) are excluded (matches n_tested).
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import pandas as pd

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(da_result.results_tsv, sep="\t", index_col=0)
    df = df.dropna(subset=["padj", "log2FoldChange", "baseMean"])
    if len(df) == 0:
        return None

    nonzero_min = df.loc[df["padj"] > 0, "padj"].min()
    if pd.isna(nonzero_min) or nonzero_min == 0:
        nonzero_min = 1e-300
    clipped      = (df["padj"] <= 0).values
    padj_floored = df["padj"].where(df["padj"] > 0, nonzero_min)
    neg_log10p   = -np.log10(padj_floored)

    p_thresh = da_result.padj_threshold
    lfc_t    = da_result.lfc_threshold
    up_mask   = ((df["padj"] < p_thresh) & (df["log2FoldChange"] >=  lfc_t)).values
    down_mask = ((df["padj"] < p_thresh) & (df["log2FoldChange"] <= -lfc_t)).values
    ns_mask   = ~(up_mask | down_mask)
    n_up, n_down, n_ns = int(up_mask.sum()), int(down_mask.sum()), int(ns_mask.sum())

    UP_CLR, DOWN_CLR, NS_CLR = "#b30000", "#4C72B0", "#999999"
    colors = np.empty(len(df), dtype=object)
    colors[up_mask] = UP_CLR; colors[down_mask] = DOWN_CLR; colors[ns_mask] = NS_CLR

    fig, ax = plt.subplots(figsize=(6, 6))
    unclipped = ~clipped
    ax.scatter(df["log2FoldChange"].values[unclipped], neg_log10p.values[unclipped],
               c=colors[unclipped], s=8, alpha=0.7, edgecolors="none", rasterized=True)
    if clipped.any():
        ax.scatter(df["log2FoldChange"].values[clipped], neg_log10p.values[clipped],
                   c=colors[clipped], s=20, alpha=0.9, marker="^",
                   edgecolors="none", rasterized=True)

    ax.axhline(-np.log10(p_thresh), color="#999999", linestyle="--", linewidth=0.8)
    ax.axvline( lfc_t, color="#999999", linestyle="--", linewidth=0.8)
    ax.axvline(-lfc_t, color="#999999", linestyle="--", linewidth=0.8)

    handles = [
        Line2D([0], [0], marker="o", linestyle="", markerfacecolor=UP_CLR,
               markeredgecolor="none", markersize=6, label=f"up (n={n_up})"),
        Line2D([0], [0], marker="o", linestyle="", markerfacecolor=DOWN_CLR,
               markeredgecolor="none", markersize=6, label=f"down (n={n_down})"),
        Line2D([0], [0], marker="o", linestyle="", markerfacecolor=NS_CLR,
               markeredgecolor="none", markersize=6, label=f"ns (n={n_ns})"),
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=8)
    ax.set_xlabel("log2 Fold Change")
    ax.set_ylabel("-log10(padj)")
    ax.set_title(f"Volcano — {da_result.contrast}")

    out_png = _save_figure(fig, f"volcano_{da_result.contrast}", output_dir)
    da_result.volcano_png = out_png

    df = df.copy()
    df["direction"] = np.where(up_mask, "up", np.where(down_mask, "down", "ns"))
    df[["baseMean", "log2FoldChange", "pvalue", "padj", "direction"]].to_csv(
        output_dir / f"volcano_{da_result.contrast}.tsv", sep="\t")
    logger.info("Volcano plot saved: %s", out_png)
    return out_png


# ===========================================================================
# Helpers
# ===========================================================================

def _parse_featurecounts_with_info(
    counts_file: Path,
) -> tuple[np.ndarray | None, list[tuple[str, int, int]] | None]:
    """Parse featureCounts output → (count_matrix, peak coords as 0-based BED)."""
    rows, info = [], []
    with open(counts_file) as f:
        for line in f:
            if line.startswith("#") or line.startswith("Geneid"):
                continue
            parts = line.strip().split("\t")
            if len(parts) > 6:
                try:
                    info.append((parts[1], int(parts[2]) - 1, int(parts[3])))
                    rows.append([int(x) for x in parts[6:]])
                except ValueError:
                    continue
    if not rows:
        return None, None
    return np.array(rows, dtype=float), info


def _merge_annotation(res_df: "pd.DataFrame", annotation_tsv: Path) -> "pd.DataFrame":
    """Merge DA results with a peak annotation TSV (exact, then ±1 offset)."""
    import pandas as pd
    ann = pd.read_csv(annotation_tsv, sep="\t")
    if ann.empty or "chr" not in res_df.columns or "peak_chr" not in ann.columns:
        return res_df
    ann_key = ann.rename(columns={"peak_chr": "chr", "peak_start": "start", "peak_end": "end"})
    ann_value_cols = [c for c in ["nearest_gene", "distance", "category",
                                  "detailed_annotation", "gene_type"] if c in ann_key.columns]
    if "nearest_gene" in ann_key.columns:
        ann_key = ann_key.rename(columns={"nearest_gene": "nearest_tss"})
        ann_value_cols = [c.replace("nearest_gene", "nearest_tss") for c in ann_value_cols]
    merge_cols = ["chr", "start", "end"]
    ann_subset = ann_key[merge_cols + ann_value_cols].drop_duplicates(subset=merge_cols)
    res_df["start"] = res_df["start"].astype(int); res_df["end"] = res_df["end"].astype(int)
    ann_subset["start"] = ann_subset["start"].astype(int)
    ann_subset["end"] = ann_subset["end"].astype(int)
    merged = res_df.merge(ann_subset, on=merge_cols, how="left")
    if ann_value_cols and merged[ann_value_cols[0]].notna().sum() > 0:
        return merged
    for offset in (1, -1):
        ao = ann_subset.copy(); ao["start"] = ao["start"] + offset
        merged = res_df.merge(ao, on=merge_cols, how="left")
        if ann_value_cols and merged[ann_value_cols[0]].notna().sum() > 0:
            return merged
    return merged


def _write_browser_bed(df: "pd.DataFrame", bed_path: Path, contrast: str,
                       *, direction: str, color: str) -> None:
    with open(bed_path, "w") as f:
        f.write(f'track name="DA_{direction}_{contrast}" '
                f'description="{direction} DA peaks ({contrast})" color={color} useScore=1\n')
        for _, row in df.iterrows():
            if "chr" not in row.index:
                continue
            score = min(int(-np.log10(max(row.get("padj", 1), 1e-300))), 1000)
            gene = str(row.get("nearest_tss", "")).strip()
            cat  = str(row.get("category", "")).strip()
            if gene and gene not in ("nan", "."):
                name = f"{gene}|{cat}_{direction}" if cat and cat != "nan" else f"{gene}_{direction}"
            else:
                name = f"{row.name}_{direction}"
            f.write(f"{row['chr']}\t{int(row['start'])}\t{int(row['end'])}\t"
                    f"{name}\t{score}\t.\t{int(row['start'])}\t{int(row['end'])}\t{color}\n")


def _write_browser_bed_all(df: "pd.DataFrame", bed_path: Path, contrast: str) -> None:
    with open(bed_path, "w") as f:
        f.write(f'track name="DA_all_{contrast}" description="All DA peaks ({contrast})" '
                f'itemRgb=On useScore=1\n')
        for _, row in df.iterrows():
            if "chr" not in row.index:
                continue
            direction = row.get("direction", "da")
            color = "255,0,0" if direction == "up" else "0,0,255"
            score = min(int(-np.log10(max(row.get("padj", 1), 1e-300))), 1000)
            gene = str(row.get("nearest_tss", "")).strip()
            cat  = str(row.get("category", "")).strip()
            if gene and gene not in ("nan", "."):
                name = f"{gene}|{cat}_{direction}" if cat and cat != "nan" else f"{gene}_{direction}"
            else:
                name = f"{row.name}_{direction}"
            f.write(f"{row['chr']}\t{int(row['start'])}\t{int(row['end'])}\t"
                    f"{name}\t{score}\t.\t{int(row['start'])}\t{int(row['end'])}\t{color}\n")


def _load_da_checkpoint(results_tsv: Path, output_dir: Path, contrast_name: str,
                        padj_threshold: float, lfc_threshold: float) -> DAResult:
    import pandas as pd
    df = pd.read_csv(results_tsv, sep="\t", index_col=0)
    sig = (df["padj"] < padj_threshold) & (df["log2FoldChange"].abs() >= lfc_threshold)
    n_up     = int((sig & (df["log2FoldChange"] > 0)).sum())
    n_down   = int((sig & (df["log2FoldChange"] < 0)).sum())
    n_tested = int(df["padj"].notna().sum())
    up_bed   = output_dir / f"da_peaks_up_{contrast_name}.bed"
    down_bed = output_dir / f"da_peaks_down_{contrast_name}.bed"
    all_bed  = output_dir / f"da_peaks_all_{contrast_name}.bed"
    logger.info("  DA checkpoint: %d up, %d down, %d tested", n_up, n_down, n_tested)
    return DAResult(
        results_tsv=results_tsv,
        up_bed=up_bed if up_bed.exists() else None,
        down_bed=down_bed if down_bed.exists() else None,
        all_bed=all_bed if all_bed.exists() else None,
        n_up=n_up, n_down=n_down, n_tested=n_tested, contrast=contrast_name,
        padj_threshold=padj_threshold, lfc_threshold=lfc_threshold,
    )

"""
QC_after_peak_calling.py — Post-peak-calling QC and visualization
                                   for bulk ATAC-seq.

Per-sample:  FRiP (Fraction of Reads in Peaks).
Cross-sample: TSS heatmap, peak-centered heatmap, PCA, sample correlation.

Metrics
-------
  FRiP (Fraction of Reads in Peaks)
    = reads falling within called peaks / total usable reads
    ENCODE preferred > 0.3, acceptable > 0.2.

Visualizations
--------------
  1. TSS heatmap (deepTools plotHeatmap)
     computeMatrix reference-point --referencePoint TSS -R <gtf>
     Per-sample + all-samples combined.

  2. Peak-centered heatmap
     computeMatrix reference-point --referencePoint center -R <consensus.bed>
     Per-sample + all-samples combined.

  3. PCA on peak count matrix
     DESeq2 VST normalisation (pyDESeq2 required).

  4. Sample correlation heatmap
     Pairwise Pearson/Spearman on normalised peak counts.

Dependencies
------------
  - Step 2 outputs: BigWigs, BAMs, GTF (from GenomeFiles)
  - Step 3a outputs: consensus peaks BED, per-sample peaks, count matrix

References
----------
  ENCODE ATAC-seq : https://www.encodeproject.org/atac-seq/
  deepTools       : https://github.com/deeptools/deepTools
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


# ===========================================================================
# Constants
# ===========================================================================

_TSS_EXTEND  = 2000
_TSS_BINSIZE = 10

_ENCODE_FRIP_THRESHOLDS = {
    "preferred":  0.3,
    "acceptable": 0.2,
}


# ===========================================================================
# Result dataclass
# ===========================================================================

@dataclass
class QcAfterPeakCallingResult:
    """Output of run_qc_after_peak_calling() for one sample."""
    sample_name: str
    frip:        float = 0.0
    frip_tier:   str   = ""
    n_reads_in_peaks: int = 0
    n_usable_reads:   int = 0


# ===========================================================================
# Tool helpers
# ===========================================================================

def _check_tool(tool: str) -> bool:
    return shutil.which(tool) is not None


def _require(tool: str) -> None:
    if not _check_tool(tool):
        raise RuntimeError(
            f"Required tool '{tool}' not found in PATH. "
            f"Install with: conda install -c bioconda {tool}"
        )


def _run(cmd: list[str], *, label: str) -> subprocess.CompletedProcess:
    logger.info("  CMD [%s]: %s", label, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(
            f"[{label}] failed (exit {result.returncode}):\n"
            f"  stderr: {result.stderr[:500]}"
        )
    return result


def _save_figure(fig, name: str, output_dir: Path) -> None:
    import matplotlib.pyplot as plt
    for ext in ("pdf", "png"):
        fig.savefig(output_dir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


def _setup_plot_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.size": 10,
        "axes.titlesize": 12,
    })


# ===========================================================================
# FRiP (Fraction of Reads in Peaks)
# ===========================================================================

def compute_frip(
    sample_name: str,
    bam: Path,
    peaks_bed: Path,
    *,
    n_usable: int = 0,
    is_paired: bool = True,
) -> QcAfterPeakCallingResult:
    """
    Compute FRiP for one sample.

    FRiP = fragments overlapping peaks / total usable fragments.

    Both numerator and denominator are in **fragment** units (not reads)
    so the metric is consistent for PE data.  ``samtools view -c`` returns
    reads; for PE we divide by 2 to get fragments.

    Note: FRiP is computed against the peak set passed in (typically the
    consensus peak set, not per-sample peaks).  This is the standard
    approach used by DiffBind and ensures all samples are measured against
    the same feature set.
    """
    _require("samtools")

    read_mult = 2 if is_paired else 1

    # Get total usable fragments if not provided
    if n_usable <= 0:
        result = _run(
            ["samtools", "view", "-c", "-F", "4", str(bam)],
            label=f"samtools count [{sample_name}]",
        )
        n_usable = int(result.stdout.strip()) // read_mult

    # Count reads in peaks, convert to fragments
    result = _run(
        ["samtools", "view", "-c", "-L", str(peaks_bed), str(bam)],
        label=f"reads in peaks [{sample_name}]",
    )
    n_reads_in_peaks = int(result.stdout.strip())
    n_frags_in_peaks = n_reads_in_peaks // read_mult

    frip = n_frags_in_peaks / n_usable if n_usable > 0 else 0.0
    tier = _frip_tier(frip)

    logger.info("  [%s] FRiP = %.3f (%s)  [%d / %d fragments]",
                sample_name, frip, tier, n_frags_in_peaks, n_usable)

    return QcAfterPeakCallingResult(
        sample_name=sample_name,
        frip=frip,
        frip_tier=tier,
        n_reads_in_peaks=n_frags_in_peaks,
        n_usable_reads=n_usable,
    )


def _frip_tier(frip: float) -> str:
    if frip >= _ENCODE_FRIP_THRESHOLDS["preferred"]:
        return "preferred"
    elif frip >= _ENCODE_FRIP_THRESHOLDS["acceptable"]:
        return "acceptable"
    else:
        return "below"


# ===========================================================================
# TSS heatmap (deepTools)
# ===========================================================================

def plot_tss_heatmap(
    bigwig_paths: list[Path],
    sample_names: list[str],
    gtf: Path,
    output_dir: Path,
    *,
    extend: int = _TSS_EXTEND,
    bin_size: int = _TSS_BINSIZE,
    threads: int = 8,
) -> None:
    """
    TSS heatmap via deepTools.

    Works for both per-sample (1 bigwig) and all-samples (N bigwigs).
    File naming: single sample → {sample}.tss_heatmap.{ext},
                 multiple samples → tss_heatmap_all.{ext}.
    """
    if not bigwig_paths or not gtf or not Path(gtf).exists():
        return
    if not _check_tool("computeMatrix") or not _check_tool("plotHeatmap"):
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    is_single = len(bigwig_paths) == 1
    tag = sample_names[0] if is_single else "all"
    prefix = f"{sample_names[0]}.tss_heatmap" if is_single else "tss_heatmap_all"

    matrix_gz = output_dir / f"tss_heatmap_matrix_{tag}.gz"
    out_pdf   = output_dir / f"{prefix}.pdf"
    out_png   = output_dir / f"{prefix}.png"

    # Checkpoint — skip if all final outputs exist
    if matrix_gz.exists() and out_pdf.exists() and out_png.exists():
        logger.info("TSS heatmap checkpoint [%s] — skipping", tag)
        return

    # Write to temp files, rename on success to avoid corrupted outputs
    tmp_matrix = output_dir / f".tmp_tss_matrix_{tag}.gz"
    tmp_pdf    = output_dir / f".tmp_{prefix}.pdf"
    tmp_png    = output_dir / f".tmp_{prefix}.png"

    # computeMatrix
    cm_cmd = [
        "computeMatrix", "reference-point",
        "-S"] + [str(bw) for bw in bigwig_paths] + [
        "-R", str(gtf),
        "--referencePoint", "TSS",
        "-b", str(extend), "-a", str(extend),
        "--binSize", str(bin_size),
        "-o", str(tmp_matrix),
        "-p", str(threads),
        "--skipZeros",
        "--sortRegions", "descend",
        "--sortUsing", "mean",
    ]
    _run(cm_cmd, label="computeMatrix TSS heatmap")

    # plotHeatmap — PDF + PNG
    heatmap_width = "4" if len(sample_names) <= 2 else "3"
    for tmp_path in (tmp_pdf, tmp_png):
        _run(
            ["plotHeatmap",
             "-m", str(tmp_matrix),
             "-out", str(tmp_path),
             "--samplesLabel"] + sample_names + [
             "--whatToShow", "plot, heatmap and colorbar",
             "--regionsLabel", "",
             "--legendLocation", "none",
             "--heatmapHeight", "12",
             "--heatmapWidth", heatmap_width,
             "--dpi", "300",
             "--refPointLabel", "TSS",
             "--xAxisLabel", "",],
            label=f"plotHeatmap TSS ({tmp_path.suffix})",
        )

    # Atomically move to final paths
    tmp_matrix.rename(matrix_gz)
    tmp_pdf.rename(out_pdf)
    tmp_png.rename(out_png)

    logger.info("TSS heatmap saved: %s", output_dir)


# ===========================================================================
# Peak-centered heatmap (deepTools)
# ===========================================================================

def plot_peak_heatmap(
    bigwig_paths: list[Path],
    sample_names: list[str],
    consensus_bed: Path,
    output_dir: Path,
    *,
    extend: int = 2000,
    bin_size: int = 10,
    threads: int = 8,
) -> None:
    """
    Peak-centered heatmap via deepTools.

    Works for both per-sample (1 bigwig) and all-samples (N bigwigs).
    File naming: single sample → {sample}.peak_heatmap.{ext},
                 multiple samples → peak_heatmap_all.{ext}.
    """
    if not bigwig_paths or not consensus_bed.exists():
        return
    if not _check_tool("computeMatrix") or not _check_tool("plotHeatmap"):
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    is_single = len(bigwig_paths) == 1
    tag = sample_names[0] if is_single else "all"

    matrix_gz = output_dir / f"peak_heatmap_matrix_{tag}.gz"
    prefix    = "peak_heatmap_all" if not is_single else f"{sample_names[0]}.peak_heatmap"
    out_pdf   = output_dir / f"{prefix}.pdf"
    out_png   = output_dir / f"{prefix}.png"

    # Checkpoint — skip if all final outputs exist
    if matrix_gz.exists() and out_pdf.exists() and out_png.exists():
        logger.info("Peak heatmap checkpoint [%s] — skipping", tag)
        return

    # Write to temp files, rename on success to avoid corrupted outputs
    tmp_matrix = output_dir / f".tmp_peak_matrix_{tag}.gz"
    tmp_pdf    = output_dir / f".tmp_{prefix}.pdf"
    tmp_png    = output_dir / f".tmp_{prefix}.png"

    cm_cmd = [
        "computeMatrix", "reference-point",
        "-S"] + [str(bw) for bw in bigwig_paths] + [
        "-R", str(consensus_bed),
        "--referencePoint", "center",
        "-b", str(extend), "-a", str(extend),
        "--binSize", str(bin_size),
        "-o", str(tmp_matrix),
        "-p", str(threads),
        "--skipZeros",
        "--sortRegions", "descend",
        "--sortUsing", "mean",
    ]
    _run(cm_cmd, label=f"computeMatrix peak heatmap [{tag}]")

    heatmap_width = "4" if is_single else "3"

    for tmp_path in (tmp_pdf, tmp_png):
        cmd = [
            "plotHeatmap",
            "-m", str(tmp_matrix),
            "-out", str(tmp_path),
            "--samplesLabel"] + sample_names + [
            "--whatToShow", "plot, heatmap and colorbar",
            "--regionsLabel", "Peaks",
            "--legendLocation", "none",
            "--heatmapHeight", "12",
            "--heatmapWidth", heatmap_width,
            "--dpi", "300",
            "--refPointLabel", "Peak",
            "--xAxisLabel", "",
        ]
        _run(cmd, label=f"plotHeatmap peaks [{tag}] ({tmp_path.suffix})")

    # Atomically move to final paths
    tmp_matrix.rename(matrix_gz)
    tmp_pdf.rename(out_pdf)
    tmp_png.rename(out_png)

    logger.info("Peak heatmap [%s] saved: %s", tag, output_dir)


# ===========================================================================
# Count normalisation (DESeq2 VST via pyDESeq2)
# ===========================================================================

def _normalise_counts(
    counts: np.ndarray,
    sample_names: list[str],
    conditions: list[str],
) -> tuple[np.ndarray, str]:
    """
    Normalise a raw count matrix (peaks × samples) using DESeq2 VST.

    Requires pyDESeq2.  Raises RuntimeError if not installed.

    References
    ----------
      DESeq2 VST : Love et al. 2014 https://doi.org/10.1186/s13059-014-0550-8
      pyDESeq2   : https://github.com/owkin/PyDESeq2

    Returns (normalised_matrix, "VST").
    """
    try:
        import pandas as pd
        from pydeseq2.dds import DeseqDataSet
    except ImportError:
        raise RuntimeError(
            "pyDESeq2 is required for PCA and sample correlation "
            "(DESeq2 VST normalisation). Install with:\n"
            "  pip install pydeseq2"
        )

    # Rows = peaks, columns = samples → transpose for pyDESeq2 (samples × peaks)
    peak_ids = [f"peak_{i}" for i in range(counts.shape[0])]
    count_df = pd.DataFrame(
        counts.astype(int),
        index=peak_ids,
        columns=sample_names,
    )
    metadata = pd.DataFrame(
        {"condition": conditions},
        index=sample_names,
    )
    # pyDESeq2 expects samples × genes (rows = samples, columns = genes).
    # The design argument was renamed across versions: <0.5 takes
    # `design_factors` (the factor column name), >=0.5 takes `design`
    # (an R-style formula string). Try the modern API, fall back.
    try:
        dds = DeseqDataSet(counts=count_df.T, metadata=metadata, design="~condition")
    except TypeError:
        dds = DeseqDataSet(counts=count_df.T, metadata=metadata,
                           design_factors="condition")
    dds.vst()
    vst_matrix = dds.layers["vst_counts"].T   # samples × peaks → peaks × samples
    logger.info("Normalisation: DESeq2 VST (pyDESeq2)")
    return np.array(vst_matrix), "VST"


# ===========================================================================
# PCA on peak counts
# ===========================================================================

def plot_pca(
    counts_file: Path,
    sample_names: list[str],
    conditions: list[str],
    output_dir: Path,
) -> None:
    """
    PCA on normalised peak count matrix.

    Uses DESeq2 VST (pyDESeq2 required). Colours samples by condition.
    """
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse featureCounts output (skip header comments, first 6 columns are annotation)
    counts = _parse_featurecounts(counts_file)
    if counts is None or counts.shape[1] < 2:
        logger.warning("PCA requires >= 2 samples — skipping")
        return

    # Normalise
    norm_data, norm_method = _normalise_counts(counts, sample_names, conditions)

    # PCA
    pca = PCA(n_components=min(2, norm_data.shape[1]))
    coords = pca.fit_transform(norm_data.T)  # samples × components

    # Plot
    fig, ax = plt.subplots(figsize=(6, 6))

    unique_conds = sorted(set(conditions))
    # Distinct, color-blind-friendly palette
    _PALETTE = [
        "#4C72B0", "#DD8452", "#55A868", "#C44E52",
        "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
        "#CCB974", "#64B5CD",
    ]
    cond_colors = {c: _PALETTE[i % len(_PALETTE)] for i, c in enumerate(unique_conds)}

    for i, (name, cond) in enumerate(zip(sample_names, conditions)):
        ax.scatter(coords[i, 0], coords[i, 1],
                   color=cond_colors[cond], s=120, edgecolors="black",
                   linewidth=0.6, zorder=3)
        ax.annotate(name, (coords[i, 0], coords[i, 1]),
                    fontsize=8, ha="left", va="bottom",
                    xytext=(6, 6), textcoords="offset points")

    # Legend
    for cond in unique_conds:
        ax.scatter([], [], color=cond_colors[cond], s=120, label=cond,
                   edgecolors="black", linewidth=0.6)

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)")
    if pca.n_components_ >= 2:
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)")
    ax.set_title(f"PCA — Peak accessibility ({norm_method})")
    ax.legend(loc="best", frameon=False)

    _save_figure(fig, "pca_peaks", output_dir)

    # Save data for user re-plotting
    data_file = output_dir / "pca_peaks.tsv"
    with open(data_file, "w") as f:
        f.write("sample\tcondition\tPC1\tPC2\n")
        for i, (name, cond) in enumerate(zip(sample_names, conditions)):
            pc2 = coords[i, 1] if pca.n_components_ >= 2 else 0.0
            f.write(f"{name}\t{cond}\t{coords[i, 0]:.6f}\t{pc2:.6f}\n")
        f.write(f"# PC1_variance_explained={pca.explained_variance_ratio_[0]:.6f}\n")
        if pca.n_components_ >= 2:
            f.write(f"# PC2_variance_explained={pca.explained_variance_ratio_[1]:.6f}\n")
        f.write(f"# normalisation={norm_method}\n")
    logger.info("PCA data saved: %s", data_file)


# ===========================================================================
# Sample correlation heatmap
# ===========================================================================

def plot_sample_correlation(
    counts_file: Path,
    sample_names: list[str],
    output_dir: Path,
    *,
    conditions: list[str] | None = None,
    method: str = "pearson",
) -> None:
    """
    Pairwise sample correlation heatmap on normalised peak counts.

    Uses DESeq2 VST (pyDESeq2 required).
    """
    import matplotlib.pyplot as plt

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    counts = _parse_featurecounts(counts_file)
    if counts is None or counts.shape[1] < 2:
        return

    conds = conditions if conditions else [""] * len(sample_names)
    norm_data, norm_method = _normalise_counts(counts, sample_names, conds)

    # Correlation matrix
    import pandas as pd
    df = pd.DataFrame(norm_data, columns=sample_names)
    corr = df.corr(method=method)

    fig, ax = plt.subplots(figsize=(6, 6))
    im = ax.imshow(corr.values, cmap="RdYlBu_r", vmin=0.5, vmax=1.0)
    ax.set_xticks(range(len(sample_names)))
    ax.set_yticks(range(len(sample_names)))
    ax.set_xticklabels(sample_names, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(sample_names, fontsize=8)

    # Annotate
    for i in range(len(sample_names)):
        for j in range(len(sample_names)):
            ax.text(j, i, f"{corr.values[i, j]:.2f}",
                    ha="center", va="center", fontsize=7,
                    color="white" if corr.values[i, j] < 0.75 else "black")

    fig.colorbar(im, ax=ax, label=f"{method.capitalize()} correlation")
    ax.set_title(f"Sample correlation ({method}, {norm_method})")

    _save_figure(fig, f"sample_correlation_{method}", output_dir)

    # Save correlation matrix for user re-plotting
    data_file = output_dir / f"sample_correlation_{method}.tsv"
    corr.to_csv(data_file, sep="\t", float_format="%.6f")
    logger.info("Correlation data saved: %s", data_file)


# ===========================================================================
# FRiP bar chart
# ===========================================================================

def plot_frip_bar(
    qc_results: list[QcAfterPeakCallingResult],
    output_dir: Path,
) -> None:
    """Bar chart of FRiP per sample with ENCODE threshold lines."""
    import matplotlib.pyplot as plt

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    names  = [r.sample_name for r in qc_results]
    frips  = [r.frip for r in qc_results]

    # Darker, more saturated tier colours
    colors = []
    for f in frips:
        if f >= _ENCODE_FRIP_THRESHOLDS["preferred"]:
            colors.append("#1a7a1a")     # dark green
        elif f >= _ENCODE_FRIP_THRESHOLDS["acceptable"]:
            colors.append("#cc6600")     # dark orange
        else:
            colors.append("#b30000")     # dark red

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.bar(names, frips, color=colors, edgecolor="black", linewidth=0.5, width=0.6)

    ax.axhline(_ENCODE_FRIP_THRESHOLDS["preferred"], color="#1a7a1a",
               linestyle="--", linewidth=1.0, label="Preferred (>0.3)")
    ax.axhline(_ENCODE_FRIP_THRESHOLDS["acceptable"], color="#cc6600",
               linestyle="--", linewidth=1.0, label="Acceptable (>0.2)")

    ax.set_ylabel("FRiP")
    ax.set_title("Fraction of Reads in Peaks")
    ax.legend(loc="upper right", frameon=False)
    if len(names) > 6:
        ax.tick_params(axis="x", rotation=45)

    _save_figure(fig, "frip_bar", output_dir)

    # Save data for user re-plotting
    data_file = output_dir / "frip_bar.tsv"
    with open(data_file, "w") as f:
        f.write("sample\tfrip\ttier\n")
        for r in qc_results:
            f.write(f"{r.sample_name}\t{r.frip:.4f}\t{r.frip_tier}\n")
    logger.info("FRiP data saved: %s", data_file)


# ===========================================================================
# ENCODE IDR (Irreproducible Discovery Rate)
# ===========================================================================

@dataclass
class IDRResult:
    """Output of run_idr_analysis() for one condition."""
    condition:              str
    n_true_rep_peaks:       int   = 0     # IDR peaks from true replicates
    n_pooled_pseudo_peaks:  int   = 0     # IDR peaks from pooled pseudo-reps
    n_self_pseudo_peaks:    list  = field(default_factory=list)  # per-rep self-pseudo IDR peaks
    rescue_ratio:           float = 0.0
    self_consistency_ratio: float = 0.0
    rescue_pass:            bool  = False
    self_consistency_pass:  bool  = False
    overall_pass:           bool  = False
    idr_peaks_bed:          Path | None = None   # final IDR-filtered peak set


def run_idr_analysis(
    condition: str,
    replicate_bams: list[Path],
    replicate_peaks: list[Path],
    genome_size: str,
    output_dir: Path,
    *,
    is_paired: bool = True,
    idr_threshold: float = 0.05,
    macs2_qvalue: float = 0.01,
    threads: int = 8,
) -> IDRResult:
    """
    Full ENCODE IDR analysis for one condition.

    Steps:
      1. Pool replicate BAMs → call peaks on pooled
      2. Create self-pseudo-replicates (split each rep BAM in half)
      3. Create pooled pseudo-replicates (pool all → split in half)
      4. Call peaks on all pseudo-replicates
      5. Run IDR:
         a. True replicates (rep1 peaks vs rep2 peaks)
         b. Self-pseudo-replicates (for each rep)
         c. Pooled pseudo-replicates
      6. Compute rescue ratio + self-consistency ratio

    Parameters
    ----------
    condition        : condition name (e.g. "T0")
    replicate_bams   : list of full-depth dedup BAMs for this condition
    replicate_peaks  : list of narrowPeak files for this condition
                       (called with relaxed threshold, e.g. -p 0.01)
    genome_size      : MACS2 -g parameter
    output_dir       : directory for IDR output
    idr_threshold    : IDR threshold (default 0.05)
    macs2_qvalue     : q-value for peak calling on pooled/pseudo BAMs
    threads          : number of threads for samtools
    """
    _require("samtools")
    _require("macs2")
    output_dir.mkdir(parents=True, exist_ok=True)

    n_reps = len(replicate_bams)
    if n_reps < 2:
        logger.warning("  [%s] IDR requires >= 2 replicates — skipping", condition)
        return IDRResult(condition=condition)

    # ── Checkpoint: skip if IDR summary already exists ────────────────────
    summary_file = output_dir / f"{condition}_idr_summary.tsv"
    true_idr     = output_dir / f"{condition}_true_rep_idr.txt"
    if summary_file.exists() and summary_file.stat().st_size > 0:
        logger.info("  [%s] IDR checkpoint — loading cached result", condition)
        metrics: dict[str, Any] = {}
        n_self_list: list[int] = []
        with open(summary_file) as f:
            next(f)  # header
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    metrics[parts[0]] = parts[1]
        n_true   = int(metrics.get("n_true_rep_idr_peaks", 0))
        n_pooled = int(metrics.get("n_pooled_pseudo_idr_peaks", 0))
        for i in range(n_reps):
            n_self_list.append(int(metrics.get(f"n_self_pseudo_rep{i+1}_idr_peaks", 0)))
        rescue_ratio = float(metrics.get("rescue_ratio", 0))
        sc_ratio     = float(metrics.get("self_consistency_ratio", 0))
        rescue_pass  = rescue_ratio < 2.0
        sc_pass      = sc_ratio < 2.0
        return IDRResult(
            condition=condition,
            n_true_rep_peaks=n_true,
            n_pooled_pseudo_peaks=n_pooled,
            n_self_pseudo_peaks=n_self_list,
            rescue_ratio=rescue_ratio,
            self_consistency_ratio=sc_ratio,
            rescue_pass=rescue_pass,
            self_consistency_pass=sc_pass,
            overall_pass=rescue_pass and sc_pass,
            idr_peaks_bed=true_idr if true_idr.exists() else None,
        )

    fmt = "BAMPE" if is_paired else "BAM"

    # ── 1. Pool replicate BAMs ────────────────────────────────────────────
    pooled_bam = output_dir / f"{condition}_pooled.bam"
    if not pooled_bam.exists():
        _run(
            ["samtools", "merge", "-@", str(threads),
             str(pooled_bam)] + [str(b) for b in replicate_bams],
            label=f"samtools merge [{condition}]",
        )
        _run(["samtools", "index", "-@", str(threads), str(pooled_bam)],
             label=f"samtools index pooled [{condition}]")

    # Call peaks on pooled
    pooled_peaks = output_dir / f"{condition}_pooled_peaks.narrowPeak"
    if not pooled_peaks.exists():
        _run_macs2(f"{condition}_pooled", pooled_bam, output_dir,
                   fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)

    # ── 2. Self-pseudo-replicates (split each rep in half) ────────────────
    self_pseudo_peaks: list[list[Path]] = []
    for i, bam in enumerate(replicate_bams):
        rep_name = f"{condition}_rep{i+1}"
        pr1_bam = output_dir / f"{rep_name}_selfpr1.bam"
        pr2_bam = output_dir / f"{rep_name}_selfpr2.bam"

        if not pr1_bam.exists() or not pr2_bam.exists():
            _split_bam(bam, pr1_bam, pr2_bam, threads=threads)

        # Call peaks on each half
        pr1_peaks = output_dir / f"{rep_name}_selfpr1_peaks.narrowPeak"
        pr2_peaks = output_dir / f"{rep_name}_selfpr2_peaks.narrowPeak"
        if not pr1_peaks.exists():
            _run_macs2(f"{rep_name}_selfpr1", pr1_bam, output_dir,
                       fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)
        if not pr2_peaks.exists():
            _run_macs2(f"{rep_name}_selfpr2", pr2_bam, output_dir,
                       fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)

        self_pseudo_peaks.append([pr1_peaks, pr2_peaks])

    # ── 3. Pooled pseudo-replicates (pool all → split in half) ────────────
    ppr1_bam = output_dir / f"{condition}_pooledpr1.bam"
    ppr2_bam = output_dir / f"{condition}_pooledpr2.bam"
    if not ppr1_bam.exists() or not ppr2_bam.exists():
        _split_bam(pooled_bam, ppr1_bam, ppr2_bam, threads=threads)

    ppr1_peaks = output_dir / f"{condition}_pooledpr1_peaks.narrowPeak"
    ppr2_peaks = output_dir / f"{condition}_pooledpr2_peaks.narrowPeak"
    if not ppr1_peaks.exists():
        _run_macs2(f"{condition}_pooledpr1", ppr1_bam, output_dir,
                   fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)
    if not ppr2_peaks.exists():
        _run_macs2(f"{condition}_pooledpr2", ppr2_bam, output_dir,
                   fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)

    # ── 4. Re-call true replicate peaks with relaxed threshold ──────────
    # IDR requires all peak sets called with the same relaxed threshold.
    # The main pipeline peaks use the user's --qvalue (e.g. 0.05), but
    # IDR needs a mix of real and noise peaks to fit its mixture model.
    relaxed_rep_peaks: list[Path] = []
    for i, bam in enumerate(replicate_bams):
        rep_name = f"{condition}_rep{i+1}_relaxed"
        rp = output_dir / f"{rep_name}_peaks.narrowPeak"
        if not rp.exists():
            _run_macs2(rep_name, bam, output_dir,
                       fmt=fmt, genome_size=genome_size, qvalue=macs2_qvalue,
                       is_paired=is_paired)
        relaxed_rep_peaks.append(rp)

    # ── 5. Run IDR ────────────────────────────────────────────────────────
    # 5a. True replicates (relaxed peaks, first two reps)
    true_idr = output_dir / f"{condition}_true_rep_idr.txt"
    n_true = _run_idr(
        relaxed_rep_peaks[0], relaxed_rep_peaks[1],
        true_idr, idr_threshold=idr_threshold,
        label=f"{condition} true-rep",
    )

    # 4b. Self-pseudo-replicates
    n_self_list = []
    for i, (pr1_pk, pr2_pk) in enumerate(self_pseudo_peaks):
        self_idr = output_dir / f"{condition}_rep{i+1}_self_idr.txt"
        n_self = _run_idr(
            pr1_pk, pr2_pk,
            self_idr, idr_threshold=idr_threshold,
            label=f"{condition} rep{i+1} self-pseudo",
        )
        n_self_list.append(n_self)

    # 4c. Pooled pseudo-replicates
    pooled_idr = output_dir / f"{condition}_pooled_pseudo_idr.txt"
    n_pooled = _run_idr(
        ppr1_peaks, ppr2_peaks,
        pooled_idr, idr_threshold=idr_threshold,
        label=f"{condition} pooled-pseudo",
    )

    # ── 5. Compute ratios ─────────────────────────────────────────────────
    # Rescue ratio = max(N_t, N_p) / min(N_t, N_p)
    n_rescue = max(n_true, n_pooled)
    n_min    = min(n_true, n_pooled)
    rescue_ratio = n_rescue / n_min if n_min > 0 else float("inf")

    # Self-consistency ratio = max(N_self) / min(N_self)
    if len(n_self_list) >= 2:
        sc_max = max(n_self_list)
        sc_min = min(n_self_list)
        self_consistency_ratio = sc_max / sc_min if sc_min > 0 else float("inf")
    else:
        self_consistency_ratio = 0.0

    rescue_pass = rescue_ratio < 2.0
    sc_pass     = self_consistency_ratio < 2.0
    overall     = rescue_pass and sc_pass

    logger.info(
        "  [%s] IDR: N_t=%d  N_p=%d  rescue=%.2f (%s)  "
        "self-consistency=%.2f (%s)  overall=%s",
        condition, n_true, n_pooled,
        rescue_ratio, "PASS" if rescue_pass else "FAIL",
        self_consistency_ratio, "PASS" if sc_pass else "FAIL",
        "PASS" if overall else "FAIL",
    )

    # Save summary
    summary_file = output_dir / f"{condition}_idr_summary.tsv"
    with open(summary_file, "w") as f:
        f.write("metric\tvalue\tpass\n")
        f.write(f"n_true_rep_idr_peaks\t{n_true}\t\n")
        f.write(f"n_pooled_pseudo_idr_peaks\t{n_pooled}\t\n")
        for i, n in enumerate(n_self_list):
            f.write(f"n_self_pseudo_rep{i+1}_idr_peaks\t{n}\t\n")
        f.write(f"rescue_ratio\t{rescue_ratio:.4f}\t{'PASS' if rescue_pass else 'FAIL'}\n")
        f.write(f"self_consistency_ratio\t{self_consistency_ratio:.4f}\t{'PASS' if sc_pass else 'FAIL'}\n")
        f.write(f"overall\t\t{'PASS' if overall else 'FAIL'}\n")

    # Cleanup intermediate BAMs (keep peaks and IDR results)
    for f_path in [pooled_bam, Path(str(pooled_bam) + ".bai"),
                   ppr1_bam, ppr2_bam,
                   Path(str(ppr1_bam) + ".bai"), Path(str(ppr2_bam) + ".bai")]:
        if f_path.exists():
            f_path.unlink()
    for i in range(n_reps):
        for suffix in ["_selfpr1.bam", "_selfpr2.bam",
                        "_selfpr1.bam.bai", "_selfpr2.bam.bai"]:
            p = output_dir / f"{condition}_rep{i+1}{suffix}"
            if p.exists():
                p.unlink()

    return IDRResult(
        condition=condition,
        n_true_rep_peaks=n_true,
        n_pooled_pseudo_peaks=n_pooled,
        n_self_pseudo_peaks=n_self_list,
        rescue_ratio=rescue_ratio,
        self_consistency_ratio=self_consistency_ratio,
        rescue_pass=rescue_pass,
        self_consistency_pass=sc_pass,
        overall_pass=overall,
        idr_peaks_bed=true_idr,
    )


def run_all_idr(
    sample_names: list[str],
    sample_conditions: dict[str, str],
    bam_paths: dict[str, Path],
    peak_paths: dict[str, Path],
    genome_size: str,
    output_dir: Path,
    *,
    is_paired: bool = True,
    idr_threshold: float = 0.05,
    macs2_qvalue: float = 0.01,
    threads: int = 8,
) -> list[IDRResult]:
    """
    Run IDR for all conditions that have >= 2 replicates.

    Parameters
    ----------
    sample_names       : ordered list of sample names
    sample_conditions  : {sample_name: condition}
    bam_paths          : {sample_name: bam_path}
    peak_paths         : {sample_name: narrowpeak_path}
    """
    # Group samples by condition
    cond_samples: dict[str, list[str]] = {}
    for name in sample_names:
        cond = sample_conditions.get(name, "")
        cond_samples.setdefault(cond, []).append(name)

    results: list[IDRResult] = []
    for cond, samples in sorted(cond_samples.items()):
        if len(samples) < 2:
            logger.warning("  [%s] Only %d replicate(s) — skipping IDR",
                           cond, len(samples))
            continue

        logger.info("IDR analysis: %s  (%d replicates)", cond, len(samples))
        cond_dir = output_dir / cond

        rep_bams  = [bam_paths[s] for s in samples if s in bam_paths]
        rep_peaks = [peak_paths[s] for s in samples if s in peak_paths]

        if len(rep_bams) < 2 or len(rep_peaks) < 2:
            logger.warning("  [%s] Missing BAMs or peaks — skipping IDR", cond)
            continue

        result = run_idr_analysis(
            cond, rep_bams, rep_peaks, genome_size, cond_dir,
            is_paired=is_paired, idr_threshold=idr_threshold,
            macs2_qvalue=macs2_qvalue, threads=threads,
        )
        results.append(result)

    return results


# ── IDR helpers ──────────────────────────────────────────────────────────────

def _split_bam(
    bam: Path,
    out1: Path,
    out2: Path,
    *,
    threads: int = 8,
) -> None:
    """Split a BAM into two complementary pseudo-replicates.

    Uses a hash of the read name to deterministically assign each read
    to exactly one of the two halves.  This guarantees complementary,
    non-overlapping splits (ENCODE standard), unlike independent
    subsampling which can place the same read in both halves.
    """
    _require("samtools")
    import hashlib

    # Read BAM, split by hash of read name (even → pr1, odd → pr2)
    import pysam
    with pysam.AlignmentFile(str(bam), "rb") as inbam:
        header = inbam.header.to_dict()
        with pysam.AlignmentFile(str(out1), "wb", header=header) as f1, \
             pysam.AlignmentFile(str(out2), "wb", header=header) as f2:
            for read in inbam:
                h = int(hashlib.md5(read.query_name.encode()).hexdigest(), 16)
                if h % 2 == 0:
                    f1.write(read)
                else:
                    f2.write(read)

    _run(["samtools", "index", "-@", str(threads), str(out1)],
         label=f"index pr1 [{bam.name}]")
    _run(["samtools", "index", "-@", str(threads), str(out2)],
         label=f"index pr2 [{bam.name}]")


def _run_macs2(
    name: str,
    bam: Path,
    output_dir: Path,
    *,
    fmt: str = "BAMPE",
    genome_size: str = "hs",
    qvalue: float = 0.01,
    is_paired: bool = True,
) -> None:
    """Call peaks with MACS2 (relaxed threshold for IDR)."""
    cmd = [
        "macs2", "callpeak",
        "-t", str(bam),
        "-f", fmt,
        "-g", genome_size,
        "-n", name,
        "--outdir", str(output_dir),
        "--nomodel",
        "-q", str(qvalue),
        "--keep-dup", "all",
        "--call-summits",
    ]
    # SE: add shift/extsize (BAMPE ignores these)
    if not is_paired:
        cmd.extend(["--shift", "-37", "--extsize", "73"])
    _run(cmd, label=f"macs2 callpeak [{name}]")


def _run_idr(
    peaks1: Path,
    peaks2: Path,
    output: Path,
    *,
    idr_threshold: float = 0.05,
    label: str = "",
) -> int:
    """
    Compute IDR between two narrowPeak files.

    Uses the reference ``idr`` tool if available in PATH, otherwise
    falls back to a native Python implementation of the Li et al. 2011
    Gaussian copula mixture model.

    Returns the number of peaks passing the IDR threshold.
    """
    if not peaks1.exists() or not peaks2.exists():
        logger.warning("  [%s] Peak file(s) missing — skipping IDR", label)
        return 0

    # Checkpoint: skip if output already exists with content
    if output.exists() and output.stat().st_size > 0:
        import re as _re
        n_pass = 0
        with open(output) as _f:
            for _line in _f:
                # Native IDR writes: # threshold=0.05  n_pass=123  n_matched=456
                m = _re.search(r"n_pass=(\d+)", _line)
                if m:
                    n_pass = int(m.group(1))
                    break
            else:
                # External IDR: count non-header, non-comment data lines
                _f.seek(0)
                n_pass = sum(1 for l in _f
                             if l.strip() and not l.startswith("#")
                             and not l.startswith("chr\t"))
        logger.info("  [%s] IDR checkpoint: %d peaks — skipping", label, n_pass)
        return n_pass

    # Try external idr tool first
    if _check_tool("idr"):
        return _run_idr_external(peaks1, peaks2, output,
                                  idr_threshold=idr_threshold, label=label)

    # Fallback: native Python implementation
    logger.info("  [%s] idr tool not in PATH — using native implementation", label)
    return _run_idr_native(peaks1, peaks2, output,
                            idr_threshold=idr_threshold, label=label)


def _run_idr_external(
    peaks1: Path, peaks2: Path, output: Path,
    *, idr_threshold: float, label: str,
) -> int:
    """Run IDR using the external idr tool."""
    cmd = [
        "idr",
        "--samples", str(peaks1), str(peaks2),
        "--input-file-type", "narrowPeak",
        "--rank", "p.value",
        "--output-file", str(output),
        "--idr-threshold", str(idr_threshold),
        "--plot",
        "--soft-idr-threshold", str(idr_threshold),
    ]
    try:
        _run(cmd, label=f"idr [{label}]")
    except RuntimeError as exc:
        logger.warning("  [%s] IDR warning: %s", label, str(exc)[:200])

    n_peaks = 0
    if output.exists():
        with open(output) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    n_peaks += 1
    logger.info("  [%s] IDR (external): %d peaks (threshold=%s)", label, n_peaks, idr_threshold)
    return n_peaks


def _run_idr_native(
    peaks1: Path, peaks2: Path, output: Path,
    *, idr_threshold: float, label: str,
) -> int:
    """
    Native Python IDR implementation (Li et al. 2011).

    Gaussian copula mixture model:
      Component 0 (irreproducible): independent N(0,1)
      Component 1 (reproducible): bivariate N(mu, sigma^2) with correlation rho

    Reference: Li et al. 2011 https://doi.org/10.1214/11-AOAS466
    """
    from scipy import stats

    # 1. Parse narrowPeak files
    def _parse_np(path: Path) -> list[tuple[str, int, int, float]]:
        peaks = []
        with open(path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 8:
                    peaks.append((parts[0], int(parts[1]), int(parts[2]), float(parts[7])))
        peaks.sort(key=lambda x: -x[3])
        return peaks

    p1, p2 = _parse_np(peaks1), _parse_np(peaks2)
    if not p1 or not p2:
        logger.warning("  [%s] Empty peak file(s)", label)
        output.write_text("")
        return 0

    # 2. Match peaks by overlap
    matched: list[tuple[int, float, float]] = []
    used2: set[int] = set()
    for i, (c1, s1, e1, sc1) in enumerate(p1):
        best_j, best_ov = -1, 0
        for j, (c2, s2, e2, sc2) in enumerate(p2):
            if j in used2 or c2 != c1:
                continue
            ov = max(0, min(e1, e2) - max(s1, s2))
            if ov > best_ov:
                best_ov, best_j = ov, j
        if best_j >= 0 and best_ov > 0:
            used2.add(best_j)
            matched.append((i, sc1, p2[best_j][3]))

    n_matched = len(matched)
    if n_matched < 10:
        logger.warning("  [%s] Only %d matched peaks — too few for IDR", label, n_matched)
        output.write_text("")
        return 0

    p1_idx = np.array([m[0] for m in matched])
    scores = np.array([(m[1], m[2]) for m in matched])

    # 3. Ranks → normal quantiles
    ranks = np.zeros_like(scores)
    for col in range(2):
        order = np.argsort(-scores[:, col])
        r = np.empty_like(order, dtype=float)
        r[order] = np.arange(1, len(order) + 1)
        ranks[:, col] = r / (len(order) + 1)
    z = np.clip(stats.norm.ppf(ranks), -6, 6)

    # 4. EM
    n = len(z)
    pi1, mu1, sigma1, rho = 0.5, 0.0, 1.0, 0.5

    for _ in range(100):
        log_p0 = stats.norm.logpdf(z[:, 0]) + stats.norm.logpdf(z[:, 1])

        s2 = max(sigma1**2, 0.01)
        rc = np.clip(rho, -0.99, 0.99)
        det = s2**2 * (1 - rc**2)
        d0, d1 = z[:, 0] - mu1, z[:, 1] - mu1
        exp = -(d0**2 * s2 - 2 * rc * s2 * d0 * d1 + d1**2 * s2) / (2 * det)
        log_p1 = exp - np.log(2 * np.pi) - 0.5 * np.log(det)

        lw1 = np.log(pi1 + 1e-300) + log_p1
        lw0 = np.log(1 - pi1 + 1e-300) + log_p0
        lmax = np.maximum(lw0, lw1)
        gamma = np.exp(lw1 - lmax - np.log(np.exp(lw0 - lmax) + np.exp(lw1 - lmax)))

        sg = np.sum(gamma)
        pi1_n = sg / n
        if sg > 1:
            mu1_n = np.sum(gamma * (z[:, 0] + z[:, 1])) / (2 * sg)
            var = np.sum(gamma * ((z[:, 0] - mu1_n)**2 + (z[:, 1] - mu1_n)**2)) / (2 * sg)
            sig_n = np.sqrt(max(var, 0.01))
            cov = np.sum(gamma * (z[:, 0] - mu1_n) * (z[:, 1] - mu1_n)) / sg
            rho_n = np.clip(cov / max(sig_n**2, 0.01), -0.99, 0.99)
        else:
            mu1_n, sig_n, rho_n = mu1, sigma1, rho

        if abs(pi1_n - pi1) < 1e-6 and abs(rho_n - rho) < 1e-6:
            break
        pi1, mu1, sigma1, rho = pi1_n, mu1_n, sig_n, rho_n

    # 5. IDR values
    idr_vals = 1 - gamma
    sorted_i = np.argsort(idr_vals)
    n_pass = int(np.sum(idr_vals < idr_threshold))

    # 6. Write output
    with open(output, "w") as f:
        f.write(f"# IDR analysis: {label}\n")
        f.write(f"# threshold={idr_threshold}  n_pass={n_pass}  n_matched={n_matched}\n")
        f.write(f"# pi={pi1:.4f}  rho={rho:.4f}  sigma={sigma1:.4f}\n")
        f.write("chr\tstart\tend\tscore1\tscore2\tidr\n")
        for idx in sorted_i:
            c, s, e, _ = p1[p1_idx[idx]]
            f.write(f"{c}\t{s}\t{e}\t{scores[idx,0]:.4f}\t{scores[idx,1]:.4f}\t{idr_vals[idx]:.6f}\n")

    logger.info("  [%s] IDR (native): %d/%d pass (threshold=%s, rho=%.3f, pi=%.3f)",
                label, n_pass, n_matched, idr_threshold, rho, pi1)
    return n_pass


def plot_idr_summary(
    idr_results: list[IDRResult],
    output_dir: Path,
) -> None:
    """Bar chart of IDR metrics per condition with ENCODE threshold lines."""
    import matplotlib.pyplot as plt

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not idr_results:
        return

    # Rescue ratio + self-consistency ratio grouped bar chart
    # Cap inf values for plotting (show as capped bar with "inf" annotation)
    conditions = [r.condition for r in idr_results]
    rescue     = [r.rescue_ratio for r in idr_results]
    self_cons  = [r.self_consistency_ratio for r in idr_results]

    # Determine y-axis cap: max finite value * 1.5 or 10 if all inf
    finite_vals = [v for v in rescue + self_cons if np.isfinite(v)]
    y_cap = max(max(finite_vals) * 1.5, 5.0) if finite_vals else 10.0

    rescue_plot    = [min(v, y_cap) if np.isfinite(v) else y_cap for v in rescue]
    self_cons_plot = [min(v, y_cap) if np.isfinite(v) else y_cap for v in self_cons]

    x = np.arange(len(conditions))
    width = 0.3

    fig, ax = plt.subplots(figsize=(7, 5))
    bars1 = ax.bar(x - width/2, rescue_plot, width, label="Rescue ratio",
                   color="#4C72B0", edgecolor="black", linewidth=0.5)
    bars2 = ax.bar(x + width/2, self_cons_plot, width, label="Self-consistency ratio",
                   color="#DD8452", edgecolor="black", linewidth=0.5)

    ax.axhline(2.0, color="#d62728", linestyle="--", linewidth=1.0,
               label="ENCODE threshold (<2.0)")

    ax.set_xticks(x)
    ax.set_xticklabels(conditions, fontsize=11)
    ax.set_ylabel("Ratio", fontsize=11)
    ax.set_ylim(0, y_cap * 1.25)
    ax.set_title("IDR Reproducibility", fontsize=13, pad=10)
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    # Mark inf values: "∞" near bar top
    for i in range(len(conditions)):
        if not np.isfinite(rescue[i]):
            ax.text(i - width/2, rescue_plot[i] - y_cap * 0.04, "∞",
                    ha="center", va="top", fontsize=10, color="white",
                    fontweight="bold")
        if not np.isfinite(self_cons[i]):
            ax.text(i + width/2, self_cons_plot[i] - y_cap * 0.04, "∞",
                    ha="center", va="top", fontsize=10, color="white",
                    fontweight="bold")

    _save_figure(fig, "idr_summary", output_dir)

    # Save data
    data_file = output_dir / "idr_summary.tsv"
    with open(data_file, "w") as f:
        f.write("condition\tn_true_rep\tn_pooled_pseudo\trescue_ratio\t"
                "self_consistency_ratio\trescue_pass\tsc_pass\toverall\n")
        for r in idr_results:
            f.write(f"{r.condition}\t{r.n_true_rep_peaks}\t{r.n_pooled_pseudo_peaks}\t"
                    f"{r.rescue_ratio:.4f}\t{r.self_consistency_ratio:.4f}\t"
                    f"{'PASS' if r.rescue_pass else 'FAIL'}\t"
                    f"{'PASS' if r.self_consistency_pass else 'FAIL'}\t"
                    f"{'PASS' if r.overall_pass else 'FAIL'}\n")
    logger.info("IDR summary saved: %s", data_file)


# ===========================================================================
# featureCounts parser
# ===========================================================================

def _parse_featurecounts(counts_file: Path) -> np.ndarray | None:
    """
    Parse featureCounts output into a numpy array (peaks × samples).

    Skips comment lines (starting with #) and the header.
    Columns 0–5 are annotation (GeneID, Chr, Start, End, Strand, Length);
    columns 6+ are sample counts.
    """
    rows = []
    with open(counts_file) as f:
        for line in f:
            if line.startswith("#"):
                continue
            if line.startswith("Geneid"):
                continue  # header
            parts = line.strip().split("\t")
            if len(parts) > 6:
                try:
                    rows.append([int(x) for x in parts[6:]])
                except ValueError:
                    continue

    if not rows:
        return None
    return np.array(rows, dtype=float)


# ===========================================================================
# Summary
# ===========================================================================

def build_qc_after_peak_calling_summary(
    qc_results: list[QcAfterPeakCallingResult],
) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd

    rows = []
    for r in qc_results:
        rows.append({
            "sample":           r.sample_name,
            "frip":             round(r.frip, 4),
            "frip_tier":        r.frip_tier,
            "n_reads_in_peaks": r.n_reads_in_peaks,
            "n_usable_reads":   r.n_usable_reads,
        })
    return pd.DataFrame(rows)


def write_qc_after_peak_calling_summary(
    qc_results: list[QcAfterPeakCallingResult],
    output_dir: Path,
) -> Path:
    df   = build_qc_after_peak_calling_summary(qc_results)
    path = output_dir / "qc_after_peak_calling_summary.csv"
    df.to_csv(path, index=False)
    logger.info("QC after peak calling summary written: %s", path)
    return path

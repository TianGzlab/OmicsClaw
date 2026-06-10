"""
peak_annotation.py — Peak annotation for bulk ATAC-seq.

Annotates consensus peaks with genomic features using HOMER annotatePeaks.pl.
Falls back to bedtools closest (distance-based only) if HOMER is unavailable.

HOMER annotation categories
----------------------------
  Promoter-TSS, TTS, 5'UTR, 3'UTR, Exon, Intron, Intergenic, non-coding

Output
------
  annotated_peaks.tsv — consensus peaks with feature annotations
  homer_annotated_full.tsv — full HOMER output (all columns)
  peak_annotation_summary.csv — counts per feature category
  peak_annotation_pie.{pdf,png} — pie chart of feature distribution
  peak_tss_distance.{pdf,png} — histogram of distance to nearest TSS

Dependencies
------------
  HOMER (annotatePeaks.pl) — preferred
  bedtools + GTF — fallback

References
----------
  HOMER annotatePeaks : http://homer.ucsd.edu/homer/ngs/annotation.html
  ChIPseeker (R)      : https://bioconductor.org/packages/ChIPseeker/
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

# HOMER annotation categories → simplified labels for summary
_HOMER_CATEGORY_MAP = {
    "promoter-tss": "Promoter-TSS",
    "tts":          "TTS",
    "5' utr":       "5'UTR",
    "3' utr":       "3'UTR",
    "exon":         "Exon",
    "intron":       "Intron",
    "intergenic":   "Intergenic",
    "non-coding":   "Non-coding",
}

# Fallback distance-based categories (when HOMER is unavailable)
_PROMOTER_DIST   = 1_000      # < 1 kb
_PROXIMAL_DIST   = 5_000      # 1–5 kb
_DISTAL_DIST     = 50_000     # 5–50 kb
# > 50 kb = intergenic


# ===========================================================================
# Result dataclass
# ===========================================================================

@dataclass
class PeakAnnotationResult:
    """Output of annotate_peaks()."""
    annotated_tsv:   Path               # simplified annotation table
    summary_csv:     Path | None = None # per-category counts
    n_peaks:         int   = 0
    category_counts: dict[str, int] = field(default_factory=dict)
    method:          str   = ""         # "homer" or "bedtools"


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


# ===========================================================================
# HOMER-based annotation (preferred)
# ===========================================================================

def _classify_homer_annotation(annotation_str: str) -> str:
    """
    Map HOMER Annotation column to a simplified category.

    HOMER outputs strings like:
      "promoter-TSS (NM_001234)"
      "intron (NM_005678, intron 3 of 12)"
      "Intergenic"
      "exon (NM_009876, exon 5 of 10)"
      "3' UTR (NM_003456)"
      "5' UTR (NM_007890)"
      "TTS (NM_001111)"
      "non-coding (NR_012345)"
    """
    lower = annotation_str.lower().strip()
    for key, label in _HOMER_CATEGORY_MAP.items():
        if lower.startswith(key):
            return label
    return "Other"


def _annotate_with_homer(
    consensus_bed: Path,
    output_dir: Path,
    *,
    genome: str | None = None,
    gtf: Path | None = None,
) -> PeakAnnotationResult:
    """
    Annotate peaks using HOMER annotatePeaks.pl.

    Two modes:
      1. Pre-installed genome:  annotatePeaks.pl peaks.bed hg38
         Requires: configureHomer.pl -install <genome>
      2. Custom GTF:            annotatePeaks.pl peaks.bed none -gtf genes.gtf
         No genome install needed — uses the GTF directly.

    If both genome and gtf are provided, uses the GTF (more portable).

    HOMER output columns (tab-separated):
      0: PeakID
      1: Chr
      2: Start
      3: End
      4: Strand
      5: Peak Score
      6: Focus Ratio/Region Size
      7: Annotation          ← genomic feature (Promoter-TSS, Intron, etc.)
      8: Detailed Annotation
      9: Distance to TSS
     10: Nearest PromoterID
     11: Entrez ID
     12: Nearest Unigene
     13: Nearest Refseq
     14: Nearest Ensembl
     15: Gene Name
     16: Gene Alias
     17: Gene Description
     18: Gene Type
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    homer_full   = output_dir / "homer_annotated_full.tsv"
    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    # Build HOMER command
    # Prefer -gtf (no genome install needed); fall back to pre-installed genome
    if gtf and gtf.exists():
        # HOMER does not support gzipped GTF — decompress next to original
        gtf_path = gtf
        if str(gtf).endswith(".gz"):
            import gzip as _gzip
            decompressed = gtf.parent / gtf.name.replace(".gz", "")
            if not decompressed.exists():
                logger.info("Decompressing GTF: %s → %s", gtf, decompressed)
                with _gzip.open(gtf, "rb") as f_in, open(decompressed, "wb") as f_out:
                    f_out.write(f_in.read())
            gtf_path = decompressed
        cmd = ["annotatePeaks.pl", str(consensus_bed), "none",
               "-gtf", str(gtf_path)]
        logger.info("HOMER: using custom GTF: %s", gtf_path)
    elif genome:
        cmd = ["annotatePeaks.pl", str(consensus_bed), genome]
        logger.info("HOMER: using pre-installed genome: %s", genome)
    else:
        raise RuntimeError(
            "HOMER annotatePeaks.pl requires either a GTF file (-gtf) "
            "or a pre-installed genome name."
        )

    result = _run(cmd, label="HOMER annotatePeaks.pl")

    # Log stderr (HOMER prints progress and errors here)
    if result.stderr:
        for stderr_line in result.stderr.strip().splitlines()[:20]:
            logger.info("  HOMER: %s", stderr_line)

    # Save full HOMER output
    with open(homer_full, "w") as f:
        f.write(result.stdout)

    # Check for empty output
    if not result.stdout.strip():
        msg = "HOMER annotatePeaks.pl produced empty output."
        if genome and not (gtf and gtf.exists()):
            msg += (
                f"\n  The genome '{genome}' is likely not installed in HOMER."
                f"\n  Fix: run  configureHomer.pl -install {genome}"
                f"\n  Or provide a GTF file via --gtf to use HOMER without genome install."
            )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Full HOMER annotation: %s", homer_full)

    # Parse HOMER output → simplified annotation table
    categories: dict[str, int] = {}
    rows: list[str] = []
    header = (
        "peak_chr\tpeak_start\tpeak_end\tnearest_gene\tdistance\tcategory\t"
        "detailed_annotation\tgene_type\n"
    )

    lines = result.stdout.splitlines()
    if lines:
        header_line = lines[0] if lines[0].startswith("PeakID") else None
        n_cols = len(header_line.split("\t")) if header_line else 0
        logger.info("HOMER output: %d lines, %d columns", len(lines), n_cols)

    for line in lines:
        if line.startswith("PeakID") or line.startswith("#"):
            continue
        parts = line.split("\t")
        # Minimum: PeakID(0) Chr(1) Start(2) End(3) Strand(4) Score(5)
        #          FocusRatio(6) Annotation(7) = 8 columns
        if len(parts) < 8:
            continue

        peak_chr   = parts[1]
        peak_start = parts[2]
        peak_end   = parts[3]
        annotation = parts[7]
        detailed   = parts[8] if len(parts) > 8 else ""
        distance   = parts[9] if len(parts) > 9 else "0"
        gene_name  = parts[15] if len(parts) > 15 else "."
        gene_type  = parts[18] if len(parts) > 18 else ""

        category = _classify_homer_annotation(annotation)
        categories[category] = categories.get(category, 0) + 1

        rows.append(
            f"{peak_chr}\t{peak_start}\t{peak_end}\t{gene_name}\t"
            f"{distance}\t{category}\t{detailed}\t{gene_type}\n"
        )

    # Write simplified annotation table
    with open(annotated_tsv, "w") as f:
        f.write(header)
        f.writelines(rows)

    # Write summary
    import pandas as pd
    n_peaks = len(rows)
    summary_df = pd.DataFrame([
        {"category": k, "count": v, "fraction": v / max(n_peaks, 1)}
        for k, v in sorted(categories.items(), key=lambda x: -x[1])
    ])
    summary_df.to_csv(summary_csv, index=False)

    logger.info("HOMER peak annotation: %d peaks annotated", n_peaks)
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d (%.1f%%)", cat, count, count / max(n_peaks, 1) * 100)

    return PeakAnnotationResult(
        annotated_tsv=annotated_tsv,
        summary_csv=summary_csv,
        n_peaks=n_peaks,
        category_counts=categories,
        method="homer",
    )


# ===========================================================================
# TSS BED extraction (for bedtools fallback)
# ===========================================================================

def _extract_tss_from_gtf(gtf: Path, output_dir: Path) -> Path:
    """
    Extract 1 bp TSS positions from a GTF for bedtools closest.

    Returns sorted BED: chr \\t tss \\t tss+1 \\t gene_name \\t . \\t strand
    """
    import gzip
    import re

    output_dir.mkdir(parents=True, exist_ok=True)
    tss_bed = output_dir / "tss_for_annotation.bed"

    if tss_bed.exists() and tss_bed.stat().st_size > 0:
        return tss_bed

    opener = gzip.open if str(gtf).endswith(".gz") else open
    tss_list: list[tuple[str, int, int, str, str, str]] = []

    with opener(gtf, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9 or parts[2] != "transcript":
                continue

            chrom  = parts[0]
            start  = int(parts[3]) - 1
            end    = int(parts[4])
            strand = parts[6]
            attrs  = parts[8]

            name = ""
            for key in ("gene_name", "transcript_id", "gene_id"):
                m = re.search(rf'{key}\s+"([^"]+)"', attrs)
                if m:
                    name = m.group(1)
                    break

            tss = start if strand == "+" else end - 1
            tss_list.append((chrom, tss, tss + 1, name, ".", strand))

    tss_list.sort(key=lambda x: (x[0], x[1]))
    with open(tss_bed, "w") as out:
        for row in tss_list:
            out.write("\t".join(str(v) for v in row) + "\n")

    logger.info("TSS BED for annotation: %s  (%d sites)", tss_bed, len(tss_list))
    return tss_bed


# ===========================================================================
# Bedtools fallback annotation
# ===========================================================================

def _annotate_with_bedtools(
    consensus_bed: Path,
    gtf: Path,
    output_dir: Path,
) -> PeakAnnotationResult:
    """
    Fallback: annotate peaks by distance to nearest TSS using bedtools closest.

    Categories (distance-based only):
      - Promoter   : < 1 kb from TSS
      - Proximal   : 1–5 kb from TSS
      - Distal     : 5–50 kb from TSS
      - Intergenic : > 50 kb from TSS
    """
    _require("bedtools")
    output_dir.mkdir(parents=True, exist_ok=True)

    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    # Extract TSS positions
    tss_bed = _extract_tss_from_gtf(gtf, output_dir)

    # Sort consensus peaks for bedtools
    sorted_peaks = output_dir / "consensus_sorted.bed"
    _run(["sort", "-k1,1", "-k2,2n", str(consensus_bed), "-o", str(sorted_peaks)],
         label="sort consensus peaks")

    # bedtools closest — find nearest TSS for each peak
    result = _run(
        ["bedtools", "closest",
         "-a", str(sorted_peaks),
         "-b", str(tss_bed),
         "-d",           # report distance
         "-t", "first"],  # ties: take first
        label="bedtools closest",
    )

    # Parse and classify
    categories: dict[str, int] = {
        "Promoter": 0, "Proximal": 0, "Distal": 0, "Intergenic": 0,
    }
    rows: list[str] = []
    header = "peak_chr\tpeak_start\tpeak_end\tnearest_gene\tdistance\tcategory\n"

    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue

        peak_chr   = parts[0]
        peak_start = parts[1]
        peak_end   = parts[2]
        gene_name  = parts[6] if len(parts) > 6 else "."
        distance   = abs(int(parts[-1])) if parts[-1].lstrip("-").isdigit() else 0

        if distance < _PROMOTER_DIST:
            cat = "Promoter"
        elif distance < _PROXIMAL_DIST:
            cat = "Proximal"
        elif distance < _DISTAL_DIST:
            cat = "Distal"
        else:
            cat = "Intergenic"

        categories[cat] += 1
        rows.append(f"{peak_chr}\t{peak_start}\t{peak_end}\t{gene_name}\t{distance}\t{cat}\n")

    # Write annotated peaks
    with open(annotated_tsv, "w") as f:
        f.write(header)
        f.writelines(rows)

    # Write summary
    import pandas as pd
    summary_df = pd.DataFrame([
        {"category": k, "count": v, "fraction": v / max(len(rows), 1)}
        for k, v in categories.items()
    ])
    summary_df.to_csv(summary_csv, index=False)

    # Cleanup
    if sorted_peaks.exists():
        sorted_peaks.unlink()

    n_peaks = len(rows)
    logger.info("Bedtools peak annotation (fallback): %d peaks annotated", n_peaks)
    for cat, count in categories.items():
        logger.info("  %s: %d (%.1f%%)", cat, count, count / max(n_peaks, 1) * 100)

    return PeakAnnotationResult(
        annotated_tsv=annotated_tsv,
        summary_csv=summary_csv,
        n_peaks=n_peaks,
        category_counts=categories,
        method="bedtools",
    )


# ===========================================================================
# Main entry point
# ===========================================================================

def annotate_peaks(
    consensus_bed: Path,
    gtf: Path | None,
    output_dir: Path,
    *,
    genome: str | None = None,
) -> PeakAnnotationResult:
    """
    Annotate consensus peaks with genomic features.

    Priority:
      1. HOMER + GTF   → annotatePeaks.pl peaks.bed none -gtf genes.gtf
                          (best: no genome install needed, uses your exact GTF)
      2. HOMER + genome → annotatePeaks.pl peaks.bed hg38
                          (requires: configureHomer.pl -install <genome>)
      3. bedtools + GTF → distance-based fallback (Promoter/Proximal/Distal/Intergenic)
      4. neither        → error

    Parameters
    ----------
    consensus_bed : consensus peaks BED from build_consensus_peaks()
    gtf           : GTF file for the genome (used by HOMER -gtf and bedtools fallback)
    output_dir    : directory for output files
    genome        : genome name (e.g. "hg38", "mm10", "sacCer3").
                    Used as HOMER genome when GTF is not available.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    # Checkpoint — reuse existing results (must have actual data, not just header)
    if annotated_tsv.exists() and annotated_tsv.stat().st_size > 0:
        counts = _load_annotation_summary(summary_csv)
        n = sum(counts.values())
        if n > 0:
            method = "homer" if (output_dir / "homer_annotated_full.tsv").exists() else "bedtools"
            logger.info("Peak annotation checkpoint (%s): %d peaks — skipping", method, n)
            return PeakAnnotationResult(
                annotated_tsv=annotated_tsv,
                summary_csv=summary_csv,
                n_peaks=n,
                category_counts=counts,
                method=method,
            )

    has_homer = _check_tool("annotatePeaks.pl")
    has_gtf   = gtf is not None and gtf.exists()

    # Priority 1: HOMER + GTF (no genome install needed)
    if has_homer and has_gtf:
        logger.info("Using HOMER annotatePeaks.pl with custom GTF: %s", gtf)
        return _annotate_with_homer(
            consensus_bed, output_dir, gtf=gtf,
        )

    # Priority 2: HOMER + pre-installed genome (may fail if genome not installed)
    if has_homer and genome:
        logger.info("Trying HOMER annotatePeaks.pl with genome: %s", genome)
        try:
            return _annotate_with_homer(
                consensus_bed, output_dir, genome=genome,
            )
        except RuntimeError as e:
            logger.warning("HOMER with genome '%s' failed: %s", genome, e)
            logger.warning("Falling back to bedtools closest.")
            # Clean up failed HOMER outputs for retry
            for f in (output_dir / "homer_annotated_full.tsv",
                      output_dir / "annotated_peaks.tsv",
                      output_dir / "peak_annotation_summary.csv"):
                if f.exists():
                    f.unlink()

    # Priority 3: bedtools fallback (needs GTF)
    if has_gtf:
        if not has_homer:
            logger.warning(
                "HOMER not found (install: conda install -c bioconda homer). "
                "Using bedtools closest (distance-based only)."
            )
        logger.info("Using bedtools closest (distance-based annotation)")
        return _annotate_with_bedtools(consensus_bed, gtf, output_dir)

    # Nothing available
    raise RuntimeError(
        "Peak annotation requires either:\n"
        "  1. HOMER + GTF:    conda install -c bioconda homer  (recommended)\n"
        "  2. HOMER + genome: configureHomer.pl -install <genome>\n"
        "  3. bedtools + GTF: provide a GTF file via --gtf\n"
        f"  Current state: HOMER={'yes' if has_homer else 'no'}, "
        f"GTF={'yes' if has_gtf else 'no'}, genome={genome or 'none'}"
    )


# ===========================================================================
# Plots
# ===========================================================================

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


def _save_figure(fig, name: str, output_dir: Path) -> None:
    import matplotlib.pyplot as plt
    for ext in ("pdf", "png"):
        fig.savefig(output_dir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


# ChIPseeker Paired palette (ColorBrewer) — standard for genomic annotation
# Source: ChIPseeker (Yu G, Wang LG, He QY. Bioinformatics 2015;31(14):2382-3)
#         https://github.com/YuLab-SMU/ChIPseeker/blob/master/R/utilities.R
#         getCols() returns col3 = ColorBrewer "Paired" 12-class palette
_ANNOTATION_COLORS = {
    # HOMER categories mapped to ChIPseeker-style colours
    "Promoter-TSS": "#a6cee3",   # light blue
    "5'UTR":        "#1f78b4",   # dark blue
    "3'UTR":        "#b2df8a",   # light green
    "Exon":         "#33a02c",   # dark green
    "Intron":       "#fdbf6f",   # light orange
    "TTS":          "#ff7f00",   # dark orange
    "Intergenic":   "#cab2d6",   # light purple
    "Non-coding":   "#6a3d9a",   # dark purple
    "Other":        "#d9d9d9",   # grey
    # Bedtools fallback categories
    "Promoter":     "#a6cee3",
    "Proximal":     "#fb9a99",
    "Distal":       "#fdbf6f",
}


def plot_annotation_pie(
    annotation_result: PeakAnnotationResult,
    output_dir: Path,
    *,
    title: str | None = None,
    filename: str = "peak_annotation_pie",
) -> None:
    """Donut chart of peak annotation categories (publication-quality)."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    counts = annotation_result.category_counts
    if not counts or sum(counts.values()) == 0:
        return

    total = sum(counts.values())

    # Sort by count descending
    sorted_items = sorted(counts.items(), key=lambda x: -x[1])
    labels = [k for k, v in sorted_items]
    sizes  = [v for k, v in sorted_items]
    colors = [_ANNOTATION_COLORS.get(lbl, "#d9d9d9") for lbl in labels]

    fig, ax = plt.subplots(figsize=(7, 5))

    # Donut chart — clean wedges, no text on slices
    wedges, _ = ax.pie(
        sizes, colors=colors,
        startangle=90, counterclock=False,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=1.5),
    )

    # Centre text: total peak count
    ax.text(0, 0, f"{total:,}\npeaks", ha="center", va="center",
            fontsize=13, fontweight="bold", color="#333333")

    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)

    # Legend: category + count + percentage, placed to the right
    legend_labels = [
        f"{lbl}  ({v:,}, {v / total * 100:.1f}%)"
        for lbl, v in zip(labels, sizes)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="center left", bbox_to_anchor=(1.0, 0.5),
        frameon=False, fontsize=9, handlelength=1.2,
    )

    _save_figure(fig, filename, output_dir)


def plot_tss_distance_histogram(
    annotated_tsv: Path,
    output_dir: Path,
    *,
    title: str = "Peak distance to TSS",
    filename: str = "peak_tss_distance",
) -> None:
    """Histogram of peak distance to nearest TSS."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    distances = _read_tss_distances(annotated_tsv)
    if not distances:
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    dist_arr = np.array(distances)
    dist_arr = dist_arr[dist_arr > 0]  # exclude 0 for log
    if len(dist_arr) == 0:
        return

    ax.hist(np.log10(dist_arr), bins=50, color="#4C72B0", edgecolor="black",
            linewidth=0.3)
    ax.set_xlabel("log$_{10}$(Distance to nearest TSS)", fontsize=11)
    ax.set_ylabel("Number of peaks", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")

    # Add category boundaries
    for dist, label in [
        (_PROMOTER_DIST, "1 kb"),
        (_PROXIMAL_DIST, "5 kb"),
        (_DISTAL_DIST, "50 kb"),
    ]:
        ax.axvline(np.log10(dist), color="#999999", linestyle="--",
                   linewidth=0.8, label=label)
    ax.legend(loc="upper right", frameon=False)

    _save_figure(fig, filename, output_dir)


def _read_tss_distances(annotated_tsv: Path) -> list[int]:
    """Read absolute TSS distances from an annotated peaks TSV."""
    distances: list[int] = []
    with open(annotated_tsv) as f:
        header = next(f).strip().split("\t")
        dist_col = header.index("distance") if "distance" in header else 4
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) > dist_col:
                try:
                    distances.append(abs(int(parts[dist_col])))
                except ValueError:
                    continue
    return distances


# ===========================================================================
# Per-condition annotation
# ===========================================================================

def annotate_per_condition_peaks(
    peak_results: list,
    sample_conditions: dict[str, str],
    gtf: Path | None,
    output_dir: Path,
    *,
    genome: str | None = None,
) -> dict[str, PeakAnnotationResult]:
    """
    Merge per-sample narrowPeak files by condition and annotate.

    Replicates within each condition are concatenated, sorted, and merged
    (bedtools merge) to produce a condition-level peak set before annotation.
    Data files are written per condition; comparison plots are produced
    by separate plot_*_comparison functions.

    Returns {condition: PeakAnnotationResult}.
    """
    # Group samples by condition
    cond_to_samples: dict[str, list] = {}
    for pr in peak_results:
        cond = sample_conditions.get(pr.sample_name, "")
        if not cond:
            continue
        cond_to_samples.setdefault(cond, []).append(pr)

    if len(cond_to_samples) < 2:
        logger.info("Fewer than 2 conditions — skipping per-condition annotation.")
        return {}

    results: dict[str, PeakAnnotationResult] = {}

    for cond, prs in sorted(cond_to_samples.items()):
        cond_dir = output_dir / cond
        cond_dir.mkdir(parents=True, exist_ok=True)

        # Concatenate all replicates' narrowPeak → 3-col BED
        concat_bed = cond_dir / f"{cond}_concat.bed"
        sorted_bed = cond_dir / f"{cond}_sorted.bed"
        merged_bed = cond_dir / f"{cond}_merged.bed"

        # Checkpoint: skip BED merge if merged file already exists
        if not (merged_bed.exists() and merged_bed.stat().st_size > 0):
            with open(concat_bed, "w") as out:
                for pr in prs:
                    if not pr.peaks_narrowpeak or not pr.peaks_narrowpeak.exists():
                        continue
                    with open(pr.peaks_narrowpeak) as fin:
                        for line in fin:
                            parts = line.split("\t")
                            if len(parts) >= 3:
                                out.write(f"{parts[0]}\t{parts[1]}\t{parts[2]}\n")

            if not concat_bed.exists() or concat_bed.stat().st_size == 0:
                logger.warning("  [%s] no peaks to merge — skipping annotation", cond)
                continue

            # Sort
            subprocess.run(
                ["sort", "-k1,1", "-k2,2n", str(concat_bed), "-o", str(sorted_bed)],
                check=True,
            )

            # Merge overlapping peaks
            if not shutil.which("bedtools"):
                logger.warning("bedtools not found — cannot merge condition peaks")
                continue
            with open(merged_bed, "w") as out:
                subprocess.run(
                    ["bedtools", "merge", "-i", str(sorted_bed)],
                    stdout=out, check=True,
                )
        else:
            logger.info("  [%s] merged BED checkpoint — skipping merge", cond)

        n_samples = len(prs)
        sample_names_str = ", ".join(pr.sample_name for pr in prs)
        logger.info("  [%s] merged %d replicates (%s) — annotating condition peaks",
                     cond, n_samples, sample_names_str)

        ann = annotate_peaks(merged_bed, gtf, cond_dir, genome=genome)
        results[cond] = ann

    return results


# Condition-aware palette (Okabe-Ito, colourblind-safe, publication standard)
# Source: Okabe & Ito 2008, https://jfly.uni-koeln.de/color/
_CONDITION_COLORS = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#F0E442",  # yellow
    "#000000",  # black
]


def _get_ordered_categories(
    annotation_results: dict[str, PeakAnnotationResult],
) -> list[str]:
    """Collect categories across conditions in a fixed display order."""
    all_cats: set[str] = set()
    for ann in annotation_results.values():
        all_cats.update(ann.category_counts.keys())
    cat_order = [
        "Promoter-TSS", "Promoter", "5'UTR", "3'UTR", "Exon",
        "Intron", "TTS", "Proximal", "Distal", "Intergenic",
        "Non-coding", "Other",
    ]
    categories = [c for c in cat_order if c in all_cats]
    categories += sorted(all_cats - set(categories))
    return categories


def plot_annotation_comparison(
    annotation_results: dict[str, PeakAnnotationResult],
    output_dir: Path,
    *,
    filename: str = "peak_annotation_pie_comparison",
) -> None:
    """
    Side-by-side donut charts — one panel per condition, shared legend
    at bottom.  Publication-quality (300 dpi, PDF + PNG).
    """
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    _setup_plot_style()

    if len(annotation_results) < 2:
        return

    conditions = list(annotation_results.keys())
    n_cond = len(conditions)
    categories = _get_ordered_categories(annotation_results)

    fig = plt.figure(figsize=(5 * n_cond, 6))
    gs = GridSpec(2, n_cond, height_ratios=[6, 1], hspace=0.08)

    for i, cond in enumerate(conditions):
        ax = fig.add_subplot(gs[0, i])
        counts = annotation_results[cond].category_counts
        total = sum(counts.values())
        if total == 0:
            continue

        # Use category order for consistent colours across panels
        nonzero = [(cat, counts.get(cat, 0)) for cat in categories
                    if counts.get(cat, 0) > 0]
        nz_sizes  = [v for _, v in nonzero]
        nz_colors = [_ANNOTATION_COLORS.get(c, "#d9d9d9") for c, _ in nonzero]

        ax.pie(
            nz_sizes, colors=nz_colors,
            startangle=90, counterclock=False,
            wedgeprops=dict(width=0.45, edgecolor="white", linewidth=1.5),
        )
        ax.text(0, 0, f"{total:,}\npeaks", ha="center", va="center",
                fontsize=12, fontweight="bold", color="#333333")
        ax.set_title(cond, fontsize=13, fontweight="bold", pad=10)

    # Shared legend at bottom
    legend_ax = fig.add_subplot(gs[1, :])
    legend_ax.axis("off")
    legend_handles = []
    legend_labels = []
    for cat in categories:
        if any(annotation_results[c].category_counts.get(cat, 0) > 0
               for c in conditions):
            legend_handles.append(
                mpatches.Patch(facecolor=_ANNOTATION_COLORS.get(cat, "#d9d9d9"),
                               edgecolor="white"))
            legend_labels.append(cat)
    legend_ax.legend(
        legend_handles, legend_labels,
        loc="center", ncol=min(len(legend_labels), 6),
        frameon=False, fontsize=9, handlelength=1.2,
    )

    _save_figure(fig, filename, output_dir)


def plot_tss_distance_comparison(
    annotation_results: dict[str, PeakAnnotationResult],
    output_dir: Path,
    *,
    filename: str = "peak_tss_distance_comparison",
) -> None:
    """
    Side-by-side TSS distance histograms — one panel per condition,
    shared x/y axes.  Publication-quality (300 dpi, PDF + PNG).
    """
    import matplotlib.pyplot as plt
    _setup_plot_style()

    if len(annotation_results) < 2:
        return

    conditions = list(annotation_results.keys())
    cond_distances: dict[str, np.ndarray] = {}
    for cond in conditions:
        dists = _read_tss_distances(annotation_results[cond].annotated_tsv)
        arr = np.array(dists)
        arr = arr[arr > 0]
        if len(arr) > 0:
            cond_distances[cond] = arr

    if len(cond_distances) < 2:
        return

    cond_names = list(cond_distances.keys())
    n_cond = len(cond_names)

    fig, axes = plt.subplots(1, n_cond, figsize=(5 * n_cond, 4.5),
                              sharey=True, sharex=True)
    if n_cond == 1:
        axes = [axes]

    for i, cond in enumerate(cond_names):
        ax = axes[i]
        arr = cond_distances[cond]
        color = _CONDITION_COLORS[i % len(_CONDITION_COLORS)]
        ax.hist(np.log10(arr), bins=60, color=color,
                edgecolor="white", linewidth=0.3, alpha=0.85)
        ax.set_title(f"{cond}  (n={len(arr):,})",
                      fontsize=12, fontweight="bold")
        ax.set_xlabel("log$_{10}$(Distance to nearest TSS)", fontsize=10)
        if i == 0:
            ax.set_ylabel("Number of peaks", fontsize=10)

        for dist, label in [
            (_PROMOTER_DIST, "1 kb"),
            (_PROXIMAL_DIST, "5 kb"),
            (_DISTAL_DIST, "50 kb"),
        ]:
            ax.axvline(np.log10(dist), color="#999999", linestyle="--",
                       linewidth=0.8)
            ax.text(np.log10(dist), ax.get_ylim()[1] * 0.95, f" {label}",
                    fontsize=7, color="#666666", va="top")

    fig.suptitle("Peak Distance to TSS by Condition",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save_figure(fig, filename, output_dir)


def plot_annotation_grouped_bar(
    annotation_results: dict[str, PeakAnnotationResult],
    output_dir: Path,
    *,
    filename: str = "peak_annotation_bar_comparison",
) -> None:
    """
    Grouped bar chart — one bar per category per condition, with count
    labels on top.  Publication-quality (300 dpi, PDF + PNG).
    """
    import matplotlib.pyplot as plt
    _setup_plot_style()

    if len(annotation_results) < 2:
        return

    categories = _get_ordered_categories(annotation_results)
    conditions = list(annotation_results.keys())
    n_cond = len(conditions)
    n_cat = len(categories)

    # Build count matrix [condition x category]
    counts_matrix = np.zeros((n_cond, n_cat), dtype=int)
    for i, cond in enumerate(conditions):
        cc = annotation_results[cond].category_counts
        for j, cat in enumerate(categories):
            counts_matrix[i, j] = cc.get(cat, 0)

    x = np.arange(n_cat)
    bar_width = 0.8 / n_cond
    fig, ax = plt.subplots(figsize=(6, 6))

    for i, cond in enumerate(conditions):
        color = _CONDITION_COLORS[i % len(_CONDITION_COLORS)]
        offset = (i - (n_cond - 1) / 2) * bar_width
        bars = ax.bar(x + offset, counts_matrix[i], bar_width,
                       color=color, edgecolor="white", linewidth=0.5,
                       label=cond)
        # Count labels on top of each bar
        for bar, val in zip(bars, counts_matrix[i]):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{val:,}", ha="center", va="bottom",
                        fontsize=7, color="#333333")

    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Number of peaks", fontsize=11)
    ax.legend(frameon=False, fontsize=10)

    # Four spines, thin and dark
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color("#333333")
    ax.tick_params(direction="out", width=0.8)

    fig.tight_layout()
    _save_figure(fig, filename, output_dir)


# ===========================================================================
# Helpers
# ===========================================================================

def _load_annotation_summary(summary_csv: Path) -> dict[str, int]:
    """Reload annotation summary from cache."""
    counts: dict[str, int] = {}
    if not summary_csv.exists():
        return counts
    with open(summary_csv) as f:
        next(f)  # header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2:
                counts[parts[0]] = int(parts[1])
    return counts

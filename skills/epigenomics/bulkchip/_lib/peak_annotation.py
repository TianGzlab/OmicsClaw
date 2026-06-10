"""
peak_annotation.py — Peak→gene genomic annotation for bulk ChIP-seq.

Annotates a ChIP-seq peak set (consensus / per-condition / DA up-down) with
genomic features using HOMER ``annotatePeaks.pl``. Falls back to ``bedtools
closest`` against TSS positions extracted from a GTF (distance-based only) when
HOMER is unavailable. Degrades gracefully (feature-less output, no crash) when
neither a HOMER genome nor a GTF is available.

This is the annotation engine consumed by the ``bulkchip-peak-annotation``
skill. It mirrors the bulkatac ``peak_annotation`` engine but exposes the
ChIP ``AnnotationResult`` contract (annotated_tsv, feature_counts,
target_genes, pie_png, tss_dist_png).

HOMER annotation categories
----------------------------
  Promoter-TSS, TTS, 5'UTR, 3'UTR, Exon, Intron, Intergenic, Non-coding

Output
------
  annotated_peaks.tsv          — peaks with feature + nearest-gene annotations
  homer_annotated_full.tsv     — full HOMER output (all columns), HOMER only
  peak_annotation_summary.csv  — counts per feature category
  peak_annotation_pie.{pdf,png}— donut chart of feature distribution
  peak_tss_distance.{pdf,png}  — histogram of distance to nearest TSS

Dependencies (lazy-imported)
----------------------------
  HOMER (annotatePeaks.pl) — preferred
  bedtools + GTF           — fallback
  pandas / numpy / matplotlib — imported lazily inside functions so this module
                                imports in the base env.

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


@dataclass
class AnnotationResult:
    """Output of annotate_peaks() for one peak set."""
    annotated_tsv:    Path                          # per-peak feature + nearest gene
    feature_counts:   dict[str, int] = field(default_factory=dict)  # feature → n
    target_genes:     list[str] = field(default_factory=list)       # genes within TSS window
    pie_png:          Path | None = None
    tss_dist_png:     Path | None = None


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
# Internal annotation record
# ===========================================================================

# Each annotated peak is captured as a tuple so plots / target-gene extraction
# can work uniformly across the HOMER and bedtools paths:
#   (peak_chr, peak_start, peak_end, nearest_gene, distance, category)


# ===========================================================================
# HOMER-based annotation (preferred)
# ===========================================================================

def _classify_homer_annotation(annotation_str: str) -> str:
    """
    Map a HOMER ``Annotation`` column value to a simplified category.

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
    peaks_bed: Path,
    output_dir: Path,
    *,
    genome: str | None = None,
    gtf: Path | None = None,
) -> tuple[Path, dict[str, int], list[tuple]]:
    """
    Annotate peaks using HOMER annotatePeaks.pl.

    Two modes:
      1. Pre-installed genome:  annotatePeaks.pl peaks.bed hg38
         Requires: configureHomer.pl -install <genome>
      2. Custom GTF:            annotatePeaks.pl peaks.bed none -gtf genes.gtf
         No genome install needed — uses the GTF directly.

    If both genome and gtf are provided, uses the GTF (more portable).

    Returns (annotated_tsv, feature_counts, records) where records is a list of
    (peak_chr, peak_start, peak_end, nearest_gene, distance, category) tuples.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    homer_full    = output_dir / "homer_annotated_full.tsv"
    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    # Build HOMER command. Prefer -gtf (no genome install needed).
    if gtf and gtf.exists():
        gtf_path = gtf
        if str(gtf).endswith(".gz"):
            import gzip as _gzip
            decompressed = gtf.parent / gtf.name.replace(".gz", "")
            if not decompressed.exists():
                logger.info("Decompressing GTF: %s → %s", gtf, decompressed)
                with _gzip.open(gtf, "rb") as f_in, open(decompressed, "wb") as f_out:
                    f_out.write(f_in.read())
            gtf_path = decompressed
        cmd = ["annotatePeaks.pl", str(peaks_bed), "none", "-gtf", str(gtf_path)]
        logger.info("HOMER: using custom GTF: %s", gtf_path)
    elif genome:
        cmd = ["annotatePeaks.pl", str(peaks_bed), genome]
        logger.info("HOMER: using pre-installed genome: %s", genome)
    else:
        raise RuntimeError(
            "HOMER annotatePeaks.pl requires either a GTF file (-gtf) "
            "or a pre-installed genome name."
        )

    result = _run(cmd, label="HOMER annotatePeaks.pl")

    if result.stderr:
        for stderr_line in result.stderr.strip().splitlines()[:20]:
            logger.info("  HOMER: %s", stderr_line)

    with open(homer_full, "w") as f:
        f.write(result.stdout)

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

    categories: dict[str, int] = {}
    records: list[tuple] = []
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

        try:
            dist_int = int(float(distance))
        except (ValueError, TypeError):
            dist_int = 0

        records.append((peak_chr, peak_start, peak_end, gene_name, dist_int, category))
        rows.append(
            f"{peak_chr}\t{peak_start}\t{peak_end}\t{gene_name}\t"
            f"{distance}\t{category}\t{detailed}\t{gene_type}\n"
        )

    with open(annotated_tsv, "w") as f:
        f.write(header)
        f.writelines(rows)

    _write_summary(summary_csv, categories, len(rows))

    logger.info("HOMER peak annotation: %d peaks annotated", len(rows))
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d (%.1f%%)", cat, count, count / max(len(rows), 1) * 100)

    return annotated_tsv, categories, records


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
    peaks_bed: Path,
    gtf: Path,
    output_dir: Path,
) -> tuple[Path, dict[str, int], list[tuple]]:
    """
    Fallback: annotate peaks by distance to nearest TSS using bedtools closest.

    Categories (distance-based only):
      - Promoter   : < 1 kb from TSS
      - Proximal   : 1–5 kb from TSS
      - Distal     : 5–50 kb from TSS
      - Intergenic : > 50 kb from TSS

    Returns (annotated_tsv, feature_counts, records).
    """
    _require("bedtools")
    output_dir.mkdir(parents=True, exist_ok=True)

    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    tss_bed = _extract_tss_from_gtf(gtf, output_dir)

    sorted_peaks = output_dir / "peaks_sorted.bed"
    _run(["sort", "-k1,1", "-k2,2n", str(peaks_bed), "-o", str(sorted_peaks)],
         label="sort peaks")

    result = _run(
        ["bedtools", "closest",
         "-a", str(sorted_peaks),
         "-b", str(tss_bed),
         "-d",            # report distance
         "-t", "first"],  # ties: take first
        label="bedtools closest",
    )

    categories: dict[str, int] = {
        "Promoter": 0, "Proximal": 0, "Distal": 0, "Intergenic": 0,
    }
    records: list[tuple] = []
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
        records.append((peak_chr, peak_start, peak_end, gene_name, distance, cat))
        rows.append(f"{peak_chr}\t{peak_start}\t{peak_end}\t{gene_name}\t{distance}\t{cat}\n")

    with open(annotated_tsv, "w") as f:
        f.write(header)
        f.writelines(rows)

    _write_summary(summary_csv, categories, len(rows))

    if sorted_peaks.exists():
        sorted_peaks.unlink()

    logger.info("Bedtools peak annotation (fallback): %d peaks annotated", len(rows))
    for cat, count in categories.items():
        logger.info("  %s: %d (%.1f%%)", cat, count, count / max(len(rows), 1) * 100)

    return annotated_tsv, categories, records


# ===========================================================================
# Graceful no-annotation fallback (neither HOMER genome nor GTF available)
# ===========================================================================

def _annotate_features_unavailable(
    peaks_bed: Path,
    output_dir: Path,
) -> tuple[Path, dict[str, int], list[tuple]]:
    """
    Write a feature-less annotated table when no annotation source is available.

    Peaks are copied through with empty gene / category fields so downstream
    consumers still receive a well-formed ``annotated_peaks.tsv``. No
    feature_counts and no target_genes are produced. Mirrors bulkatac's
    graceful degradation (warn + emit, do not crash).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    annotated_tsv = output_dir / "annotated_peaks.tsv"
    summary_csv   = output_dir / "peak_annotation_summary.csv"

    rows: list[str] = []
    header = "peak_chr\tpeak_start\tpeak_end\tnearest_gene\tdistance\tcategory\n"

    if peaks_bed.exists():
        with open(peaks_bed) as fin:
            for line in fin:
                if line.startswith(("#", "track", "browser")):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                rows.append(f"{parts[0]}\t{parts[1]}\t{parts[2]}\t.\t.\tNA\n")

    with open(annotated_tsv, "w") as f:
        f.write(header)
        f.writelines(rows)

    _write_summary(summary_csv, {}, len(rows))

    logger.warning(
        "Peak annotation: neither a HOMER genome nor a GTF was available — "
        "wrote %d peaks with no feature / gene annotation to %s",
        len(rows), annotated_tsv,
    )
    return annotated_tsv, {}, []


def _write_summary(summary_csv: Path, categories: dict[str, int], n_peaks: int) -> None:
    """Write per-category counts + fractions (lazy pandas; plain-text fallback)."""
    rows = sorted(categories.items(), key=lambda x: -x[1])
    try:
        import pandas as pd
        pd.DataFrame([
            {"category": k, "count": v, "fraction": v / max(n_peaks, 1)}
            for k, v in rows
        ]).to_csv(summary_csv, index=False)
    except ImportError:
        with open(summary_csv, "w") as f:
            f.write("category,count,fraction\n")
            for k, v in rows:
                f.write(f"{k},{v},{v / max(n_peaks, 1)}\n")


# ===========================================================================
# Target-gene extraction
# ===========================================================================

def _extract_target_genes(records: list[tuple], tss_window: int) -> list[str]:
    """
    Unique nearest genes whose absolute TSS distance is within ``tss_window``.

    Preserves first-seen order so the gene list is deterministic.
    """
    seen: set[str] = set()
    genes: list[str] = []
    for rec in records:
        gene = rec[3]
        dist = rec[4]
        if gene in (".", "", "NA", None):
            continue
        try:
            if abs(int(dist)) > tss_window:
                continue
        except (ValueError, TypeError):
            continue
        if gene not in seen:
            seen.add(gene)
            genes.append(gene)
    return genes


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


def _save_figure(fig, name: str, output_dir: Path) -> Path:
    import matplotlib.pyplot as plt
    png_path = output_dir / f"{name}.png"
    for ext in ("pdf", "png"):
        fig.savefig(output_dir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    return png_path


# ChIPseeker Paired palette (ColorBrewer) — standard for genomic annotation
# Source: ChIPseeker (Yu G, Wang LG, He QY. Bioinformatics 2015;31(14):2382-3)
_ANNOTATION_COLORS = {
    "Promoter-TSS": "#a6cee3",
    "5'UTR":        "#1f78b4",
    "3'UTR":        "#b2df8a",
    "Exon":         "#33a02c",
    "Intron":       "#fdbf6f",
    "TTS":          "#ff7f00",
    "Intergenic":   "#cab2d6",
    "Non-coding":   "#6a3d9a",
    "Other":        "#d9d9d9",
    # Bedtools fallback categories
    "Promoter":     "#a6cee3",
    "Proximal":     "#fb9a99",
    "Distal":       "#fdbf6f",
}


def plot_annotation_pie(
    feature_counts: dict[str, int],
    output_dir: Path,
    *,
    title: str | None = None,
    filename: str = "peak_annotation_pie",
) -> Path | None:
    """Donut chart of peak annotation categories (publication-quality)."""
    if not feature_counts or sum(feature_counts.values()) == 0:
        return None

    import matplotlib.pyplot as plt
    _setup_plot_style()

    total = sum(feature_counts.values())
    sorted_items = sorted(feature_counts.items(), key=lambda x: -x[1])
    labels = [k for k, _ in sorted_items]
    sizes  = [v for _, v in sorted_items]
    colors = [_ANNOTATION_COLORS.get(lbl, "#d9d9d9") for lbl in labels]

    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, _ = ax.pie(
        sizes, colors=colors,
        startangle=90, counterclock=False,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=1.5),
    )
    ax.text(0, 0, f"{total:,}\npeaks", ha="center", va="center",
            fontsize=13, fontweight="bold", color="#333333")
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)

    legend_labels = [
        f"{lbl}  ({v:,}, {v / total * 100:.1f}%)"
        for lbl, v in zip(labels, sizes)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="center left", bbox_to_anchor=(1.0, 0.5),
        frameon=False, fontsize=9, handlelength=1.2,
    )

    return _save_figure(fig, filename, output_dir)


def plot_tss_distance_histogram(
    annotated_tsv: Path,
    output_dir: Path,
    *,
    title: str = "Peak distance to TSS",
    filename: str = "peak_tss_distance",
) -> Path | None:
    """Histogram of peak distance to nearest TSS (log10)."""
    import numpy as np

    distances = _read_tss_distances(annotated_tsv)
    if not distances:
        return None

    import matplotlib.pyplot as plt
    _setup_plot_style()

    dist_arr = np.array(distances)
    dist_arr = dist_arr[dist_arr > 0]  # exclude 0 for log
    if len(dist_arr) == 0:
        return None

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.hist(np.log10(dist_arr), bins=50, color="#4C72B0", edgecolor="black",
            linewidth=0.3)
    ax.set_xlabel("log$_{10}$(Distance to nearest TSS)", fontsize=11)
    ax.set_ylabel("Number of peaks", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")

    for dist, label in [
        (_PROMOTER_DIST, "1 kb"),
        (_PROXIMAL_DIST, "5 kb"),
        (_DISTAL_DIST, "50 kb"),
    ]:
        ax.axvline(np.log10(dist), color="#999999", linestyle="--",
                   linewidth=0.8, label=label)
    ax.legend(loc="upper right", frameon=False)

    return _save_figure(fig, filename, output_dir)


def _read_tss_distances(annotated_tsv: Path) -> list[int]:
    """Read absolute TSS distances from an annotated peaks TSV."""
    distances: list[int] = []
    if not annotated_tsv.exists():
        return distances
    with open(annotated_tsv) as f:
        header = next(f).strip().split("\t")
        dist_col = header.index("distance") if "distance" in header else 4
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) > dist_col:
                try:
                    distances.append(abs(int(float(parts[dist_col]))))
                except ValueError:
                    continue
    return distances


# ===========================================================================
# Main entry point
# ===========================================================================

def annotate_peaks(
    peaks_bed: Path,
    output_dir: Path,
    *,
    genome: str | None = None,
    gtf: Path | None = None,
    tss_window: int = 3000,
    threads: int = 8,  # noqa: ARG001 — accepted for signature symmetry / future use
) -> AnnotationResult:
    """
    Annotate ChIP-seq peaks with genomic features + nearest genes.

    Priority:
      1. HOMER + GTF    → annotatePeaks.pl peaks.bed none -gtf genes.gtf
                          (best: no genome install, uses your exact GTF)
      2. HOMER + genome → annotatePeaks.pl peaks.bed <genome>
                          (requires: configureHomer.pl -install <genome>)
      3. bedtools + GTF → distance-based fallback
                          (Promoter / Proximal / Distal / Intergenic)
      4. none available → graceful feature-less output (warn, no crash)

    Parameters
    ----------
    peaks_bed   : peak BED (consensus / per-condition / DA up-down subset)
    output_dir  : directory for output files
    genome      : genome name (e.g. "hg38"); used as HOMER genome when no GTF
    gtf         : GTF (used by HOMER -gtf and the bedtools fallback)
    tss_window  : peaks whose nearest-gene TSS distance ≤ this (bp) define the
                  target-gene set (default 3000)
    threads     : accepted for symmetry (HOMER/bedtools paths are single-threaded here)

    Returns
    -------
    AnnotationResult with annotated_tsv, feature_counts, target_genes,
    pie_png, tss_dist_png.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    has_homer = _check_tool("annotatePeaks.pl")
    has_gtf   = gtf is not None and Path(gtf).exists()
    gtf_path  = Path(gtf) if gtf is not None else None

    annotated_tsv: Path
    feature_counts: dict[str, int]
    records: list[tuple]

    # Priority 1: HOMER + GTF
    if has_homer and has_gtf:
        logger.info("Using HOMER annotatePeaks.pl with custom GTF: %s", gtf_path)
        annotated_tsv, feature_counts, records = _annotate_with_homer(
            peaks_bed, output_dir, gtf=gtf_path,
        )
    # Priority 2: HOMER + pre-installed genome (may fail if not installed)
    elif has_homer and genome:
        logger.info("Trying HOMER annotatePeaks.pl with genome: %s", genome)
        try:
            annotated_tsv, feature_counts, records = _annotate_with_homer(
                peaks_bed, output_dir, genome=genome,
            )
        except RuntimeError as e:
            logger.warning("HOMER with genome '%s' failed: %s", genome, e)
            for f in (output_dir / "homer_annotated_full.tsv",
                      output_dir / "annotated_peaks.tsv",
                      output_dir / "peak_annotation_summary.csv"):
                if f.exists():
                    f.unlink()
            if has_gtf:
                logger.warning("Falling back to bedtools closest.")
                annotated_tsv, feature_counts, records = _annotate_with_bedtools(
                    peaks_bed, gtf_path, output_dir,
                )
            else:
                annotated_tsv, feature_counts, records = _annotate_features_unavailable(
                    peaks_bed, output_dir,
                )
    # Priority 3: bedtools + GTF
    elif has_gtf:
        if not has_homer:
            logger.warning(
                "HOMER not found (install: conda install -c bioconda homer). "
                "Using bedtools closest (distance-based only)."
            )
        annotated_tsv, feature_counts, records = _annotate_with_bedtools(
            peaks_bed, gtf_path, output_dir,
        )
    # Priority 4: nothing available — graceful degradation
    else:
        annotated_tsv, feature_counts, records = _annotate_features_unavailable(
            peaks_bed, output_dir,
        )

    target_genes = _extract_target_genes(records, tss_window)
    logger.info("Target genes (TSS distance ≤ %d bp): %d", tss_window, len(target_genes))

    # Plots (degrade gracefully when there is nothing to plot)
    pie_png = plot_annotation_pie(
        feature_counts, output_dir,
        title="Peak feature distribution",
    )
    tss_dist_png = plot_tss_distance_histogram(annotated_tsv, output_dir)

    return AnnotationResult(
        annotated_tsv=annotated_tsv,
        feature_counts=feature_counts,
        target_genes=target_genes,
        pie_png=pie_png,
        tss_dist_png=tss_dist_png,
    )

"""
QC_after_mapping.py — Post-alignment QC for bulk ATAC-seq.

Per-sample:  TSS enrichment (deepTools computeMatrix), fragment-length
             distribution (samtools), bigWig signal tracks (deepTools
             bamCoverage RPGC).
Cross-sample: overlay plots with ENCODE threshold comparisons.

Requires: samtools (always), deepTools (for bigWig + TSS enrichment),
          bedtools (fallback TSS enrichment).
"""

from __future__ import annotations

import gzip
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .encode_qc_criteria import (
    ENCODE_QC_THRESHOLDS,
    tss_tier,
)

# Genomes with ENCODE TSS enrichment thresholds (human + mouse only)
_ENCODE_TSS_GENOMES: frozenset[str] = frozenset({
    "hg38", "hg19",   # human
    "mm10", "mm39",   # mouse
})
from .mapping import (
    MappingResult,
    generate_bigwig,
    generate_all_bigwigs,
    _EFFECTIVE_GENOME_SIZES,
)

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Nucleosome periodicity bands (bp) for fragment-length annotation
# Ref: Buenrostro et al., Nat Methods 2013 https://doi.org/10.1038/nmeth.2688
_NFR_RANGE  = (0, 147)       # nucleosome-free region
_MONO_RANGE = (147, 294)     # mono-nucleosomal
_DI_RANGE   = (294, 440)     # di-nucleosomal

_MAX_FRAG_LENGTH = 1000      # cap for histogram

# TSS enrichment window
_TSS_EXTEND  = 2000   # bp upstream/downstream of TSS
_TSS_BINSIZE = 10     # bp per bin


# ===========================================================================
# Result dataclass
# ===========================================================================

@dataclass
class QcAfterMappingResult:
    """Output of run_qc_after_mapping() for one sample."""
    sample_name:      str
    # TSS enrichment
    tss_score:        float         = 0.0
    tss_tier:         str           = ""
    tss_profile:      np.ndarray | None = field(default=None, repr=False)
    tss_positions:    np.ndarray | None = field(default=None, repr=False)
    tss_data_file:    Path | None   = None
    # Fragment-length distribution
    frag_mode:        int           = 0       # mode of distribution (bp)
    nfr_fraction:     float         = 0.0     # fraction of fragments < 147 bp
    mono_fraction:    float         = 0.0     # fraction 147–294 bp
    frag_hist:        np.ndarray | None = field(default=None, repr=False)
    frag_bins:        np.ndarray | None = field(default=None, repr=False)
    frag_data_file:   Path | None   = None
    # BigWig
    bigwig:           Path | None   = None


# ===========================================================================
# BAM selection helper
# ===========================================================================

def get_analysis_bam(result: MappingResult) -> Path:
    """Return the BAM for QC. Uses full-depth dedup BAM by default;
    falls back to downsampled BAM only when --downsample was used."""
    if result.downsampled and result.bam_downsampled and result.bam_downsampled.exists():
        return result.bam_downsampled
    return result.bam


# ===========================================================================
# Fragment-length distribution  (samtools — always available)
# ===========================================================================

def compute_fragment_length(
    sample_name: str,
    bam: Path,
    output_dir: Path,
    *,
    max_length: int = _MAX_FRAG_LENGTH,
) -> dict[str, Any]:
    """
    Extract insert-size distribution from a paired-end BAM.

    Uses ``samtools view -f 66`` (paired + first-in-pair) to avoid
    double-counting fragments, then collects positive TLEN values.

    Returns
    -------
    dict with keys: hist (counts array), bins (length array), mode,
    nfr_fraction, mono_fraction, data_file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    data_file = output_dir / f"{sample_name}.fragment_length.txt"

    if data_file.exists() and data_file.stat().st_size > 0:
        return _load_fragment_data(data_file, sample_name)

    # samtools view -f 66: paired(0x1) + first_in_pair(0x40) = 0x42 = 66
    # Extract positive TLEN (column 9) capped at max_length
    cmd = (
        f"samtools view -f 66 {bam} "
        f"| awk '($9 > 0 && $9 < {max_length}) {{print $9}}'"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Fragment length extraction failed for %s: %s",
                        sample_name, result.stderr[-500:])
        return {"hist": np.array([]), "bins": np.array([]), "mode": 0,
                "nfr_fraction": 0.0, "mono_fraction": 0.0, "data_file": None}

    lengths = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            try:
                lengths.append(int(line.strip()))
            except ValueError:
                pass

    if not lengths:
        logger.warning("[%s] No fragment lengths extracted.", sample_name)
        return {"hist": np.array([]), "bins": np.array([]), "mode": 0,
                "nfr_fraction": 0.0, "mono_fraction": 0.0, "data_file": None}

    arr = np.array(lengths)
    bins = np.arange(0, max_length + 1, 1)
    hist, _ = np.histogram(arr, bins=bins)

    mode = int(bins[np.argmax(hist)])
    total = len(arr)
    nfr_count  = int(np.sum((arr >= _NFR_RANGE[0]) & (arr < _NFR_RANGE[1])))
    mono_count = int(np.sum((arr >= _MONO_RANGE[0]) & (arr < _MONO_RANGE[1])))
    nfr_fraction  = nfr_count / total if total > 0 else 0.0
    mono_fraction = mono_count / total if total > 0 else 0.0

    # Write data file (length\tcount)
    with open(data_file, "w") as f:
        f.write("length\tcount\n")
        for i in range(len(hist)):
            f.write(f"{bins[i]}\t{hist[i]}\n")

    logger.info("  [%s] fragment mode=%d bp | NFR=%.1f%% | mono=%.1f%%",
                sample_name, mode, nfr_fraction * 100, mono_fraction * 100)

    return {
        "hist": hist, "bins": bins[:-1], "mode": mode,
        "nfr_fraction": nfr_fraction, "mono_fraction": mono_fraction,
        "data_file": data_file,
    }


def _load_fragment_data(data_file: Path, sample_name: str) -> dict[str, Any]:
    """Reload previously computed fragment-length data."""
    bins_list, hist_list = [], []
    with open(data_file) as f:
        next(f)  # skip header
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                bins_list.append(int(parts[0]))
                hist_list.append(int(parts[1]))
    bins = np.array(bins_list)
    hist = np.array(hist_list)
    mode = int(bins[np.argmax(hist)]) if len(hist) > 0 else 0
    total = int(np.sum(hist))
    nfr_mask  = (bins >= _NFR_RANGE[0]) & (bins < _NFR_RANGE[1])
    mono_mask = (bins >= _MONO_RANGE[0]) & (bins < _MONO_RANGE[1])
    nfr_fraction  = int(np.sum(hist[nfr_mask])) / total if total > 0 else 0.0
    mono_fraction = int(np.sum(hist[mono_mask])) / total if total > 0 else 0.0
    logger.info("  [%s] fragment data loaded from cache: mode=%d bp", sample_name, mode)
    return {
        "hist": hist, "bins": bins, "mode": mode,
        "nfr_fraction": nfr_fraction, "mono_fraction": mono_fraction,
        "data_file": data_file,
    }


# ===========================================================================
# TSS enrichment  (deepTools computeMatrix + plotProfile)
# ===========================================================================

def compute_tss_enrichment(
    sample_name: str,
    bigwig: Path,
    gtf: Path,
    output_dir: Path,
    *,
    genome: str = "",
    tissue_type: str | None = None,
    extend: int = _TSS_EXTEND,
    bin_size: int = _TSS_BINSIZE,
    threads: int = 8,
) -> dict[str, Any]:
    """
    Compute TSS enrichment score and signal profile.

    Passes the GTF directly to ``computeMatrix reference-point
    --referencePoint TSS -R <gtf>``.  deepTools extracts TSS positions
    from GTF transcript records internally, so the reference point is
    always anchored exactly at each TSS (position 0).

    TSS score = max(normalised profile) where the profile is normalised
    by flanking signal (outermost 100 bp each side → background = 1.0).

    ENCODE tier is assigned only for human/mouse genomes (hg38, hg19,
    mm10, mm39).  For other organisms the score is computed but no tier
    is assigned (reported as "—").

    Returns
    -------
    dict with keys: score, tier, positions (array), profile (array),
    data_file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    data_file   = output_dir / f"{sample_name}.tss_enrichment.txt"
    matrix_gz   = output_dir / f"{sample_name}.tss_matrix.gz"
    profile_tab = output_dir / f"{sample_name}.tss_profile_raw.tab"

    if data_file.exists() and data_file.stat().st_size > 0:
        return _load_tss_data(data_file, sample_name)

    if not _check_tool("computeMatrix"):
        logger.warning(
            "computeMatrix (deeptools) not found — skipping TSS enrichment "
            "for %s. Install: conda install -c bioconda deeptools",
            sample_name,
        )
        return _empty_tss_result()

    # Step 1: computeMatrix reference-point using GTF directly
    # deepTools parses transcript features from the GTF and anchors
    # --referencePoint TSS at each transcript start site.
    _run(
        ["computeMatrix", "reference-point",
         "-S", str(bigwig),
         "-R", str(gtf),
         "--referencePoint", "TSS",
         "-b", str(extend), "-a", str(extend),
         "--binSize", str(bin_size),
         "-o", str(matrix_gz),
         "-p", str(threads),
         "--skipZeros",
         "--sortRegions", "descend",
         "--sortUsing", "mean"],
        label=f"computeMatrix [{sample_name}]",
    )

    # Step 2: plotProfile → extract data table
    # plotProfile requires a real output file (rejects /dev/null)
    dummy_plot = output_dir / f"{sample_name}.tss_profile_tmp.png"
    _run(
        ["plotProfile",
         "-m", str(matrix_gz),
         "--outFileNameData", str(profile_tab),
         "-o", str(dummy_plot)],
        label=f"plotProfile data [{sample_name}]",
    )
    _rm(dummy_plot)

    # Step 3: parse profile table — use signal values from plotProfile,
    # but compute positions ourselves (plotProfile "bins" row contains
    # bin indices, not genomic coordinates relative to TSS).
    _, profile = _parse_profile_tab(profile_tab)

    if len(profile) == 0:
        logger.warning("[%s] Empty TSS profile.", sample_name)
        return _empty_tss_result()

    n_bins = len(profile)
    positions = np.linspace(-extend, extend - bin_size, n_bins)

    # Step 4: compute TSS enrichment score
    # Ref: ATACseqQC TSSEscore — normalise by flanking signal so that
    # background = 1.0 and the score = fold enrichment at TSS.
    # Flanks: 100 bp at each end of the window (positions near ±extend).
    # Ref: https://rdrr.io/bioc/ATACseqQC/man/TSSEscore.html
    flank_mask = np.abs(positions) >= (extend - 100)   # outermost 100 bp each side
    flank_signal = np.mean(profile[flank_mask]) if np.any(flank_mask) else 0.0

    # Normalise: divide entire profile by flank signal → background = 1.0
    if flank_signal > 0:
        norm_profile = profile / flank_signal
    else:
        norm_profile = profile.copy()

    # TSS score = max of the normalised profile (peak enrichment over background)
    score = float(np.max(norm_profile)) if len(norm_profile) > 0 else 0.0
    # Use normalised profile for plotting (y-axis = fold enrichment)
    profile = norm_profile

    # ENCODE tier only when user specifies cell_type AND genome is human/mouse
    if tissue_type is not None and genome in _ENCODE_TSS_GENOMES:
        tier = tss_tier(score, tissue_type=tissue_type)
    else:
        tier = "—"

    # Write data file
    with open(data_file, "w") as f:
        f.write(f"# tss_score={score:.4f}\n")
        f.write(f"# tss_tier={tier}\n")
        f.write("position\tsignal\n")
        for pos, sig in zip(positions, profile):
            f.write(f"{pos}\t{sig:.6f}\n")

    logger.info("  [%s] TSS enrichment = %.2f  [%s]", sample_name, score, tier)

    # Cleanup intermediates
    _rm(matrix_gz)
    _rm(profile_tab)

    return {
        "score": score, "tier": tier,
        "positions": positions, "profile": profile,
        "data_file": data_file,
    }


def _parse_profile_tab(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse deepTools plotProfile --outFileNameData output.

    Format (deepTools save_tabulated_values):
      row 0: "bin labels" \\t \\t label1 \\t label2 ...
      row 1: "bins"       \\t \\t pos1   \\t pos2   ...
      row 2: sample_name  \\t group \\t val1 \\t val2 ...

    The first two columns of the data row are sample name and group;
    actual signal values start at column index 2.
    """
    positions, values = [], []
    with open(path) as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]

    if len(lines) < 3:
        logger.warning("plotProfile data file has < 3 lines: %s", path)
        return np.array([]), np.array([])

    # Row 1 (index 1): bin positions — skip first 2 columns ("bins", "")
    pos_parts = lines[1].split("\t")[2:]
    for p in pos_parts:
        p = p.strip()
        if p:
            try:
                positions.append(float(p))
            except ValueError:
                pass

    # Row 2+ (data rows): signal values — skip first 2 columns (sample, group)
    # Average across all data rows if multiple groups exist
    all_values: list[list[float]] = []
    for line in lines[2:]:
        parts = line.split("\t")[2:]
        row_vals = []
        for v in parts:
            v = v.strip()
            try:
                row_vals.append(float(v))
            except ValueError:
                row_vals.append(0.0)
        if row_vals:
            all_values.append(row_vals)

    if not all_values:
        return np.array([]), np.array([])

    # Average across groups
    arr = np.array(all_values)
    values = np.nanmean(arr, axis=0)

    n = min(len(positions), len(values))
    return np.array(positions[:n]), np.array(values[:n])


def _load_tss_data(data_file: Path, sample_name: str) -> dict[str, Any]:
    """Reload previously computed TSS enrichment data."""
    score, tier = 0.0, ""
    positions, profile = [], []
    with open(data_file) as f:
        for line in f:
            if line.startswith("# tss_score="):
                score = float(line.strip().split("=")[1])
            elif line.startswith("# tss_tier="):
                tier = line.strip().split("=")[1]
            elif line.startswith("position") or line.startswith("#"):
                continue
            else:
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    positions.append(float(parts[0]))
                    profile.append(float(parts[1]))
    logger.info("  [%s] TSS data loaded from cache: score=%.2f [%s]",
                sample_name, score, tier)
    return {
        "score": score, "tier": tier,
        "positions": np.array(positions), "profile": np.array(profile),
        "data_file": data_file,
    }


def _empty_tss_result() -> dict[str, Any]:
    return {
        "score": 0.0, "tier": "",
        "positions": np.array([]), "profile": np.array([]),
        "data_file": None,
    }


# ===========================================================================
# Plotting helpers
# ===========================================================================

def _setup_plot_style() -> None:
    """Configure matplotlib for publication-quality figures."""
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family":       "sans-serif",
        "font.sans-serif":   ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size":         10,
        "axes.titlesize":    12,
        "axes.labelsize":    11,
        "xtick.labelsize":   9,
        "ytick.labelsize":   9,
        "legend.fontsize":   8,
        "figure.dpi":        150,
        "savefig.dpi":       300,
        "axes.linewidth":    0.8,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "axes.spines.top":   True,
        "axes.spines.right": True,
    })


def _save_figure(fig, stem: str, output_dir: Path) -> None:
    """Save figure as PNG (dpi=300) and PDF, then close."""
    import matplotlib.pyplot as plt
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    logger.info("  Saved %s.{png,pdf}", stem)


# ── Per-sample fragment-length plot ──────────────────────────────────────────

def plot_fragment_length_single(
    sample_name: str,
    hist: np.ndarray,
    bins: np.ndarray,
    output_dir: Path,
) -> None:
    """Single-sample fragment-length histogram with NFR/mono/di bands."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.fill_between(bins, hist, alpha=0.4, color="#4C72B0")
    ax.plot(bins, hist, color="#4C72B0", linewidth=0.8)

    # Shade nucleosome bands
    ax.axvspan(*_NFR_RANGE,  alpha=0.08, color="#2ca02c", label="NFR (<147 bp)")
    ax.axvspan(*_MONO_RANGE, alpha=0.08, color="#ff7f0e", label="Mono (147–294 bp)")
    ax.axvspan(*_DI_RANGE,   alpha=0.08, color="#d62728", label="Di (294–440 bp)")

    ax.set_xlabel("Fragment length (bp)")
    ax.set_ylabel("Count")
    ax.set_title(sample_name)
    ax.legend(loc="upper right", frameon=False)
    ax.set_xlim(0, 800)

    _save_figure(fig, f"{sample_name}.fragment_length", output_dir)


# ── Per-sample TSS enrichment plot ───────────────────────────────────────────

def plot_tss_enrichment_single(
    sample_name: str,
    positions: np.ndarray,
    profile: np.ndarray,
    score: float,
    output_dir: Path,
) -> None:
    """Single-sample TSS enrichment profile."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.fill_between(positions, profile, alpha=0.3, color="#4C72B0")
    ax.plot(positions, profile, color="#4C72B0", linewidth=1.0)
    ax.axvline(0, color="#555555", linestyle="--", linewidth=0.8, label="TSS")
    ax.axhline(1.0, color="#999999", linestyle=":", linewidth=0.6, label="Background")
    ax.set_xlabel("Distance from TSS (bp)")
    ax.set_ylabel("TSS enrichment score")
    ax.set_title(f"{sample_name}  (TSS score = {score:.2f})")
    ax.legend(loc="upper right", frameon=False)

    _save_figure(fig, f"{sample_name}.tss_enrichment", output_dir)


# ── Cross-sample fragment-length overlay ─────────────────────────────────────

def plot_fragment_length_all(
    all_results: list[QcAfterMappingResult],
    output_dir: Path,
) -> None:
    """Overlay fragment-length distributions for all samples."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    valid = [r for r in all_results if r.frag_hist is not None and len(r.frag_hist) > 0]
    if not valid:
        return

    fig, ax = plt.subplots(figsize=(6, 6))

    # Shade nucleosome bands first (behind lines)
    ax.axvspan(*_NFR_RANGE,  alpha=0.06, color="#2ca02c", label="NFR (<147 bp)")
    ax.axvspan(*_MONO_RANGE, alpha=0.06, color="#ff7f0e", label="Mono (147–294 bp)")
    ax.axvspan(*_DI_RANGE,   alpha=0.06, color="#d62728", label="Di (294–440 bp)")

    # Ref: Buenrostro et al., Nat Methods 2013
    colors = plt.cm.Set2(np.linspace(0, 1, max(len(valid), 3)))
    for i, r in enumerate(valid):
        total = np.sum(r.frag_hist)
        density = r.frag_hist / total if total > 0 else r.frag_hist
        ax.plot(r.frag_bins, density, linewidth=1.0, alpha=0.85,
                color=colors[i], label=f"{r.sample_name} (mode={r.frag_mode} bp)")

    ax.set_xlabel("Fragment length (bp)")
    ax.set_ylabel("Density")
    ax.set_title("Fragment-length distribution")
    ax.legend(loc="upper right", frameon=False)
    ax.set_xlim(0, 800)

    # Write combined data
    data_file = output_dir / "fragment_length_all.txt"
    with open(data_file, "w") as f:
        f.write("sample\tlength\tcount\n")
        for r in valid:
            for b, c in zip(r.frag_bins, r.frag_hist):
                f.write(f"{r.sample_name}\t{b}\t{c}\n")

    _save_figure(fig, "fragment_length_all", output_dir)


# ── Cross-sample TSS enrichment overlay ──────────────────────────────────────

def plot_tss_enrichment_all(
    all_results: list[QcAfterMappingResult],
    output_dir: Path,
) -> None:
    """Overlay TSS enrichment profiles for all samples."""
    import matplotlib.pyplot as plt
    _setup_plot_style()

    valid = [r for r in all_results
             if r.tss_profile is not None and len(r.tss_profile) > 0]
    if not valid:
        return

    fig, ax = plt.subplots(figsize=(6, 6))

    colors = plt.cm.Set2(np.linspace(0, 1, max(len(valid), 3)))
    for i, r in enumerate(valid):
        ax.plot(r.tss_positions, r.tss_profile, linewidth=1.0, alpha=0.85,
                color=colors[i], label=f"{r.sample_name} ({r.tss_score:.2f})")

    ax.axvline(0, color="#555555", linestyle="--", linewidth=0.8)
    ax.axhline(1.0, color="#999999", linestyle=":", linewidth=0.6)
    ax.set_xlabel("Distance from TSS (bp)")
    ax.set_ylabel("TSS enrichment score")
    ax.set_title("TSS enrichment profile")
    ax.legend(loc="upper right", frameon=False)

    # Write combined data
    data_file = output_dir / "tss_enrichment_all.txt"
    with open(data_file, "w") as f:
        f.write("sample\tposition\tsignal\n")
        for r in valid:
            for pos, sig in zip(r.tss_positions, r.tss_profile):
                f.write(f"{r.sample_name}\t{pos}\t{sig:.6f}\n")

    _save_figure(fig, "tss_enrichment_all", output_dir)


# ── TSS score vs ENCODE thresholds bar chart ─────────────────────────────────

def plot_tss_enrichment_vs_encode(
    all_results: list[QcAfterMappingResult],
    output_dir: Path,
    *,
    tissue_type: str | None = None,
) -> None:
    """Bar chart of TSS enrichment scores with ENCODE threshold lines.

    Only rendered when tissue_type is set (i.e. user passed --cell-type
    and genome is human/mouse).  Otherwise skipped.
    """
    import matplotlib.pyplot as plt

    if tissue_type is None:
        return

    valid = [r for r in all_results if r.tss_score > 0]
    if not valid:
        return

    t = ENCODE_QC_THRESHOLDS["tss_enrichment"]
    preferred  = t["preferred"]          # 7.0
    acceptable = t["acceptable_tissue"] if tissue_type == "tissue" else t["acceptable"]

    names  = [r.sample_name for r in valid]
    scores = [r.tss_score   for r in valid]

    # Colour bars by tier
    colours = []
    for s in scores:
        if s >= preferred:
            colours.append("#2ca02c")     # green
        elif s >= acceptable:
            colours.append("#ff7f0e")     # orange
        else:
            colours.append("#d62728")     # red

    _setup_plot_style()

    fig, ax = plt.subplots(figsize=(6, 6))
    bars = ax.bar(names, scores, color=colours, edgecolor="black", linewidth=0.3,
                  width=0.6)

    # ENCODE threshold lines
    ax.axhline(preferred, color="#2ca02c", linestyle="--", linewidth=1.0,
               label=f"Preferred (≥{preferred})")
    ax.axhline(acceptable, color="#ff7f0e", linestyle="--", linewidth=1.0,
               label=f"Acceptable (≥{acceptable})")

    ax.set_ylabel("TSS enrichment score")
    ax.set_title(f"TSS enrichment vs ENCODE ({tissue_type})")
    ax.legend(loc="upper right", frameon=False)
    if len(names) > 6:
        ax.tick_params(axis="x", rotation=45)

    # Write data
    data_file = output_dir / "tss_enrichment_vs_encode.txt"
    with open(data_file, "w") as f:
        f.write("sample\ttss_score\ttier\n")
        for r in valid:
            f.write(f"{r.sample_name}\t{r.tss_score:.4f}\t{r.tss_tier}\n")

    _save_figure(fig, "tss_enrichment_vs_encode", output_dir)


# ===========================================================================
# Main per-sample entry point
# ===========================================================================

def run_qc_after_mapping(
    mapping_result: MappingResult,
    genome_files: "GenomeFiles",
    mapping_dir: Path,
    *,
    threads: int = 8,
    tissue_type: str | None = None,
) -> QcAfterMappingResult:
    """
    Run all post-alignment QC for one sample.

    Reads the analysis BAM (downsampled if available), generates bigWig,
    computes TSS enrichment and fragment-length distribution.

    Parameters
    ----------
    mapping_result : MappingResult from run_mapping()
    genome_files   : GenomeFiles with gtf, genome, chrom_sizes
    mapping_dir    : root mapping output dir (contains bam/, bigwig/, qc_after_mapping/)
    threads        : number of threads
    tissue_type    : None (score only), "cell_line", or "tissue".
                     ENCODE tier assigned only when set AND genome is human/mouse.
    """
    sample     = mapping_result.sample_name
    bam        = get_analysis_bam(mapping_result)
    genome     = genome_files.genome
    gtf        = genome_files.gtf

    bigwig_dir = mapping_dir / "bigwig"
    qc_dir     = mapping_dir / "qc_after_mapping"
    tss_dir    = qc_dir / "tss_enrichment"
    frag_dir   = qc_dir / "fragment_length"

    logger.info("QC after mapping: %s  [bam=%s]", sample, bam.name)

    # ── BigWig ─────────────────────────────────────────────────────────────
    bw = generate_bigwig(
        sample, bam, bigwig_dir,
        genome=genome, genome_fasta=genome_files.fasta,
        threads=threads, downsampled=mapping_result.downsampled,
    )

    # ── TSS enrichment ─────────────────────────────────────────────────────
    tss_data: dict[str, Any] = _empty_tss_result()
    if bw and gtf and Path(gtf).exists():
        tss_data = compute_tss_enrichment(
            sample, bw, Path(gtf), tss_dir,
            genome=genome, tissue_type=tissue_type,
            threads=threads,
        )
        if len(tss_data.get("positions", [])) > 0:
            plot_tss_enrichment_single(
                sample, tss_data["positions"], tss_data["profile"],
                tss_data["score"], tss_dir,
            )
    else:
        reason = "no bigWig" if not bw else "no GTF"
        logger.warning("  [%s] Skipping TSS enrichment: %s", sample, reason)

    # ── Fragment-length distribution ───────────────────────────────────────
    frag_data = compute_fragment_length(sample, bam, frag_dir)
    if len(frag_data.get("hist", [])) > 0:
        plot_fragment_length_single(
            sample, frag_data["hist"], frag_data["bins"], frag_dir,
        )

    return QcAfterMappingResult(
        sample_name    = sample,
        tss_score      = tss_data.get("score", 0.0),
        tss_tier       = tss_data.get("tier", ""),
        tss_profile    = tss_data.get("profile"),
        tss_positions  = tss_data.get("positions"),
        tss_data_file  = tss_data.get("data_file"),
        frag_mode      = frag_data.get("mode", 0),
        nfr_fraction   = frag_data.get("nfr_fraction", 0.0),
        mono_fraction  = frag_data.get("mono_fraction", 0.0),
        frag_hist      = frag_data.get("hist"),
        frag_bins      = frag_data.get("bins"),
        frag_data_file = frag_data.get("data_file"),
        bigwig         = bw,
    )


# ===========================================================================
# Batch entry point
# ===========================================================================

def run_all_qc_after_mapping(
    mapping_results: list[MappingResult],
    genome_files: "GenomeFiles",
    mapping_dir: Path,
    *,
    threads: int = 8,
    tissue_type: str | None = None,
) -> list[QcAfterMappingResult]:
    """
    Run post-alignment QC for all samples, then generate cross-sample plots.

    Parameters
    ----------
    mapping_results : list of MappingResult from run_all_mapping()
    genome_files    : GenomeFiles with gtf, genome
    mapping_dir     : root mapping output dir
    threads         : number of threads
    tissue_type     : None (score only), "cell_line", or "tissue".
                      ENCODE tier assigned only when set AND genome is human/mouse.
    """
    qc_results: list[QcAfterMappingResult] = []

    for mr in mapping_results:
        qc = run_qc_after_mapping(mr, genome_files, mapping_dir,
                                  threads=threads, tissue_type=tissue_type)
        qc_results.append(qc)

    # ── Cross-sample plots ─────────────────────────────────────────────────
    qc_dir = mapping_dir / "qc_after_mapping"

    # Fragment-length overlay
    frag_dir = qc_dir / "fragment_length"
    plot_fragment_length_all(qc_results, frag_dir)

    # TSS enrichment overlay + ENCODE comparison
    tss_dir = qc_dir / "tss_enrichment"
    plot_tss_enrichment_all(qc_results, tss_dir)
    if tissue_type is not None:
        plot_tss_enrichment_vs_encode(qc_results, tss_dir, tissue_type=tissue_type)

    return qc_results


# ===========================================================================
# Summary
# ===========================================================================

def build_qc_after_mapping_summary(
    results: list[QcAfterMappingResult],
) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd

    rows = []
    for r in results:
        rows.append({
            "sample":         r.sample_name,
            "tss_score":      round(r.tss_score, 2),
            "tss_tier":       r.tss_tier,
            "frag_mode_bp":   r.frag_mode,
            "nfr_fraction":   round(r.nfr_fraction, 4),
            "mono_fraction":  round(r.mono_fraction, 4),
            "bigwig":         str(r.bigwig) if r.bigwig else "",
        })
    return pd.DataFrame(rows)


def write_qc_after_mapping_summary(
    results: list[QcAfterMappingResult],
    output_dir: Path,
) -> Path:
    df   = build_qc_after_mapping_summary(results)
    path = output_dir / "qc_after_mapping_summary.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("QC-after-mapping summary: %s", path)
    return path


# ===========================================================================
# Utility helpers (local copies — avoid importing private names)
# ===========================================================================

def _check_tool(tool: str) -> bool:
    return shutil.which(tool) is not None


def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.\n"
            f"Install: conda install -c bioconda {tool.replace('_', '-')}"
        )


def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}"
        )


def _rm(p: Path) -> None:
    import os
    try:
        if p.exists():
            os.remove(p)
    except OSError:
        pass

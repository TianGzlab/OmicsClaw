"""
footprinting.py — TF footprint analysis for bulk ATAC-seq using TOBIAS.

TOBIAS corrects Tn5 insertion bias, computes per-base footprint scores,
scans for motif occurrences, and classifies each TFBS as bound or unbound
per condition.  With two conditions it also estimates differential TF binding.

Pipeline
--------
  0. Merge biological replicates → one BAM per condition
  1. TOBIAS ATACorrect   — Tn5 bias correction  → *_corrected.bw
  2. TOBIAS ScoreBigwig  — footprint scoring     → *_footprints.bw
  3. TOBIAS BINDetect    — motif scan + binding prediction + differential
  4. TOBIAS PlotAggregate — aggregate footprint plots for top TFs
  5. Summary volcano / ranking table

Required external tools
-----------------------
  TOBIAS   ≥ 0.14   (pip install tobias  /  conda install -c bioconda tobias)
  samtools ≥ 1.10   (for BAM merging + indexing)
  bedtools ≥ 2.30   (for peak merging)

Required reference files
------------------------
  • Genome FASTA (.fa) with .fai index  — must match BAM chromosome names
  • Motif file in JASPAR / PFM / MEME format
  • (Recommended) ENCODE blacklist BED

References
----------
  TOBIAS  : Bentsen et al. 2020, Nat Commun 11:4267
            https://doi.org/10.1038/s41467-020-18035-1
  GitHub  : https://github.com/loosolab/TOBIAS
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


# ===========================================================================
# Result dataclasses
# ===========================================================================

@dataclass
class MergedConditionBAM:
    """One merged BAM per condition (replicates combined)."""
    condition: str
    bam: Path
    n_replicates: int = 1


@dataclass
class ATACorrectResult:
    """Output of TOBIAS ATACorrect for one condition."""
    condition: str
    corrected_bw: Path
    uncorrected_bw: Path | None = None
    bias_bw: Path | None = None
    expected_bw: Path | None = None
    qc_pdf: Path | None = None


@dataclass
class FootprintResult:
    """Output of TOBIAS ScoreBigwig for one condition."""
    condition: str
    footprint_bw: Path


@dataclass
class BINDetectResult:
    """Output of TOBIAS BINDetect."""
    output_dir: Path
    results_txt: Path | None = None
    results_xlsx: Path | None = None
    figures_pdf: Path | None = None
    n_motifs_tested: int = 0
    n_differential: int = 0
    cond_names: list[str] = field(default_factory=list)
    is_differential: bool = False


@dataclass
class FootprintingResult:
    """Top-level result of the full footprint pipeline."""
    merged_peaks_bed: Path
    atacorrect: list[ATACorrectResult] = field(default_factory=list)
    footprints: list[FootprintResult] = field(default_factory=list)
    bindetect: BINDetectResult | None = None
    aggregate_plots: list[Path] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    n_conditions: int = 0


# ===========================================================================
# Tool checks
# ===========================================================================

def _check_tool(name: str) -> str | None:
    return shutil.which(name)


def check_tobias() -> bool:
    """Log the TOBIAS version from the isolated ``omicsclaw_tobias`` env.

    TOBIAS is intentionally NOT expected on the main PATH — it runs in a
    dedicated conda sub-env (pandas<2 conflict; see ``_run_in_tobias_env``).
    This is an informational check: it logs the sub-env's TOBIAS version
    when that env already exists. A ``False`` return is NOT fatal — the
    env is auto-created on first real use by ``_ensure_tobias_env()``.
    """
    try:
        tobias_exe = _tobias_env_bin() / "TOBIAS"
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    if not tobias_exe.is_file():
        return False
    try:
        r = subprocess.run([str(tobias_exe), "--version"], capture_output=True,
                           text=True, timeout=30)
        version = (r.stdout.strip() or r.stderr.strip()).split("\n")[0]
        logger.info("TOBIAS version (env %s): %s", _TOBIAS_ENV_NAME, version)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def check_prerequisites() -> list[str]:
    """Return the list of missing required tools.

    TOBIAS is intentionally excluded — it runs in the isolated
    ``omicsclaw_tobias`` conda sub-env (see ``_run_in_tobias_env``), not on
    the current PATH, and is auto-provisioned by ``_ensure_tobias_env()``.
    Only samtools + bedtools run directly from the current environment.
    """
    missing = []
    for tool in ("samtools", "bedtools"):
        if not _check_tool(tool):
            missing.append(tool)
    return missing


# ===========================================================================
# Step 0: Merge replicates per condition
# ===========================================================================

def merge_replicates(
    sample_bams: dict[str, Path],
    sample_conditions: dict[str, str],
    output_dir: Path,
    *,
    threads: int = 8,
) -> list[MergedConditionBAM]:
    """Merge biological replicates into one BAM per condition.

    TOBIAS does not handle replicates natively — merging improves
    sequencing depth for footprinting (recommended by TOBIAS authors).
    Single-replicate conditions are symlinked.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cond_to_bams: dict[str, list[Path]] = {}
    for sample, bam in sample_bams.items():
        cond = sample_conditions.get(sample, "unknown")
        cond_to_bams.setdefault(cond, []).append(bam)

    results: list[MergedConditionBAM] = []
    for cond, bams in sorted(cond_to_bams.items()):
        merged_bam = output_dir / f"{cond}_merged.bam"

        if merged_bam.exists() and merged_bam.stat().st_size > 0:
            logger.info("  [%s] checkpoint: %s", cond, merged_bam)
            results.append(MergedConditionBAM(cond, merged_bam, len(bams)))
            continue

        if len(bams) == 1:
            logger.info("  [%s] single replicate — symlinking", cond)
            if merged_bam.is_symlink():
                merged_bam.unlink()
            merged_bam.symlink_to(bams[0].resolve())
        else:
            logger.info("  [%s] merging %d replicates ...", cond, len(bams))
            _run([
                "samtools", "merge", "-f",
                "--threads", str(threads),
                str(merged_bam),
            ] + [str(b) for b in bams], f"samtools merge ({cond})")

        _index_bam(merged_bam, threads=threads)
        results.append(MergedConditionBAM(cond, merged_bam, len(bams)))

    return results


# ===========================================================================
# Step 1: Merge peaks
# ===========================================================================

def merge_peaks(
    peak_beds: list[Path],
    output_dir: Path,
) -> Path:
    """Sort + merge peak BEDs into a union set for TOBIAS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_bed = output_dir / "merged_peaks.bed"

    if merged_bed.exists() and merged_bed.stat().st_size > 0:
        logger.info("  Merged peaks checkpoint: %s", merged_bed)
        return merged_bed

    cat_bed = output_dir / "concat_peaks.bed"
    with open(cat_bed, "w") as out:
        for bed in peak_beds:
            with open(bed) as f:
                for line in f:
                    if line.startswith("#") or line.startswith("track"):
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 3:
                        out.write(f"{parts[0]}\t{parts[1]}\t{parts[2]}\n")

    sorted_bed = output_dir / "sorted_peaks.bed"
    _run(["bedtools", "sort", "-i", str(cat_bed)],
         "bedtools sort", stdout_file=sorted_bed)
    _run(["bedtools", "merge", "-i", str(sorted_bed)],
         "bedtools merge", stdout_file=merged_bed)

    n_peaks = sum(1 for _ in open(merged_bed))
    logger.info("  Merged peak set: %d peaks", n_peaks)

    cat_bed.unlink(missing_ok=True)
    sorted_bed.unlink(missing_ok=True)
    return merged_bed


# ===========================================================================
# Step 2: TOBIAS ATACorrect
# ===========================================================================

def run_atacorrect(
    bam: Path,
    genome_fasta: Path,
    peaks_bed: Path,
    output_dir: Path,
    condition: str,
    *,
    blacklist: Path | None = None,
    cores: int = 8,
) -> ATACorrectResult:
    """Run TOBIAS ATACorrect — Tn5 bias correction.

    TOBIAS internally handles +4/-5 read shifting (do NOT pre-shift).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = bam.stem
    corrected_bw = output_dir / f"{prefix}_corrected.bw"
    done_marker = output_dir / f".{prefix}_atacorrect.done"

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written after TOBIAS returns 0 — a crash mid-run leaves a partial
    # _corrected.bw but no marker, so the next run redoes it.
    if done_marker.exists() and corrected_bw.exists():
        logger.info("  [%s] ATACorrect checkpoint", condition)
        return _collect_atacorrect(output_dir, prefix, condition)

    logger.info("  [%s] Running TOBIAS ATACorrect ...", condition)
    cmd = [
        "TOBIAS", "ATACorrect",
        "--bam", str(bam),
        "--genome", str(genome_fasta),
        "--peaks", str(peaks_bed),
        "--outdir", str(output_dir),
        "--cores", str(cores),
    ]
    if blacklist and blacklist.exists():
        cmd += ["--blacklist", str(blacklist)]

    # TOBIAS lives in the isolated omicsclaw_tobias env (pandas<2 conflict
    # with pyDESeq2). _run_in_tobias_env rewrites cmd[0] to the env's
    # absolute path so we never need TOBIAS on the active env's PATH.
    _run_in_tobias_env(cmd, f"TOBIAS ATACorrect ({condition})")
    done_marker.write_text("")   # success sentinel — TOBIAS returned 0
    return _collect_atacorrect(output_dir, prefix, condition)


def _collect_atacorrect(
    output_dir: Path, prefix: str, condition: str,
) -> ATACorrectResult:
    return ATACorrectResult(
        condition=condition,
        corrected_bw=output_dir / f"{prefix}_corrected.bw",
        uncorrected_bw=_if_exists(output_dir / f"{prefix}_uncorrected.bw"),
        bias_bw=_if_exists(output_dir / f"{prefix}_bias.bw"),
        expected_bw=_if_exists(output_dir / f"{prefix}_expected.bw"),
        qc_pdf=_if_exists(output_dir / f"{prefix}_atacorrect.pdf"),
    )


# ===========================================================================
# Step 3: TOBIAS ScoreBigwig
# ===========================================================================

def run_score_bigwig(
    corrected_bw: Path,
    peaks_bed: Path,
    output_dir: Path,
    condition: str,
    *,
    cores: int = 8,
) -> FootprintResult:
    """Compute per-base footprint scores from bias-corrected signal."""
    output_dir.mkdir(parents=True, exist_ok=True)
    footprint_bw = output_dir / f"{condition}_footprints.bw"
    done_marker = output_dir / f".{condition}_scorebigwig.done"

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written after TOBIAS returns 0 — a crash mid-run leaves a partial
    # _footprints.bw but no marker, so the next run redoes it.
    if done_marker.exists() and footprint_bw.exists():
        logger.info("  [%s] ScoreBigwig checkpoint", condition)
        return FootprintResult(condition=condition, footprint_bw=footprint_bw)

    logger.info("  [%s] Running TOBIAS ScoreBigwig ...", condition)
    _run_in_tobias_env([
        "TOBIAS", "ScoreBigwig",
        "--signal", str(corrected_bw),
        "--regions", str(peaks_bed),
        "--output", str(footprint_bw),
        "--cores", str(cores),
    ], f"TOBIAS ScoreBigwig ({condition})")

    done_marker.write_text("")   # success sentinel — TOBIAS returned 0
    return FootprintResult(condition=condition, footprint_bw=footprint_bw)


# ===========================================================================
# Step 4: TOBIAS BINDetect
# ===========================================================================

def run_bindetect(
    footprint_bws: list[Path],
    cond_names: list[str],
    motifs_file: Path,
    genome_fasta: Path,
    peaks_bed: Path,
    output_dir: Path,
    *,
    cores: int = 8,
) -> BINDetectResult:
    """Run TOBIAS BINDetect — motif scanning + binding classification.

    One condition: predicts bound/unbound TFBS.
    Two conditions: also estimates differential binding + volcano plots.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results_txt = output_dir / "bindetect_results.txt"
    done_marker = output_dir / ".bindetect.done"

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written after TOBIAS returns 0 — a crash mid-run leaves a partial
    # bindetect_results.txt but no marker, so the next run redoes it.
    if done_marker.exists() and results_txt.exists():
        logger.info("  BINDetect checkpoint: %s", results_txt)
        return _parse_bindetect(output_dir, cond_names)

    logger.info("  Running TOBIAS BINDetect (%d condition(s): %s) ...",
                len(cond_names), ", ".join(cond_names))

    _run_in_tobias_env([
        "TOBIAS", "BINDetect",
        "--motifs", str(motifs_file),
        "--signals", *[str(bw) for bw in footprint_bws],
        "--genome", str(genome_fasta),
        "--peaks", str(peaks_bed),
        "--outdir", str(output_dir),
        "--cond_names", *cond_names,
        "--cores", str(cores),
    ], "TOBIAS BINDetect")

    done_marker.write_text("")   # success sentinel — TOBIAS returned 0
    return _parse_bindetect(output_dir, cond_names)


def _parse_bindetect(
    output_dir: Path, cond_names: list[str],
) -> BINDetectResult:
    results_txt = output_dir / "bindetect_results.txt"
    n_motifs = 0
    n_diff = 0
    is_diff = len(cond_names) >= 2

    if results_txt.exists():
        with open(results_txt) as f:
            header = f.readline()
            cols = header.strip().split("\t")
            change_idx = None
            if is_diff:
                for i, col in enumerate(cols):
                    if col.endswith("_change"):
                        change_idx = i
                        break

            for line in f:
                n_motifs += 1
                if change_idx is not None:
                    parts = line.strip().split("\t")
                    if change_idx < len(parts):
                        try:
                            if abs(float(parts[change_idx])) > 0.1:
                                n_diff += 1
                        except ValueError:
                            pass

    return BINDetectResult(
        output_dir=output_dir,
        results_txt=results_txt if results_txt.exists() else None,
        results_xlsx=_if_exists(output_dir / "bindetect_results.xlsx"),
        figures_pdf=_if_exists(output_dir / "bindetect_figures.pdf"),
        n_motifs_tested=n_motifs,
        n_differential=n_diff,
        cond_names=list(cond_names),
        is_differential=is_diff,
    )


# ===========================================================================
# Step 5: Aggregate footprint plots for top TFs
# ===========================================================================

def plot_aggregate_top_tfs(
    bindetect: BINDetectResult,
    corrected_bws: dict[str, Path],
    output_dir: Path,
    *,
    top_n: int = 20,
    cores: int = 8,
) -> list[Path]:
    """Generate aggregate footprint plots for the top-ranked TFs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plots: list[Path] = []

    if not bindetect.results_txt or not bindetect.results_txt.exists():
        return plots

    top_tfs = _get_top_tfs(bindetect, top_n=top_n)
    if not top_tfs:
        return plots

    signal_args = [str(corrected_bws[c]) for c in bindetect.cond_names
                   if c in corrected_bws]
    if not signal_args:
        return plots

    for tf_name in top_tfs:
        tf_dir = bindetect.output_dir / tf_name
        if not tf_dir.is_dir():
            continue

        tfbs_beds = list(tf_dir.glob("beds/*_all.bed"))
        if not tfbs_beds:
            tfbs_beds = list(tf_dir.glob("beds/*.bed"))
        if not tfbs_beds:
            continue

        plot_file = output_dir / f"aggregate_{tf_name}.png"
        if plot_file.exists():
            plots.append(plot_file)
            continue

        try:
            _run_in_tobias_env([
                "TOBIAS", "PlotAggregate",
                "--TFBS", str(tfbs_beds[0]),
                "--signals", *signal_args,
                "--output", str(plot_file),
                "--share_y", "both",
                "--plot_boundaries",
            ], f"PlotAggregate ({tf_name})")
            if plot_file.exists():
                plots.append(plot_file)
        except RuntimeError:
            logger.warning("  PlotAggregate failed for %s — skipping", tf_name)

    logger.info("  Generated %d aggregate footprint plots", len(plots))
    return plots


def _get_top_tfs(bindetect: BINDetectResult, *, top_n: int = 20) -> list[str]:
    """Extract top TF names ranked by |change| or mean score."""
    if not bindetect.results_txt:
        return []

    rows: list[tuple[str, float]] = []
    with open(bindetect.results_txt) as f:
        header = f.readline().strip().split("\t")

        sort_idx = None
        if bindetect.is_differential:
            for i, col in enumerate(header):
                if col.endswith("_change"):
                    sort_idx = i
                    break
        if sort_idx is None:
            for i, col in enumerate(header):
                if col.endswith("_score"):
                    sort_idx = i
                    break

        name_idx = 0
        for i, col in enumerate(header):
            if col == "output_prefix":
                name_idx = i
                break

        if sort_idx is None:
            return []

        for line in f:
            parts = line.strip().split("\t")
            if len(parts) <= max(name_idx, sort_idx):
                continue
            try:
                rows.append((parts[name_idx], abs(float(parts[sort_idx]))))
            except ValueError:
                continue

    rows.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in rows[:top_n]]


# ===========================================================================
# Step 6: Summary plots (matplotlib — no TOBIAS dependency)
# ===========================================================================

def plot_differential_volcano(
    bindetect: BINDetectResult,
    output_dir: Path,
    *,
    top_n_label: int = 15,
) -> Path | None:
    """Volcano plot of differential TF binding from BINDetect."""
    if not bindetect.is_differential:
        return None
    if not bindetect.results_txt or not bindetect.results_txt.exists():
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib not available — skipping volcano")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    names, changes, pvals = [], [], []
    with open(bindetect.results_txt) as f:
        header = f.readline().strip().split("\t")
        name_idx = 0
        change_idx = pval_idx = None
        for i, col in enumerate(header):
            if col == "output_prefix":
                name_idx = i
            elif col.endswith("_change"):
                change_idx = i
            elif col.endswith("_pvalue"):
                pval_idx = i

        if change_idx is None:
            return None

        for line in f:
            parts = line.strip().split("\t")
            try:
                names.append(parts[name_idx])
                changes.append(float(parts[change_idx]))
                pvals.append(float(parts[pval_idx]) if pval_idx is not None else 1.0)
            except (ValueError, IndexError):
                continue

    if not names:
        return None

    changes_arr = np.array(changes)
    pvals_arr = np.array(pvals)
    neg_log10p = -np.log10(np.clip(pvals_arr, 1e-300, None))

    colors = np.full(len(names), "#999999")
    colors[(changes_arr > 0.1) & (pvals_arr < 0.05)] = "#b30000"
    colors[(changes_arr < -0.1) & (pvals_arr < 0.05)] = "#4C72B0"

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(changes_arr, neg_log10p, c=colors, s=12, alpha=0.7,
               edgecolors="none", rasterized=True)
    ax.axhline(-np.log10(0.05), color="#999999", linestyle="--", linewidth=0.8)
    ax.axvline(0.1, color="#999999", linestyle="--", linewidth=0.8)
    ax.axvline(-0.1, color="#999999", linestyle="--", linewidth=0.8)

    ranked = sorted(range(len(names)), key=lambda i: abs(changes[i]), reverse=True)
    for idx in ranked[:top_n_label]:
        ax.annotate(names[idx], (changes_arr[idx], neg_log10p[idx]),
                    fontsize=7, alpha=0.85,
                    textcoords="offset points", xytext=(5, 3))

    cond = bindetect.cond_names
    ax.set_xlabel(f"Differential binding ({cond[0]} → {cond[1]})" if len(cond) >= 2 else "Binding change")
    ax.set_ylabel("-log10(p-value)")
    n_up = int(((changes_arr > 0.1) & (pvals_arr < 0.05)).sum())
    n_down = int(((changes_arr < -0.1) & (pvals_arr < 0.05)).sum())
    ax.set_title(f"TF Differential Binding — {' vs '.join(cond)}\n"
                 f"({n_up} enriched in {cond[-1]}, {n_down} enriched in {cond[0]})")

    plt.rcParams.update({"figure.dpi": 300, "savefig.dpi": 300})
    vol_path = output_dir / "tf_differential_volcano"
    for ext in ("pdf", "png"):
        fig.savefig(f"{vol_path}.{ext}", bbox_inches="tight")
    plt.close(fig)
    return Path(f"{vol_path}.pdf")


def write_top_tf_table(
    bindetect: BINDetectResult,
    output_dir: Path,
    *,
    top_n: int = 50,
) -> Path | None:
    """Write a ranked TSV of top TFs for easy inspection."""
    if not bindetect.results_txt or not bindetect.results_txt.exists():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[list[str]] = []
    with open(bindetect.results_txt) as f:
        header_line = f.readline().strip()
        header = header_line.split("\t")

        keep_cols = []
        for i, col in enumerate(header):
            if any(kw in col.lower() for kw in
                   ("name", "prefix", "motif_id", "score", "change",
                    "pvalue", "bound", "n_")):
                keep_cols.append(i)
        if not keep_cols:
            keep_cols = list(range(min(len(header), 10)))

        sort_col_local = None
        for j, idx in enumerate(keep_cols):
            if header[idx].endswith("_change"):
                sort_col_local = j
                break
        if sort_col_local is None:
            for j, idx in enumerate(keep_cols):
                if header[idx].endswith("_score"):
                    sort_col_local = j
                    break

        for line in f:
            parts = line.strip().split("\t")
            rows.append([parts[i] if i < len(parts) else "" for i in keep_cols])

    if sort_col_local is not None:
        try:
            rows.sort(key=lambda r: abs(float(r[sort_col_local])), reverse=True)
        except (ValueError, IndexError):
            pass

    rows = rows[:top_n]
    out_path = output_dir / "top_tf_ranking.tsv"
    with open(out_path, "w") as f:
        f.write("\t".join(header[i] for i in keep_cols) + "\n")
        for row in rows:
            f.write("\t".join(row) + "\n")

    logger.info("  Top TF ranking: %s (%d TFs)", out_path, len(rows))
    return out_path


# ===========================================================================
# Full pipeline orchestrator
# ===========================================================================

def run_footprinting(
    sample_bams: dict[str, Path],
    sample_conditions: dict[str, str],
    consensus_bed: Path,
    genome_fasta: Path,
    motifs_file: Path,
    output_dir: Path,
    *,
    blacklist: Path | None = None,
    treat: str | None = None,
    control: str | None = None,
    cores: int = 8,
) -> FootprintingResult:
    """Run the full TOBIAS footprint pipeline.

    Parameters
    ----------
    sample_bams       : {sample_name: bam_path}
    sample_conditions : {sample_name: condition_name}
    consensus_bed     : consensus peak BED from Step 3
    genome_fasta      : genome FASTA with .fai index
    motifs_file       : JASPAR / PFM / MEME motif file
    output_dir        : root output directory
    blacklist         : ENCODE blacklist BED (recommended)
    treat             : treatment condition (controls BINDetect ordering)
    control           : control condition
    cores             : number of threads
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Condition order ────────────────────────────────────────────────
    unique_conds = sorted(set(sample_conditions.values()))
    if treat and control:
        cond_order = [control, treat]
        for c in unique_conds:
            if c not in cond_order:
                cond_order.append(c)
    else:
        cond_order = unique_conds

    logger.info("Footprint analysis: %d conditions → %s", len(cond_order), cond_order)

    # ── Step 0: Merge replicates ───────────────────────────────────────
    logger.info("Step 0: Merging replicates per condition ...")
    merged = merge_replicates(
        sample_bams, sample_conditions,
        output_dir / "merged_bams", threads=cores,
    )
    cond_bam = {m.condition: m.bam for m in merged}

    # ── Step 1: Merge peaks ────────────────────────────────────────────
    logger.info("Step 1: Preparing merged peak set ...")
    merged_peaks = merge_peaks([consensus_bed], output_dir)

    # ── Step 2: ATACorrect ─────────────────────────────────────────────
    logger.info("Step 2: TOBIAS ATACorrect ...")
    ac_results: list[ATACorrectResult] = []
    corrected_bws: dict[str, Path] = {}
    for cond in cond_order:
        if cond not in cond_bam:
            logger.warning("  [%s] no BAM — skipping", cond)
            continue
        ac = run_atacorrect(
            cond_bam[cond], genome_fasta, merged_peaks,
            output_dir / "atacorrect" / cond, condition=cond,
            blacklist=blacklist, cores=cores,
        )
        ac_results.append(ac)
        corrected_bws[cond] = ac.corrected_bw

    # ── Step 3: ScoreBigwig ────────────────────────────────────────────
    logger.info("Step 3: TOBIAS ScoreBigwig ...")
    fp_results: list[FootprintResult] = []
    fp_bws: list[Path] = []
    ordered_conds: list[str] = []
    for cond in cond_order:
        if cond not in corrected_bws:
            continue
        fp = run_score_bigwig(
            corrected_bws[cond], merged_peaks,
            output_dir / "footprints" / cond, condition=cond, cores=cores,
        )
        fp_results.append(fp)
        fp_bws.append(fp.footprint_bw)
        ordered_conds.append(cond)

    # ── Step 4: BINDetect ──────────────────────────────────────────────
    logger.info("Step 4: TOBIAS BINDetect ...")
    bindetect = run_bindetect(
        fp_bws, ordered_conds, motifs_file, genome_fasta,
        merged_peaks, output_dir / "bindetect", cores=cores,
    )

    # ── Step 5: Aggregate plots ────────────────────────────────────────
    logger.info("Step 5: Aggregate footprint plots ...")
    agg_plots = plot_aggregate_top_tfs(
        bindetect, corrected_bws,
        output_dir / "plots" / "aggregate", top_n=20, cores=cores,
    )

    # ── Step 6: Summary ────────────────────────────────────────────────
    logger.info("Step 6: Summary plots & tables ...")
    vol = plot_differential_volcano(bindetect, output_dir / "plots")
    write_top_tf_table(bindetect, output_dir)
    if vol:
        agg_plots.append(vol)

    return FootprintingResult(
        merged_peaks_bed=merged_peaks,
        atacorrect=ac_results,
        footprints=fp_results,
        bindetect=bindetect,
        aggregate_plots=agg_plots,
        conditions=ordered_conds,
        n_conditions=len(ordered_conds),
    )


# ===========================================================================
# Helpers
# ===========================================================================

_TOBIAS_ENV_NAME = "omicsclaw_tobias"
_TOBIAS_SPECS = ["tobias>=0.17", "pandas<2"]
_tobias_env_ready = False


def _conda_bin() -> str:
    """Return path to conda executable."""
    p = shutil.which("conda")
    if p:
        return p
    raise FileNotFoundError("conda not found on PATH")


def _ensure_tobias_env() -> None:
    """Create a dedicated conda env for TOBIAS if it doesn't exist yet."""
    global _tobias_env_ready
    if _tobias_env_ready:
        return
    conda = _conda_bin()
    tobias_exe = _tobias_env_bin() / "TOBIAS"
    # Check if env already exists and TOBIAS is available
    if tobias_exe.exists():
        check = subprocess.run(
            [str(tobias_exe), "--version"],
            capture_output=True, text=True,
        )
        if check.returncode == 0:
            _tobias_env_ready = True
            return
    # Create the env
    logger.info("  Creating isolated conda env '%s' for TOBIAS ...",
                _TOBIAS_ENV_NAME)
    subprocess.run(
        [conda, "create", "-y", "-n", _TOBIAS_ENV_NAME,
         "-c", "bioconda", "-c", "conda-forge", *_TOBIAS_SPECS],
        check=True, capture_output=True, text=True,
    )
    _tobias_env_ready = True
    logger.info("  Conda env '%s' ready.", _TOBIAS_ENV_NAME)


def _run(
    cmd: list[str],
    label: str,
    *,
    stdout_file: Path | None = None,
) -> subprocess.CompletedProcess:
    logger.info("  CMD [%s]: %s", label, " ".join(cmd))
    try:
        if stdout_file:
            with open(stdout_file, "w") as fout:
                result = subprocess.run(cmd, check=True, stdout=fout,
                                        stderr=subprocess.PIPE, text=True)
        else:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        log_tool_output(cmd, result)
        return result
    except subprocess.CalledProcessError as e:
        log_tool_output(cmd, e)
        # If a TOBIAS command fails, retry in an isolated conda env
        if cmd and cmd[0] == "TOBIAS":
            logger.warning("  %s failed in current env, retrying in isolated "
                           "conda env '%s' ...", label, _TOBIAS_ENV_NAME)
            return _run_in_tobias_env(cmd, label, stdout_file=stdout_file)
        logger.error("  %s FAILED (exit %d):\n%s",
                     label, e.returncode, (e.stderr or "")[:2000])
        raise RuntimeError(f"{label} failed (exit {e.returncode})") from e


def _conda_base_prefix() -> Path:
    """Return the conda base prefix (e.g. /home/user/.miniconda)."""
    conda = _conda_bin()
    result = subprocess.run(
        [conda, "info", "--base"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def _tobias_env_bin() -> Path:
    """Return the bin/ directory of the isolated TOBIAS conda env."""
    return _conda_base_prefix() / "envs" / _TOBIAS_ENV_NAME / "bin"


def _run_in_tobias_env(
    cmd: list[str],
    label: str,
    *,
    stdout_file: Path | None = None,
) -> subprocess.CompletedProcess:
    """Re-run a TOBIAS command inside the isolated conda env."""
    _ensure_tobias_env()
    env_bin = _tobias_env_bin()
    # Replace the executable (e.g. "TOBIAS") with its full path in the env
    wrapped = [str(env_bin / cmd[0])] + cmd[1:]
    logger.info("  CMD [%s] (env %s): %s", label, _TOBIAS_ENV_NAME,
                " ".join(wrapped))
    try:
        if stdout_file:
            with open(stdout_file, "w") as fout:
                result = subprocess.run(wrapped, check=True, stdout=fout,
                                        stderr=subprocess.PIPE, text=True)
        else:
            result = subprocess.run(wrapped, check=True,
                                    capture_output=True, text=True)
        log_tool_output(wrapped, result)
        return result
    except subprocess.CalledProcessError as e:
        log_tool_output(wrapped, e)
        logger.error("  %s FAILED in isolated env (exit %d):\n%s",
                     label, e.returncode, (e.stderr or "")[:2000])
        raise RuntimeError(f"{label} failed (exit {e.returncode})") from e


def _index_bam(bam: Path, *, threads: int = 4) -> None:
    bai = bam.with_suffix(".bam.bai")
    if bai.exists() and bai.stat().st_mtime >= bam.stat().st_mtime:
        return
    _run(["samtools", "index", "-@", str(threads), str(bam)], "samtools index")


def _if_exists(p: Path) -> Path | None:
    return p if p.exists() else None

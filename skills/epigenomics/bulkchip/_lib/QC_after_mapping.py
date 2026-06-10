"""
QC_after_mapping.py — Bulk ChIP-seq Step 2b: ChIP-specific signal-to-noise QC.

ChIP signal-to-noise is assessed by metrics that ATAC does not use:
  * Strand cross-correlation  →  NSC / RSC + fragment-length estimate
    (phantompeakqualtools ``run_spp.R``).  Computed per ChIP sample.
  * deepTools fingerprint     →  ChIP-vs-input enrichment curve + JS distance
    (``plotFingerprint --JSDsample <input>``).
  * RPGC-normalised bigWig signal tracks (deepTools ``bamCoverage``).
  * ChIP-vs-input log2-ratio bigWig (deepTools ``bamCompare``) — ChIP-specific,
    subtracts the matched input background that RPGC-per-sample cannot.

These replace ATAC's TSS-enrichment and fragment-length nucleosome ladder.

Every external step degrades gracefully: if the tool is missing the metric is
left at 0.0 (or None) with a warning, so the skill still completes and writes a
report.

Tools: phantompeakqualtools (run_spp.R), deeptools (plotFingerprint,
bamCoverage, bamCompare).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .encode_qc_criteria import nsc_tier, rsc_tier
from .mapping import MappingResult, GenomeFiles, generate_bigwig

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


@dataclass
class QcAfterMappingResult:
    """Per-sample ChIP signal-to-noise QC."""
    sample_name:    str
    is_control:     bool = False
    nsc:            float = 0.0     # normalized strand cross-correlation
    rsc:            float = 0.0     # relative strand cross-correlation
    nsc_tier:       str = ""
    rsc_tier:       str = ""
    est_frag_len:   int = 0         # cross-correlation fragment-length estimate
    fingerprint_js: float = 0.0     # deepTools fingerprint JS distance vs input
    bigwig:         Path | None = None   # RPGC per-sample track
    bigwig_log2_input: Path | None = None   # bamCompare log2(ChIP/input) track


# ===========================================================================
# Public API
# ===========================================================================

def run_all_qc_after_mapping(
    mapping_results: list[MappingResult],
    genome_files: GenomeFiles,
    output_dir: Path,
    *,
    threads: int = 8,
) -> list[QcAfterMappingResult]:
    """
    NSC/RSC cross-correlation + deepTools fingerprint + RPGC bigWig over every
    sample.  Cross-correlation is computed for ChIP samples; the fingerprint
    compares each ChIP sample against its matched input control.
    """
    qc_dir   = output_dir / "qc_after_mapping"
    cc_dir   = qc_dir / "cross_correlation"
    fp_dir   = qc_dir / "fingerprint"
    bw_dir   = output_dir / "bigwig"
    for d in (cc_dir, fp_dir, bw_dir):
        d.mkdir(parents=True, exist_ok=True)

    by_name = {r.sample_name: r for r in mapping_results}
    results: list[QcAfterMappingResult] = []

    for r in mapping_results:
        bam = r.get_analysis_bam()
        qc  = QcAfterMappingResult(sample_name=r.sample_name, is_control=r.is_control)

        # 1. RPGC bigWig (all samples, incl. controls)
        qc.bigwig = generate_bigwig(
            r.sample_name, bam, bw_dir,
            genome=genome_files.genome, genome_fasta=genome_files.fasta,
            threads=threads, downsampled=r.downsampled,
        )

        # 2. Strand cross-correlation NSC/RSC (ChIP samples only)
        if not r.is_control:
            nsc, rsc, frag = _cross_correlation(r.sample_name, bam, cc_dir, threads=threads)
            qc.nsc, qc.rsc, qc.est_frag_len = nsc, rsc, frag
            qc.nsc_tier = nsc_tier(nsc) if nsc > 0 else ""
            qc.rsc_tier = rsc_tier(rsc) if rsc > 0 else ""

        # 3. ChIP-vs-input metrics (ChIP samples with a matched control)
        if not r.is_control and r.control and r.control in by_name:
            ctrl_bam = by_name[r.control].get_analysis_bam()
            # 3a. deepTools fingerprint → JS distance
            qc.fingerprint_js = _fingerprint(
                r.sample_name, bam, r.control, ctrl_bam, fp_dir, threads=threads,
            )
            # 3b. bamCompare log2(ChIP/input) bigWig track
            qc.bigwig_log2_input = _bamcompare_log2(
                r.sample_name, bam, r.control, ctrl_bam, bw_dir, threads=threads,
            )

        results.append(qc)
        logger.info(
            "  [%s] NSC=%.3f RSC=%.3f fragLen=%d JSD=%.3f%s",
            r.sample_name, qc.nsc, qc.rsc, qc.est_frag_len, qc.fingerprint_js,
            "  (control)" if r.is_control else "",
        )

    return results


def build_qc_after_mapping_summary(results: list[QcAfterMappingResult]) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd
    rows = [{
        "sample":         q.sample_name,
        "is_control":     q.is_control,
        "nsc":            round(q.nsc, 4),
        "nsc_tier":       q.nsc_tier,
        "rsc":            round(q.rsc, 4),
        "rsc_tier":       q.rsc_tier,
        "est_frag_len":   q.est_frag_len,
        "fingerprint_js": round(q.fingerprint_js, 4),
        "bigwig":         str(q.bigwig) if q.bigwig else "",
        "bigwig_log2_input": str(q.bigwig_log2_input) if q.bigwig_log2_input else "",
    } for q in results]
    return pd.DataFrame(rows)


def write_qc_after_mapping_summary(results: list[QcAfterMappingResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    df   = build_qc_after_mapping_summary(results)
    path = output_dir / "qc_after_mapping_summary.csv"
    df.to_csv(path, index=False)
    logger.info("ChIP QC summary written: %s", path)
    return path


# ===========================================================================
# Strand cross-correlation (phantompeakqualtools run_spp.R)
# ===========================================================================

def _cross_correlation(
    sample_name: str, bam: Path, cc_dir: Path, *, threads: int,
) -> tuple[float, float, int]:
    """
    Run phantompeakqualtools run_spp.R → (NSC, RSC, est_frag_len).

    run_spp.R writes a tab-delimited line:
      1 Filename  2 numReads  3 estFragLen(csv)  4 corr_estFragLen
      5 phantomPeak  6 corr_phantomPeak  7 argmin_corr  8 min_corr
      9 NSC  10 RSC  11 QualityTag
    """
    runner = shutil.which("run_spp.R") or shutil.which("run_spp")
    if not runner:
        logger.warning(
            "run_spp.R (phantompeakqualtools) not found — skipping NSC/RSC for %s. "
            "Install: conda install -c bioconda phantompeakqualtools", sample_name,
        )
        return 0.0, 0.0, 0
    if not shutil.which("Rscript"):
        logger.warning("Rscript not found — skipping NSC/RSC for %s.", sample_name)
        return 0.0, 0.0, 0

    out_file = cc_dir / f"{sample_name}.cc.txt"
    save_pdf = cc_dir / f"{sample_name}.cc.pdf"

    # Checkpoint: reuse the cross-correlation result from a prior run.
    if out_file.exists() and out_file.stat().st_size > 0:
        logger.info("  [%s] cross-correlation checkpoint — skipping run_spp.R", sample_name)
        return _parse_spp(out_file, sample_name)

    cmd = [
        "Rscript", runner,
        f"-c={bam}", f"-p={threads}",
        f"-savp={save_pdf}", f"-out={out_file}",
        "-rf",   # overwrite existing out file
    ]
    try:
        _run(cmd, label=f"run_spp.R cross-correlation [{sample_name}]")
    except RuntimeError as exc:
        logger.warning("Cross-correlation failed for %s: %s", sample_name, exc)
        return 0.0, 0.0, 0

    return _parse_spp(out_file, sample_name)


def _parse_spp(out_file: Path, sample_name: str) -> tuple[float, float, int]:
    if not out_file.exists() or out_file.stat().st_size == 0:
        logger.warning("[%s] cross-correlation output empty.", sample_name)
        return 0.0, 0.0, 0
    line = out_file.read_text().strip().splitlines()[-1]
    cols = line.split("\t")
    if len(cols) < 10:
        logger.warning("[%s] malformed run_spp.R output (%d cols).", sample_name, len(cols))
        return 0.0, 0.0, 0
    try:
        frag = int(str(cols[2]).split(",")[0])   # first estFragLen value
        nsc  = float(cols[8])
        rsc  = float(cols[9])
    except (ValueError, IndexError):
        return 0.0, 0.0, 0
    return nsc, rsc, frag


# ===========================================================================
# deepTools fingerprint (ChIP vs input)
# ===========================================================================

def _fingerprint(
    chip_name: str, chip_bam: Path, ctrl_name: str, ctrl_bam: Path,
    fp_dir: Path, *, threads: int,
) -> float:
    """
    deepTools plotFingerprint ChIP vs input → JS distance (vs the input).

    Returns the JS distance from the quality-metrics table (0.0 if deeptools
    is missing or the run fails).
    """
    if not shutil.which("plotFingerprint"):
        logger.warning(
            "plotFingerprint (deeptools) not found — skipping fingerprint for %s. "
            "Install: conda install -c bioconda deeptools", chip_name,
        )
        return 0.0

    plot_file    = fp_dir / f"{chip_name}_vs_{ctrl_name}.fingerprint.png"
    metrics_file = fp_dir / f"{chip_name}_vs_{ctrl_name}.qcmetrics.txt"

    # Checkpoint: reuse the fingerprint metrics from a prior run.
    if (metrics_file.exists() and metrics_file.stat().st_size > 0 and plot_file.exists()):
        logger.info("  [%s] fingerprint checkpoint — skipping plotFingerprint", chip_name)
        return _parse_fingerprint_jsd(metrics_file, chip_name)

    cmd = [
        "plotFingerprint",
        "-b", str(chip_bam), str(ctrl_bam),
        "--labels", chip_name, ctrl_name,
        "--JSDsample", str(ctrl_bam),
        "--outQualityMetrics", str(metrics_file),
        "--plotFile", str(plot_file),
        "--minMappingQuality", "30", "--skipZeros",
        "-p", str(threads),
    ]
    try:
        _run(cmd, label=f"plotFingerprint [{chip_name} vs {ctrl_name}]")
    except RuntimeError as exc:
        logger.warning("Fingerprint failed for %s: %s", chip_name, exc)
        return 0.0

    return _parse_fingerprint_jsd(metrics_file, chip_name)


def _parse_fingerprint_jsd(metrics_file: Path, chip_name: str) -> float:
    """Parse the 'JS Distance' column for the ChIP sample row."""
    if not metrics_file.exists() or metrics_file.stat().st_size == 0:
        return 0.0
    lines = metrics_file.read_text().strip().splitlines()
    if len(lines) < 2:
        return 0.0
    header = [h.strip().strip('"') for h in lines[0].split("\t")]
    try:
        jsd_col = next(i for i, h in enumerate(header) if h.lower().startswith("js distance"))
    except StopIteration:
        return 0.0
    for row in lines[1:]:
        cols = [c.strip().strip('"') for c in row.split("\t")]
        if cols and cols[0] == chip_name and len(cols) > jsd_col:
            try:
                return float(cols[jsd_col])
            except ValueError:
                return 0.0
    return 0.0


# ===========================================================================
# ChIP-vs-input log2 ratio track (deepTools bamCompare)
# ===========================================================================

def _bamcompare_log2(
    chip_name: str, chip_bam: Path, ctrl_name: str, ctrl_bam: Path,
    bw_dir: Path, *, threads: int, bin_size: int = 10,
) -> Path | None:
    """
    deepTools bamCompare → log2(ChIP / input) bigWig.

    Unlike the per-sample RPGC track, this subtracts the matched input
    background: the two BAMs are depth-scaled to each other
    (``--scaleFactorsMethod readCount``) and the per-bin log2 ratio is written.
    Returns the bigWig path (None if deeptools is missing or the run fails).
    """
    if not shutil.which("bamCompare"):
        logger.warning(
            "bamCompare (deeptools) not found — skipping log2(ChIP/input) track for %s. "
            "Install: conda install -c bioconda deeptools", chip_name,
        )
        return None

    bw_path = bw_dir / f"{chip_name}.log2_input.bw"
    if bw_path.exists():
        logger.info("log2(ChIP/input) bigWig already exists: %s", bw_path)
        return bw_path

    cmd = [
        "bamCompare",
        "-b1", str(chip_bam), "-b2", str(ctrl_bam),
        "-o", str(bw_path),
        "--operation", "log2",
        "--scaleFactorsMethod", "readCount",
        "--binSize", str(bin_size),
        "--extendReads",
        "--ignoreDuplicates", "--minMappingQuality", "30",
        "-p", str(threads),
    ]
    try:
        _run(cmd, label=f"bamCompare log2 [{chip_name} vs {ctrl_name}]")
        logger.info("log2(ChIP/input) bigWig written: %s", bw_path)
        return bw_path
    except RuntimeError as exc:
        logger.warning("bamCompare failed for %s: %s", chip_name, exc)
        return None


# ===========================================================================
# Utility helpers
# ===========================================================================

def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")

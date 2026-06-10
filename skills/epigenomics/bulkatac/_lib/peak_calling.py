"""
peak_calling.py — Peak calling and consensus peak set generation
                          for bulk ATAC-seq.

Per-sample: MACS2 callpeak (BAMPE mode, no model) on full-depth dedup BAMs.

Consensus peak set (ENCODE naive overlap)
-----------------------------------------
  Per condition:
    1. Pool replicate BAMs → call peaks on pooled
    2. Sequential intersect: pooled peaks ∩ rep1 ∩ rep2 ... (≥50% reciprocal overlap)
    3. Surviving peaks = reproducible peaks for that condition
  Across conditions:
    4. Union (cat + sort + bedtools merge) of all per-condition reproducible peaks
    5. Convert to SAF format for featureCounts

  This follows the ENCODE ATAC-seq pipeline's "naive overlap" method and the
  CebolaLab approach: peaks must be present in the pooled analysis AND in every
  replicate within a condition to be considered reproducible.

  Reference: https://www.encodeproject.org/atac-seq/
             https://github.com/CebolaLab/ATAC-seq

MACS2 parameters (ENCODE / CebolaLab)
--------------------------------------
  PE: -f BAMPE --nomodel --keep-dup all
      (BAMPE uses actual fragment positions; --shift/--extsize are ignored)
  SE: -f BAM   --nomodel --shift -37 --extsize 73 --keep-dup all
      (--shift -37 --extsize 73 centres a 73 bp half-nucleosome window
       on the Tn5 cut site, following CebolaLab convention)

  --keep-dup all because our BAMs are already deduplicated in Step 2.

  --nomodel skips fragment-size estimation (ATAC-seq fragments are NOT
  ChIP-like peaks — the NFR signal is at cut sites, not extended reads).

References
----------
  ENCODE ATAC-seq pipeline : https://www.encodeproject.org/atac-seq/
  MACS2                    : https://github.com/macs3-project/MACS
  CebolaLab ATAC-seq       : https://github.com/CebolaLab/ATAC-seq
  bedtools                 : https://github.com/arq5x/bedtools2
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .encode_qc_criteria import ENCODE_QC_THRESHOLDS

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
class PeakCallingResult:
    """Output of run_peak_calling() for one sample."""
    sample_name:      str
    peaks_narrowpeak: Path              # *_peaks.narrowPeak
    summits_bed:      Path | None = None  # *_summits.bed
    n_peaks:          int   = 0
    peak_count_tier:  str   = ""        # ENCODE tier (preferred/acceptable/below)
    macs2_log:        str   = ""


@dataclass
class ConsensusPeakResult:
    """Output of build_consensus_peaks()."""
    consensus_bed:    Path               # merged consensus peaks BED
    consensus_saf:    Path               # SAF format for featureCounts
    n_peaks:          int   = 0
    per_sample_peaks: dict[str, int] = field(default_factory=dict)


# ===========================================================================
# ENCODE peak count tier
# ===========================================================================

def peak_count_tier(n_peaks: int) -> str:
    """Assign ENCODE tier based on replicated peak count."""
    t = ENCODE_QC_THRESHOLDS["n_peaks_replicated"]
    if n_peaks >= t["preferred"]:
        return "preferred"
    elif n_peaks >= t["acceptable"]:
        return "acceptable"
    else:
        return "below"


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
            f"  stdout: {result.stdout[:500]}\n"
            f"  stderr: {result.stderr[:500]}"
        )
    return result


# ===========================================================================
# Per-sample peak calling
# ===========================================================================

def run_peak_calling(
    sample_name: str,
    bam: Path,
    output_dir: Path,
    *,
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    shift: int = -37,
    extsize: int = 73,
) -> PeakCallingResult:
    """
    Call peaks for one sample using MACS2.

    Uses full-depth deduplicated BAMs.  --keep-dup all because our BAMs
    are already deduplicated in Step 2.

    Parameters
    ----------
    bam         : full-depth deduplicated BAM
    output_dir  : directory for MACS2 output
    genome_size : MACS2 -g parameter (hs, mm, ce, dm, or integer)
    is_paired   : True for PE (BAMPE), False for SE (BAM)
    qvalue      : MACS2 -q threshold (default 0.05)
    shift       : MACS2 --shift (default -37, half-nucleosome centering)
    extsize     : MACS2 --extsize (default 73, half-nucleosome window)
    """
    _require("macs2")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written at the very end, after MACS2 returns 0 — a crash mid-run
    # leaves a partial narrowPeak but no marker, so the next run redoes it.
    np_path = output_dir / f"{sample_name}_peaks.narrowPeak"
    done_marker = output_dir / f"{sample_name}.macs2.done"
    if done_marker.exists() and np_path.exists():
        n_peaks = _count_lines(np_path)
        tier = peak_count_tier(n_peaks)
        logger.info("  [%s] checkpoint: %d peaks [%s] — skipping",
                     sample_name, n_peaks, tier)
        return PeakCallingResult(
            sample_name=sample_name,
            peaks_narrowpeak=np_path,
            summits_bed=output_dir / f"{sample_name}_summits.bed",
            n_peaks=n_peaks,
            peak_count_tier=tier,
        )

    fmt = "BAMPE" if is_paired else "BAM"
    cmd = [
        "macs2", "callpeak",
        "-t", str(bam),
        "-f", fmt,
        "-g", str(genome_size),
        "-n", sample_name,
        "--outdir", str(output_dir),
        "--nomodel",
        "-q", str(qvalue),
        "--keep-dup", "all",
        "--call-summits",
    ]
    # --shift/--extsize only apply to single-end mode (BAM/BED).
    # BAMPE uses actual fragment positions and ignores these flags.
    if not is_paired:
        cmd.extend(["--shift", str(shift), "--extsize", str(extsize)])

    _run(cmd, label=f"macs2 callpeak [{sample_name}]")

    n_peaks = _count_lines(np_path) if np_path.exists() else 0
    summits = output_dir / f"{sample_name}_summits.bed"
    tier = peak_count_tier(n_peaks)

    logger.info("  [%s] %d peaks called (q < %s)  [%s]",
                sample_name, n_peaks, qvalue, tier)

    done_marker.write_text("")   # success sentinel — MACS2 returned 0

    return PeakCallingResult(
        sample_name=sample_name,
        peaks_narrowpeak=np_path,
        summits_bed=summits if summits.exists() else None,
        n_peaks=n_peaks,
        peak_count_tier=tier,
    )


def run_all_peak_calling(
    mapping_results: list,   # list[MappingResult]
    output_dir: Path,
    *,
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    shift: int = -37,
    extsize: int = 73,
) -> list[PeakCallingResult]:
    """Call peaks for all samples using full-depth dedup BAMs.

    Each sample gets its own subdirectory: {sample}/qvalue{qvalue}/
    """
    results: list[PeakCallingResult] = []

    for mr in mapping_results:
        logger.info("Peak calling: %s", mr.sample_name)
        sample_dir = output_dir / mr.sample_name / f"qvalue{qvalue}"
        result = run_peak_calling(
            mr.sample_name, mr.bam, sample_dir,
            genome_size=genome_size, is_paired=is_paired,
            qvalue=qvalue, shift=shift, extsize=extsize,
        )
        results.append(result)

    return results


# ===========================================================================
# Consensus peak set
# ===========================================================================

def build_consensus_peaks(
    peak_results: list[PeakCallingResult],
    sample_conditions: dict[str, str],
    bam_paths: dict[str, Path],
    output_dir: Path,
    *,
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    shift: int = -37,
    extsize: int = 73,
    threads: int = 8,
    overlap_fraction: float = 0.50,
) -> ConsensusPeakResult:
    """
    Build a consensus peak set using the ENCODE naive overlap method.

    Per condition (requires ≥ 2 replicates):
      1. Pool replicate BAMs (samtools merge) → call peaks on pooled
      2. Sequential intersect: pooled peaks ∩ rep1 peaks ∩ rep2 peaks ...
         using bedtools intersect -f/-F (reciprocal overlap ≥ 50%)
      3. Surviving peaks = reproducible peaks for that condition

    For conditions with only 1 replicate, the per-sample peaks are used
    directly (no pooling or intersection possible).

    Across conditions:
      4. Union: cat + sort + bedtools merge of all per-condition
         reproducible peak sets
      5. Convert to SAF format for featureCounts

    Parameters
    ----------
    peak_results       : per-sample PeakCallingResult from run_all_peak_calling()
    sample_conditions  : {sample_name: condition} mapping
    bam_paths          : {sample_name: Path} to full-depth dedup BAMs
    output_dir         : directory for consensus output files
    genome_size        : MACS2 -g parameter
    is_paired          : True for PE (BAMPE), False for SE
    qvalue             : MACS2 -q threshold for pooled peak calling
    shift / extsize    : MACS2 SE parameters
    threads            : samtools merge threads
    overlap_fraction   : reciprocal overlap fraction for bedtools intersect
                         (default 0.50 = ENCODE standard)

    References
    ----------
    ENCODE naive overlap : https://www.encodeproject.org/atac-seq/
    CebolaLab            : https://github.com/CebolaLab/ATAC-seq
    """
    _require("bedtools")
    _require("samtools")
    _require("macs2")
    output_dir.mkdir(parents=True, exist_ok=True)

    consensus_bed = output_dir / "consensus_peaks.bed"
    consensus_saf = output_dir / "consensus_peaks.saf"

    # Checkpoint
    if consensus_bed.exists() and consensus_bed.stat().st_size > 0:
        n_peaks = _count_lines(consensus_bed)
        logger.info("Consensus peaks checkpoint: %d peaks — skipping", n_peaks)
        if not consensus_saf.exists():
            _bed_to_saf(consensus_bed, consensus_saf)
        return ConsensusPeakResult(
            consensus_bed=consensus_bed,
            consensus_saf=consensus_saf,
            n_peaks=n_peaks,
            per_sample_peaks={r.sample_name: r.n_peaks for r in peak_results},
        )

    # ── Group samples by condition ────────────────────────────────────────
    peak_by_name = {r.sample_name: r for r in peak_results}
    cond_samples: dict[str, list[str]] = {}
    for name, cond in sample_conditions.items():
        cond_samples.setdefault(cond, []).append(name)

    fmt = "BAMPE" if is_paired else "BAM"
    overlap_str = str(overlap_fraction)
    reproducible_beds: list[Path] = []

    for cond, samples in sorted(cond_samples.items()):
        cond_dir = output_dir / cond
        cond_dir.mkdir(parents=True, exist_ok=True)
        repro_bed = cond_dir / f"{cond}_reproducible.bed"

        # Checkpoint per condition
        if repro_bed.exists() and repro_bed.stat().st_size > 0:
            n = _count_lines(repro_bed)
            logger.info("  [%s] reproducible peaks checkpoint: %d — skipping", cond, n)
            reproducible_beds.append(repro_bed)
            continue

        rep_bams  = [bam_paths[s] for s in samples if s in bam_paths]
        rep_peaks = [peak_by_name[s].peaks_narrowpeak for s in samples
                     if s in peak_by_name and peak_by_name[s].peaks_narrowpeak.exists()]

        if len(rep_bams) < 2:
            # Single replicate — use its peaks directly (3-col BED)
            logger.info("  [%s] single replicate — using peaks directly", cond)
            if rep_peaks:
                _narrowpeak_to_bed3(rep_peaks[0], repro_bed)
                reproducible_beds.append(repro_bed)
            continue

        # ── 1. Pool replicate BAMs → call peaks on pooled ────────────────
        pooled_bam = cond_dir / f"{cond}_pooled.bam"
        if not pooled_bam.exists():
            _run(
                ["samtools", "merge", "-@", str(threads),
                 str(pooled_bam)] + [str(b) for b in rep_bams],
                label=f"samtools merge [{cond}]",
            )
            _run(["samtools", "index", "-@", str(threads), str(pooled_bam)],
                 label=f"samtools index [{cond}]")

        pooled_peaks = cond_dir / f"{cond}_pooled_peaks.narrowPeak"
        if not pooled_peaks.exists():
            macs2_cmd = [
                "macs2", "callpeak",
                "-t", str(pooled_bam),
                "-f", fmt,
                "-g", str(genome_size),
                "-n", f"{cond}_pooled",
                "--outdir", str(cond_dir),
                "--nomodel",
                "-q", str(qvalue),
                "--keep-dup", "all",
                "--call-summits",
            ]
            if not is_paired:
                macs2_cmd.extend(["--shift", str(shift), "--extsize", str(extsize)])
            _run(macs2_cmd, label=f"macs2 callpeak pooled [{cond}]")

        n_pooled = _count_lines(pooled_peaks) if pooled_peaks.exists() else 0
        logger.info("  [%s] pooled peaks: %d", cond, n_pooled)

        # ── 2. Sequential intersect: pooled ∩ rep1 ∩ rep2 ... ────────────
        #   ENCODE: take pooled peaks, require ≥50% reciprocal overlap
        #   with each replicate's peaks sequentially.
        current = pooled_peaks
        for i, rp in enumerate(rep_peaks):
            intersected = cond_dir / f"{cond}_pooled_intersect_rep{i+1}.bed"
            if not intersected.exists() or intersected.stat().st_size == 0:
                result = _run(
                    ["bedtools", "intersect",
                     "-a", str(current),
                     "-b", str(rp),
                     "-f", overlap_str,
                     "-F", overlap_str,
                     "-e",       # use either -f or -F (not both required)
                     "-wa",      # report the -a entry
                     ],
                    label=f"bedtools intersect [{cond}] pooled ∩ rep{i+1}",
                )
                intersected.write_text(result.stdout)
            n_surv = _count_lines(intersected) if intersected.exists() else 0
            logger.info("  [%s] after ∩ rep%d: %d peaks", cond, i + 1, n_surv)
            current = intersected

        # Convert final intersect result to 3-col BED and deduplicate
        _narrowpeak_to_bed3(current, repro_bed)
        n_repro = _count_lines(repro_bed)
        logger.info("  [%s] reproducible peaks: %d", cond, n_repro)
        reproducible_beds.append(repro_bed)

        # Cleanup pooled BAM (large)
        for f in [pooled_bam, Path(str(pooled_bam) + ".bai")]:
            if f.exists():
                f.unlink()

    # ── 3. Union across conditions ────────────────────────────────────────
    if not reproducible_beds:
        logger.warning("No reproducible peaks from any condition")
        consensus_bed.write_text("")
        _bed_to_saf(consensus_bed, consensus_saf)
        return ConsensusPeakResult(
            consensus_bed=consensus_bed, consensus_saf=consensus_saf,
            n_peaks=0,
            per_sample_peaks={r.sample_name: r.n_peaks for r in peak_results},
        )

    concat_bed = output_dir / "all_reproducible_concat.bed"
    sorted_bed = output_dir / "all_reproducible_sorted.bed"

    with open(concat_bed, "w") as out:
        for bed in reproducible_beds:
            with open(bed) as f:
                for line in f:
                    out.write(line)

    _run(["sort", "-k1,1", "-k2,2n", str(concat_bed), "-o", str(sorted_bed)],
         label="sort reproducible peaks")

    result = _run(
        ["bedtools", "merge", "-i", str(sorted_bed)],
        label="bedtools merge (union across conditions)",
    )
    consensus_bed.write_text(result.stdout)

    # SAF format
    _bed_to_saf(consensus_bed, consensus_saf)

    # Cleanup intermediates
    for f in (concat_bed, sorted_bed):
        if f.exists():
            f.unlink()

    n_peaks = _count_lines(consensus_bed)
    logger.info("Consensus peaks (ENCODE naive overlap): %d", n_peaks)

    return ConsensusPeakResult(
        consensus_bed=consensus_bed,
        consensus_saf=consensus_saf,
        n_peaks=n_peaks,
        per_sample_peaks={r.sample_name: r.n_peaks for r in peak_results},
    )


def _narrowpeak_to_bed3(src: Path, dst: Path) -> None:
    """Extract chr, start, end from narrowPeak/BED and sort + deduplicate."""
    lines: set[str] = set()
    with open(src) as f:
        for line in f:
            parts = line.split("\t")
            if len(parts) >= 3:
                lines.add(f"{parts[0]}\t{parts[1]}\t{parts[2]}\n")
    sorted_lines = sorted(lines, key=lambda x: (x.split("\t")[0], int(x.split("\t")[1])))
    with open(dst, "w") as out:
        out.writelines(sorted_lines)


# ===========================================================================
# Count matrix (featureCounts)
# ===========================================================================

def build_count_matrix(
    bam_paths: list[Path],
    sample_names: list[str],
    consensus_saf: Path,
    output_dir: Path,
    *,
    is_paired: bool = True,
    threads: int = 8,
) -> Path:
    """
    Count reads per consensus peak per sample using featureCounts.

    Uses full-depth dedup BAMs — featureCounts counts are normalised
    downstream by DESeq2 size factors.

    Returns
    -------
    Path to the count matrix TSV file.
    """
    _require("featureCounts")
    output_dir.mkdir(parents=True, exist_ok=True)

    counts_file = output_dir / "peak_counts.txt"
    done_marker = output_dir / ".count_matrix.done"

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written after featureCounts returns 0 — a crash mid-run leaves a
    # partial peak_counts.txt but no marker, so the next run redoes it.
    if done_marker.exists() and counts_file.exists():
        logger.info("Count matrix checkpoint: %s — skipping", counts_file)
        return counts_file

    cmd = [
        "featureCounts",
        "-F", "SAF",
        "-a", str(consensus_saf),
        "-o", str(counts_file),
        "-T", str(threads),
    ]
    if is_paired:
        cmd.extend(["-p", "--countReadPairs"])

    cmd.extend(str(b) for b in bam_paths)

    _run(cmd, label="featureCounts")

    done_marker.write_text("")   # success sentinel — featureCounts returned 0

    logger.info("Count matrix written: %s  (%d samples)", counts_file, len(bam_paths))
    return counts_file


# ===========================================================================
# MACS2 genome size mapping
# ===========================================================================

# Effective genome sizes from deepTools (non-N bases / total mappable genome).
# Using numeric values consistently instead of MACS2 built-in shortcuts
# (hs=2.7e9, mm=1.87e9, dm=1.2e8) which are older, less precise estimates.
# Reference: https://deeptools.readthedocs.io/en/latest/content/feature/effectiveGenomeSize.html
MACS2_GENOME_SIZES: dict[str, str] = {
    "hg38":     "2.91e9",        # deepTools GRCh38: 2,913,022,398
    "hg19":     "2.86e9",        # deepTools GRCh37: 2,864,785,220
    "mm10":     "2.65e9",        # deepTools GRCm38: 2,652,783,500
    "mm39":     "2.65e9",        # deepTools GRCm39: 2,654,621,783
    "dm6":      "1.43e8",        # deepTools dm6:      142,573,017
    "dm3":      "1.62e8",        # deepTools dm3:      162,367,812
    "danRer11": "1.37e9",        # deepTools GRCz11: 1,368,780,147
    "danRer10": "1.37e9",        # deepTools GRCz10: 1,369,631,918
    "sacCer3":  "1.2e7",         # ~12 Mb
    "ce11":     "1.00e8",        # deepTools WBcel235: 100,286,401
    "rn6":      "2.15e9",        # rat
    "rn7":      "2.15e9",        # rat (mRatBN7.2)
    "galGal6":  "1.05e9",        # chicken
    "TAIR10":   "1.19e8",        # deepTools TAIR10:   119,482,012
}


def get_macs2_genome_size(
    genome: str,
    fasta: Path | None = None,
) -> str:
    """Return MACS2 -g value for a genome build.

    Falls back to computing non-N bases from *fasta* when the genome
    is not in the lookup table.
    """
    if genome in MACS2_GENOME_SIZES:
        return MACS2_GENOME_SIZES[genome]
    if fasta and fasta.exists():
        from .mapping import compute_effective_genome_size
        size = compute_effective_genome_size(fasta)
        # Format as scientific notation for MACS2 and cache
        size_str = f"{size:.2e}"
        MACS2_GENOME_SIZES[genome] = size_str
        return size_str
    logger.warning(
        "No MACS2 genome size for '%s' and no FASTA available to compute it. "
        "Falling back to genome name (MACS2 may reject this). "
        "Known genomes: %s",
        genome, sorted(MACS2_GENOME_SIZES),
    )
    return genome


# ===========================================================================
# Helpers
# ===========================================================================

def _count_lines(path: Path) -> int:
    """Count non-empty, non-comment lines in a file."""
    n = 0
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                n += 1
    return n


def _bed_to_saf(bed_path: Path, saf_path: Path) -> None:
    """
    Convert a 3-column BED to SAF format for featureCounts.

    SAF: GeneID \\t Chr \\t Start \\t End \\t Strand
    """
    with open(bed_path) as bed, open(saf_path, "w") as saf:
        saf.write("GeneID\tChr\tStart\tEnd\tStrand\n")
        for i, line in enumerate(bed, 1):
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                # BED is 0-based half-open; SAF is 1-based inclusive
                start_1based = int(parts[1]) + 1
                saf.write(f"peak_{i}\t{parts[0]}\t{start_1based}\t{parts[2]}\t.\n")
    logger.info("SAF written: %s", saf_path)


# ===========================================================================
# Summary
# ===========================================================================

def build_peak_calling_summary(
    peak_results: list[PeakCallingResult],
    consensus: ConsensusPeakResult,
) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd

    rows = []
    for r in peak_results:
        rows.append({
            "sample":          r.sample_name,
            "n_peaks":         r.n_peaks,
            "peak_count_tier": r.peak_count_tier,
            "narrowpeak":      str(r.peaks_narrowpeak),
        })
    rows.append({
        "sample":          "consensus",
        "n_peaks":         consensus.n_peaks,
        "peak_count_tier": peak_count_tier(consensus.n_peaks),
        "narrowpeak":      str(consensus.consensus_bed),
    })
    return pd.DataFrame(rows)


def write_peak_calling_summary(
    peak_results: list[PeakCallingResult],
    consensus: ConsensusPeakResult,
    output_dir: Path,
) -> Path:
    df   = build_peak_calling_summary(peak_results, consensus)
    path = output_dir / "peak_calling_summary.csv"
    df.to_csv(path, index=False)
    logger.info("Peak calling summary written: %s", path)
    return path

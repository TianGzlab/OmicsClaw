"""
peak_calling.py — Bulk ChIP-seq Step 3: MACS2 peak calling against input
control, consensus peak set, featureCounts matrix, FRiP, and optional IDR.

Peak calling (ENCODE / nf-core/chipseq):
  * Against the matched input/IgG control when present:  ``macs2 callpeak -t
    chip -c control``. When a ChIP sample has NO control (control-free design),
    MACS2 is run WITHOUT ``-c`` — it builds the background from the ChIP itself
    (local lambda). Supported end-to-end (per-sample + pooled consensus), but
    lower-confidence; ENCODE recommends a matched input. A warning is logged.
  * Narrow mode (TF / sharp histone marks)  →  narrowPeak (+ --call-summits).
  * Broad  mode (broad histone marks)        →  ``--broad`` broadPeak.
  * No Tn5 shift (unlike ATAC) and no --nomodel: PE uses BAMPE fragment
    positions, SE lets MACS2 build the shifting model.
  * ``--keep-dup all`` because BAMs were deduplicated in Step 2.

Consensus peak set (ENCODE naive overlap): per condition pool replicate ChIP
BAMs → re-call vs the pooled matched control → intersect with each replicate at
``--overlap-fraction`` reciprocal overlap → union conditions → BED + SAF +
featureCounts matrix (peaks × ChIP samples) ready for ``bulkchip-DA``.

Signal-to-noise: FRiP per ChIP sample (vs the consensus set).
Reproducibility: optional IDR on true replicates (point-source / narrow only).

Tools: macs2, bedtools, samtools, featureCounts (subread), idr.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .encode_qc_criteria import frip_tier

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


# ===========================================================================
# Data contracts
# ===========================================================================

@dataclass
class PeakCallingResult:
    """Output of run_peak_calling() for one ChIP sample (vs its control)."""
    sample_name:    str
    control_name:   str | None
    peak_mode:      str                        # "narrow" | "broad"
    peaks_file:     Path                        # *_peaks.narrowPeak / *_peaks.broadPeak
    summits_bed:    Path | None = None          # narrow mode only
    n_peaks:        int = 0
    frip:           float = 0.0
    frip_tier:      str = ""
    macs2_log:      str = ""


@dataclass
class ConsensusPeakResult:
    """Output of build_consensus_peaks()."""
    consensus_bed:    Path
    consensus_saf:    Path
    count_matrix:     Path | None = None        # featureCounts peaks × samples
    n_peaks:          int = 0
    per_sample_peaks: dict[str, int] = field(default_factory=dict)


@dataclass
class IdrResult:
    """Output of one condition's true-replicate IDR run."""
    condition:    str
    n_idr_peaks:  int = 0
    idr_file:     Path | None = None
    note:         str = ""


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
    logger.info("  CMD [%s]: %s", label, " ".join(str(c) for c in cmd))
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
# MACS2 effective genome size
# ===========================================================================

# Effective genome sizes (deepTools non-N bases), used for MACS2 -g.
MACS2_GENOME_SIZES: dict[str, str] = {
    "hg38":     "2.91e9",
    "hg19":     "2.86e9",
    "mm10":     "2.65e9",
    "mm39":     "2.65e9",
    "dm6":      "1.43e8",
    "dm3":      "1.62e8",
    "danRer11": "1.37e9",
    "danRer10": "1.37e9",
    "sacCer3":  "1.2e7",
    "ce11":     "1.00e8",
    "rn6":      "2.15e9",
    "rn7":      "2.15e9",
    "galGal6":  "1.05e9",
    "TAIR10":   "1.19e8",
}


def get_macs2_genome_size(genome: str, fasta: Path | None = None) -> str:
    """Return MACS2 -g value for a genome build (FASTA non-N fallback)."""
    if genome in MACS2_GENOME_SIZES:
        return MACS2_GENOME_SIZES[genome]
    if fasta and Path(fasta).exists():
        from .mapping import compute_effective_genome_size
        size = compute_effective_genome_size(Path(fasta))
        size_str = f"{size:.2e}"
        MACS2_GENOME_SIZES[genome] = size_str
        return size_str
    logger.warning(
        "No MACS2 genome size for '%s' and no FASTA to compute it; "
        "passing the genome name to MACS2 (may be rejected). Known: %s",
        genome, sorted(MACS2_GENOME_SIZES),
    )
    return genome


# ===========================================================================
# Per-sample peak calling (vs matched control)
# ===========================================================================

def _macs2_callpeak(
    name: str,
    chip_bam: Path,
    control_bam: Path | None,
    output_dir: Path,
    *,
    peak_mode: str,
    genome_size: str,
    is_paired: bool,
    qvalue: float,
    broad_cutoff: float,
) -> None:
    """Run one MACS2 callpeak (ChIP vs control), narrow or broad."""
    fmt = "BAMPE" if is_paired else "BAM"
    cmd = [
        "macs2", "callpeak",
        "-t", str(chip_bam),
    ]
    if control_bam is not None:
        cmd += ["-c", str(control_bam)]
    cmd += [
        "-f", fmt,
        "-g", str(genome_size),
        "-n", name,
        "--outdir", str(output_dir),
        "-q", str(qvalue),
        "--keep-dup", "all",
    ]
    if peak_mode == "broad":
        cmd += ["--broad", "--broad-cutoff", str(broad_cutoff)]
    else:
        cmd += ["--call-summits"]
    _run(cmd, label=f"macs2 callpeak [{name}] ({peak_mode})")


def run_peak_calling(
    sample_name: str,
    chip_bam: Path,
    control_bam: Path | None,
    control_name: str | None,
    output_dir: Path,
    *,
    peak_mode: str = "narrow",
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    broad_cutoff: float = 0.1,
) -> PeakCallingResult:
    """Call peaks for one ChIP sample against its matched input control."""
    _require("macs2")
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = "broadPeak" if peak_mode == "broad" else "narrowPeak"
    peaks_file  = output_dir / f"{sample_name}_peaks.{suffix}"
    summits_bed = output_dir / f"{sample_name}_summits.bed"
    done_marker = output_dir / f"{sample_name}.macs2.done"

    if done_marker.exists() and peaks_file.exists():
        n_peaks = _count_lines(peaks_file)
        logger.info("  [%s] checkpoint: %d %s peaks — skipping",
                    sample_name, n_peaks, peak_mode)
        return PeakCallingResult(
            sample_name=sample_name, control_name=control_name, peak_mode=peak_mode,
            peaks_file=peaks_file,
            summits_bed=summits_bed if (peak_mode != "broad" and summits_bed.exists()) else None,
            n_peaks=n_peaks,
        )

    _macs2_callpeak(
        sample_name, chip_bam, control_bam, output_dir,
        peak_mode=peak_mode, genome_size=genome_size, is_paired=is_paired,
        qvalue=qvalue, broad_cutoff=broad_cutoff,
    )

    n_peaks = _count_lines(peaks_file) if peaks_file.exists() else 0
    logger.info("  [%s] %d %s peaks (vs %s, q < %s)",
                sample_name, n_peaks, peak_mode, control_name or "no control", qvalue)
    done_marker.write_text("")

    return PeakCallingResult(
        sample_name=sample_name, control_name=control_name, peak_mode=peak_mode,
        peaks_file=peaks_file,
        summits_bed=summits_bed if (peak_mode != "broad" and summits_bed.exists()) else None,
        n_peaks=n_peaks,
    )


def run_all_peak_calling(
    mapping_results: list,            # list of objects with .sample_name/.bam/.is_control/.control
    output_dir: Path,
    *,
    control_map: dict[str, str],
    peak_modes: dict[str, str],
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    broad_cutoff: float = 0.1,
) -> list[PeakCallingResult]:
    """Call peaks for every ChIP sample (control/input samples are skipped)."""
    bam_by_name = {mr.sample_name: Path(mr.bam) for mr in mapping_results}
    is_control  = {mr.sample_name: bool(getattr(mr, "is_control", False)) for mr in mapping_results}

    results: list[PeakCallingResult] = []
    for mr in mapping_results:
        if is_control.get(mr.sample_name):
            continue  # input/IgG controls are not peak-called on their own
        ctrl_name = control_map.get(mr.sample_name) or getattr(mr, "control", None)
        ctrl_bam  = bam_by_name.get(ctrl_name) if ctrl_name else None
        if ctrl_name and ctrl_bam is None:
            logger.warning("  [%s] control '%s' BAM not found — calling without -c "
                           "(MACS2 local-lambda background)", mr.sample_name, ctrl_name)
        elif not ctrl_name:
            logger.warning("  [%s] no input/IgG control — calling without -c "
                           "(MACS2 local-lambda background; ENCODE recommends an input)",
                           mr.sample_name)
        mode = peak_modes.get(mr.sample_name, "narrow")
        logger.info("Peak calling: %s (vs %s, %s)", mr.sample_name,
                    ctrl_name or "no control", mode)
        sample_dir = output_dir / mr.sample_name
        results.append(run_peak_calling(
            mr.sample_name, Path(mr.bam), ctrl_bam, ctrl_name, sample_dir,
            peak_mode=mode, genome_size=genome_size, is_paired=is_paired,
            qvalue=qvalue, broad_cutoff=broad_cutoff,
        ))
    return results


# ===========================================================================
# Consensus peak set (ENCODE naive overlap, pooled vs pooled control)
# ===========================================================================

def build_consensus_peaks(
    peak_results: list[PeakCallingResult],
    sample_conditions: dict[str, str],
    chip_bam_paths: dict[str, Path],
    control_bam_paths: dict[str, Path],
    control_map: dict[str, str],
    output_dir: Path,
    *,
    genome_size: str = "hs",
    is_paired: bool = True,
    qvalue: float = 0.05,
    broad_cutoff: float = 0.1,
    threads: int = 8,
    overlap_fraction: float = 0.50,
) -> ConsensusPeakResult:
    """
    ENCODE naive-overlap consensus.

    Per condition (≥ 2 ChIP replicates):
      1. Pool replicate ChIP BAMs  + pool their matched control BAMs.
      2. MACS2 callpeak pooled ChIP vs pooled control.
      3. Sequential intersect: pooled ∩ rep1 ∩ rep2 ... (reciprocal overlap).
    Single-replicate conditions: use the replicate's peaks directly.
    Across conditions: cat | sort | bedtools merge → consensus BED + SAF.
    """
    _require("bedtools"); _require("samtools"); _require("macs2")
    output_dir.mkdir(parents=True, exist_ok=True)

    consensus_bed = output_dir / "consensus_peaks.bed"
    consensus_saf = output_dir / "consensus_peaks.saf"

    if consensus_bed.exists() and consensus_bed.stat().st_size > 0:
        n_peaks = _count_lines(consensus_bed)
        logger.info("Consensus checkpoint: %d peaks — skipping", n_peaks)
        if not consensus_saf.exists():
            _bed_to_saf(consensus_bed, consensus_saf)
        return ConsensusPeakResult(
            consensus_bed=consensus_bed, consensus_saf=consensus_saf, n_peaks=n_peaks,
            per_sample_peaks={r.sample_name: r.n_peaks for r in peak_results},
        )

    peak_by_name = {r.sample_name: r for r in peak_results}
    # peak_results only contains ChIP samples; group those by condition.
    cond_samples: dict[str, list[str]] = {}
    for r in peak_results:
        cond = sample_conditions.get(r.sample_name, "")
        cond_samples.setdefault(cond, []).append(r.sample_name)

    overlap_str = str(overlap_fraction)
    reproducible_beds: list[Path] = []
    # A condition is "broad" if any of its samples is broad → pooled call matches.
    for cond, samples in sorted(cond_samples.items()):
        cond_dir = output_dir / cond
        cond_dir.mkdir(parents=True, exist_ok=True)
        repro_bed = cond_dir / f"{cond}_reproducible.bed"

        if repro_bed.exists() and repro_bed.stat().st_size > 0:
            logger.info("  [%s] reproducible checkpoint: %d — skipping",
                        cond, _count_lines(repro_bed))
            reproducible_beds.append(repro_bed)
            continue

        rep_bams  = [chip_bam_paths[s] for s in samples if s in chip_bam_paths]
        rep_peaks = [peak_by_name[s].peaks_file for s in samples
                     if s in peak_by_name and peak_by_name[s].peaks_file.exists()]
        cond_mode = "broad" if any(peak_by_name[s].peak_mode == "broad" for s in samples) else "narrow"

        if len(rep_bams) < 2:
            logger.info("  [%s] single replicate — using its peaks directly", cond)
            if rep_peaks:
                _narrowpeak_to_bed3(rep_peaks[0], repro_bed)
                reproducible_beds.append(repro_bed)
            continue

        # 1. Pool ChIP BAMs + pool matched control BAMs
        pooled_chip = cond_dir / f"{cond}_pooled.chip.bam"
        _merge_bams(rep_bams, pooled_chip, threads=threads)

        ctrl_names = {control_map.get(s) for s in samples if control_map.get(s)}
        ctrl_bams  = [control_bam_paths[c] for c in ctrl_names if c in control_bam_paths]
        pooled_ctrl: Path | None = None
        if ctrl_bams:
            pooled_ctrl = cond_dir / f"{cond}_pooled.control.bam"
            _merge_bams(ctrl_bams, pooled_ctrl, threads=threads)
        else:
            logger.warning("  [%s] no input/IgG control — pooled peaks called without -c "
                           "(MACS2 local-lambda background)", cond)

        # 2. MACS2 pooled ChIP vs pooled control
        suffix = "broadPeak" if cond_mode == "broad" else "narrowPeak"
        pooled_peaks = cond_dir / f"{cond}_pooled_peaks.{suffix}"
        if not pooled_peaks.exists():
            _macs2_callpeak(
                f"{cond}_pooled", pooled_chip, pooled_ctrl, cond_dir,
                peak_mode=cond_mode, genome_size=genome_size, is_paired=is_paired,
                qvalue=qvalue, broad_cutoff=broad_cutoff,
            )
        logger.info("  [%s] pooled peaks: %d", cond,
                    _count_lines(pooled_peaks) if pooled_peaks.exists() else 0)

        # 3. Sequential intersect pooled ∩ each replicate
        current = pooled_peaks
        for i, rp in enumerate(rep_peaks):
            intersected = cond_dir / f"{cond}_pooled_intersect_rep{i+1}.bed"
            if not intersected.exists() or intersected.stat().st_size == 0:
                res = _run(
                    ["bedtools", "intersect", "-a", str(current), "-b", str(rp),
                     "-f", overlap_str, "-F", overlap_str, "-e", "-wa"],
                    label=f"bedtools intersect [{cond}] pooled ∩ rep{i+1}",
                )
                intersected.write_text(res.stdout)
            logger.info("  [%s] after ∩ rep%d: %d peaks", cond, i + 1,
                        _count_lines(intersected) if intersected.exists() else 0)
            current = intersected

        _narrowpeak_to_bed3(current, repro_bed)
        logger.info("  [%s] reproducible peaks: %d", cond, _count_lines(repro_bed))
        reproducible_beds.append(repro_bed)

        for f in (pooled_chip, Path(str(pooled_chip) + ".bai")):
            if f.exists():
                f.unlink()
        if pooled_ctrl:
            for f in (pooled_ctrl, Path(str(pooled_ctrl) + ".bai")):
                if f.exists():
                    f.unlink()

    if not reproducible_beds:
        logger.warning("No reproducible peaks from any condition")
        consensus_bed.write_text("")
        _bed_to_saf(consensus_bed, consensus_saf)
        return ConsensusPeakResult(
            consensus_bed=consensus_bed, consensus_saf=consensus_saf, n_peaks=0,
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
    res = _run(["bedtools", "merge", "-i", str(sorted_bed)],
               label="bedtools merge (union across conditions)")
    consensus_bed.write_text(res.stdout)
    _bed_to_saf(consensus_bed, consensus_saf)
    for f in (concat_bed, sorted_bed):
        if f.exists():
            f.unlink()

    n_peaks = _count_lines(consensus_bed)
    logger.info("Consensus peaks (ENCODE naive overlap): %d", n_peaks)
    return ConsensusPeakResult(
        consensus_bed=consensus_bed, consensus_saf=consensus_saf, n_peaks=n_peaks,
        per_sample_peaks={r.sample_name: r.n_peaks for r in peak_results},
    )


def _merge_bams(bams: list[Path], dest: Path, *, threads: int) -> None:
    if dest.exists():
        return
    _run(["samtools", "merge", "-f", "-@", str(threads), str(dest)] + [str(b) for b in bams],
         label=f"samtools merge [{dest.name}]")
    _run(["samtools", "index", "-@", str(threads), str(dest)],
         label=f"samtools index [{dest.name}]")


# ===========================================================================
# Count matrix (featureCounts over ChIP samples)
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
    """featureCounts over the consensus SAF → raw peaks × ChIP-samples matrix."""
    _require("featureCounts")
    output_dir.mkdir(parents=True, exist_ok=True)
    counts_file = output_dir / "peak_counts.txt"
    done_marker = output_dir / ".count_matrix.done"

    if done_marker.exists() and counts_file.exists():
        logger.info("Count matrix checkpoint: %s — skipping", counts_file)
        return counts_file

    cmd = ["featureCounts", "-F", "SAF", "-a", str(consensus_saf),
           "-o", str(counts_file), "-T", str(threads)]
    if is_paired:
        cmd += ["-p", "--countReadPairs"]
    cmd += [str(b) for b in bam_paths]
    _run(cmd, label="featureCounts")
    done_marker.write_text("")
    logger.info("Count matrix written: %s  (%d ChIP samples)", counts_file, len(bam_paths))
    return counts_file


# ===========================================================================
# FRiP
# ===========================================================================

def compute_frip(
    sample_name: str,
    bam: Path,
    peaks_bed: Path,
    *,
    n_usable: int = 0,
    is_paired: bool = True,
) -> tuple[float, str]:
    """FRiP = fragments overlapping *peaks_bed* / total usable fragments.

    Returns (frip, tier). Measured against the consensus peak set (DiffBind
    convention) so all samples share one feature set.
    """
    _require("samtools")
    read_mult = 2 if is_paired else 1
    if n_usable <= 0:
        res = _run(["samtools", "view", "-c", "-F", "4", str(bam)],
                   label=f"samtools count [{sample_name}]")
        n_usable = int(res.stdout.strip()) // read_mult
    res = _run(["samtools", "view", "-c", "-L", str(peaks_bed), str(bam)],
               label=f"reads in peaks [{sample_name}]")
    n_in_peaks = int(res.stdout.strip()) // read_mult
    frip = n_in_peaks / n_usable if n_usable > 0 else 0.0
    tier = frip_tier(frip)
    logger.info("  [%s] FRiP = %.3f (%s)  [%d / %d fragments]",
                sample_name, frip, tier, n_in_peaks, n_usable)
    return frip, tier


# ===========================================================================
# IDR (optional; true-replicate, narrow/point-source only)
# ===========================================================================

def run_all_idr(
    peak_results: list[PeakCallingResult],
    sample_conditions: dict[str, str],
    output_dir: Path,
) -> list[IdrResult]:
    """
    Pairwise true-replicate IDR per condition (narrow peaks only).

    Bounded implementation: for each condition with ≥ 2 narrow-mode ChIP
    replicates, run ``idr`` on the first two replicates' narrowPeak files and
    count peaks passing IDR < 0.05. Broad marks and single-replicate conditions
    are skipped with a note. Requires the ``idr`` tool; degrades gracefully.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[IdrResult] = []

    if not _check_tool("idr"):
        logger.warning("idr not found — skipping IDR. Install: conda install -c bioconda idr")
        return [IdrResult(condition="(all)", note="idr tool not installed")]

    by_cond: dict[str, list[PeakCallingResult]] = {}
    for r in peak_results:
        by_cond.setdefault(sample_conditions.get(r.sample_name, ""), []).append(r)

    for cond, reps in sorted(by_cond.items()):
        narrow = [r for r in reps if r.peak_mode == "narrow" and r.peaks_file.exists()]
        if len(narrow) < 2:
            results.append(IdrResult(condition=cond, note="needs ≥2 narrow replicates — skipped"))
            continue
        idr_out = output_dir / f"{cond}.idr.txt"
        try:
            # --rank signal.value is the IDR tool's recommended ranking for
            # narrowPeak/broadPeak inputs (github.com/nboley/idr).
            _run(
                ["idr", "--samples", str(narrow[0].peaks_file), str(narrow[1].peaks_file),
                 "--input-file-type", "narrowPeak", "--rank", "signal.value",
                 "--output-file", str(idr_out), "--idr-threshold", "0.05"],
                label=f"idr [{cond}]",
            )
            n_idr = _count_lines(idr_out) if idr_out.exists() else 0
            logger.info("  [%s] IDR peaks (IDR < 0.05): %d", cond, n_idr)
            results.append(IdrResult(condition=cond, n_idr_peaks=n_idr, idr_file=idr_out,
                                     note=f"{narrow[0].sample_name} vs {narrow[1].sample_name}"))
        except RuntimeError as exc:
            logger.warning("  [%s] IDR failed: %s", cond, exc)
            results.append(IdrResult(condition=cond, note=f"idr failed: {exc}"))
    return results


# ===========================================================================
# Helpers
# ===========================================================================

def _count_lines(path: Path) -> int:
    n = 0
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                n += 1
    return n


def _narrowpeak_to_bed3(src: Path, dst: Path) -> None:
    """Extract chr,start,end from narrowPeak/broadPeak/BED; sort + dedupe."""
    seen: set[str] = set()
    with open(src) as f:
        for line in f:
            parts = line.split("\t")
            if len(parts) >= 3:
                seen.add(f"{parts[0]}\t{parts[1]}\t{parts[2]}\n")
    ordered = sorted(seen, key=lambda x: (x.split("\t")[0], int(x.split("\t")[1])))
    with open(dst, "w") as out:
        out.writelines(ordered)


def _bed_to_saf(bed_path: Path, saf_path: Path) -> None:
    """3-column BED → SAF (GeneID Chr Start End Strand) for featureCounts."""
    with open(bed_path) as bed, open(saf_path, "w") as saf:
        saf.write("GeneID\tChr\tStart\tEnd\tStrand\n")
        for i, line in enumerate(bed, 1):
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                saf.write(f"peak_{i}\t{parts[0]}\t{int(parts[1]) + 1}\t{parts[2]}\t.\n")
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
            "sample":     r.sample_name,
            "control":    r.control_name or "",
            "peak_mode":  r.peak_mode,
            "n_peaks":    r.n_peaks,
            "frip":       round(r.frip, 4),
            "frip_tier":  r.frip_tier,
            "peaks_file": str(r.peaks_file),
        })
    rows.append({
        "sample": "consensus", "control": "", "peak_mode": "",
        "n_peaks": consensus.n_peaks, "frip": "", "frip_tier": "",
        "peaks_file": str(consensus.consensus_bed),
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

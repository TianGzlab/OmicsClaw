"""
encode_qc_criteria.py — ENCODE ChIP-seq QC thresholds, usable-read rules,
strand cross-correlation (NSC/RSC) tiers, and downsampling depth calculation.

This module is the single source of truth for all numeric thresholds used
across every bulkchip skill.  Import it before touching any BAM or peak file.

How ChIP-seq QC differs from ATAC-seq
-------------------------------------
  * Depth standards depend on the **peak mode**: point-source TF / narrow
    histone marks target ~20 M usable reads; broad histone marks
    (H3K9me3, H3K27me3, H3K36me3, ...) target ~45 M.
  * Signal-to-noise is judged by **strand cross-correlation** (NSC / RSC,
    phantompeakqualtools / ssp) and the **deepTools fingerprint**, NOT by
    the ATAC TSS-enrichment / fragment-length nucleosome ladder.
  * Library-complexity bottlenecking uses the same NRF / PBC1 / PBC2
    formulas, but ENCODE's ChIP PBC2 bar is **> 10** (vs ATAC's > 3).
  * Every ChIP sample is interpreted against a matched **input/IgG control**.

Key concepts
------------
Usable reads (ENCODE definition)
  A read/fragment is "usable" if it passes ALL of:
    1. Uniquely mapped     (MAPQ ≥ 30, i.e. no multi-mappers)
    2. Non-duplicate       (Picard / samtools markdup applied)
    3. Pass samtools flags (-F 1804 -f 2 for PE;  -F 1796 for SE)
  (Mitochondrial removal is optional for ChIP and is applied as a courtesy
   filter, not an ENCODE requirement.)

Strand cross-correlation
  NSC = fragment-length cross-correlation / minimum cross-correlation
  RSC = (fragment CC − min CC) / (phantom-peak CC − min CC)
  Computed by phantompeakqualtools ``run_spp.R`` (or ``ssp``).

References
----------
  ENCODE ChIP-seq TF standards : https://www.encodeproject.org/chip-seq/transcription_factor/
  ENCODE data standards        : https://www.encodeproject.org/data-standards/chip-seq/
  Landt et al. 2012 (ENCODE)   : https://doi.org/10.1101/gr.136184.111
  phantompeakqualtools         : https://github.com/kundajelab/phantompeakqualtools
  nf-core/chipseq              : https://github.com/nf-core/chipseq
  Churros                      : https://churros.readthedocs.io/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ENCODE ChIP-seq QC threshold table
# ---------------------------------------------------------------------------

ENCODE_QC_THRESHOLDS: dict[str, dict[str, float]] = {
    # ── Library complexity ───────────────────────────────────────────────────
    # Non-Redundant Fraction  NRF = Distinct / Total
    "nrf": {
        "preferred":  0.90,
        "acceptable": 0.80,
    },
    # PCR Bottleneck Coefficient 1  PBC1 = OneReadPair / Distinct
    # Bottlenecking ladder:
    #   0.0–0.5  severe  |  0.5–0.8  moderate  |  0.8–0.9  mild  |  0.9–1.0  none
    "pbc1": {
        "preferred":     0.90,
        "acceptable":    0.50,
        "severe_cutoff": 0.50,
    },
    # PCR Bottleneck Coefficient 2  PBC2 = OneReadPair / TwoReadPair
    # ENCODE ChIP bar is > 10 (stricter than ATAC's > 3).
    "pbc2": {
        "preferred":  10.0,
        "acceptable": 3.0,
    },
    # ── Strand cross-correlation (signal-to-noise) ───────────────────────────
    # Normalized Strand Cross-correlation (phantompeakqualtools)
    # ENCODE: NSC > 1.05 acceptable; higher is better.
    "nsc": {
        "preferred":  1.10,
        "acceptable": 1.05,
    },
    # Relative Strand Cross-correlation
    # ENCODE: RSC > 0.8 acceptable; > 1.0 strong enrichment.
    "rsc": {
        "preferred":  1.00,
        "acceptable": 0.80,
    },
    # ── Fraction of reads in peaks ───────────────────────────────────────────
    # ENCODE sets NO hard FRiP cutoff for ChIP (it is target-dependent — sharp
    # TF marks run low, broad histone marks run high). These are report-only
    # heuristic tiers, NOT a pass/fail gate.
    "frip": {
        "preferred":  0.05,
        "acceptable": 0.01,
    },
    # ── Read depth (peak-mode dependent) ─────────────────────────────────────
    # Point-source TF / narrow histone marks
    # ENCODE: ≥20 M usable preferred, ≥10 M acceptable
    "usable_reads_tf": {
        "preferred":  20_000_000,
        "acceptable": 10_000_000,
    },
    # Broad-source histone marks (H3K27me3, H3K36me3, H3K9me3, ...)
    # ENCODE histone standard states a single 45 M usable/replicate target for
    # broad marks (encodeproject.org/chip-seq/histone). The 20 M "acceptable"
    # floor here is an interpolation (ENCODE's narrow bar reused as a soft lower
    # tier), NOT an explicit ENCODE broad cutoff.
    "usable_reads_broad": {
        "preferred":  45_000_000,
        "acceptable": 20_000_000,
    },
    # ── Alignment ────────────────────────────────────────────────────────────
    # ENCODE: >95% preferred, >80% acceptable
    "align_rate": {
        "preferred":  0.95,
        "acceptable": 0.80,
    },
    # ── IDR-thresholded peak set (point-source) ──────────────────────────────
    "n_peaks_idr": {
        "preferred":  70_000,
        "acceptable": 50_000,
    },
    # ── Minimum read length (before trimming) ────────────────────────────────
    # ENCODE ChIP: 25 bp processable, ≥50 bp recommended.
    "min_read_length_bp": {
        "preferred":  50.0,
        "acceptable": 25.0,
    },
    # ── IDR reproducibility ──────────────────────────────────────────────────
    # Both ratios must be < 2 to pass ENCODE
    "idr_rescue_ratio": {
        "acceptable": 2.0,
    },
    "idr_self_consistency_ratio": {
        "acceptable": 2.0,
    },
}

# Illumina universal adapter (TruSeq) — the common ChIP-seq library adapter.
ILLUMINA_UNIVERSAL_ADAPTER = "AGATCGGAAGAGC"

# ENCODE BAM filter flags (shared with ATAC)
ENCODE_BAM_EXCL_FLAGS_PE = 1804   # unmapped, mate unmapped, not primary, QC-fail, dup
ENCODE_BAM_EXCL_FLAGS_SE = 1796   # same minus "mate unmapped" bit (bit 8)
ENCODE_BAM_REQ_FLAGS_PE  = 2      # properly paired (PE only)
ENCODE_MAPQ_MIN          = 30     # removes multi-mappers

# Mitochondrial contig names (optional courtesy filter for ChIP).
MITO_CONTIGS = frozenset({"chrM", "chrMT", "MT", "M"})

# Peak modes recognised by the suite.
NARROW_MODE = "narrow"   # TF / sharp histone marks  → MACS2 narrowPeak
BROAD_MODE  = "broad"    # broad histone marks       → MACS2 --broad broadPeak

# Histone marks ENCODE calls in broad mode (normalized: lowercase, no -/_).
# Source: ENCODE histone ChIP-seq standards (encodeproject.org/chip-seq/histone)
# — H3K9me3 is listed as the broad-mode exception despite repeat enrichment.
BROAD_HISTONE_MARKS = frozenset({
    "h3f3a", "h3k27me3", "h3k36me3", "h3k4me1", "h3k79me2", "h3k79me3",
    "h3k9me1", "h3k9me2", "h3k9me3", "h4k20me1",
})


# ---------------------------------------------------------------------------
# Usable-read rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UsableReadRule:
    """
    Codifies what counts as a "usable" read/fragment for this experiment.

    ENCODE definition:
      uniquely_mapped AND non_duplicate AND pass_filters
    """
    layout: str   # "paired-end" | "single-end"

    @property
    def samtools_excl_flags(self) -> int:
        return (
            ENCODE_BAM_EXCL_FLAGS_PE if self.layout == "paired-end"
            else ENCODE_BAM_EXCL_FLAGS_SE
        )

    @property
    def samtools_req_flags(self) -> int | None:
        return ENCODE_BAM_REQ_FLAGS_PE if self.layout == "paired-end" else None

    @property
    def mapq_threshold(self) -> int:
        return ENCODE_MAPQ_MIN

    @property
    def exclude_contigs(self) -> frozenset[str]:
        return MITO_CONTIGS

    def samtools_view_args(self) -> list[str]:
        """Return the samtools view arguments that implement the usable-read filter."""
        args = ["-F", str(self.samtools_excl_flags), "-q", str(self.mapq_threshold)]
        if self.samtools_req_flags is not None:
            args += ["-f", str(self.samtools_req_flags)]
        return args

    def description(self) -> str:
        lines = [
            f"Usable read rule ({self.layout}):",
            f"  samtools -F {self.samtools_excl_flags}",
        ]
        if self.samtools_req_flags:
            lines.append(f"  samtools -f {self.samtools_req_flags}")
        lines.append(f"  MAPQ ≥ {self.mapq_threshold}")
        lines.append(f"  Exclude contigs (optional): {', '.join(sorted(self.exclude_contigs))}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Peak-mode helpers
# ---------------------------------------------------------------------------

def infer_peak_mode(mark: str | None) -> str:
    """Best-effort peak mode from an antibody/mark label.

    Broad histone marks → BROAD_MODE; everything else (TFs, sharp marks)
    → NARROW_MODE. Callers should let an explicit --peak-mode override this.
    """
    if not mark:
        return NARROW_MODE
    key = mark.strip().lower().replace("-", "").replace("_", "")
    return BROAD_MODE if key in BROAD_HISTONE_MARKS else NARROW_MODE


def _depth_key(peak_mode: str) -> str:
    return "usable_reads_broad" if peak_mode == BROAD_MODE else "usable_reads_tf"


# ---------------------------------------------------------------------------
# Downsampling depth calculation
# ---------------------------------------------------------------------------

@dataclass
class DownsampleConfig:
    """
    Result of compute_downsample_depth().

    Attributes
    ----------
    target_depth   : number of usable reads/fragments to keep per sample
    method         : "none" (no downsampling needed) | "picard" | "samtools"
    floor          : minimum acceptable depth; samples below this fail QC
    per_sample     : {sample_name → usable_read_count} (input counts)
    failing        : sample names with usable reads < floor
    seed           : random seed for reproducibility
    """
    target_depth:  int
    method:        str
    floor:         int
    per_sample:    dict[str, int]
    failing:       list[str]
    seed:          int = 42

    @property
    def needs_downsampling(self) -> bool:
        return self.method != "none"

    def downsample_fraction(self, sample_name: str) -> float:
        """Fraction (0 < f ≤ 1.0) for samtools view -s / Picard DownsampleSam."""
        count = self.per_sample.get(sample_name, 0)
        if count == 0:
            return 0.0
        frac = self.target_depth / count
        return min(1.0, round(frac, 6))


def compute_downsample_depth(
    usable_read_counts: dict[str, int],
    *,
    peak_mode: str = NARROW_MODE,
    floor: int | None = None,
    method: str = "auto",
    seed: int = 42,
) -> DownsampleConfig:
    """
    Determine the common downsampling depth for all ChIP samples.

    The depth is set to min(usable_reads) across all samples, then clamped to
    the floor.  If any sample falls below the floor it is recorded in
    `failing` — the caller decides whether to abort or warn.
    """
    if not usable_read_counts:
        raise ValueError("usable_read_counts is empty — no samples to process")

    if floor is None:
        floor = int(ENCODE_QC_THRESHOLDS[_depth_key(peak_mode)]["acceptable"])

    min_depth = min(usable_read_counts.values())
    target    = min_depth

    failing = [name for name, count in usable_read_counts.items() if count < floor]
    if failing:
        logger.warning(
            "Samples below the ENCODE ChIP usable-read floor (%d, %s mode): %s. "
            "Retained but flagged as failing QC; consider re-sequencing.",
            floor, peak_mode, failing,
        )

    if method == "auto":
        fracs = [target / c for c in usable_read_counts.values() if c > 0]
        method = "picard" if any(f < 0.90 for f in fracs) else "samtools"
    if min_depth == max(usable_read_counts.values()):
        method = "none"

    return DownsampleConfig(
        target_depth=target, method=method, floor=floor,
        per_sample=dict(usable_read_counts), failing=failing, seed=seed,
    )


# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------

def nrf_tier(nrf: float) -> str:
    t = ENCODE_QC_THRESHOLDS["nrf"]
    if nrf >= t["preferred"]:  return "preferred"
    if nrf >= t["acceptable"]: return "acceptable"
    return "fail"


def pbc1_tier(pbc1: float) -> str:
    t = ENCODE_QC_THRESHOLDS["pbc1"]
    if pbc1 >= t["preferred"]:  return "preferred"
    if pbc1 >= t["acceptable"]: return "acceptable"
    return "fail"


def pbc2_tier(pbc2: float) -> str:
    t = ENCODE_QC_THRESHOLDS["pbc2"]
    if pbc2 >= t["preferred"]:  return "preferred"
    if pbc2 >= t["acceptable"]: return "acceptable"
    return "fail"


def nsc_tier(nsc: float) -> str:
    t = ENCODE_QC_THRESHOLDS["nsc"]
    if nsc >= t["preferred"]:  return "preferred"
    if nsc >= t["acceptable"]: return "acceptable"
    return "fail"


def rsc_tier(rsc: float) -> str:
    t = ENCODE_QC_THRESHOLDS["rsc"]
    if rsc >= t["preferred"]:  return "preferred"
    if rsc >= t["acceptable"]: return "acceptable"
    return "fail"


def frip_tier(frip: float) -> str:
    """Report-only FRiP tier — ENCODE sets no hard ChIP cutoff."""
    t = ENCODE_QC_THRESHOLDS["frip"]
    if frip >= t["preferred"]:  return "preferred"
    if frip >= t["acceptable"]: return "acceptable"
    return "low"


def align_rate_tier(rate: float) -> str:
    t = ENCODE_QC_THRESHOLDS["align_rate"]
    if rate >= t["preferred"]:  return "preferred"
    if rate >= t["acceptable"]: return "acceptable"
    return "fail"


def depth_tier(n: int, *, peak_mode: str = NARROW_MODE) -> str:
    t = ENCODE_QC_THRESHOLDS[_depth_key(peak_mode)]
    if n >= t["preferred"]:  return "preferred"
    if n >= t["acceptable"]: return "acceptable"
    return "fail"


def worst_tier(*tiers: str) -> str:
    """Return the worst tier across a collection: fail > acceptable > preferred."""
    if "fail"       in tiers: return "fail"
    if "low"        in tiers: return "low"
    if "acceptable" in tiers: return "acceptable"
    return "preferred"


def assign_all_tiers(
    metrics: dict[str, float | int],
    *,
    peak_mode: str = NARROW_MODE,
) -> dict[str, str]:
    """
    Given a flat dict of QC metric values for one sample, return a dict of
    ENCODE ChIP tier assignments. Missing keys are silently skipped.
    """
    tiers: dict[str, str] = {}
    if "nrf"          in metrics: tiers["nrf_tier"]   = nrf_tier(metrics["nrf"])
    if "pbc1"         in metrics: tiers["pbc1_tier"]  = pbc1_tier(metrics["pbc1"])
    if "pbc2"         in metrics: tiers["pbc2_tier"]  = pbc2_tier(metrics["pbc2"])
    if "nsc"          in metrics: tiers["nsc_tier"]   = nsc_tier(metrics["nsc"])
    if "rsc"          in metrics: tiers["rsc_tier"]   = rsc_tier(metrics["rsc"])
    if "frip_score"   in metrics: tiers["frip_tier"]  = frip_tier(metrics["frip_score"])
    if "align_rate"   in metrics: tiers["align_tier"] = align_rate_tier(metrics["align_rate"])
    if "usable_reads" in metrics: tiers["depth_tier"] = depth_tier(int(metrics["usable_reads"]), peak_mode=peak_mode)
    return tiers

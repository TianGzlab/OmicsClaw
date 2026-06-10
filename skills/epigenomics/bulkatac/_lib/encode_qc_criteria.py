"""
encode_qc_criteria.py — ENCODE ATAC-seq QC thresholds, usable-read rules,
and downsampling depth calculation.

This module is the single source of truth for all numeric thresholds used
across every bulkatac skill.  Import it before touching any BAM or peak file.

Key concepts
------------
Usable reads (ENCODE definition)
  A read/fragment is "usable" if it passes ALL four filters:
    1. Uniquely mapped     (MAPQ ≥ 30, i.e. no multi-mappers)
    2. Non-duplicate       (Picard MarkDuplicates applied)
    3. Non-mitochondrial   (chrM / chrMT / MT excluded)
    4. Pass samtools flags (-F 1804  -f 2 for PE;  -F 1796 for SE)

Downsampling depth
  All samples are downsampled to the SAME number of usable reads/fragments
  before any downstream analysis (peak calling, QC, DA).
  The common depth is determined by:
    min_usable_reads = min(usable reads across all samples)
  clamped to a configurable floor (default: 10 M for PE, 20 M for SE).
  If any sample falls below the floor, it is flagged as failing QC and the
  user is warned. Downsampling uses picard DownsampleSam or samtools view -s.

References
----------
  ENCODE ATAC-seq standards: https://www.encodeproject.org/atac-seq/
  ENCODE pipeline spec (PDF): ATACSeqPipeline.pdf (BAM filter flags, PBC formulas)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ENCODE QC threshold table
# ---------------------------------------------------------------------------

ENCODE_QC_THRESHOLDS: dict[str, dict[str, float]] = {
    # ── Signal-to-noise ──────────────────────────────────────────────────────
    # Fraction of reads in peaks
    # ENCODE: >0.30 preferred, >0.20 acceptable
    "frip": {
        "preferred":  0.30,
        "acceptable": 0.20,
    },
    # TSS enrichment (hg38)
    # ENCODE: >7.0 preferred, >5.0 acceptable (cell lines), >3.0 (primary tissue)
    "tss_enrichment": {
        "preferred":          7.0,
        "acceptable":         5.0,
        "acceptable_tissue":  3.0,
    },
    # ── Library complexity ───────────────────────────────────────────────────
    # Non-Redundant Fraction  NRF = Distinct / Total
    "nrf": {
        "preferred":  0.90,
        "acceptable": 0.80,
    },
    # PCR Bottleneck Coefficient 1  PBC1 = OneReadPair / Distinct
    # Primary complexity measure.  Bottlenecking ladder:
    #   0.0–0.5  severe  |  0.5–0.8  moderate  |  0.8–0.9  mild  |  0.9–1.0  none
    "pbc1": {
        "preferred":     0.90,
        "acceptable":    0.50,
        "severe_cutoff": 0.50,
    },
    # PCR Bottleneck Coefficient 2  PBC2 = OneReadPair / TwoReadPair
    "pbc2": {
        "preferred":  3.0,
        "acceptable": 1.0,
    },
    # ── Read depth ───────────────────────────────────────────────────────────
    # Non-dup, non-mito, uniquely mapped fragments (paired-end)
    # ENCODE: ≥25 M preferred, ≥10 M acceptable
    "usable_fragments_pe": {
        "preferred":  25_000_000,
        "acceptable": 10_000_000,
    },
    # Single-end usable reads
    # ENCODE does not set SE-specific depth; community standard ~20 M
    "usable_reads_se": {
        "preferred":  20_000_000,
        "acceptable": 10_000_000,
    },
    # ── Alignment ────────────────────────────────────────────────────────────
    # ENCODE: >95% preferred, >80% acceptable
    "align_rate": {
        "preferred":  0.95,
        "acceptable": 0.80,
    },
    # ── Peak counts ──────────────────────────────────────────────────────────
    # Replicated peak set
    "n_peaks_replicated": {
        "preferred":  150_000,
        "acceptable": 100_000,
    },
    # IDR peak set (high-confidence)
    "n_peaks_idr": {
        "preferred":  70_000,
        "acceptable": 50_000,
    },
    # ── Mitochondrial reads ──────────────────────────────────────────────────
    # Community standard; ENCODE does not enforce a hard cutoff
    "pct_mito": {
        "preferred":  5.0,
        "acceptable": 20.0,
    },
    # ── Minimum read length (before trimming) ────────────────────────────────
    # ENCODE hard minimum: 45 bp
    "min_read_length_bp": {
        "preferred":  76.0,
        "acceptable": 45.0,
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

# ENCODE Tn5 adapter sequence
NEXTERA_ADAPTER = "CTGTCTCTTATACACATCT"

# ENCODE BAM filter flags
ENCODE_BAM_EXCL_FLAGS_PE = 1804   # unmapped, mate unmapped, not primary, QC-fail, dup
ENCODE_BAM_EXCL_FLAGS_SE = 1796   # same minus "mate unmapped" bit (bit 8)
ENCODE_BAM_REQ_FLAGS_PE  = 2      # properly paired (PE only)
ENCODE_MAPQ_MIN          = 30     # removes multi-mappers

# Mitochondrial contig names to exclude
MITO_CONTIGS = frozenset({"chrM", "chrMT", "MT", "M"})


# ---------------------------------------------------------------------------
# Usable-read rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UsableReadRule:
    """
    Codifies what counts as a "usable" read/fragment for this experiment.

    ENCODE definition:
      uniquely_mapped AND non_duplicate AND non_mitochondrial AND pass_filters
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
        lines.append(f"  Exclude contigs: {', '.join(sorted(self.exclude_contigs))}")
        return "\n".join(lines)


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
        """
        Return the fraction (0 < f ≤ 1.0) to pass to samtools view -s
        or Picard DownsampleSam for the given sample.
        """
        count = self.per_sample.get(sample_name, 0)
        if count == 0:
            return 0.0
        frac = self.target_depth / count
        return min(1.0, round(frac, 6))

    def summary(self) -> str:
        lines = [
            f"  Target depth    : {self.target_depth:,} usable reads/fragments",
            f"  Method          : {self.method}",
            f"  Floor           : {self.floor:,}",
            f"  Failing samples : {self.failing or 'none'}",
        ]
        for name, count in sorted(self.per_sample.items()):
            tier = _depth_tier(count, floor=self.floor)
            arrow = "→ downsample" if count > self.target_depth else "→ keep all"
            lines.append(f"    {name}: {count:,}  [{tier}]  {arrow}")
        return "\n".join(lines)


def compute_downsample_depth(
    usable_read_counts: dict[str, int],
    *,
    layout: str = "paired-end",
    floor: int | None = None,
    method: str = "auto",
    seed: int = 42,
) -> DownsampleConfig:
    """
    Determine the common downsampling depth for all samples.

    The depth is set to min(usable_reads) across all samples, then
    clamped to the floor.  If any sample falls below the floor it is
    recorded in `failing` — the caller decides whether to abort or warn.

    Parameters
    ----------
    usable_read_counts : {sample_name → n_usable_reads} (post-filter counts)
    layout             : "paired-end" | "single-end"
    floor              : minimum acceptable depth; if None, uses ENCODE acceptable
    method             : "auto" (pick based on fraction), "picard", "samtools", "none"
    seed               : random seed for reproducibility

    Returns
    -------
    DownsampleConfig
    """
    if not usable_read_counts:
        raise ValueError("usable_read_counts is empty — no samples to process")

    # Default floor from ENCODE thresholds
    if floor is None:
        key   = "usable_fragments_pe" if layout == "paired-end" else "usable_reads_se"
        floor = int(ENCODE_QC_THRESHOLDS[key]["acceptable"])

    min_depth = min(usable_read_counts.values())
    target    = min_depth   # downsample everything to the smallest library

    failing = [
        name for name, count in usable_read_counts.items()
        if count < floor
    ]

    if failing:
        logger.warning(
            "The following samples have fewer usable reads than the ENCODE floor "
            "(%d): %s.  They will be retained but flagged as failing QC.  "
            "Consider re-sequencing.",
            floor, failing,
        )

    # Pick method
    if method == "auto":
        # If any sample needs to retain < 90% of its reads, use picard
        # (more accurate for large fractions); otherwise samtools is fine
        fracs = [
            target / count for count in usable_read_counts.values() if count > 0
        ]
        method = "picard" if any(f < 0.90 for f in fracs) else "samtools"

    if min_depth == max(usable_read_counts.values()):
        # All samples have identical counts — no downsampling needed
        method = "none"

    config = DownsampleConfig(
        target_depth=target,
        method=method,
        floor=floor,
        per_sample=dict(usable_read_counts),
        failing=failing,
        seed=seed,
    )
    logger.info("Downsampling config:\n%s", config.summary())
    return config


# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------

def frip_tier(frip: float) -> str:
    t = ENCODE_QC_THRESHOLDS["frip"]
    if frip >= t["preferred"]:  return "preferred"
    if frip >= t["acceptable"]: return "acceptable"
    return "fail"


def pbc1_tier(pbc1: float) -> str:
    """
    PBC1 bottlenecking ladder:
      0.9–1.0  no bottlenecking       → preferred
      0.5–0.9  moderate / mild        → acceptable
      0.0–0.5  severe bottlenecking   → fail
    """
    t = ENCODE_QC_THRESHOLDS["pbc1"]
    if pbc1 >= t["preferred"]:  return "preferred"
    if pbc1 >= t["acceptable"]: return "acceptable"
    return "fail"


def nrf_tier(nrf: float) -> str:
    t = ENCODE_QC_THRESHOLDS["nrf"]
    if nrf >= t["preferred"]:  return "preferred"
    if nrf >= t["acceptable"]: return "acceptable"
    return "fail"


def tss_tier(tss: float, *, tissue_type: str = "cell_line") -> str:
    t = ENCODE_QC_THRESHOLDS["tss_enrichment"]
    if tss >= t["preferred"]: return "preferred"
    cutoff = t["acceptable_tissue"] if tissue_type == "tissue" else t["acceptable"]
    if tss >= cutoff: return "acceptable"
    return "fail"


def align_rate_tier(rate: float) -> str:
    t = ENCODE_QC_THRESHOLDS["align_rate"]
    if rate >= t["preferred"]:  return "preferred"
    if rate >= t["acceptable"]: return "acceptable"
    return "fail"


def depth_tier(n: int, *, layout: str = "paired-end") -> str:
    key = "usable_fragments_pe" if layout == "paired-end" else "usable_reads_se"
    t = ENCODE_QC_THRESHOLDS[key]
    if n >= t["preferred"]:  return "preferred"
    if n >= t["acceptable"]: return "acceptable"
    return "fail"


def pbc2_tier(pbc2: float) -> str:
    t = ENCODE_QC_THRESHOLDS["pbc2"]
    if pbc2 >= t["preferred"]:  return "preferred"
    if pbc2 >= t["acceptable"]: return "acceptable"
    return "fail"


def worst_tier(*tiers: str) -> str:
    """Return the worst tier across a collection: fail > acceptable > preferred."""
    if "fail"       in tiers: return "fail"
    if "acceptable" in tiers: return "acceptable"
    return "preferred"


def assign_all_tiers(
    metrics: dict[str, float | int],
    *,
    layout: str = "paired-end",
    tissue_type: str = "cell_line",
) -> dict[str, str]:
    """
    Given a flat dict of QC metric values for one sample,
    return a dict of ENCODE tier assignments.
    Missing keys are silently skipped.
    """
    tiers: dict[str, str] = {}
    if "frip_score"     in metrics: tiers["frip_tier"]   = frip_tier(metrics["frip_score"])
    if "tss_enrichment" in metrics: tiers["tss_tier"]    = tss_tier(metrics["tss_enrichment"], tissue_type=tissue_type)
    if "nrf"            in metrics: tiers["nrf_tier"]    = nrf_tier(metrics["nrf"])
    if "pbc1"           in metrics: tiers["pbc1_tier"]   = pbc1_tier(metrics["pbc1"])
    if "pbc2"           in metrics: tiers["pbc2_tier"]   = pbc2_tier(metrics["pbc2"])
    if "align_rate"     in metrics: tiers["align_tier"]  = align_rate_tier(metrics["align_rate"])
    if "usable_reads"   in metrics: tiers["depth_tier"]  = depth_tier(metrics["usable_reads"], layout=layout)
    return tiers


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _depth_tier(n: int, *, floor: int) -> str:
    if n >= floor * 2.5: return "preferred"
    if n >= floor:       return "acceptable"
    return "fail"
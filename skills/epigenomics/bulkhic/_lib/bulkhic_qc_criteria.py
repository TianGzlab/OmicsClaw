"""
bulkhic_qc_criteria.py — Hi-C library QC thresholds + tier helpers.

Mirrors the role of the bulk-ChIP/ATAC ``encode_qc_criteria`` module: a single
source of truth for the QC numbers surfaced in reports and ``result.json``.
The metrics here are the standard pairtools / 4DN Hi-C library-quality
statistics (computed by ``pairtools stats`` on the deduplicated ``.pairs``):

  * **valid-pair fraction**   — uniquely-mapped, deduplicated pairs as a
    fraction of total read pairs. Low values flag mapping / ligation problems.
  * **duplicate fraction**    — PCR duplicates among mapped pairs. High values
    flag low library complexity (over-amplification / under-sequencing).
  * **cis fraction**          — intra-chromosomal pairs / (cis + trans).
    Random ligation noise inflates trans, so a high cis fraction is good.
  * **cis/trans ratio**       — cis / trans; a coarse signal-to-noise proxy.
  * **cis-long fraction**     — cis pairs separated by >20 kb as a fraction of
    all cis pairs. The single most informative Hi-C complexity metric: genuine
    chromatin contacts are long-range, whereas dangling-ends / self-circles /
    re-ligation pile up at short range.

These are *guidance tiers*, not hard gates — Hi-C quality is depth- and
protocol-dependent (DpnII vs Micro-C, read depth, organism). They follow the
4DN data-portal QC conventions and the pairtools documentation.
"""

from __future__ import annotations

# Reference thresholds (preferred / acceptable). Surfaced verbatim in reports.
HIC_QC_THRESHOLDS: dict[str, dict[str, float]] = {
    "valid_pair_fraction": {"preferred": 0.70, "acceptable": 0.50},
    "duplicate_fraction":  {"preferred": 0.15, "acceptable": 0.30},   # lower is better
    "cis_fraction":        {"preferred": 0.55, "acceptable": 0.40},
    "cis_trans_ratio":     {"preferred": 3.0,  "acceptable": 1.0},
    "cis_long_fraction":   {"preferred": 0.40, "acceptable": 0.20},
}

# Distance (bp) above which a cis contact counts as "long-range" for the
# cis-long complexity metric (4DN/pairtools convention).
CIS_LONG_DISTANCE_BP = 20_000


def _tier(value: float, preferred: float, acceptable: float, *, higher_is_better: bool = True) -> str:
    """Return 'preferred' | 'acceptable' | 'low' for a metric value."""
    if higher_is_better:
        if value >= preferred:
            return "preferred"
        if value >= acceptable:
            return "acceptable"
        return "low"
    # lower-is-better (duplicate fraction)
    if value <= preferred:
        return "preferred"
    if value <= acceptable:
        return "acceptable"
    return "high"


def valid_pair_tier(fraction: float) -> str:
    t = HIC_QC_THRESHOLDS["valid_pair_fraction"]
    return _tier(fraction, t["preferred"], t["acceptable"])


def duplicate_tier(fraction: float) -> str:
    t = HIC_QC_THRESHOLDS["duplicate_fraction"]
    return _tier(fraction, t["preferred"], t["acceptable"], higher_is_better=False)


def cis_fraction_tier(fraction: float) -> str:
    t = HIC_QC_THRESHOLDS["cis_fraction"]
    return _tier(fraction, t["preferred"], t["acceptable"])


def cis_trans_ratio_tier(ratio: float) -> str:
    t = HIC_QC_THRESHOLDS["cis_trans_ratio"]
    return _tier(ratio, t["preferred"], t["acceptable"])


def cis_long_tier(fraction: float) -> str:
    t = HIC_QC_THRESHOLDS["cis_long_fraction"]
    return _tier(fraction, t["preferred"], t["acceptable"])


def thresholds_markdown() -> list[str]:
    """Return the QC-threshold table as markdown lines (for reports)."""
    return [
        "| Metric | Preferred | Acceptable |",
        "|---|---|---|",
        "| Valid-pair fraction      | > 0.70 | > 0.50 |",
        "| Duplicate fraction       | < 0.15 | < 0.30 |",
        "| Cis fraction             | > 0.55 | > 0.40 |",
        "| Cis/trans ratio          | > 3.0  | > 1.0  |",
        f"| Cis-long (>{CIS_LONG_DISTANCE_BP // 1000} kb) fraction | > 0.40 | > 0.20 |",
    ]

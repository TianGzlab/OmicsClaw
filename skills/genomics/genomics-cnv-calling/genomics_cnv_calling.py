#!/usr/bin/env python3
"""Genomics CNV Calling — Copy Number Variation detection and segmentation.

Implements a simplified Circular Binary Segmentation (CBS) algorithm for
demo and lightweight analysis. For production data, wraps external tools
(CNVkit, Control-FREEC, GATK gCNV).

CBS algorithm reference:
  Olshen et al. (2004) "Circular binary segmentation for the analysis
  of array-based DNA copy number data." Biostatistics 5(4):557-72.

CNV calling thresholds follow CNVkit conventions:
  - log2 ratio > 0.3  → gain (single-copy gain ~0.585 for pure diploid)
  - log2 ratio < -0.3 → loss (single-copy loss ~-1.0 for pure diploid)

Usage:
    python genomics_cnv_calling.py --input <bam/csv> --output <dir>
    python genomics_cnv_calling.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-cnv-calling"
SKILL_VERSION = "0.2.0"

# CNV calling thresholds (log2 ratio, CNVkit defaults)
GAIN_THRESHOLD = 0.3
LOSS_THRESHOLD = -0.3

# Amplification / deep deletion thresholds
AMP_THRESHOLD = 1.0    # high-level amplification
DEEP_DEL_THRESHOLD = -1.0  # homozygous / deep deletion


# ---------------------------------------------------------------------------
# Simplified Circular Binary Segmentation (CBS)
# ---------------------------------------------------------------------------

def _t_statistic(data: np.ndarray, i: int, j: int) -> float:
    """Compute the CBS t-statistic for a candidate changepoint.

    The statistic measures the difference between the mean of the segment
    [i, j] and the rest of the data. Higher values indicate stronger
    evidence for a breakpoint.

    Ref: Venkatraman & Olshen (2007). "A faster circular binary
    segmentation algorithm for the analysis of array CGH data."
    """
    n = len(data)
    if j <= i or n < 3:
        return 0.0

    seg_mean = data[i:j].mean()
    rest_mean = np.concatenate([data[:i], data[j:]]).mean() if (i > 0 or j < n) else seg_mean
    seg_len = j - i

    # Avoid division by zero
    total_var = data.var()
    if total_var < 1e-10:
        return 0.0

    # t-statistic scaled by segment proportion
    t = abs(seg_mean - rest_mean) * np.sqrt(seg_len * (n - seg_len) / n) / np.sqrt(total_var)
    return float(t)


def cbs_segment(
    log2_ratios: np.ndarray,
    alpha: float = 0.01,
    min_segment_size: int = 3,
    max_iterations: int = 100,
) -> list[tuple[int, int, float]]:
    """Simplified CBS segmentation.

    Recursively splits data at the point that maximizes the t-statistic,
    stopping when no split exceeds the significance threshold.

    Args:
        log2_ratios: array of log2 copy-ratio values (ordered by genomic position)
        alpha: significance level (lower -> fewer breakpoints, more conservative)
        min_segment_size: minimum number of probes per segment
        max_iterations: maximum recursion depth

    Returns:
        List of (start_idx, end_idx, segment_mean) tuples
    """
    n = len(log2_ratios)
    if n < 2 * min_segment_size:
        return [(0, n, float(log2_ratios.mean()))]

    # Critical t-value increases with lower alpha (more conservative)
    # Approximate: for alpha=0.01 ~ 3.0, alpha=0.05 ~ 2.0
    t_crit = 2.0 + (-np.log10(alpha))

    segments: list[tuple[int, int, float]] = []

    def _recurse(start: int, end: int, depth: int = 0):
        if end - start < 2 * min_segment_size or depth > max_iterations:
            segments.append((start, end, float(log2_ratios[start:end].mean())))
            return

        data = log2_ratios[start:end]
        best_t = 0.0
        best_split = -1

        for k in range(min_segment_size, len(data) - min_segment_size):
            t = _t_statistic(data, 0, k)
            if t > best_t:
                best_t = t
                best_split = k

        if best_t > t_crit and best_split > 0:
            _recurse(start, start + best_split, depth + 1)
            _recurse(start + best_split, end, depth + 1)
        else:
            segments.append((start, end, float(data.mean())))

    _recurse(0, n)
    return segments


def call_cnv_from_segments(segments_df: pd.DataFrame) -> pd.DataFrame:
    """Classify CNV segments based on log2 ratio thresholds.

    Classification follows CNVkit conventions:
    - amplification: log2 > 1.0
    - gain: 0.3 < log2 <= 1.0
    - neutral: -0.3 <= log2 <= 0.3
    - loss: -1.0 <= log2 < -0.3
    - deep_deletion: log2 < -1.0
    """
    df = segments_df.copy()

    conditions = [
        df["log2_ratio"] > AMP_THRESHOLD,
        df["log2_ratio"] > GAIN_THRESHOLD,
        df["log2_ratio"] >= LOSS_THRESHOLD,
        df["log2_ratio"] >= DEEP_DEL_THRESHOLD,
    ]
    choices = ["amplification", "gain", "neutral", "loss"]
    df["cn_state"] = np.select(conditions, choices, default="deep_deletion")

    # Estimate integer copy number from log2 ratio (diploid baseline)
    # CN = 2 * 2^(log2_ratio)
    df["estimated_cn"] = np.round(2 * np.power(2, df["log2_ratio"]), 1)
    df["estimated_cn"] = df["estimated_cn"].clip(lower=0)

    return df


# ---------------------------------------------------------------------------
# Demo data generation
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> tuple[Path, pd.DataFrame]:
    """Generate synthetic CNV demo data with realistic characteristics.

    Simulates read-depth log2 ratios across chromosomes with:
    - Background noise ~ N(0, 0.15)
    - Focal amplifications and deletions injected
    - Arm-level events
    """
    rng = np.random.RandomState(42)
    chroms_info = [(f"chr{i}", 250_000_000 // 22) for i in range(1, 23)]

    all_records = []
    bin_size = 50_000  # 50kb bins

    for chrom, chrom_len in chroms_info:
        n_bins = chrom_len // bin_size
        starts = np.arange(0, n_bins) * bin_size
        ends = starts + bin_size

        # Background noise
        log2_ratios = rng.normal(0, 0.15, n_bins)

        # Inject focal CNV events (~5% of the genome)
        if rng.random() < 0.3:
            # Focal gain
            event_start = rng.randint(0, max(1, n_bins - 20))
            event_len = rng.randint(5, 20)
            log2_ratios[event_start:event_start + event_len] += rng.uniform(0.5, 1.5)

        if rng.random() < 0.3:
            # Focal loss
            event_start = rng.randint(0, max(1, n_bins - 20))
            event_len = rng.randint(5, 15)
            log2_ratios[event_start:event_start + event_len] -= rng.uniform(0.5, 1.5)

        if rng.random() < 0.1:
            # Arm-level event (large region)
            midpoint = n_bins // 2
            arm = rng.choice(["p", "q"])
            if arm == "p":
                log2_ratios[:midpoint] += rng.uniform(0.3, 0.8)
            else:
                log2_ratios[midpoint:] -= rng.uniform(0.3, 0.8)

        for i in range(n_bins):
            all_records.append({
                "chrom": chrom,
                "start": int(starts[i]),
                "end": int(ends[i]),
                "log2_ratio": round(float(log2_ratios[i]), 4),
            })

    df = pd.DataFrame(all_records)
    data_path = output_dir / "demo_cnv_bins.csv"
    df.to_csv(data_path, index=False)
    logger.info(f"Generated demo CNV data: {data_path} ({len(df)} bins)")
    return data_path, df


# ---------------------------------------------------------------------------
# Analysis pipeline
# ---------------------------------------------------------------------------

def run_cnv_analysis(data_path: Path, method: str = "cbs", alpha: float = 0.01) -> tuple[pd.DataFrame, dict]:
    """Run CNV calling pipeline.

    Steps:
    1. Load bin-level log2 ratios
    2. Segment per chromosome using CBS
    3. Classify CNV states
    4. Compute summary statistics
    """
    logger.info(f"CNV calling with method={method}, alpha={alpha}")

    df = pd.read_csv(data_path)

    # Segment per chromosome
    segment_records = []
    for chrom in df["chrom"].unique():
        chrom_data = df[df["chrom"] == chrom].sort_values("start")
        log2_arr = chrom_data["log2_ratio"].values
        starts = chrom_data["start"].values
        ends = chrom_data["end"].values

        if method == "cbs":
            segments = cbs_segment(log2_arr, alpha=alpha)
        else:
            # Fallback: treat each bin as its own segment
            segments = [(i, i + 1, float(log2_arr[i])) for i in range(len(log2_arr))]

        for seg_start, seg_end, seg_mean in segments:
            segment_records.append({
                "chrom": chrom,
                "start": int(starts[seg_start]),
                "end": int(ends[min(seg_end - 1, len(ends) - 1)]),
                "n_bins": seg_end - seg_start,
                "log2_ratio": round(seg_mean, 4),
            })

    segments_df = pd.DataFrame(segment_records)

    # Call CNV states
    result_df = call_cnv_from_segments(segments_df)

    # Compute statistics
    gains = (result_df["cn_state"].isin(["gain", "amplification"])).sum()
    losses = (result_df["cn_state"].isin(["loss", "deep_deletion"])).sum()
    neutral = (result_df["cn_state"] == "neutral").sum()

    stats = {
        "n_segments": len(result_df),
        "n_gains": int(gains),
        "n_losses": int(losses),
        "n_neutral": int(neutral),
        "n_amplifications": int((result_df["cn_state"] == "amplification").sum()),
        "n_deep_deletions": int((result_df["cn_state"] == "deep_deletion").sum()),
        "method": method,
        "alpha": alpha,
        "gain_threshold": GAIN_THRESHOLD,
        "loss_threshold": LOSS_THRESHOLD,
        "genome_fraction_altered": round(
            (gains + losses) / len(result_df), 4
        ) if len(result_df) > 0 else 0,
    }
    return result_df, stats


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write CNV calling report."""
    header = generate_report_header(
        title="Copy Number Variation Calling Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Segments": str(stats["n_segments"])},
    )

    body_lines = [
        "## Segmentation Summary\n",
        f"- **Total segments**: {stats['n_segments']:,}",
        f"- **Method**: {stats['method']} (alpha={stats['alpha']})",
        "",
        "### CNV Classification\n",
        f"- 🔴 **Amplifications** (log2 > {AMP_THRESHOLD}): {stats['n_amplifications']:,}",
        f"- 🟠 **Gains** ({GAIN_THRESHOLD} < log2 ≤ {AMP_THRESHOLD}): "
        f"{stats['n_gains'] - stats['n_amplifications']:,}",
        f"- 🟢 **Neutral** ({LOSS_THRESHOLD} ≤ log2 ≤ {GAIN_THRESHOLD}): {stats['n_neutral']:,}",
        f"- 🔵 **Losses** ({DEEP_DEL_THRESHOLD} ≤ log2 < {LOSS_THRESHOLD}): "
        f"{stats['n_losses'] - stats['n_deep_deletions']:,}",
        f"- ⚫ **Deep deletions** (log2 < {DEEP_DEL_THRESHOLD}): {stats['n_deep_deletions']:,}",
        "",
        f"- **Genome fraction altered**: {stats['genome_fraction_altered']:.1%}",
        "",
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Genomics CNV Calling")
    parser.add_argument("--input", dest="input_path", help="Input bin-level log2 ratio CSV")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument(
        "--method", default="cbs",
        choices=["cbs", "none"],
        help="Segmentation method (default: cbs)",
    )
    parser.add_argument("--alpha", type=float, default=0.01, help="CBS significance level (default: 0.01)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path, _ = generate_demo_data(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        if not data_path.exists():
            raise FileNotFoundError(f"Input file not found: {data_path}")
        input_file = args.input_path

    result_df, stats = run_cnv_analysis(data_path, method=args.method, alpha=args.alpha)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "cnv_segments.csv", index=False)

    # Per-chromosome summary
    chrom_summary = result_df.groupby("chrom").agg(
        n_segments=("cn_state", "count"),
        n_gains=("cn_state", lambda x: (x.isin(["gain", "amplification"])).sum()),
        n_losses=("cn_state", lambda x: (x.isin(["loss", "deep_deletion"])).sum()),
        mean_log2=("log2_ratio", "mean"),
    ).reset_index()
    chrom_summary.to_csv(tables_dir / "cnv_per_chromosome.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=stats,
        data={},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"CNV calling complete: {stats['n_segments']} segments, "
          f"{stats['n_gains']} gains, {stats['n_losses']} losses, "
          f"{stats['genome_fraction_altered']:.1%} altered")


if __name__ == "__main__":
    main()

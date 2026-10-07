#!/usr/bin/env python3
"""Genomics cnv-calling: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-cnv-calling"
SKILL_VERSION = "0.5.0"

# CNV calling thresholds (log2 ratio, CNVkit defaults)
GAIN_THRESHOLD = 0.3
LOSS_THRESHOLD = -0.3

# Amplification / deep deletion thresholds
AMP_THRESHOLD = 1.0    # high-level amplification
DEEP_DEL_THRESHOLD = -1.0  # homozygous / deep deletion


# ---------------------------------------------------------------------------
# Simplified Circular Binary Segmentation (CBS)


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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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

    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    result_df = api.analyze(api.read_bins(data_path), method=args.method, alpha=args.alpha)
    stats = api.run_info(result_df, keep=False)["summary"]

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

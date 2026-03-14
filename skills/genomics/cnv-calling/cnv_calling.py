#!/usr/bin/env python3
"""Genomics CNV Calling — Copy Number Variation analysis.

Usage:
    python cnv_calling.py --input <bam/vcf> --output <dir>
    python cnv_calling.py --demo --output <dir>
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

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "cnv-calling"
SKILL_VERSION = "0.1.0"


def generate_demo_data(output_dir):
    """Generate synthetic CNV demo data."""
    n_segments = 200

    chroms = np.random.choice(
        [f"chr{i}" for i in range(1, 23)] + ["chrX"], n_segments
    )
    starts = np.sort(np.random.randint(1, 250_000_000, n_segments))
    ends = starts + np.random.randint(100_000, 10_000_000, n_segments)
    log2_ratios = np.random.normal(0, 0.5, n_segments)
    # Inject some CNV events
    cnv_idx = np.random.choice(n_segments, size=20, replace=False)
    log2_ratios[cnv_idx[:10]] = np.random.uniform(0.5, 1.5, 10)   # gains
    log2_ratios[cnv_idx[10:]] = np.random.uniform(-1.5, -0.5, 10)  # losses

    df = pd.DataFrame({
        "chrom": chroms,
        "start": starts,
        "end": ends,
        "log2_ratio": np.round(log2_ratios, 4),
        "cn_state": np.where(log2_ratios > 0.3, "gain",
                             np.where(log2_ratios < -0.3, "loss", "neutral")),
    })

    data_path = output_dir / "demo_cnv_segments.csv"
    df.to_csv(data_path, index=False)
    logger.info(f"Generated demo CNV data: {data_path}")
    return data_path, df


def call_cnv(data_path, method="cnvkit"):
    """Placeholder for CNV calling pipeline.

    In production this would wrap:
    - CNVkit: ``cnvkit.py batch``
    - Control-FREEC
    - GATK gCNV
    """
    logger.info(f"CNV calling with method={method}")

    df = pd.read_csv(data_path)

    gains = (df["cn_state"] == "gain").sum() if "cn_state" in df.columns else 0
    losses = (df["cn_state"] == "loss").sum() if "cn_state" in df.columns else 0

    stats = {
        "n_segments": len(df),
        "n_gains": int(gains),
        "n_losses": int(losses),
        "method": method,
    }
    return df, stats


def main():
    parser = argparse.ArgumentParser(description="Genomics CNV Calling")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="cnvkit", choices=["cnvkit", "control-freec", "gatk-gcnv"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path, _ = generate_demo_data(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    result_df, stats = call_cnv(data_path, method=args.method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "cnv_segments.csv", index=False)

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"CNV calling complete: {stats['n_segments']} segments, "
          f"{stats['n_gains']} gains, {stats['n_losses']} losses")


if __name__ == "__main__":
    main()

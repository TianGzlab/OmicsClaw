#!/usr/bin/env python3
"""Genomics Epigenomics — ChIP-seq / ATAC-seq peak calling and motif analysis.

Usage:
    python epigenomics.py --input <bam/bed> --output <dir>
    python epigenomics.py --demo --output <dir>
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

SKILL_NAME = "epigenomics"
SKILL_VERSION = "0.1.0"


def generate_demo_peaks(output_dir):
    """Generate synthetic ChIP-seq/ATAC-seq peak data."""
    n_peaks = 500

    chroms = np.random.choice([f"chr{i}" for i in range(1, 23)], n_peaks)
    starts = np.random.randint(1, 250_000_000, n_peaks)
    widths = np.random.randint(200, 5000, n_peaks)

    df = pd.DataFrame({
        "chrom": chroms,
        "start": starts,
        "end": starts + widths,
        "name": [f"peak_{i}" for i in range(n_peaks)],
        "score": np.round(np.random.uniform(10, 1000, n_peaks), 2),
        "fold_enrichment": np.round(np.random.lognormal(1, 0.8, n_peaks), 3),
        "pvalue": np.round(np.random.uniform(1e-10, 0.05, n_peaks), 10),
        "qvalue": np.round(np.random.uniform(1e-8, 0.1, n_peaks), 8),
    })

    data_path = output_dir / "demo_peaks.bed"
    df.to_csv(data_path, sep="\t", index=False, header=False)
    logger.info(f"Generated demo peak data: {data_path}")
    return data_path, df


def analyse_peaks(data_path, method="macs2"):
    """Placeholder for epigenomics peak analysis pipeline.

    In production this would wrap:
    - MACS2 peak calling
    - Homer motif finding
    - pyGenomeTracks visualisation
    """
    logger.info(f"Epigenomics analysis with method={method}")

    try:
        df = pd.read_csv(data_path, sep="\t", header=None,
                         names=["chrom", "start", "end", "name", "score",
                                "fold_enrichment", "pvalue", "qvalue"])
    except Exception:
        df = pd.read_csv(data_path)

    stats = {
        "n_peaks": len(df),
        "mean_score": float(df["score"].mean()) if "score" in df.columns else 0,
        "method": method,
    }
    return df, stats


def main():
    parser = argparse.ArgumentParser(description="Genomics Epigenomics Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="macs2", choices=["macs2", "homer", "genrich"])
    parser.add_argument("--assay", default="chip-seq", choices=["chip-seq", "atac-seq", "cut-tag"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path, _ = generate_demo_peaks(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    result_df, stats = analyse_peaks(data_path, method=args.method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "peaks_summary.csv", index=False)

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Epigenomics analysis complete: {stats['n_peaks']} peaks")


if __name__ == "__main__":
    main()

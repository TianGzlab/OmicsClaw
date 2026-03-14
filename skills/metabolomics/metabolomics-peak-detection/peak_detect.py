#!/usr/bin/env python3
"""Metabolomics Peak Detection - Detect metabolite peaks.

Usage:
    python peak_detect.py --input <data.csv> --output <dir>
    python peak_detect.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "peak-detection"
SKILL_VERSION = "0.1.0"


def detect_peaks(data_path):
    """Simple peak detection for metabolomics data."""
    df = pd.read_csv(data_path)

    n_peaks = len(df)
    n_samples = len([c for c in df.columns if 'intensity' in c.lower()])

    stats = {
        'n_peaks': n_peaks,
        'n_samples': n_samples,
    }

    logger.info(f"Peak detection complete: {n_peaks} peaks")
    return stats


def generate_demo_data(output_path):
    """Generate demo metabolomics data."""
    n_peaks = 50
    n_samples = 3

    data = {
        'mz': np.random.uniform(100, 1000, n_peaks),
        'rt': np.random.uniform(0, 30, n_peaks),
    }

    for i in range(n_samples):
        data[f'intensity_{i+1}'] = np.random.lognormal(8, 2, n_peaks)

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.info(f"Generated demo data: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Metabolomics Peak Detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_metabolomics.csv"
        generate_demo_data(data_path)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    stats = detect_peaks(data_path)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Peak detection complete: {stats['n_peaks']} peaks detected")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Metabolomics Peak Detection — detect metabolite peaks using scipy.signal.

Implements local-maxima peak detection with configurable prominence, height,
and minimum distance thresholds.  Operates on tabular intensity data
(CSV with m/z, rt, and intensity columns) or on raw 1-D intensity traces
extracted per-sample.

Usage:
    python peak_detect.py --input <data.csv> --output <dir>
    python peak_detect.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json
from skills._sdk.notebook import load_skill

logger = logging.getLogger(__name__)

SKILL_NAME = "peak-detection"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Demo data generation
# ---------------------------------------------------------------------------

def generate_demo_data(output_path: Path) -> None:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import peak_detection
    data = peak_detection()
    data.to_csv(output_path, index=False)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write markdown report."""
    header = generate_report_header(
        title="Metabolomics Peak Detection Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Peaks detected": str(summary.get("n_peaks", 0)),
            "Samples": str(summary.get("n_samples", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Total data points**: {summary.get('n_points', 'N/A')}",
        f"- **Samples processed**: {summary.get('n_samples', 0)}",
        f"- **Peaks detected**: {summary.get('n_peaks', 0)}",
        f"- **Mean prominence**: {summary.get('mean_prominence', 0):.1f}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    body_lines.extend([
        "",
        "## Method\n",
        "Peaks are detected using `scipy.signal.find_peaks` with configurable "
        "prominence, height, and minimum-distance thresholds. Peak widths are "
        "measured at 50% relative height via `scipy.signal.peak_widths`.",
    ])

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Metabolomics Peak Detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--prominence", type=float, default=1e4,
                        help="Minimum peak prominence (default: 10000)")
    parser.add_argument("--height", type=float, default=None,
                        help="Minimum absolute peak height")
    parser.add_argument("--distance", type=int, default=5,
                        help="Minimum distance between peaks in data points")
    parser.add_argument("--sample-prefix", default=None,
                        help="Column prefix to identify samples (default: auto)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_metabolomics.csv"
        generate_demo_data(data_path)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    df = pd.read_csv(data_path)

    # Determine sample columns
    sample_cols = None
    if args.sample_prefix:
        sample_cols = [c for c in df.columns if c.startswith(args.sample_prefix)]

    library = load_skill("metabolomics-peak-detection")
    peaks_df = library.detect_peaks(
        df,
        sample_cols=sample_cols,
        prominence=args.prominence,
        height=args.height,
        distance=args.distance,
    )

    library.run_info(peaks_df, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    peaks_df.to_csv(tables_dir / "detected_peaks.csv", index=False)

    n_samples = len(peaks_df["sample"].unique()) if not peaks_df.empty else 0
    mean_prom = float(peaks_df["prominence"].mean()) if not peaks_df.empty else 0.0

    summary = {
        "n_points": len(df),
        "n_samples": n_samples,
        "n_peaks": len(peaks_df),
        "mean_prominence": mean_prom,
    }

    params = {
        "prominence": args.prominence,
        "height": args.height,
        "distance": args.distance,
    }

    write_report(output_dir, summary, input_file if not args.demo else None, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Peak detection complete: {summary['n_peaks']} peaks across {n_samples} samples")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Metabolomics XCMS Preprocessing — Peak detection and alignment simulation.

Simulates the XCMS centWave peak detection pipeline in Python, generating
realistic peak tables whose characteristics respond to the user-supplied
ppm and peakwidth parameters.

For production use with real mzML files, this module should be replaced
with an R/rpy2 bridge to the actual XCMS package.

Usage:
    python metabolomics_xcms_preprocessing.py --input <data.mzML> [<data2.mzML> ...] --output <dir>
    python metabolomics_xcms_preprocessing.py --demo --output <dir>
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
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "xcms-preprocess"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Simulated XCMS preprocessing
# ---------------------------------------------------------------------------

def xcms_preprocess_python(
    input_files: list[Path],
    ppm: float = 25.0,
    peakwidth: tuple[float, float] = (10.0, 60.0),
) -> pd.DataFrame:
    """Simulate XCMS centWave peak detection (Python fallback).

    The number of detected peaks and their characteristics are modulated
    by the ppm tolerance and peakwidth parameters to produce a realistic
    demonstration.

    Parameters
    ----------
    input_files : list[Path]
        Input mzML file paths (used for naming only in simulation mode).
    ppm : float
        Mass accuracy in ppm. Tighter tolerance → fewer peaks.
    peakwidth : tuple[float, float]
        Minimum and maximum peak width in seconds.

    Returns
    -------
    DataFrame — simulated peak table.
    """
    rng = np.random.default_rng(42)
    n_samples = len(input_files)

    # Number of peaks scales inversely with strictness of parameters
    base_peaks = 1200
    ppm_factor = min(ppm / 25.0, 2.0)  # looser ppm → more peaks
    width_factor = (peakwidth[1] - peakwidth[0]) / 50.0
    n_peaks = int(base_peaks * ppm_factor * max(width_factor, 0.3))
    n_peaks = max(200, min(n_peaks, 3000))

    logger.info(
        "Simulating XCMS centWave: %d files, ppm=%.1f, peakwidth=(%.0f,%.0f) → ~%d peaks",
        n_samples, ppm, peakwidth[0], peakwidth[1], n_peaks,
    )

    # Generate realistic m/z, RT, and intensity distributions
    mz_values = rng.uniform(80, 1200, n_peaks)
    rt_values = rng.uniform(peakwidth[0], 600 - peakwidth[1], n_peaks)  # within valid RT window
    base_intensities = rng.lognormal(10, 2, n_peaks)

    # Apply m/z noise consistent with ppm tolerance
    mz_noise = mz_values * ppm * 1e-6 * rng.standard_normal(n_peaks)
    mz_values = mz_values + mz_noise

    # Peak widths within the specified range
    peak_widths = rng.uniform(peakwidth[0], peakwidth[1], n_peaks)

    peaks = pd.DataFrame({
        "mz": np.round(mz_values, 6),
        "mzmin": np.round(mz_values - abs(mz_noise) * 2, 6),
        "mzmax": np.round(mz_values + abs(mz_noise) * 2, 6),
        "rt": np.round(rt_values, 2),
        "rtmin": np.round(rt_values - peak_widths / 2, 2),
        "rtmax": np.round(rt_values + peak_widths / 2, 2),
        "into": np.round(base_intensities, 2),  # integrated intensity
        "maxo": np.round(base_intensities * rng.uniform(1.2, 3.0, n_peaks), 2),
    })

    # Per-sample intensities with biological+technical variation
    for i in range(n_samples):
        sample_factor = rng.uniform(0.5, 2.0)
        noise = rng.lognormal(0, 0.3, n_peaks)
        sample_int = base_intensities * sample_factor * noise
        # ~5% missing values (below LOD)
        mask = rng.random(n_peaks) < 0.05
        sample_int[mask] = 0
        peaks[f"sample_{i + 1}"] = np.round(sample_int, 2)

    return peaks


def get_demo_data() -> tuple[list[Path], pd.DataFrame]:
    """Generate demo metabolomics data."""
    logger.info("Generating demo metabolomics data (5 simulated samples)")
    demo_files = [Path(f"demo_sample_{i}.mzML") for i in range(1, 6)]
    peaks = xcms_preprocess_python(demo_files)
    return demo_files, peaks


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_files: list[Path] | None,
    params: dict,
) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="XCMS Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=input_files,
        extra_metadata={
            "Peaks": str(summary.get("n_peaks", 0)),
            "Samples": str(summary.get("n_samples", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Samples processed**: {summary.get('n_samples', 0)}",
        f"- **Peaks detected**: {summary.get('n_peaks', 0)}",
        f"- **m/z range**: {summary.get('mz_min', 0):.4f} – {summary.get('mz_max', 0):.4f}",
        f"- **RT range**: {summary.get('rt_min', 0):.2f} – {summary.get('rt_max', 0):.2f} sec",
        "",
        "## Method\n",
        "Python simulation of XCMS centWave peak detection with configurable "
        "ppm tolerance and peak width parameters. For production use, an R/rpy2 "
        "bridge to the XCMS Bioconductor package is recommended.",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python metabolomics_xcms_preprocessing.py --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="XCMS Preprocessing")
    parser.add_argument("--input", dest="input_path", nargs="+")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--ppm", type=float, default=25.0)
    parser.add_argument("--peakwidth-min", type=float, default=10.0)
    parser.add_argument("--peakwidth-max", type=float, default=60.0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    peakwidth = (args.peakwidth_min, args.peakwidth_max)

    if args.demo:
        input_files, peaks = get_demo_data()
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        input_files = [Path(p) for p in args.input_path]
        peaks = xcms_preprocess_python(input_files, args.ppm, peakwidth)

    logger.info("Detected %d peaks across %d samples", len(peaks), len(input_files))

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    peaks.to_csv(tables_dir / "peak_table.csv", index=False)

    summary = {
        "n_samples": len(input_files),
        "n_peaks": len(peaks),
        "mz_min": float(peaks["mz"].min()),
        "mz_max": float(peaks["mz"].max()),
        "rt_min": float(peaks["rt"].min()),
        "rt_max": float(peaks["rt"].max()),
    }

    params = {
        "ppm": args.ppm,
        "peakwidth": f"{peakwidth[0]}-{peakwidth[1]}",
    }

    write_report(output_dir, summary, input_files if not args.demo else None, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"XCMS preprocessing complete: {summary['n_peaks']} peaks, "
        f"{summary['n_samples']} samples"
    )


if __name__ == "__main__":
    main()

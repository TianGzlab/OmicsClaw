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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "peak-detection"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def detect_peaks(
    intensities: np.ndarray,
    *,
    prominence: float = 1e4,
    height: float | None = None,
    distance: int = 5,
    rel_height: float = 0.5,
) -> dict:
    """Detect peaks in a 1-D intensity array using scipy.signal.find_peaks.

    Parameters
    ----------
    intensities : 1-D array-like
        Signal intensity values sorted by retention time.
    prominence : float
        Minimum prominence a peak must have to be detected.
    height : float or None
        Minimum absolute intensity for a peak.
    distance : int
        Minimum number of data points between neighbouring peaks.
    rel_height : float
        Relative height at which the peak width is measured (0–1).

    Returns
    -------
    dict with keys *peak_indices*, *properties* (from scipy), *n_peaks*.
    """
    intensities = np.asarray(intensities, dtype=float)
    peak_kwargs: dict = {"prominence": prominence, "distance": distance}
    if height is not None:
        peak_kwargs["height"] = height

    indices, properties = find_peaks(intensities, **peak_kwargs)

    # Measure peak widths at rel_height
    if len(indices) > 0:
        from scipy.signal import peak_widths
        widths, width_heights, left_ips, right_ips = peak_widths(
            intensities, indices, rel_height=rel_height,
        )
        properties["widths"] = widths
        properties["width_heights"] = width_heights
        properties["left_ips"] = left_ips
        properties["right_ips"] = right_ips

    return {
        "peak_indices": indices,
        "properties": properties,
        "n_peaks": len(indices),
    }


def detect_peaks_table(
    df: pd.DataFrame,
    *,
    sample_cols: list[str] | None = None,
    prominence: float = 1e4,
    height: float | None = None,
    distance: int = 5,
) -> pd.DataFrame:
    """Run peak detection on a tabular feature matrix.

    For each sample column, sort by retention time, run ``detect_peaks``,
    and aggregate per-feature peak calls.

    Parameters
    ----------
    df : DataFrame
        Must contain 'mz' and 'rt' columns.  Additional numeric columns
        are treated as sample intensities.
    sample_cols : list[str] or None
        Which columns to treat as sample intensities.  If *None*, all
        columns containing 'intensity' or starting with 'sample' are used.
    prominence, height, distance
        Forwarded to :func:`detect_peaks`.

    Returns
    -------
    DataFrame with one row per detected peak, columns:
        mz, rt, sample, intensity, prominence, width
    """
    if sample_cols is None:
        sample_cols = [
            c for c in df.columns
            if "intensity" in c.lower() or c.lower().startswith("sample")
        ]

    if not sample_cols:
        raise ValueError(
            "No sample/intensity columns detected. Supply --sample-prefix "
            "or ensure columns contain 'intensity' or start with 'sample'."
        )

    # Sort by retention time to ensure signal ordering is meaningful
    df_sorted = df.sort_values("rt").reset_index(drop=True)

    peak_records: list[dict] = []
    for col in sample_cols:
        result = detect_peaks(
            df_sorted[col].values,
            prominence=prominence,
            height=height,
            distance=distance,
        )
        idxs = result["peak_indices"]
        props = result["properties"]

        for i, idx in enumerate(idxs):
            record = {
                "mz": float(df_sorted.loc[idx, "mz"]),
                "rt": float(df_sorted.loc[idx, "rt"]),
                "sample": col,
                "intensity": float(df_sorted.loc[idx, col]),
                "prominence": float(props["prominences"][i]),
            }
            if "widths" in props:
                record["width"] = float(props["widths"][i])
            peak_records.append(record)

    return pd.DataFrame(peak_records)


# ---------------------------------------------------------------------------
# Demo data generation
# ---------------------------------------------------------------------------

def generate_demo_data(output_path: Path) -> None:
    """Generate realistic demo metabolomics data with embedded peaks.

    Creates a synthetic dataset sorted by retention time, with Gaussian
    peaks added on top of a noisy baseline to simulate a realistic
    chromatographic signal.
    """
    rng = np.random.default_rng(42)
    n_points = 500
    n_samples = 3

    # Retention time axis (minutes)
    rt = np.linspace(0.5, 30.0, n_points)
    # m/z values — assign realistic m/z drawn from a plausible range
    mz = rng.uniform(80, 1200, n_points)

    data: dict = {"mz": np.round(mz, 4), "rt": np.round(rt, 4)}

    # Number of true peaks to embed
    n_true_peaks = 25

    for s in range(n_samples):
        # Noisy baseline (log-normal background + white noise)
        baseline = rng.lognormal(6, 0.5, n_points) + rng.normal(0, 200, n_points)
        baseline = np.clip(baseline, 0, None)

        # Add Gaussian peaks at random RT positions
        peak_centres = rng.uniform(2, 28, n_true_peaks)
        peak_heights = rng.uniform(5e4, 5e5, n_true_peaks)
        peak_sigmas = rng.uniform(0.1, 0.5, n_true_peaks)

        signal = baseline.copy()
        for pc, ph, ps in zip(peak_centres, peak_heights, peak_sigmas):
            signal += ph * np.exp(-0.5 * ((rt - pc) / ps) ** 2)

        data[f"intensity_{s + 1}"] = np.round(signal, 2)

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.info("Generated demo data with %d points, %d embedded peaks: %s",
                n_points, n_true_peaks, output_path)


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

    peaks_df = detect_peaks_table(
        df,
        sample_cols=sample_cols,
        prominence=args.prominence,
        height=args.height,
        distance=args.distance,
    )

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

#!/usr/bin/env python3
"""Genomics epigenomics: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import logging
import random
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

SKILL_NAME = "genomics-epigenomics"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Peak File Parsing (BED / narrowPeak format)


# ---------------------------------------------------------------------------
# Peak Analysis


# ---------------------------------------------------------------------------
# Demo Data Generation
# ---------------------------------------------------------------------------

def generate_demo_peaks(output_dir: Path, n_peaks: int = 500, assay: str = "chip-seq") -> Path:
    """Generate realistic synthetic peak data in narrowPeak format.

    Peak characteristics vary by assay type:
    - ChIP-seq: wider peaks (200-5000 bp), moderate enrichment
    - ATAC-seq: narrower peaks (150-500 bp), higher enrichment
    - CUT&Tag: very narrow peaks (150-300 bp)
    """
    rng = random.Random(42)
    np_rng = np.random.RandomState(42)
    chroms = [f"chr{i}" for i in range(1, 23)]

    # Peak width distribution by assay
    if assay == "atac-seq":
        widths = np_rng.lognormal(mean=5.5, sigma=0.5, size=n_peaks).astype(int)
        widths = np.clip(widths, 100, 2000)
    elif assay == "cut-tag":
        widths = np_rng.lognormal(mean=5.2, sigma=0.3, size=n_peaks).astype(int)
        widths = np.clip(widths, 100, 1000)
    else:  # chip-seq
        widths = np_rng.lognormal(mean=6.0, sigma=0.8, size=n_peaks).astype(int)
        widths = np.clip(widths, 150, 10000)

    bed_path = output_dir / f"demo_peaks.narrowPeak"

    with open(bed_path, "w") as fh:
        for i in range(n_peaks):
            chrom = rng.choice(chroms)
            start = rng.randint(10000, 249_000_000)
            end = start + int(widths[i])
            name = f"peak_{i}"
            score = rng.randint(100, 1000)
            strand = rng.choice(["+", "-", "."])

            # Fold enrichment (log-normal, median ~5)
            fe = round(np_rng.lognormal(1.5, 0.8), 3)

            # -log10(p-value)
            pvalue = round(np_rng.uniform(2, 50), 2)  # -log10 scale
            qvalue = round(max(0, pvalue - np_rng.uniform(0, 5)), 2)

            # Peak summit offset from start
            peak_offset = rng.randint(0, int(widths[i]))

            fh.write(f"{chrom}\t{start}\t{end}\t{name}\t{score}\t{strand}\t"
                     f"{fe}\t{pvalue}\t{qvalue}\t{peak_offset}\n")

    logger.info(f"Generated demo {assay} peaks: {bed_path} ({n_peaks} peaks)")
    return bed_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write epigenomics analysis report."""
    header = generate_report_header(
        title="Epigenomics Peak Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Peaks": f"{stats['n_peaks']:,}",
            "Assay": stats.get("assay", "unknown"),
        },
    )

    body_lines = [
        "## Peak Summary\n",
        f"- **Total peaks**: {stats['n_peaks']:,}",
        f"- **Total peak coverage**: {stats['total_peak_coverage_bp']:,} bp",
        f"- **Chromosomes with peaks**: {stats['n_chromosomes']}",
        f"- **Assay type**: {stats.get('assay', 'unknown')}",
        "",
        "## Peak Width Distribution\n",
        f"- **Mean width**: {stats['mean_peak_width']:,} bp",
        f"- **Median width**: {stats['median_peak_width']:,} bp",
        f"- **Q25–Q75**: {stats['peak_width_q25']:,}–{stats['peak_width_q75']:,} bp",
        f"- **Min/Max**: {stats['min_peak_width']:,}–{stats['max_peak_width']:,} bp",
    ]

    if "expected_peak_width_range" in stats:
        body_lines.append(f"- **Expected range ({stats['assay']})**: {stats['expected_peak_width_range']}")

    body_lines.append("")

    if "mean_fold_enrichment" in stats:
        body_lines.extend([
            "## Signal Quality\n",
            f"- **Mean fold enrichment**: {stats['mean_fold_enrichment']:.2f}",
            f"- **Median fold enrichment**: {stats['median_fold_enrichment']:.2f}",
            "",
        ])

    if "mean_score" in stats:
        body_lines.extend([
            "## Peak Scores\n",
            f"- **Mean score**: {stats['mean_score']:.1f}",
            f"- **Median score**: {stats['median_score']:.1f}",
            "",
        ])

    # Quality assessment (ENCODE standards)
    body_lines.append("## Quality Assessment (ENCODE Standards)\n")

    if stats["n_peaks"] >= 10000:
        body_lines.append(f"✅ **Peak count** ({stats['n_peaks']:,}): PASS (≥ 10,000 recommended)\n")
    elif stats["n_peaks"] >= 1000:
        body_lines.append(f"⚠️ **Peak count** ({stats['n_peaks']:,}): Moderate\n")
    else:
        body_lines.append(f"❌ **Peak count** ({stats['n_peaks']:,}): Low — check library complexity\n")

    body_lines.append("")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genomics Epigenomics Analysis")
    parser.add_argument("--input", dest="input_path", help="Input BED/narrowPeak file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument(
        "--method", default="macs2",
        choices=["macs2", "macs3", "homer", "genrich"],
        help="Peak calling method (for metadata)",
    )
    parser.add_argument(
        "--assay", default="chip-seq",
        choices=["chip-seq", "atac-seq", "cut-tag"],
        help="Assay type (affects expected peak characteristics)",
    )
    parser.add_argument("--n-peaks", type=int, default=500, help="Number of demo peaks")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_peaks(output_dir, n_peaks=args.n_peaks, assay=args.assay)
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
    df = api.analyze(api.read_records(data_path), assay=args.assay)
    stats = api.run_info(df, keep=False)["summary"]

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df.to_csv(tables_dir / "peaks_summary.csv", index=False)

    # Per-chromosome summary
    if "peaks_per_chrom" in stats:
        chrom_df = pd.DataFrame(
            sorted(stats["peaks_per_chrom"].items()),
            columns=["chrom", "n_peaks"],
        )
        chrom_df.to_csv(tables_dir / "peaks_per_chromosome.csv", index=False)

    # Remove non-serializable items
    summary = {k: v for k, v in stats.items() if k != "peaks_per_chrom"}

    write_report(output_dir, stats, input_file)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={"peaks_per_chrom": stats.get("peaks_per_chrom", {})},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Epigenomics analysis complete: {stats['n_peaks']} {args.assay} peaks, "
          f"median width={stats['median_peak_width']} bp")


if __name__ == "__main__":
    main()

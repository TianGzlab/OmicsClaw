#!/usr/bin/env python3
"""Proteomics PTM Analysis - Analyze post-translational modifications.

Supports identification and quantification of PTM sites from peptide-level
data. Generates PTM site localization confidence, motif analysis, and
summary statistics.

Usage:
    python proteomics_ptm.py --input <ptm_data.csv> --output <dir>
    python proteomics_ptm.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import collections
import logging
import re
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
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "ptm"
SKILL_VERSION = "0.5.0"

# Common PTM types with their mass shifts (monoisotopic, Da)
PTM_MASS_SHIFTS = {
    "Phosphorylation": 79.9663,
    "Acetylation": 42.0106,
    "Methylation": 14.0157,
    "Ubiquitination": 114.0429,  # GG remnant after trypsin
    "Oxidation": 15.9949,
    "Deamidation": 0.9840,
    "Carbamylation": 43.0058,
    "Succinylation": 100.0160,
}

# Amino acids targeted by each PTM type
PTM_TARGETS = {
    "Phosphorylation": ["S", "T", "Y"],
    "Acetylation": ["K", "N-term"],
    "Methylation": ["K", "R"],
    "Ubiquitination": ["K"],
    "Oxidation": ["M", "W"],
    "Deamidation": ["N", "Q"],
}


def write_report(output_dir: Path, stats: dict, input_file: str | None, *, loc_threshold: float = 0.75) -> None:
    """Write PTM analysis report."""
    header = generate_report_header(
        title="Post-Translational Modification Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Total sites": str(stats["n_total_sites"]),
            "Proteins": str(stats["n_unique_proteins"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Total PTM sites**: {stats['n_total_sites']}",
        f"- **Unique proteins**: {stats['n_unique_proteins']}",
        f"- **Mean PTMs per protein**: {stats['mean_ptm_per_protein']}",
        f"- **Max PTMs per protein**: {stats['max_ptm_per_protein']}",
        "",
        "### PTM Types\n",
    ]
    for ptm_type, count in stats.get("ptm_type_distribution", {}).items():
        body_lines.append(f"- **{ptm_type}**: {count}")

    body_lines.extend(["", "### Site Localization Classes\n",
                        "| Class | Count | Description |",
                        "|-------|-------|-------------|"])
    class_dist = stats.get("site_class_distribution", {})
    body_lines.append(f"| Class I | {class_dist.get('Class I', 0)} | Well-localized (prob >= {loc_threshold}) |")
    body_lines.append(f"| Class II | {class_dist.get('Class II', 0)} | Moderate (0.50 <= prob < {loc_threshold}) |")
    body_lines.append(f"| Class III | {class_dist.get('Class III', 0)} | Poorly localized (prob < 0.50) |")

    if "phosphorylation" in stats:
        ps = stats["phosphorylation"]
        body_lines.extend([
            "", "### Phosphorylation Distribution\n",
            f"- pSer: {ps['n_pSer']} ({ps['pct_pSer']}%)",
            f"- pThr: {ps['n_pThr']} ({ps['pct_pThr']}%)",
            f"- pTyr: {ps['n_pTyr']} ({ps['pct_pTyr']}%)",
            "",
            "**Expected distribution** (mammalian cells): ~86% pSer, ~12% pThr, ~2% pTyr",
            "(Olsen et al. 2006, Cell 127:635-648)",
        ])

    body_lines.extend([
        "",
        "## Methodology\n",
        "- Site classification: Olsen et al. (2006) Class I/II/III scheme",
        f"- Localization probability threshold for Class I: >= {loc_threshold}",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-ptm")
    parser = argparse.ArgumentParser(description="PTM Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--loc-threshold", type=float, default=0.75,
                        help="Localization probability threshold for Class I (default: 0.75)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_ptm_sites.csv"
        library.demo_data().to_csv(data_path, index=False)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    result_df = library.classify_sites(pd.read_csv(data_path), loc_threshold=args.loc_threshold)
    diagnostics = library.run_info(result_df, keep=False)
    stats = diagnostics.pop("summary")

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    result_df.to_csv(tables_dir / "ptm_sites.csv", index=False)

    # Class I sites separately
    if "site_class" in result_df.columns:
        class_i = result_df[result_df["site_class"] == "Class I"]
        class_i.to_csv(tables_dir / "ptm_class_I_sites.csv", index=False)

    write_report(output_dir, stats, input_file, loc_threshold=args.loc_threshold)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {"diagnostics": diagnostics})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"PTM analysis complete: {stats['n_total_sites']} sites, "
          f"{stats['n_class_I']} Class I")


if __name__ == "__main__":
    main()

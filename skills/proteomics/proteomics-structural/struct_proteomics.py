#!/usr/bin/env python3
"""Proteomics Structural Analysis — cross-linking MS and structural proteomics.

Implements XL-MS data analysis including:
- Cross-link classification (inter/intra-protein)
- Distance constraint validation against common crosslinker limits
- FDR filtering
- Summary statistics and reporting

Usage:
    python struct_proteomics.py --input <crosslinks.csv> --output <dir>
    python struct_proteomics.py --demo --output <dir>
"""

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
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "struct-proteomics"
SKILL_VERSION = "0.5.0"

# Common crosslinker distance constraints (Cα-Cα, in Ångströms)
# Reference: Rappsilber (2011) J Struct Biol 173(3):530-540
CROSSLINKER_CONSTRAINTS = {
    "DSS": 30.0,     # Disuccinimidyl suberate, ~11.4Å spacer + side chains
    "BS3": 30.0,     # Bis(sulfosuccinimidyl) suberate, same as DSS
    "EDC": 20.0,     # Zero-length crosslinker
    "DSSO": 30.0,    # Cleavable crosslinker
    "DSBU": 30.0,    # Cleavable crosslinker
}


def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write structural proteomics report."""
    header = generate_report_header(
        title="Structural Proteomics / XL-MS Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Crosslinks (after FDR)": str(stats["n_after_fdr"]),
            "Crosslinker": stats["crosslinker"],
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Raw crosslinks**: {stats['n_raw_crosslinks']}",
        f"- **After FDR filtering**: {stats['n_after_fdr']}",
        f"- **Inter-protein**: {stats['n_inter_protein']}",
        f"- **Intra-protein**: {stats['n_intra_protein']}",
        f"- **Unique proteins**: {stats['n_unique_proteins']}",
        f"- **Unique protein pairs**: {stats['n_unique_protein_pairs']}",
        "",
        "### Distance Constraints\n",
        f"- **Crosslinker**: {stats['crosslinker']} (max Cα-Cα: {stats['max_distance_constraint']}Å)",
        f"- **Satisfied**: {stats['n_constraint_satisfied']}",
        f"- **Violated**: {stats['n_constraint_violated']}",
        f"- **Satisfaction rate**: {stats['constraint_satisfaction_rate']}%",
    ]

    if "mean_distance" in stats:
        body_lines.extend([
            "",
            "### Distance Distribution\n",
            f"- **Mean**: {stats['mean_distance']}Å",
            f"- **Median**: {stats['median_distance']}Å",
            f"- **Range**: {stats['min_distance']}Å – {stats['max_distance_observed']}Å",
        ])

    body_lines.extend([
        "",
        "## Methodology\n",
        f"- Crosslinker constraints from Rappsilber (2011) J Struct Biol 173:530-540",
        f"- DSS/BS3 max Cα-Cα distance: 30Å (11.4Å spacer + side chain flexibility)",
        f"- FDR filtering applied before distance validation",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-structural")
    parser = argparse.ArgumentParser(description="Structural Proteomics / XL-MS Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--crosslinker", default="DSS",
                        choices=list(CROSSLINKER_CONSTRAINTS.keys()),
                        help="Crosslinker type for distance constraints")
    parser.add_argument("--fdr", type=float, default=0.05,
                        help="FDR threshold for filtering")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_crosslinks.csv"
        library.demo_data().to_csv(data_path, index=False)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    result_df = library.analyse_crosslinks(
        pd.read_csv(data_path),
        fdr_threshold=args.fdr,
        crosslinker=args.crosslinker,
    )

    diagnostics = library.run_info(result_df, keep=False)
    stats = diagnostics.pop("summary")

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "crosslinks.csv", index=False)

    # Save inter-protein links separately
    if "link_type" in result_df.columns:
        inter = result_df[result_df["link_type"] == "inter-protein"]
        inter.to_csv(tables_dir / "inter_protein_crosslinks.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {"diagnostics": diagnostics})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Structural analysis complete: {stats['n_after_fdr']} crosslinks "
          f"({stats['n_inter_protein']} inter-protein, "
          f"{stats['constraint_satisfaction_rate']}% satisfy distance constraint)")


if __name__ == "__main__":
    main()

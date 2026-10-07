#!/usr/bin/env python3
"""Proteomics Data Import - Import and convert proteomics data formats.

Supports reading data from common proteomics search engine output formats
(MaxQuant, FragPipe/MSFragger, DIA-NN, generic CSV/TSV) and converting to
a standardized OmicsClaw format.

Usage:
    python proteomics_data_import.py --input <data.txt> --output <dir> --format maxquant
    python proteomics_data_import.py --demo --output <dir>
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

SKILL_NAME = "data-import"
SKILL_VERSION = "0.5.0"

SUPPORTED_FORMATS = ("maxquant", "fragpipe", "diann", "generic")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write import summary report."""
    header = generate_report_header(
        title="Proteomics Data Import Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Format": stats["format"],
            "Proteins": str(stats["n_proteins"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Input format**: {stats['format']}",
        f"- **Proteins imported**: {stats['n_proteins']}",
        f"- **Columns**: {stats['n_columns']}",
    ]

    if "intensity_columns" in stats:
        body_lines.append(f"- **Intensity/sample columns**: {stats['intensity_columns']}")
    if "n_filtered" in stats and stats["n_filtered"] > 0:
        body_lines.append(f"- **Entries filtered**: {stats['n_filtered']} (contaminants/reverse/site-only)")

    body_lines.extend(["", "## Output\n",
                        "Standardized data saved to `tables/proteins.csv`"])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-data-import")
    parser = argparse.ArgumentParser(description="Proteomics Data Import")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--format", dest="data_format", default="maxquant",
                        choices=list(SUPPORTED_FORMATS),
                        help="Input data format")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_proteinGroups.txt"
        library.demo_data().to_csv(data_path, index=False, sep="\t")
        data_format = "maxquant"
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        data_format = args.data_format
        input_file = args.input_path

    df = library.standardize(library.read_table(data_path), format=data_format)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df.to_csv(tables_dir / "proteins.csv", index=False)

    stats = library.run_info(df, keep=False)["summary"]

    write_report(output_dir, stats, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Data import complete: {stats['n_proteins']} proteins from {data_format} format")


if __name__ == "__main__":
    main()

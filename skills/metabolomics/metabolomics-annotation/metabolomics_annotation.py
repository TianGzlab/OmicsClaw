#!/usr/bin/env python3
"""Metabolomics Annotation — Annotate metabolite features by m/z matching.

Supports multiple adduct types ([M+H]+, [M-H]-, [M+Na]+) and configurable
mass tolerance in ppm.

Usage:
    python annotation.py --input <data.csv> --output <dir> --database hmdb
    python annotation.py --demo --output <dir>
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
from skills._sdk.notebook import load_skill

logger = logging.getLogger(__name__)

SKILL_NAME = "annotation"
SKILL_VERSION = "0.5.0"
SUPPORTED_DATABASES = ("hmdb", "kegg", "lipidmaps", "metlin")

# ---------------------------------------------------------------------------
# Adduct definitions (mass shifts)
# ---------------------------------------------------------------------------
# Proton mass: 1.007276 Da
from skills.metabolomics._lib.annotation import DEMO_METABOLITES, _PROTON

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def get_demo_data() -> pd.DataFrame:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import annotation
    data = annotation()
    return data


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Metabolite Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Database": summary["database"],
            "Annotated": f"{summary['n_annotated']}/{summary['n_queries']}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Database**: {summary['database']}",
        f"- **Adducts considered**: {summary['adducts']}",
        f"- **Total query features**: {summary['n_queries']}",
        f"- **Features with ≥1 match**: {summary['n_annotated']} ({summary['annotation_rate']:.1f}%)",
        f"- **Total matches**: {summary['n_total_matches']}",
        f"- **High confidence**: {summary.get('n_high_conf', 0)}",
        "",
        "## Method\n",
        "Each observed m/z is compared against theoretical m/z values for every "
        "metabolite × adduct combination in the database. All matches within the "
        "specified ppm tolerance are reported.",
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
    cmd = f"python metabolomics_annotation.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Metabolite Annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--database", default="hmdb", choices=list(SUPPORTED_DATABASES))
    parser.add_argument("--ppm", type=float, default=10.0)
    parser.add_argument(
        "--adducts",
        nargs="+",
        default=["[M+H]+", "[M-H]-"],
        help="Adduct types to consider (default: [M+H]+ [M-H]-)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        peaks = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        peaks = pd.read_csv(args.input_path)
        input_file = args.input_path

    logger.info("Input: %d features", len(peaks))

    library = load_skill("metabolomics-annotation")
    annotations = library.annotate(peaks, database=args.database, ppm=args.ppm, adducts=args.adducts)

    library.run_info(annotations, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    annotations.to_csv(tables_dir / "annotations.csv", index=False)

    # Unique query features that got at least one non-Unknown match
    n_queries = int(peaks["mz"].nunique())
    n_annotated = int(annotations.loc[annotations["name"] != "Unknown", "query_mz"].nunique())
    n_total_matches = int((annotations["name"] != "Unknown").sum())
    n_high_conf = int((annotations["confidence"] == "high").sum())

    summary = {
        "database": args.database,
        "adducts": ", ".join(args.adducts),
        "n_queries": n_queries,
        "n_annotated": n_annotated,
        "n_total_matches": n_total_matches,
        "n_high_conf": n_high_conf,
        "annotation_rate": float(n_annotated / max(n_queries, 1) * 100),
    }

    params = {
        "database": args.database,
        "ppm": args.ppm,
        "adducts": ", ".join(args.adducts),
    }

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Annotation complete: {summary['n_annotated']}/{summary['n_queries']} features "
        f"({summary['annotation_rate']:.1f}%), {n_total_matches} total matches"
    )


if __name__ == "__main__":
    main()

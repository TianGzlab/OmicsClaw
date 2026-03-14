#!/usr/bin/env python3
"""Metabolomics Annotation - Annotate metabolite features.

Usage:
    python annotation.py --input <data.csv> --output <dir> --database hmdb
    python annotation.py --demo --output <dir>
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

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "annotation"
SKILL_VERSION = "0.2.0"
SUPPORTED_DATABASES = ("hmdb", "kegg", "lipidmaps", "metlin")

# Demo metabolite database
DEMO_METABOLITES = [
    ("Glucose", 180.0634, "HMDB0000122"),
    ("Lactate", 90.0320, "HMDB0000190"),
    ("Alanine", 89.0477, "HMDB0000161"),
    ("Glycine", 75.0320, "HMDB0000123"),
    ("Serine", 105.0426, "HMDB0000187"),
    ("Proline", 115.0633, "HMDB0000162"),
    ("Valine", 117.0790, "HMDB0000883"),
    ("Leucine", 131.0946, "HMDB0000687"),
    ("Isoleucine", 131.0946, "HMDB0000172"),
    ("Threonine", 119.0582, "HMDB0000167"),
]


def annotate_mz(mz_values: pd.Series, database: str = "hmdb", ppm: float = 10) -> pd.DataFrame:
    """Annotate m/z values against metabolite database."""
    logger.info(f"Annotating {len(mz_values)} features against {database} (ppm={ppm})")

    annotations = []
    for mz in mz_values:
        matched = False
        for name, ref_mz, db_id in DEMO_METABOLITES:
            error = abs(mz - ref_mz) / ref_mz * 1e6
            if error <= ppm:
                annotations.append({
                    "mz": mz,
                    "name": name,
                    "formula": "",
                    "database_id": db_id,
                    "ppm_error": round(error, 2),
                    "confidence": "high" if error < 5 else "medium",
                })
                matched = True
                break

        if not matched:
            annotations.append({
                "mz": mz,
                "name": "Unknown",
                "formula": "",
                "database_id": "",
                "ppm_error": np.nan,
                "confidence": "none",
            })

    return pd.DataFrame(annotations)


def get_demo_data() -> pd.DataFrame:
    """Generate demo peak table."""
    logger.info("Generating demo peak table")
    n_peaks = 50
    mz_values = np.concatenate([
        np.random.choice([m[1] for m in DEMO_METABOLITES], 15) + np.random.normal(0, 0.001, 15),
        np.random.uniform(100, 500, n_peaks - 15)
    ])

    return pd.DataFrame({
        "mz": mz_values,
        "rt": np.random.uniform(0, 600, n_peaks),
        "intensity": np.random.uniform(1e3, 1e6, n_peaks),
    })


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Metabolite Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Database": summary['database'],
            "Annotated": f"{summary['n_annotated']}/{summary['n_total']}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Database**: {summary['database']}",
        f"- **Total features**: {summary['n_total']}",
        f"- **Annotated**: {summary['n_annotated']} ({summary['annotation_rate']:.1f}%)",
        f"- **High confidence**: {summary.get('n_high_conf', 0)}",
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
    cmd = f"python annotation.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Metabolite Annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--database", default="hmdb", choices=list(SUPPORTED_DATABASES))
    parser.add_argument("--ppm", type=float, default=10)
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

    logger.info(f"Input: {len(peaks)} features")

    annotations = annotate_mz(peaks['mz'], args.database, args.ppm)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    annotations.to_csv(tables_dir / "annotations.csv", index=False)

    n_annotated = (annotations['name'] != "Unknown").sum()
    n_high_conf = (annotations['confidence'] == "high").sum()

    summary = {
        "database": args.database,
        "n_total": len(annotations),
        "n_annotated": int(n_annotated),
        "n_high_conf": int(n_high_conf),
        "annotation_rate": float(n_annotated / len(annotations) * 100),
    }

    params = {
        "database": args.database,
        "ppm": args.ppm,
    }

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Annotation complete: {summary['n_annotated']}/{summary['n_total']} features ({summary['annotation_rate']:.1f}%)")


if __name__ == "__main__":
    main()

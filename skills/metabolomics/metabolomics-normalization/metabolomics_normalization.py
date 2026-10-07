#!/usr/bin/env python3
"""Metabolomics Normalization — Normalize metabolite abundance data.

Supports five methods: median, quantile, total-ion-count, PQN, and log2.

Usage:
    python normalization.py --input <data.csv> --output <dir> --method median
    python normalization.py --demo --output <dir>
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

SKILL_NAME = "normalization"
SKILL_VERSION = "0.5.0"
SUPPORTED_METHODS = ("median", "quantile", "total", "pqn", "log")


# ---------------------------------------------------------------------------
# Normalization methods
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Demo & report
# ---------------------------------------------------------------------------

def get_demo_data() -> pd.DataFrame:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import normalization
    data = normalization()
    return data


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write comprehensive markdown report."""
    header = generate_report_header(
        title="Metabolite Normalization Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Features": str(summary["n_features"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Features**: {summary['n_features']}",
        f"- **Samples**: {summary['n_samples']}",
        "",
        "## Method Details\n",
    ]
    method_desc = {
        "median": "Scale each sample so that its median equals the global median-of-medians.",
        "quantile": "Quantile normalization (Bolstad et al., 2003): sort → row-mean → rank-assign.",
        "total": "Total-ion-count normalization: scale by column sums.",
        "pqn": "Probabilistic Quotient Normalization (Dieterle et al., 2006): "
               "reference = median spectrum, factor = median quotient.",
        "log": "Log2(x + 1) transformation.",
    }
    body_lines.append(f"> {method_desc.get(summary['method'], 'N/A')}")
    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python metabolomics_normalization.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Metabolite Normalization")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="median", choices=list(SUPPORTED_METHODS))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data = pd.read_csv(args.input_path, index_col=0)
        input_file = args.input_path

    logger.info("Input: %d features × %d samples", data.shape[0], data.shape[1])

    library = load_skill("metabolomics-normalization")
    normalized = library.normalize(data, method=args.method)
    library.run_info(normalized, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    normalized.to_csv(tables_dir / "normalized.csv")

    summary = {
        "method": args.method,
        "n_features": data.shape[0],
        "n_samples": data.shape[1],
    }

    params = {"method": args.method}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Normalization complete: {summary['n_features']} features, method={args.method}")


if __name__ == "__main__":
    main()

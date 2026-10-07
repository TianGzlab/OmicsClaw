#!/usr/bin/env python3
"""Metabolomics Pathway Analysis — metabolic pathway enrichment via ORA.

Uses the hypergeometric test (Fisher's exact test / Over-Representation
Analysis) for statistically sound pathway enrichment, with
Benjamini-Hochberg FDR correction.

Usage:
    python met_pathway.py --input <features.csv> --output <dir>
    python met_pathway.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

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

SKILL_NAME = "met-pathway"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Demo metabolic pathway database (KEGG-like)
# IDs verified against KEGG (https://www.kegg.jp/kegg/pathway.html)
# ---------------------------------------------------------------------------
from skills.metabolomics._lib.pathways import DEMO_METABOLIC_PATHWAYS

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import pathway_enrichment
    data = pathway_enrichment()
    path = output_dir / "demo_metabolites.csv"
    data.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
    result_df: pd.DataFrame,
) -> None:
    """Write markdown report."""
    header = generate_report_header(
        title="Metabolomics Pathway Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Significant (FDR<0.05)": str(summary.get("n_significant", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Query metabolites**: {summary['n_metabolites']}",
        f"- **Pathways tested**: {summary['n_pathways_tested']}",
        f"- **Significant (FDR < 0.05)**: {summary['n_significant']}",
        f"- **Method**: {summary['method']}",
        "",
        "## Method\n",
        "Over-representation analysis (ORA) using the hypergeometric test "
        "(equivalent to one-sided Fisher's exact test). P-values are adjusted "
        "for multiple testing using Benjamini-Hochberg FDR correction.",
        "",
    ]

    if not result_df.empty:
        body_lines.extend([
            "## Enriched Pathways\n",
            "| Pathway | KEGG ID | Hits/Size | P-value | FDR | Impact |",
            "|---------|---------|-----------|---------|-----|--------|",
        ])
        for _, row in result_df.iterrows():
            body_lines.append(
                f"| {row['pathway']} | `{row['kegg_id']}` | "
                f"{row['hits']}/{row['pathway_size']} | "
                f"{row['pvalue']:.2e} | {row.get('fdr', 'N/A'):.2e} | "
                f"{row['impact']:.2f} |"
            )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Metabolomics Pathway Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ora", choices=["ora", "mummichog", "fella"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    df = pd.read_csv(data_path)
    met_col = "metabolite" if "metabolite" in df.columns else df.columns[0]
    metabolite_list = df[met_col].tolist()

    library = load_skill("metabolomics-pathway-enrichment")
    result_df = library.enrich(metabolite_list, method=args.method)

    library.run_info(result_df, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "pathway_enrichment.csv", index=False)

    n_sig = int((result_df["fdr"] < 0.05).sum()) if not result_df.empty else 0

    summary = {
        "n_metabolites": len(metabolite_list),
        "n_pathways_tested": len(DEMO_METABOLIC_PATHWAYS),
        "n_significant": n_sig,
        "method": args.method,
    }
    params = {"method": args.method}

    write_report(output_dir, summary, args.input_path if not args.demo else None, params, result_df)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Pathway analysis complete: {n_sig} significant pathways")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Proteomics Pathway Enrichment — functional enrichment analysis for protein lists.

Implements proper over-representation analysis (ORA) using Fisher's exact test
with Benjamini-Hochberg FDR correction.

Usage:
    python prot_enrichment.py --input <proteins.csv> --output <dir>
    python prot_enrichment.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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

SKILL_NAME = "prot-enrichment"
SKILL_VERSION = "0.5.0"

# Demo pathway database (curated subset for testing)
DEMO_PATHWAYS = {
    "PI3K-Akt signaling": ["AKT1", "PIK3CA", "MTOR", "PTEN", "RPS6KB1"],
    "MAPK signaling": ["BRAF", "MAP2K1", "MAPK1", "MAPK3", "RAF1"],
    "Apoptosis": ["BAX", "BCL2", "CASP3", "CASP9", "CYCS"],
    "Proteasome": ["PSMA1", "PSMB1", "PSMC1", "PSMD1", "PSME1"],
    "Glycolysis": ["HK1", "PFKL", "PKM", "LDHA", "ENO1"],
    "Oxidative phosphorylation": ["NDUFA1", "SDHA", "UQCRC1", "COX5A", "ATP5F1A"],
    "Cell cycle": ["CDK1", "CDK2", "CCNB1", "CCND1", "RB1"],
    "DNA repair": ["BRCA1", "BRCA2", "RAD51", "XRCC5", "PARP1"],
}


# ---------------------------------------------------------------------------
# Fisher exact test ORA
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(output_dir: Path, stats_dict: dict, input_file: str | None) -> None:
    """Write enrichment report."""
    header = generate_report_header(
        title="Pathway Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Input genes": str(stats_dict["n_input_genes"]),
            "Pathways tested": str(stats_dict["n_pathways_tested"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Input genes**: {stats_dict['n_input_genes']}",
        f"- **Pathways tested**: {stats_dict['n_pathways_tested']}",
        f"- **Significant pathways (FDR < 0.05)**: {stats_dict['n_significant']}",
        "",
        "## Methodology\n",
        "- **Test**: Fisher's exact test (one-sided, over-representation)",
        "- **Multiple testing correction**: Benjamini-Hochberg FDR",
        "- **Reference**: Rivals et al. (2007) BMC Bioinformatics 8:21",
        "",
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-enrichment")
    parser = argparse.ArgumentParser(description="Proteomics Enrichment Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ora", choices=["ora"])
    parser.add_argument("--species", default="human")
    parser.add_argument("--pathways", help="JSON object mapping pathway names to protein identifiers")
    parser.add_argument("--background-size", type=int, default=None,
                        help="Size of the background gene universe")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_proteins.csv"
        library.demo_data().to_csv(data_path, index=False)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    df = pd.read_csv(data_path)
    gene_col = "protein_id" if "protein_id" in df.columns else df.columns[0]
    gene_list = df[gene_col].tolist()

    if args.demo:
        pathways = library.demo_pathways()
    elif args.pathways:
        pathways = json.loads(Path(args.pathways).read_text())
    else:
        raise ValueError('--pathways is required for real input; the demo dictionary is not a production database')

    result_df = library.enrich(
        gene_list,
        background_size=args.background_size,
        method=args.method,
        pathway_db=pathways,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "enrichment_results.csv", index=False)

    stats_dict = {
        "n_input_genes": len(gene_list),
        "n_pathways_tested": len(pathways),
        "n_significant": int((result_df["fdr"] < 0.05).sum()) if not result_df.empty else 0,
        "method": args.method,
    }

    write_report(output_dir, stats_dict, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats_dict, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Enrichment complete: {stats_dict['n_significant']} significant pathways")


if __name__ == "__main__":
    main()

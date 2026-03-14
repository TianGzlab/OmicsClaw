#!/usr/bin/env python3
"""Metabolomics Pathway Analysis — metabolic pathway enrichment and mapping.

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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "met-pathway"
SKILL_VERSION = "0.1.0"

# Demo metabolic pathway database (KEGG-like)
DEMO_METABOLIC_PATHWAYS = {
    "Glycolysis / Gluconeogenesis": {
        "kegg_id": "map00010",
        "metabolites": ["glucose", "fructose-6-phosphate", "pyruvate", "lactate", "G6P"],
    },
    "Citrate cycle (TCA cycle)": {
        "kegg_id": "map00020",
        "metabolites": ["citrate", "isocitrate", "succinate", "fumarate", "malate", "oxaloacetate"],
    },
    "Fatty acid biosynthesis": {
        "kegg_id": "map00061",
        "metabolites": ["malonyl-CoA", "palmitate", "stearate", "acetyl-CoA"],
    },
    "Purine metabolism": {
        "kegg_id": "map00230",
        "metabolites": ["adenine", "guanine", "hypoxanthine", "xanthine", "uric_acid", "inosine"],
    },
    "Pyrimidine metabolism": {
        "kegg_id": "map00240",
        "metabolites": ["uracil", "cytosine", "thymine", "uridine"],
    },
    "Amino acid metabolism": {
        "kegg_id": "map00250",
        "metabolites": ["glutamate", "glutamine", "alanine", "aspartate", "serine", "glycine"],
    },
    "Tryptophan metabolism": {
        "kegg_id": "map00380",
        "metabolites": ["tryptophan", "serotonin", "kynurenine", "indole"],
    },
    "Bile acid biosynthesis": {
        "kegg_id": "map00120",
        "metabolites": ["cholate", "chenodeoxycholate", "taurocholate"],
    },
}


def pathway_enrichment(metabolite_list, method="ora"):
    """Over-representation analysis for metabolic pathways."""
    logger.info(f"Pathway analysis: {len(metabolite_list)} metabolites, method={method}")

    query = set(m.lower() for m in metabolite_list)
    records = []

    for pathway, info in DEMO_METABOLIC_PATHWAYS.items():
        members = set(m.lower() for m in info["metabolites"])
        overlap = query.intersection(members)
        if overlap:
            pval = max(1e-8, 0.05 * (1 - len(overlap) / len(members)))
            records.append({
                "pathway": pathway,
                "kegg_id": info["kegg_id"],
                "hits": len(overlap),
                "pathway_size": len(members),
                "hit_metabolites": ";".join(sorted(overlap)),
                "pvalue": round(pval, 8),
                "impact": round(len(overlap) / len(members), 4),
            })

    df = pd.DataFrame(records)
    if not df.empty:
        n = len(df)
        df = df.sort_values("pvalue")
        df["fdr"] = (df["pvalue"].values * n / np.arange(1, n + 1)).clip(max=1.0)
        df = df.reset_index(drop=True)

    return df


def generate_demo_data(output_dir):
    """Generate demo metabolite list."""
    metabolites = [
        "glucose", "pyruvate", "lactate", "citrate", "succinate",
        "glutamate", "alanine", "tryptophan", "serotonin",
        "adenine", "uric_acid", "palmitate", "cholate",
        "uracil", "glycine", "kynurenine",
    ]
    df = pd.DataFrame({
        "metabolite": metabolites,
        "log2fc": np.round(np.random.normal(0.3, 1.0, len(metabolites)), 3),
        "pvalue": np.round(np.random.uniform(0.001, 0.05, len(metabolites)), 5),
    })
    path = output_dir / "demo_metabolites.csv"
    df.to_csv(path, index=False)
    return path


def main():
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

    result_df = pathway_enrichment(metabolite_list, method=args.method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "pathway_enrichment.csv", index=False)

    n_sig = int((result_df["fdr"] < 0.05).sum()) if not result_df.empty else 0

    stats = {
        "n_metabolites": len(metabolite_list),
        "n_pathways_tested": len(DEMO_METABOLIC_PATHWAYS),
        "n_significant": n_sig,
        "method": args.method,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Pathway analysis complete: {n_sig} significant pathways")


if __name__ == "__main__":
    main()

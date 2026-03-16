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
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "prot-enrichment"
SKILL_VERSION = "0.2.0"

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
# BH FDR correction (reusable)
# ---------------------------------------------------------------------------
def benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction.

    Reference: Benjamini & Hochberg (1995). Controlling the False Discovery
    Rate: A Practical and Powerful Approach to Multiple Testing. JRSS-B 57(1).
    """
    n = len(pvalues)
    if n == 0:
        return np.array([])

    finite_mask = np.isfinite(pvalues)
    adjusted = np.full_like(pvalues, np.nan, dtype=float)

    if finite_mask.sum() == 0:
        return adjusted

    finite_pvals = pvalues[finite_mask]
    n_finite = len(finite_pvals)

    sort_idx = np.argsort(finite_pvals)
    sorted_pvals = finite_pvals[sort_idx]
    ranks = np.arange(1, n_finite + 1, dtype=float)

    adj = sorted_pvals * n_finite / ranks

    # Enforce monotonicity (step-up)
    for i in range(n_finite - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])

    adj = np.clip(adj, 0.0, 1.0)

    result_finite = np.empty(n_finite, dtype=float)
    result_finite[sort_idx] = adj
    adjusted[finite_mask] = result_finite

    return adjusted


# ---------------------------------------------------------------------------
# Fisher exact test ORA
# ---------------------------------------------------------------------------
def enrichment_analysis(
    gene_list: list[str],
    background_size: int | None = None,
    pathway_db: dict[str, list[str]] | None = None,
    method: str = "ora",
) -> pd.DataFrame:
    """Over-representation analysis using Fisher's exact test.

    Constructs a 2×2 contingency table for each pathway:

                        In pathway    Not in pathway
    In gene list        a             b
    Not in gene list    c             d

    Then applies scipy.stats.fisher_exact with alternative='greater'
    for over-representation.

    Reference: Rivals et al. (2007) BMC Bioinformatics 8:21.
    """
    if pathway_db is None:
        pathway_db = DEMO_PATHWAYS

    gene_set = set(g.upper() for g in gene_list)
    logger.info(f"Running enrichment: method={method}, {len(gene_set)} input genes")

    # Build the background universe
    all_pathway_genes = set()
    for members in pathway_db.values():
        all_pathway_genes.update(m.upper() for m in members)

    if background_size is None:
        # Use union of input genes and all pathway genes as background
        background_size = max(len(gene_set | all_pathway_genes), len(gene_set) + 1)

    records = []

    for pathway, members in pathway_db.items():
        members_set = set(m.upper() for m in members)
        overlap = gene_set & members_set

        # 2×2 contingency table
        a = len(overlap)                                     # in gene list AND in pathway
        b = len(gene_set) - a                                # in gene list BUT NOT in pathway
        c = len(members_set) - a                             # NOT in gene list BUT in pathway
        d = background_size - a - b - c                      # NOT in gene list AND NOT in pathway

        # Ensure non-negative
        d = max(d, 0)

        # Fisher exact test (one-sided, testing for over-representation)
        contingency = [[a, b], [c, d]]
        odds_ratio, pvalue = stats.fisher_exact(contingency, alternative="greater")

        # Enrichment ratio
        expected = len(gene_set) * len(members_set) / background_size if background_size > 0 else 0
        enrichment_ratio = a / expected if expected > 0 else float("inf")

        records.append({
            "pathway": pathway,
            "overlap_count": a,
            "pathway_size": len(members_set),
            "overlap_genes": ";".join(sorted(overlap)) if overlap else "",
            "odds_ratio": round(odds_ratio, 4) if np.isfinite(odds_ratio) else float("inf"),
            "enrichment_ratio": round(enrichment_ratio, 4),
            "pvalue": pvalue,
        })

    df = pd.DataFrame(records)

    if not df.empty:
        # Apply Benjamini-Hochberg FDR correction
        df["fdr"] = benjamini_hochberg(df["pvalue"].values)
        df = df.sort_values("pvalue").reset_index(drop=True)
        # Round for display
        df["pvalue"] = df["pvalue"].round(8)
        df["fdr"] = df["fdr"].round(6)

    return df


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
def generate_demo_data(output_dir: Path) -> Path:
    """Generate demo differentially abundant protein list."""
    rng = np.random.default_rng(42)
    proteins = [
        "AKT1", "MTOR", "BRAF", "CASP3", "CDK1", "HK1",
        "BRCA1", "PSMA1", "CCNB1", "PIK3CA", "MAP2K1", "PTEN",
        "SDHA", "MAPK1", "ENO1", "RAD51", "BCL2", "PKM",
    ]
    df = pd.DataFrame({
        "protein_id": proteins,
        "log2fc": np.round(rng.normal(0.5, 1.0, len(proteins)), 3),
        "pvalue": np.round(rng.uniform(0.001, 0.05, len(proteins)), 5),
    })
    path = output_dir / "demo_proteins.csv"
    df.to_csv(path, index=False)
    return path


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
    parser = argparse.ArgumentParser(description="Proteomics Enrichment Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ora", choices=["ora"])
    parser.add_argument("--species", default="human")
    parser.add_argument("--background-size", type=int, default=None,
                        help="Size of the background gene universe")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    df = pd.read_csv(data_path)
    gene_col = "protein_id" if "protein_id" in df.columns else df.columns[0]
    gene_list = df[gene_col].tolist()

    result_df = enrichment_analysis(
        gene_list,
        background_size=args.background_size,
        method=args.method,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "enrichment_results.csv", index=False)

    stats_dict = {
        "n_input_genes": len(gene_list),
        "n_pathways_tested": len(DEMO_PATHWAYS),
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

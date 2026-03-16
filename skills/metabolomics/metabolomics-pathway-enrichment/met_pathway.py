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

SKILL_NAME = "met-pathway"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Demo metabolic pathway database (KEGG-like)
# IDs verified against KEGG (https://www.kegg.jp/kegg/pathway.html)
# ---------------------------------------------------------------------------
DEMO_METABOLIC_PATHWAYS = {
    "Glycolysis / Gluconeogenesis": {
        "kegg_id": "map00010",
        "metabolites": [
            "glucose", "glucose-6-phosphate", "fructose-6-phosphate",
            "glyceraldehyde-3-phosphate", "pyruvate", "lactate",
        ],
    },
    "Citrate cycle (TCA cycle)": {
        "kegg_id": "map00020",
        "metabolites": [
            "citrate", "isocitrate", "alpha-ketoglutarate", "succinate",
            "fumarate", "malate", "oxaloacetate",
        ],
    },
    "Fatty acid biosynthesis": {
        "kegg_id": "map00061",
        "metabolites": [
            "acetyl-CoA", "malonyl-CoA", "palmitate", "stearate", "oleate",
        ],
    },
    "Purine metabolism": {
        "kegg_id": "map00230",
        "metabolites": [
            "adenine", "guanine", "hypoxanthine", "xanthine",
            "uric_acid", "inosine", "adenosine",
        ],
    },
    "Pyrimidine metabolism": {
        "kegg_id": "map00240",
        "metabolites": ["uracil", "cytosine", "thymine", "uridine", "thymidine"],
    },
    "Alanine, aspartate and glutamate metabolism": {
        "kegg_id": "map00250",
        "metabolites": [
            "alanine", "aspartate", "glutamate", "glutamine",
            "asparagine", "oxaloacetate",
        ],
    },
    "Glycine, serine and threonine metabolism": {
        "kegg_id": "map00260",
        "metabolites": ["glycine", "serine", "threonine", "pyruvate"],
    },
    "Tryptophan metabolism": {
        "kegg_id": "map00380",
        "metabolites": [
            "tryptophan", "serotonin", "kynurenine", "indole",
            "5-hydroxyindoleacetate",
        ],
    },
    "Primary bile acid biosynthesis": {
        "kegg_id": "map00120",
        "metabolites": [
            "cholesterol", "cholate", "chenodeoxycholate",
            "taurocholate", "glycocholate",
        ],
    },
}

# Total background metabolite set (union of all pathways)
_ALL_PATHWAY_METABOLITES = set()
for _info in DEMO_METABOLIC_PATHWAYS.values():
    _ALL_PATHWAY_METABOLITES.update(m.lower() for m in _info["metabolites"])


# ---------------------------------------------------------------------------
# Hypergeometric ORA
# ---------------------------------------------------------------------------

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]
    adjusted = np.empty(n)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        adjusted[i] = min(sorted_p[i] * n / (i + 1), adjusted[i + 1])
    adjusted = np.clip(adjusted, 0, 1)
    result = np.empty(n)
    result[order] = adjusted
    return result


def pathway_enrichment(
    metabolite_list: list[str],
    method: str = "ora",
) -> pd.DataFrame:
    """Over-representation analysis using the hypergeometric test.

    For each pathway, the p-value is computed as::

        P(X >= k) = 1 - hypergeom.cdf(k-1, N, K, n)

    where

    - N = total metabolites in the background (all pathway members)
    - K = number of metabolites in the current pathway
    - n = number of query (significant) metabolites that are in the background
    - k = number of query metabolites that overlap with the pathway

    Parameters
    ----------
    metabolite_list : list[str]
        Query metabolite names (e.g., significant metabolites).
    method : str
        Analysis method label (informational).

    Returns
    -------
    DataFrame with enrichment results, sorted by p-value, with FDR column.
    """
    logger.info(
        "Pathway analysis: %d metabolites, method=%s",
        len(metabolite_list), method,
    )

    query = set(m.lower() for m in metabolite_list)
    N = len(_ALL_PATHWAY_METABOLITES)  # background size
    n = len(query.intersection(_ALL_PATHWAY_METABOLITES))  # query hits in background

    records: list[dict] = []

    for pathway, info in DEMO_METABOLIC_PATHWAYS.items():
        members = set(m.lower() for m in info["metabolites"])
        K = len(members)  # pathway size
        overlap = query.intersection(members)
        k = len(overlap)  # hits

        if k == 0:
            continue

        # Hypergeometric test: P(X >= k)
        pval = float(sp_stats.hypergeom.sf(k - 1, N, K, n))

        records.append({
            "pathway": pathway,
            "kegg_id": info["kegg_id"],
            "hits": k,
            "pathway_size": K,
            "background_size": N,
            "query_in_background": n,
            "hit_metabolites": ";".join(sorted(overlap)),
            "pvalue": pval,
            "impact": round(k / K, 4),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("pvalue").reset_index(drop=True)
        df["fdr"] = _benjamini_hochberg(df["pvalue"].values)

    return df


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Generate demo metabolite list."""
    rng = np.random.default_rng(42)
    metabolites = [
        "glucose", "pyruvate", "lactate", "citrate", "succinate",
        "glutamate", "alanine", "tryptophan", "serotonin",
        "adenine", "uric_acid", "palmitate", "cholate",
        "uracil", "glycine", "kynurenine",
    ]
    df = pd.DataFrame({
        "metabolite": metabolites,
        "log2fc": np.round(rng.normal(0.3, 1.0, len(metabolites)), 3),
        "pvalue": np.round(rng.uniform(0.001, 0.05, len(metabolites)), 5),
    })
    path = output_dir / "demo_metabolites.csv"
    df.to_csv(path, index=False)
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

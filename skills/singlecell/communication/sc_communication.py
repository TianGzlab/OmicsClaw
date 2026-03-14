#!/usr/bin/env python3
"""Single-Cell Cell-Cell Communication — ligand-receptor interaction analysis.

Usage:
    python sc_communication.py --input <data.h5ad> --output <dir>
    python sc_communication.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import scanpy as sc
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.adata_utils import store_analysis_metadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-communication"
SKILL_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Curated ligand-receptor pairs (subset for built-in scoring)
# ---------------------------------------------------------------------------
BUILTIN_LR_PAIRS = [
    ("CCL5", "CCR5"), ("CXCL12", "CXCR4"), ("CD40LG", "CD40"),
    ("TNF", "TNFRSF1A"), ("IL6", "IL6R"), ("IFNG", "IFNGR1"),
    ("IL2", "IL2RA"), ("IL10", "IL10RA"), ("FAS", "FASLG"),
    ("TGFB1", "TGFBR1"), ("VEGFA", "FLT1"), ("HGF", "MET"),
    ("WNT5A", "FZD5"), ("BMP2", "BMPR1A"), ("NOTCH1", "JAG1"),
    ("PDGFA", "PDGFRA"), ("EGF", "EGFR"), ("IGF1", "IGF1R"),
    ("CSF1", "CSF1R"), ("CCL2", "CCR2"),
]


def builtin_lr_scoring(adata, cell_type_key="leiden", species="human", n_perms=100):
    """Score L-R interactions using mean-expression product + permutation test."""
    logger.info(f"Built-in L-R scoring: {len(BUILTIN_LR_PAIRS)} pairs, "
                f"cell_type_key={cell_type_key}")

    groups = adata.obs[cell_type_key].unique().tolist()
    gene_names = set(adata.var_names)

    # Filter to available L-R pairs
    available_pairs = [
        (l, r) for l, r in BUILTIN_LR_PAIRS
        if l in gene_names and r in gene_names
    ]
    logger.info(f"Available L-R pairs: {len(available_pairs)}/{len(BUILTIN_LR_PAIRS)}")

    if not available_pairs:
        logger.warning("No L-R pairs found in data — returning empty results")
        return pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue"])

    try:
        X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.array(adata.X)
    except Exception:
        X = np.array(adata.X)

    var_list = list(adata.var_names)
    records = []

    for l_gene, r_gene in available_pairs:
        l_idx = var_list.index(l_gene)
        r_idx = var_list.index(r_gene)

        for src in groups:
            for tgt in groups:
                src_mask = (adata.obs[cell_type_key] == src).values
                tgt_mask = (adata.obs[cell_type_key] == tgt).values

                l_mean = X[src_mask, l_idx].mean()
                r_mean = X[tgt_mask, r_idx].mean()
                score = float(l_mean * r_mean)

                # Simple permutation p-value
                null_scores = []
                labels = adata.obs[cell_type_key].values.copy()
                for _ in range(n_perms):
                    np.random.shuffle(labels)
                    perm_src = labels == src
                    perm_tgt = labels == tgt
                    null_scores.append(
                        float(X[perm_src, l_idx].mean() * X[perm_tgt, r_idx].mean())
                    )
                pval = (np.sum(np.array(null_scores) >= score) + 1) / (n_perms + 1)

                records.append({
                    "ligand": l_gene,
                    "receptor": r_gene,
                    "source": str(src),
                    "target": str(tgt),
                    "score": round(score, 6),
                    "pvalue": round(float(pval), 4),
                })

    df = pd.DataFrame(records)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


def try_liana(adata, cell_type_key="leiden"):
    """Attempt to run LIANA+ if available."""
    try:
        import liana as li
        logger.info("LIANA+ detected — running multi-method consensus scoring")
        li.mt.rank_aggregate(
            adata,
            groupby=cell_type_key,
            use_raw=False,
            verbose=True,
        )
        result_df = adata.uns["liana_res"].copy()
        return result_df
    except ImportError:
        logger.info("liana not installed — falling back to built-in scoring")
        return None
    except Exception as e:
        logger.warning(f"LIANA+ failed: {e} — falling back to built-in scoring")
        return None


def get_demo_data():
    """Load preprocessed PBMC3k for demo."""
    logger.info("Loading demo PBMC3k for communication analysis")
    adata = sc.datasets.pbmc3k_processed()
    return adata


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Cell-Cell Communication Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get('method', 'auto'),
            "Interactions": str(summary.get('n_interactions_scored', 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', 'auto')}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        f"- **Interactions scored**: {summary.get('n_interactions_scored', 0)}",
        f"- **Significant interactions**: {summary.get('n_significant', 0)}",
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
    cmd = f"python sc_communication.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Communication Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="auto", choices=["auto", "liana", "builtin"])
    parser.add_argument("--cell-type-key", default="louvain")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--n-perms", type=int, default=100)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Run communication analysis
    result_df = None
    if args.method in ("auto", "liana"):
        result_df = try_liana(adata, cell_type_key=args.cell_type_key)

    if result_df is None:
        result_df = builtin_lr_scoring(
            adata,
            cell_type_key=args.cell_type_key,
            species=args.species,
            n_perms=args.n_perms,
        )

    # Save
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "lr_scores.csv", index=False)

    sig = result_df[result_df["pvalue"] < 0.05] if "pvalue" in result_df.columns else result_df.head(50)
    sig.to_csv(tables_dir / "top_interactions.csv", index=False)

    n_interactions = len(result_df)
    n_sig = len(sig)

    summary = {
        "n_cells": int(adata.n_obs),
        "n_interactions_scored": n_interactions,
        "n_significant": n_sig,
        "method": args.method,
    }

    params = {
        "method": args.method,
        "cell_type_key": args.cell_type_key,
        "species": args.species,
        "n_perms": args.n_perms,
    }

    write_report(output_dir, summary, input_file, params)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    if input_file:
        store_analysis_metadata(adata, SKILL_NAME, args.method, params)
        adata.write_h5ad(output_dir / "processed.h5ad")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Communication analysis complete: {n_interactions} interactions, {n_sig} significant")


if __name__ == "__main__":
    main()

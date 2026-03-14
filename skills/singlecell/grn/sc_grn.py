#!/usr/bin/env python3
"""Single-Cell Gene Regulatory Network Inference — pySCENIC / GRNBoost2.

Usage:
    python sc_grn.py --input <data.h5ad> --output <dir>
    python sc_grn.py --demo --output <dir>
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

SKILL_NAME = "sc-grn"
SKILL_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Curated TF list (subset for demo / fallback)
# ---------------------------------------------------------------------------
DEMO_TFS = [
    "STAT1", "IRF1", "IRF7", "NFKB1", "RELA", "JUN", "FOS",
    "MYC", "TP53", "ETS1", "SPI1", "CEBPB", "RUNX1", "GATA2",
    "PAX5", "TCF7", "LEF1", "FOXP3", "TBX21", "EOMES",
]


def infer_grn_correlation(adata, tf_list=None, n_top_targets=50):
    """Lightweight GRN inference via TF-target correlation.

    This is a simplified approach suitable as a baseline when pySCENIC is not
    installed.  It computes Pearson correlations between known TFs and all
    genes, keeping the top correlated targets per TF.
    """
    if tf_list is None:
        tf_list = DEMO_TFS

    available_tfs = [tf for tf in tf_list if tf in adata.var_names]
    if not available_tfs:
        logger.warning("No known TFs found in var_names; returning empty GRN.")
        return pd.DataFrame(columns=["TF", "target", "importance"])

    logger.info(f"Computing correlations for {len(available_tfs)} TFs …")

    # Use dense matrix for correlation
    try:
        X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.array(adata.X)
    except Exception:
        X = np.array(adata.X)

    gene_names = list(adata.var_names)
    tf_indices = [gene_names.index(tf) for tf in available_tfs]

    records = []
    for tf, tf_idx in zip(available_tfs, tf_indices):
        tf_expr = X[:, tf_idx]
        if tf_expr.std() == 0:
            continue
        for g_idx, gene in enumerate(gene_names):
            if gene == tf:
                continue
            g_expr = X[:, g_idx]
            if g_expr.std() == 0:
                continue
            corr = np.corrcoef(tf_expr, g_expr)[0, 1]
            records.append({"TF": tf, "target": gene, "importance": abs(corr)})

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Keep top targets per TF
    df = (
        df.sort_values("importance", ascending=False)
        .groupby("TF")
        .head(n_top_targets)
        .reset_index(drop=True)
    )
    return df


def try_pyscenic(adata, tf_list=None):
    """Attempt to run pySCENIC GRNBoost2 if available."""
    try:
        from arboreto.algo import grnboost2
        logger.info("pySCENIC / arboreto detected — running GRNBoost2")

        if tf_list is None:
            tf_list = DEMO_TFS
        available_tfs = [tf for tf in tf_list if tf in adata.var_names]
        if not available_tfs:
            return None

        try:
            X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.array(adata.X)
        except Exception:
            X = np.array(adata.X)

        expr_df = pd.DataFrame(X, index=adata.obs_names, columns=adata.var_names)
        network = grnboost2(expression_data=expr_df, tf_names=available_tfs)
        network.columns = ["TF", "target", "importance"]
        return network
    except ImportError:
        logger.info("arboreto not installed — falling back to correlation-based GRN")
        return None


def get_demo_data():
    """Load preprocessed PBMC3k for demo."""
    logger.info("Loading demo PBMC3k data for GRN inference")
    adata = sc.datasets.pbmc3k_processed()
    return adata


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Gene Regulatory Network Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get('method', 'auto'),
            "TFs": str(summary.get('n_tfs', 0)),
            "Edges": str(summary.get('n_edges', 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', 'auto')}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        f"- **Genes**: {summary.get('n_genes', 'N/A')}",
        f"- **TFs analyzed**: {summary.get('n_tfs', 0)}",
        f"- **Network edges**: {summary.get('n_edges', 0)}",
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
    cmd = f"python sc_grn.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell GRN Inference")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="auto", choices=["auto", "grnboost2", "correlation"])
    parser.add_argument("--n-top-targets", type=int, default=50)
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

    # Infer GRN
    network = None
    if args.method in ("auto", "grnboost2"):
        network = try_pyscenic(adata)

    if network is None:
        network = infer_grn_correlation(adata, n_top_targets=args.n_top_targets)

    # Save outputs
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    network.to_csv(tables_dir / "grn_network.csv", index=False)

    n_tfs = network["TF"].nunique() if not network.empty else 0
    n_edges = len(network)

    summary = {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_tfs": n_tfs,
        "n_edges": n_edges,
        "method": "grnboost2" if args.method != "correlation" and network is not None else "correlation",
    }

    params = {
        "method": args.method,
        "n_top_targets": args.n_top_targets,
    }

    write_report(output_dir, summary, input_file, params)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    if input_file:
        store_analysis_metadata(adata, SKILL_NAME, summary['method'], params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"GRN inference complete: {n_tfs} TFs, {n_edges} edges")


if __name__ == "__main__":
    main()

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


def try_pyscenic(adata, tf_list=None, motif_db_path=None, species="human"):
    """Run full pySCENIC pipeline: GRNBoost2 → motif enrichment → AUCell."""
    try:
        from arboreto.algo import grnboost2
        from pyscenic.utils import modules_from_adjacencies
        from pyscenic.prune import prune2df, df2regulons
        from pyscenic.aucell import aucell

        logger.info("pySCENIC detected — running full pipeline")

        if tf_list is None:
            tf_list = DEMO_TFS
        available_tfs = [tf for tf in tf_list if tf in adata.var_names]
        if not available_tfs:
            logger.warning("No TFs found in data")
            return None, None, None

        # Step 1: GRNBoost2 network inference
        logger.info(f"Step 1/3: GRNBoost2 inference with {len(available_tfs)} TFs")
        try:
            X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.array(adata.X)
        except Exception:
            X = np.array(adata.X)

        expr_df = pd.DataFrame(X, index=adata.obs_names, columns=adata.var_names)
        adjacencies = grnboost2(expression_data=expr_df, tf_names=available_tfs)

        # Step 2: Motif enrichment (if database provided)
        regulons = None
        if motif_db_path and Path(motif_db_path).exists():
            logger.info("Step 2/3: Motif enrichment with cisTarget")
            try:
                modules = list(modules_from_adjacencies(adjacencies, expr_df))
                df = prune2df(motif_db_path, modules, available_tfs)
                regulons = df2regulons(df)
                logger.info(f"Created {len(regulons)} regulons after motif pruning")
            except Exception as e:
                logger.warning(f"Motif enrichment failed: {e}, skipping")
                regulons = None
        else:
            logger.info("Step 2/3: Skipped (no motif database)")

        # Step 3: AUCell scoring (if regulons available)
        auc_mtx = None
        if regulons:
            logger.info("Step 3/3: AUCell scoring")
            try:
                auc_mtx = aucell(expr_df, regulons, num_workers=1)
                logger.info(f"AUCell matrix: {auc_mtx.shape}")
            except Exception as e:
                logger.warning(f"AUCell failed: {e}")
                auc_mtx = None
        else:
            logger.info("Step 3/3: Skipped (no regulons)")

        adjacencies.columns = ["TF", "target", "importance"]
        return adjacencies, regulons, auc_mtx

    except ImportError as e:
        logger.info(f"pySCENIC not fully installed ({e}) — falling back")
        return None, None, None


def try_celloracle(adata, perturb_gene=None, perturb_type="knockout"):
    """Run CellOracle for perturbation simulation."""
    try:
        import celloracle as co
        logger.info("CellOracle detected — running perturbation simulation")

        # Ensure data has required fields
        if "X_umap" not in adata.obsm:
            logger.warning("UMAP coordinates required for CellOracle, computing...")
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)

        # Build base GRN from expression data
        logger.info("Building base GRN with CellOracle")
        oracle = co.Oracle()

        # Use existing clustering if available
        if "leiden" not in adata.obs:
            sc.tl.leiden(adata)

        oracle.import_anndata_as_raw_count(adata, cluster_column_name="leiden")
        oracle.perform_PCA()
        oracle.knn_imputation(n_neighbors=50)

        # Infer GRN
        logger.info("Inferring GRN with CellOracle")
        links = oracle.get_links(cluster_name_for_GRN_unit="leiden")

        # Simulate perturbation if gene specified
        perturb_results = None
        if perturb_gene and perturb_gene in adata.var_names:
            logger.info(f"Simulating {perturb_type} of {perturb_gene}")
            oracle.simulate_shift(
                perturb_condition={perturb_gene: 0.0 if perturb_type == "knockout" else 2.0},
                n_propagation=3
            )
            perturb_results = {
                "gene": perturb_gene,
                "type": perturb_type,
                "delta_embedding": oracle.delta_embedding,
            }

        # Extract network as DataFrame
        network = links.links_dict
        network_df = pd.DataFrame([
            {"TF": tf, "target": target, "importance": score}
            for tf, targets in network.items()
            for target, score in targets.items()
        ])

        return network_df, perturb_results

    except ImportError:
        logger.info("CellOracle not installed — skipping")
        return None, None
    except Exception as e:
        logger.warning(f"CellOracle failed: {e}")
        return None, None


def get_demo_data():
    """Load preprocessed PBMC3k for demo."""
    logger.info("Loading demo PBMC3k data for GRN inference")
    demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_processed.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path)
    logger.warning("Local demo data not found, downloading from scanpy")
    return sc.datasets.pbmc3k_processed()


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
        f"- **Regulons**: {summary.get('n_regulons', 0)}",
        f"- **Motif enrichment**: {'Yes' if summary.get('has_motif_enrichment') else 'No'}",
        f"- **AUCell scoring**: {'Yes' if summary.get('has_aucell') else 'No'}",
        f"- **Perturbation**: {summary.get('perturb_gene', 'None')}",
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
    parser.add_argument("--method", default="auto", choices=["auto", "pyscenic", "grnboost2", "celloracle", "correlation"])
    parser.add_argument("--motif-db", dest="motif_db_path", help="Path to pySCENIC motif database (.feather)")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--perturb-gene", help="Gene to perturb (for CellOracle)")
    parser.add_argument("--perturb-type", default="knockout", choices=["knockout", "overexpression"])
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
    network, regulons, auc_mtx = None, None, None
    perturb_results = None

    if args.method == "celloracle":
        network, perturb_results = try_celloracle(adata, args.perturb_gene, args.perturb_type)
    elif args.method in ("auto", "pyscenic", "grnboost2"):
        network, regulons, auc_mtx = try_pyscenic(adata, motif_db_path=args.motif_db_path, species=args.species)

    if network is None:
        network = infer_grn_correlation(adata, n_top_targets=args.n_top_targets)

    # Save outputs
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    network.to_csv(tables_dir / "grn_network.csv", index=False)

    n_tfs = network["TF"].nunique() if not network.empty else 0
    n_edges = len(network)
    n_regulons = len(regulons) if regulons else 0

    # Save regulons if available
    if regulons:
        import pickle
        with open(tables_dir / "regulons.pkl", "wb") as f:
            pickle.dump(regulons, f)
        logger.info(f"Saved {n_regulons} regulons")

    # Save AUCell matrix if available
    if auc_mtx is not None:
        auc_mtx.to_csv(tables_dir / "auc_matrix.csv")
        logger.info(f"Saved AUCell matrix: {auc_mtx.shape}")

    # Save perturbation results if available
    if perturb_results:
        import pickle
        with open(tables_dir / "perturbation_results.pkl", "wb") as f:
            pickle.dump(perturb_results, f)
        logger.info(f"Saved perturbation results for {perturb_results['gene']}")

    summary = {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_tfs": n_tfs,
        "n_edges": n_edges,
        "n_regulons": n_regulons,
        "has_motif_enrichment": regulons is not None,
        "has_aucell": auc_mtx is not None,
        "has_perturbation": perturb_results is not None,
        "perturb_gene": perturb_results['gene'] if perturb_results else None,
        "method": "celloracle" if perturb_results else ("pyscenic" if regulons else ("grnboost2" if args.method != "correlation" else "correlation")),
    }

    params = {
        "method": args.method,
        "motif_db": args.motif_db_path or "none",
        "species": args.species,
        "perturb_gene": args.perturb_gene or "none",
        "perturb_type": args.perturb_type,
        "n_top_targets": args.n_top_targets,
    }

    write_report(output_dir, summary, input_file, params)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    if input_file:
        store_analysis_metadata(adata, SKILL_NAME, summary['method'], params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"GRN inference complete: {n_tfs} TFs, {n_edges} edges, {n_regulons} regulons")


if __name__ == "__main__":
    main()

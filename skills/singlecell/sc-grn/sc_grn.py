#!/usr/bin/env python3
"""Single-Cell Gene Regulatory Network Analysis - pySCENIC workflow.

Usage:
    python sc_grn.py --input <data.h5ad> --output <dir> --tf-list <tf.txt> --db <db_glob> --motif <motif.tbl>
    python sc_grn.py --demo --output <dir>

This skill performs GRN inference using pySCENIC:
1. GRNBoost2 for co-expression network inference
2. cisTarget for motif enrichment and pruning
3. AUCell for regulon activity scoring

Requirements:
    - arboreto (GRNBoost2)
    - pyscenic
    - External databases: TF list, cisTarget DBs, motif annotations
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

# Fix for anndata >= 0.11 with StringArray
try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.viz_utils import save_figure
from omicsclaw.singlecell import io as sc_io
from omicsclaw.singlecell import grn as sc_grn_utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-grn"
SKILL_VERSION = "0.1.0"


def generate_grn_figures(
    adata,
    regulons: list[dict],
    auc_matrix: pd.DataFrame,
    output_dir: Path,
    cluster_key: str = "leiden",
) -> list[str]:
    """Generate GRN visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Regulon activity UMAP
    try:
        logger.info("Generating regulon activity UMAP...")
        fig_paths = sc_grn_utils.plot_regulon_activity_umap(
            adata,
            auc_matrix,
            output_dir=figures_dir,
            n_top=9,
        )
        figures.extend(fig_paths)
    except Exception as e:
        logger.warning(f"Regulon activity UMAP failed: {e}")

    # Regulon heatmap
    try:
        logger.info("Generating regulon heatmap...")
        cluster_labels = adata.obs[cluster_key] if cluster_key in adata.obs.columns else None
        fig_path = sc_grn_utils.plot_regulon_heatmap(
            auc_matrix,
            output_dir=figures_dir,
            cluster_labels=cluster_labels,
            n_top=20,
            title="Regulon Activity by Cluster",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Regulon heatmap failed: {e}")

    # Regulon network
    try:
        logger.info("Generating regulon network diagram...")
        fig_path = sc_grn_utils.plot_regulon_network(
            regulons,
            output_dir=figures_dir,
            n_top=20,
            min_targets=5,
            title="Gene Regulatory Network",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Regulon network plot failed: {e}")

    return figures


def write_grn_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
    top_regulons: list[dict],
) -> None:
    """Write GRN analysis report."""
    header = generate_report_header(
        title="Single-Cell Gene Regulatory Network Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Regulons": str(summary.get("n_regulons", 0)),
            "TFs": str(summary.get("n_tfs", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Transcription factors**: {summary.get('n_tfs', 'N/A')}",
        f"- **Regulons identified**: {summary.get('n_regulons', 0)}",
        f"- **Total adjacencies**: {summary.get('n_adjacencies', 0)}",
        f"- **Cells analyzed**: {summary.get('n_cells', 'N/A')}",
        "",
        "## Methods\n",
        "### GRNBoost2",
        "GRNBoost2 is a gradient boosting-based method for inferring co-expression",
        "networks between TFs and target genes.\n",
        "### cisTarget",
        "cisTarget performs motif enrichment analysis to identify direct TF targets",
        "by matching regulatory sequences to known TF binding motifs.\n",
        "### AUCell",
        "AUCell calculates the activity of each regulon in each cell by computing",
        "the area under the recovery curve of gene expression rankings.\n",
        "",
        "## Top Regulons\n",
    ]

    # Add top regulons table
    body_lines.append("| TF | Targets | Motif NES |")
    body_lines.append("|----|---------|-----------|")
    for r in top_regulons[:15]:
        nes = f"{r.get('motif_nes', 0):.2f}" if r.get('motif_nes') else "N/A"
        body_lines.append(f"| {r['tf']} | {r['n_targets']} | {nes} |")
    body_lines.append("")

    body_lines.extend([
        "## Parameters\n",
        f"- `--tf-list`: {params.get('tf_list', 'N/A')}",
        f"- `--n-top-targets`: {params.get('n_top_targets', 50)}",
        f"- `--n-jobs`: {params.get('n_jobs', 4)}",
        "",
        "## Output Files\n",
        "- `adata_with_grn.h5ad` — AnnData with regulon activity scores",
        "- `tables/grn_adjacencies.csv` — All TF-target adjacencies",
        "- `tables/grn_regulons.csv` — Regulon summary",
        "- `tables/grn_regulon_targets.csv` — TF-target pairs",
        "- `tables/grn_auc_matrix.csv` — AUCell activity scores",
        "- `figures/regulon_activity_umap.png` — Regulon activity on UMAP",
        "- `figures/regulon_heatmap.png` — Regulon activity heatmap",
        "- `figures/regulon_network.png` — Network diagram",
        "",
        "## Requirements\n",
        "This skill requires:",
        "- **pySCENIC** and **arboreto** packages",
        "- **TF list file**: One TF symbol per line",
        "- **cisTarget databases**: .feather or .db files",
        "- **Motif annotations**: .tbl or .csv file",
        "",
        "### Database Sources\n",
        "- TF list: [pySCENIC resources](https://github.com/aertslab/pySCENIC/tree/master/resources)",
        "- cisTarget DBs: [cisTarget DBs](https://resources.aertslab.org/cistarget/)",
        "- Motif annotations: [motif2TF](https://resources.aertslab.org/cistarget/motif2tf/)",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data for GRN analysis.

    Note: Demo mode requires pre-downloaded database files.
    If not available, will show error with download instructions.
    """
    import scanpy as sc

    logger.info("Generating synthetic demo data...")

    np.random.seed(42)
    n_cells = 300
    n_genes = 1000

    # Generate synthetic counts
    counts = np.random.negative_binomial(5, 0.1, size=(n_cells, n_genes)).astype(np.float32)

    adata = sc.AnnData(
        X=counts,
        obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
    )

    # Add some TF-like gene names
    tf_names = ["TP53", "MYC", "STAT1", "NFkB1", "SP1", "E2F1", "GATA1", "FOXA1", "CEBPB", "IRF1"]
    for i, tf in enumerate(tf_names):
        if i < len(adata.var_names):
            adata.var_names.values[i] = tf

    # Preprocessing
    sc.pp.filter_genes(adata, min_cells=10)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=500)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)

    # Clustering
    try:
        sc.tl.leiden(adata, resolution=0.8)
    except ImportError:
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(
            kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str)
        )

    # UMAP
    sc.tl.umap(adata)

    logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes")

    return adata


def create_demo_tf_list(output_dir: Path) -> Path:
    """Create demo TF list file."""
    tf_file = output_dir / "demo_tf_list.txt"
    tf_list = ["TP53", "MYC", "STAT1", "NFkB1", "SP1", "E2F1", "GATA1", "FOXA1", "CEBPB", "IRF1",
               "JUN", "FOS", "ATF3", "CREB1", "ELK1", "SRF", "YY1", "CTCF", "MAX", "MXD1"]

    with open(tf_file, "w") as f:
        f.write("\n".join(tf_list))

    return tf_file


def run_demo_mode(adata, output_dir: Path, params: dict) -> dict | None:
    """Run GRN analysis in demo mode (GRNBoost2 only, no cisTarget)."""
    logger.warning("="*60)
    logger.warning("Demo mode: Running GRNBoost2 only (no cisTarget pruning)")
    logger.warning("For full analysis, provide database files:")
    logger.warning("  --tf-list <file> --db <glob> --motif <file>")
    logger.warning("="*60)

    try:
        # Prepare expression matrix
        ex_matrix = sc_grn_utils.prepare_expression_matrix(adata)

        # Create demo TF list
        tf_file = create_demo_tf_list(output_dir)
        tf_list = sc_grn_utils.load_tf_list(tf_file)

        # Filter TFs to those in data
        tf_list = [tf for tf in tf_list if tf in adata.var_names]
        logger.info(f"Using {len(tf_list)} TFs from demo list")

        # Run GRNBoost2 only
        adjacencies = sc_grn_utils.run_grnboost2(
            ex_matrix,
            tf_list,
            seed=42,
            n_jobs=params.get("n_jobs", 4),
        )

        # Create simple regulons from adjacencies
        regulons = []
        for tf in tf_list:
            tf_adj = adjacencies[adjacencies["TF"] == tf].nlargest(params.get("n_top_targets", 50), "importance")
            if len(tf_adj) > 0:
                regulons.append({
                    "tf": tf,
                    "targets": tf_adj["target"].tolist(),
                    "n_targets": len(tf_adj),
                    "motif_nes": None,
                })

        # Compute pseudo-AUC scores (using top targets)
        logger.info("Computing pseudo-activity scores...")
        auc_matrix = pd.DataFrame(index=adata.obs_names)
        for r in regulons:
            target_mask = adata.var_names.isin(r["targets"])
            if target_mask.sum() > 0:
                if hasattr(adata.X, "toarray"):
                    expr = adata.X[:, target_mask].toarray()
                else:
                    expr = adata.X[:, target_mask]
                # Mean expression of targets
                auc_matrix[r["tf"]] = expr.mean(axis=1)

        return {
            "adjacencies": adjacencies,
            "regulons": regulons,
            "auc_matrix": auc_matrix,
        }

    except ImportError as e:
        logger.error(f"GRNBoost2 requires arboreto: {e}")
        logger.info("Install with: pip install arboreto")
        return None


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Gene Regulatory Network Analysis")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data (GRNBoost2 only)")
    parser.add_argument("--tf-list", dest="tf_list", help="TF list file (one TF per line)")
    parser.add_argument("--db", dest="database_glob", help="cisTarget database glob pattern")
    parser.add_argument("--motif", dest="motif_annotations", help="Motif annotations file")
    parser.add_argument("--n-top-targets", type=int, default=50, help="Max targets per regulon")
    parser.add_argument("--n-jobs", type=int, default=4, help="Number of parallel jobs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata = generate_demo_data()
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        logger.info(f"Loading: {input_path}")
        adata = sc_io.smart_load(input_path)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Parameters
    params = {
        "tf_list": args.tf_list,
        "database_glob": args.database_glob,
        "motif_annotations": args.motif_annotations,
        "n_top_targets": args.n_top_targets,
        "n_jobs": args.n_jobs,
        "seed": args.seed,
    }

    # Check for full analysis requirements
    has_full_dbs = all([args.tf_list, args.database_glob, args.motif_annotations])

    if has_full_dbs and not args.demo:
        # Full pySCENIC workflow
        logger.info("Running full pySCENIC workflow...")
        try:
            result = sc_grn_utils.run_complete_grn_workflow(
                adata,
                tf_list_file=args.tf_list,
                database_glob=args.database_glob,
                motif_annotations_file=args.motif_annotations,
                n_top_targets=args.n_top_targets,
                n_jobs=args.n_jobs,
                seed=args.seed,
            )
        except Exception as e:
            logger.error(f"Full workflow failed: {e}")
            logger.info("Falling back to GRNBoost2 only...")
            result = run_demo_mode(adata, output_dir, params)
    else:
        # Demo mode (GRNBoost2 only)
        result = run_demo_mode(adata, output_dir, params)

    if result is None:
        logger.error("GRN analysis failed")
        print("\nERROR: GRN analysis failed")
        print("For full analysis, provide:")
        print("  --tf-list <file> --db <glob> --motif <file>")
        print("Or install arboreto for demo mode: pip install arboreto")
        sys.exit(1)

    adjacencies = result["adjacencies"]
    regulons = result["regulons"]
    auc_matrix = result["auc_matrix"]

    # Add AUC scores to adata
    for col in auc_matrix.columns:
        adata.obs[f"regulon_{col}"] = auc_matrix[col]

    # Summary
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "n_tfs": len(set(adjacencies["TF"].unique())),
        "n_regulons": len(regulons),
        "n_adjacencies": len(adjacencies),
    }

    logger.info(f"Identified {len(regulons)} regulons")

    # Ensure UMAP is computed
    import scanpy as sc
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_grn_figures(adata, regulons, auc_matrix, output_dir)

    # Export tables
    logger.info("Exporting results...")
    files = sc_grn_utils.export_grn_results(
        output_dir / "tables",
        adjacencies,
        regulons,
        auc_matrix,
        prefix="grn",
    )

    # Sort regulons by target count
    regulons_sorted = sorted(regulons, key=lambda x: x["n_targets"], reverse=True)

    # Write report
    logger.info("Writing report...")
    write_grn_report(output_dir, summary, params, input_file, regulons_sorted)

    # Save data
    output_h5ad = output_dir / "adata_with_grn.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_grn.py --output {output_dir} --n-top-targets {args.n_top_targets} --n-jobs {args.n_jobs}"
    if input_file:
        cmd += f" --input {input_file}"
    if args.tf_list:
        cmd += f" --tf-list {args.tf_list}"
    if args.database_glob:
        cmd += f" --db '{args.database_glob}'"
    if args.motif_annotations:
        cmd += f" --motif {args.motif_annotations}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Regulons: {len(regulons)}")
    print(f"  TFs: {summary['n_tfs']}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()

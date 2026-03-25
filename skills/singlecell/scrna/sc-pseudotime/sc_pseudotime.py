#!/usr/bin/env python3
"""Single-Cell Pseudotime Analysis - PAGA + DPT trajectory inference.

Usage:
    python sc_pseudotime.py --input <data.h5ad> --output <dir> --root-cluster <cluster>
    python sc_pseudotime.py --demo --output <dir>

This skill performs core trajectory analysis using methods available in scanpy:
- PAGA graph for cluster connectivity
- Diffusion map for dimensionality reduction
- DPT pseudotime for temporal ordering
- Trajectory gene identification
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.method_config import (
    MethodConfig,
    validate_method_choice,
)
from skills.singlecell._lib.viz_utils import save_figure
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import trajectory as sc_traj

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-pseudotime"
SKILL_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "dpt": MethodConfig(
        name="dpt",
        description="PAGA + Diffusion Pseudotime (scanpy built-in)",
        dependencies=("scanpy",),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

# Currently only DPT is supported; dispatch kept for future methods.
_METHOD_DISPATCH = {
    "dpt": "dpt",
}


def generate_trajectory_figures(adata, trajectory_genes: pd.DataFrame, output_dir: Path) -> list[str]:
    """Generate trajectory visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # PAGA graph
    try:
        logger.info("Generating PAGA graph...")
        fig_path = sc_traj.plot_paga_graph(
            adata,
            output_dir=figures_dir,
            cluster_key="leiden",
            title="PAGA Connectivity Graph",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"PAGA graph plot failed: {e}")

    # Pseudotime UMAP
    try:
        logger.info("Generating pseudotime UMAP...")
        fig_path = sc_traj.plot_pseudotime_umap(
            adata,
            output_dir=figures_dir,
            pseudotime_key="dpt_pseudotime",
            title="DPT Pseudotime",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Pseudotime UMAP plot failed: {e}")

    # Diffusion components
    try:
        logger.info("Generating diffusion component plots...")
        fig_paths = sc_traj.plot_diffusion_components(
            adata,
            output_dir=figures_dir,
            n_components=3,
        )
        figures.extend(fig_paths)
    except Exception as e:
        logger.warning(f"Diffusion component plots failed: {e}")

    # Trajectory gene heatmap
    try:
        logger.info("Generating trajectory gene heatmap...")
        fig_path = sc_traj.plot_trajectory_gene_heatmap(
            adata,
            trajectory_genes,
            output_dir=figures_dir,
            pseudotime_key="dpt_pseudotime",
            n_genes=30,
            title="Trajectory-Associated Genes",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Trajectory gene heatmap failed: {e}")

    return figures


def write_pseudotime_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
    top_genes: pd.DataFrame,
) -> None:
    """Write pseudotime analysis report."""
    header = generate_report_header(
        title="Single-Cell Pseudotime Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Root Cluster": str(params.get("root_cluster", "auto")),
            "N Clusters": str(summary.get("n_clusters", "N/A")),
            "Trajectory Genes": str(summary.get("n_trajectory_genes", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Root cluster**: {params.get('root_cluster', 'auto-detected')}",
        f"- **Root cell index**: {summary.get('root_cell', 'N/A')}",
        f"- **Number of clusters**: {summary.get('n_clusters', 'N/A')}",
        f"- **Trajectory genes found**: {summary.get('n_trajectory_genes', 0)}",
        f"- **Pseudotime range**: [{summary.get('pseudotime_min', 0):.3f}, {summary.get('pseudotime_max', 1):.3f}]",
        "",
        "## Methods\n",
        "### PAGA (Partition-based Graph Abstraction)",
        "PAGA estimates connectivity between clusters by quantifying the connectivity",
        "of the underlying single-cell graph at each cluster resolution.\n",
        "### Diffusion Map",
        "Diffusion maps provide a non-linear dimensionality reduction that preserves",
        "the underlying manifold structure of the data.\n",
        "### DPT (Diffusion Pseudotime)",
        "DPT uses random walks on the diffusion graph to estimate pseudotemporal",
        "ordering of cells from a root cell.\n",
        "",
        "## Top Trajectory Genes\n",
    ]

    # Add top genes table
    body_lines.append("| Gene | Correlation | P-value |")
    body_lines.append("|------|-------------|---------|")
    for _, row in top_genes.head(20).iterrows():
        gene = row.get("gene", "N/A")
        corr = row.get("correlation", 0)
        pval = row.get("pvalue", 1)
        body_lines.append(f"| {gene} | {corr:.3f} | {pval:.2e} |")
    body_lines.append("")

    body_lines.extend([
        "## Parameters\n",
        f"- `--cluster-key`: {params.get('cluster_key', 'leiden')}",
        f"- `--root-cluster`: {params.get('root_cluster', 'auto')}",
        f"- `--n-dcs`: {params.get('n_dcs', 10)}",
        f"- `--n-genes`: {params.get('n_genes', 50)}",
        "",
        "## Output Files\n",
        "- `adata_with_trajectory.h5ad` — AnnData with pseudotime and diffusion map",
        "- `figures/paga_graph.png` — PAGA connectivity graph",
        "- `figures/pseudotime_umap.png` — Pseudotime on UMAP",
        "- `figures/diffusion_components.png` — Diffusion map components",
        "- `figures/trajectory_gene_heatmap.png` — Heatmap of trajectory genes",
        "- `tables/trajectory_genes.csv` — All trajectory-associated genes",
        "",
        "## Interpretation\n",
        "- **Pseudotime** represents the inferred temporal ordering (0 = root, 1 = terminal)",
        "- **PAGA edges** show significant connectivity between clusters",
        "- **Trajectory genes** are correlated with pseudotime and may drive transitions",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with trajectory structure."""
    import scanpy as sc

    logger.info("Generating demo data with trajectory structure...")

    try:
        adata = sc.datasets.pbmc3k()
        # Quick preprocessing
        sc.pp.filter_cells(adata, min_genes=200)
        sc.pp.filter_genes(adata, min_cells=3)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        sc.pp.pca(adata)
        sc.pp.neighbors(adata)

        # Try leiden clustering
        try:
            sc.tl.leiden(adata, resolution=0.8)
        except ImportError:
            logger.warning("leidenalg not installed, using kmeans")
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
            adata.obs['leiden'] = pd.Categorical(
                kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str)
            )

        logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes, {adata.obs['leiden'].nunique()} clusters")
    except Exception as e:
        logger.warning(f"Failed to load pbmc3k: {e}. Generating synthetic data.")
        np.random.seed(42)
        n_cells, n_genes = 500, 1000
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))
        adata = sc.AnnData(
            X=counts.astype(np.float32),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.pca(adata)
        sc.pp.neighbors(adata)

        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str))

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Pseudotime Analysis")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--cluster-key", default="leiden", help="Cluster key (default: leiden)")
    parser.add_argument("--root-cluster", default=None, help="Root cluster for pseudotime")
    parser.add_argument("--root-cell", type=int, default=None, help="Root cell index")
    parser.add_argument("--n-dcs", type=int, default=10, help="Number of diffusion components")
    parser.add_argument("--n-genes", type=int, default=50, help="Number of trajectory genes")
    parser.add_argument("--analysis-method", default="dpt", choices=list(METHOD_REGISTRY.keys()),
                        help="Trajectory analysis method (default: dpt)")
    parser.add_argument("--method", default="pearson", choices=["pearson", "spearman"],
                        help="Correlation method for trajectory genes")
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

    # Check cluster key
    if args.cluster_key not in adata.obs.columns:
        logger.error(f"Cluster key '{args.cluster_key}' not found in adata.obs")
        logger.info(f"Available columns: {list(adata.obs.columns)}")
        raise ValueError(f"Column '{args.cluster_key}' not found")

    # Ensure neighbors are computed
    import scanpy as sc
    if "neighbors" not in adata.uns:
        logger.info("Computing neighbor graph...")
        sc.pp.neighbors(adata)

    # Validate analysis method & check dependencies
    analysis_method = validate_method_choice(args.analysis_method, METHOD_REGISTRY)

    # Parameters
    params = {
        "analysis_method": analysis_method,
        "cluster_key": args.cluster_key,
        "root_cluster": args.root_cluster,
        "root_cell": args.root_cell,
        "n_dcs": args.n_dcs,
        "n_genes": args.n_genes,
        "method": args.method,
    }

    # Step 1: PAGA analysis
    logger.info("Running PAGA analysis...")
    paga_result = sc_traj.run_paga_analysis(adata, cluster_key=args.cluster_key)

    # Step 2: Diffusion map
    logger.info("Running diffusion map...")
    diffmap_result = sc_traj.run_diffusion_map(adata, n_comps=max(15, args.n_dcs + 5))

    # Step 3: DPT pseudotime
    logger.info("Running DPT pseudotime...")
    dpt_result = sc_traj.run_dpt_pseudotime(
        adata,
        root_cell_indices=[args.root_cell] if args.root_cell is not None else None,
        root_cluster=args.root_cluster,
        cluster_key=args.cluster_key,
        n_dcs=args.n_dcs,
    )

    # Step 4: Find trajectory genes
    logger.info("Finding trajectory genes...")
    trajectory_genes = sc_traj.find_trajectory_genes(
        adata,
        pseudotime_key="dpt_pseudotime",
        n_genes=args.n_genes,
        method=args.method,
    )

    # Summary
    n_clusters = adata.obs[args.cluster_key].nunique()
    summary = {
        "n_clusters": int(n_clusters),
        "n_trajectory_genes": len(trajectory_genes),
        "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
        "pseudotime_min": float(adata.obs["dpt_pseudotime"].min()),
        "pseudotime_max": float(adata.obs["dpt_pseudotime"].max()),
        "n_diffusion_components": diffmap_result["diffmap"].shape[1],
    }

    logger.info(f"Found {len(trajectory_genes)} trajectory-associated genes")

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_trajectory_figures(adata, trajectory_genes, output_dir)

    # Export tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    trajectory_genes.to_csv(tables_dir / "trajectory_genes.csv", index=False)
    logger.info(f"  Saved: tables/trajectory_genes.csv")

    # Write report
    logger.info("Writing report...")
    write_pseudotime_report(output_dir, summary, params, input_file, trajectory_genes)

    # Save data
    output_h5ad = output_dir / "adata_with_trajectory.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_pseudotime.py --output {output_dir} --cluster-key {args.cluster_key}"
    if input_file:
        cmd += f" --input {input_file}"
    if args.root_cluster:
        cmd += f" --root-cluster {args.root_cluster}"
    cmd += f" --n-dcs {args.n_dcs} --n-genes {args.n_genes} --method {args.method}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Root cluster: {params.get('root_cluster', 'auto')}")
    print(f"  Clusters: {n_clusters}")
    print(f"  Trajectory genes: {len(trajectory_genes)}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()

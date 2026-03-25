#!/usr/bin/env python3
"""Single-Cell Preprocessing - Scanpy or Seurat/SCTransform workflows."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_result_json
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.r_bridge import run_seurat_preprocessing
from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-preprocessing"
SKILL_VERSION = "0.4.0"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scanpy": MethodConfig(
        name="scanpy",
        description="Scanpy preprocessing workflow",
        dependencies=("scanpy",),
    ),
    "seurat": MethodConfig(
        name="seurat",
        description="Seurat LogNormalize workflow (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
    "sctransform": MethodConfig(
        name="sctransform",
        description="Seurat SCTransform workflow (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
}

DEFAULT_METHOD = "scanpy"


def preprocess_scanpy(
    adata,
    *,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
):
    """Minimal Scanpy preprocessing pipeline."""
    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)

    adata.layers["counts"] = adata.X.copy()
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)

    adata.var["mt"] = adata.var_names.str.startswith("MT-") | adata.var_names.str.startswith("mt-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True)
    adata = adata[adata.obs.pct_counts_mt < max_mt_pct, :].copy()
    adata.layers["counts"] = adata.X.copy()

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=n_top_hvg, flavor="seurat")
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=n_pcs, svd_solver="arpack")
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, adata.obsm["X_pca"].shape[1]))
    sc.tl.umap(adata)
    sc.tl.leiden(adata, resolution=leiden_resolution)

    return adata


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate QC and analysis figures."""
    figures = []

    try:
        qc_cols = ["n_genes_by_counts", "total_counts", "pct_counts_mt"]
        if all(col in adata.obs for col in qc_cols):
            sc.pl.violin(adata, qc_cols, multi_panel=True, show=False)
            p = save_figure(plt.gcf(), output_dir, "qc_violin.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("QC violin plot failed: %s", exc)

    try:
        required_hvg_cols = {"highly_variable", "means", "dispersions", "dispersions_norm"}
        if required_hvg_cols.issubset(set(adata.var.columns)):
            sc.pl.highly_variable_genes(adata, show=False)
            p = save_figure(plt.gcf(), output_dir, "hvg_plot.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("HVG plot failed: %s", exc)

    try:
        if "X_pca" in adata.obsm and "pca" in adata.uns and "variance_ratio" in adata.uns["pca"]:
            sc.pl.pca_variance_ratio(adata, n_pcs=min(50, adata.obsm["X_pca"].shape[1]), show=False)
            p = save_figure(plt.gcf(), output_dir, "pca_variance.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("PCA variance plot failed: %s", exc)

    try:
        cluster_key = "leiden" if "leiden" in adata.obs else "seurat_clusters"
        if "X_umap" in adata.obsm and cluster_key in adata.obs:
            sc.pl.umap(adata, color=cluster_key, show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_clusters.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("UMAP plot failed: %s", exc)

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Single-Cell Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
            "Clusters": str(summary["n_clusters"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells after QC**: {summary['n_cells']}",
        f"- **Genes after QC**: {summary['n_genes']}",
        f"- **HVGs selected**: {summary['n_hvg']}",
        f"- **Clusters**: {summary['n_clusters']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    cluster_counts = summary.get("cluster_counts", {})
    if cluster_counts:
        df = pd.DataFrame(
            [
                {"cluster": k, "n_cells": v, "proportion": round(v / summary["n_cells"] * 100, 2)}
                for k, v in cluster_counts.items()
            ]
        )
        df.to_csv(tables_dir / "cluster_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_preprocess.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def get_demo_data():
    logger.info("Generating demo single-cell data")
    demo_path = _PROJECT_ROOT / "examples" / "pbmc3k.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), None
    logger.warning("Local demo data not found, downloading from scanpy")
    return sc.datasets.pbmc3k(), None


def build_summary(adata, method: str) -> dict:
    cluster_key = "leiden" if "leiden" in adata.obs else "seurat_clusters"
    n_hvg = int(adata.var["highly_variable"].sum()) if "highly_variable" in adata.var else 0
    cluster_counts = adata.obs[cluster_key].astype(str).value_counts().to_dict() if cluster_key in adata.obs else {}
    return {
        "method": method,
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_hvg": n_hvg,
        "n_clusters": len(cluster_counts),
        "cluster_counts": {str(k): int(v) for k, v in cluster_counts.items()},
    }


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Preprocessing")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--min-genes", type=int, default=200)
    parser.add_argument("--min-cells", type=int, default=3)
    parser.add_argument("--max-mt-pct", type=float, default=20.0)
    parser.add_argument("--n-top-hvg", type=int, default=2000)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--leiden-resolution", type=float, default=1.0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    params = {
        "method": method,
        "min_genes": args.min_genes,
        "min_cells": args.min_cells,
        "max_mt_pct": args.max_mt_pct,
        "n_top_hvg": args.n_top_hvg,
        "n_pcs": args.n_pcs,
        "n_neighbors": args.n_neighbors,
        "leiden_resolution": args.leiden_resolution,
    }

    if method == "scanpy":
        adata = preprocess_scanpy(
            adata,
            min_genes=args.min_genes,
            min_cells=args.min_cells,
            max_mt_pct=args.max_mt_pct,
            n_top_hvg=args.n_top_hvg,
            n_pcs=args.n_pcs,
            n_neighbors=args.n_neighbors,
            leiden_resolution=args.leiden_resolution,
        )
    else:
        adata = run_seurat_preprocessing(
            adata,
            workflow=method,
            min_genes=args.min_genes,
            min_cells=args.min_cells,
            max_mt_pct=args.max_mt_pct,
            n_top_hvg=args.n_top_hvg,
            n_pcs=args.n_pcs,
            n_neighbors=args.n_neighbors,
            leiden_resolution=args.leiden_resolution,
        )

    summary = build_summary(adata, method)
    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)
    store_analysis_metadata(adata, SKILL_NAME, method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Preprocessing complete: {summary['n_cells']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()

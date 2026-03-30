#!/usr/bin/env python3
"""Single-Cell Preprocessing - Scanpy or Seurat/SCTransform workflows."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
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
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_result_json
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice

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
        dependencies=(),
    ),
    "sctransform": MethodConfig(
        name="sctransform",
        description="Seurat SCTransform workflow (R)",
        dependencies=(),
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


def _choose_counts_matrix(adata):
    """Return the best available raw-count-like matrix for R-backed workflows."""
    if "counts" in adata.layers:
        return adata.layers["counts"]
    if adata.raw is not None and adata.raw.shape == adata.shape:
        return adata.raw.X
    return adata.X


def _build_export_adata(adata):
    """Build an AnnData export where ``X`` contains counts for the R script."""
    export_adata = adata.copy()
    export_adata.obs_names_make_unique()
    export_adata.var_names_make_unique()
    export_adata.X = _choose_counts_matrix(export_adata).copy()
    return export_adata


def _load_seurat_result(
    export_adata,
    *,
    output_dir: Path,
    workflow: str,
    n_neighbors: int,
    n_pcs: int,
):
    """Load Seurat CSV outputs back into a standard AnnData object."""
    obs_df = pd.read_csv(output_dir / "obs.csv", index_col=0)
    pca_df = pd.read_csv(output_dir / "pca.csv", index_col=0)
    umap_df = pd.read_csv(output_dir / "umap.csv", index_col=0)
    hvg_df = pd.read_csv(output_dir / "hvg.csv")
    norm_df = pd.read_csv(output_dir / "X_norm.csv", index_col=0)

    info = {}
    info_path = output_dir / "info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))

    norm_df = norm_df.T
    norm_df.index = norm_df.index.astype(str)
    norm_df.columns = norm_df.columns.astype(str)
    obs_df.index = obs_df.index.astype(str)
    pca_df.index = pca_df.index.astype(str)
    umap_df.index = umap_df.index.astype(str)

    ordered_cells = [cell for cell in norm_df.index if cell in export_adata.obs_names]
    ordered_genes = [gene for gene in norm_df.columns if gene in export_adata.var_names]
    if not ordered_cells or not ordered_genes:
        raise RuntimeError("Seurat preprocessing returned no overlapping cells or genes")

    norm_df = norm_df.loc[ordered_cells, ordered_genes]
    obs_base = export_adata.obs.loc[ordered_cells].copy()
    var_base = export_adata.var.loc[ordered_genes].copy()

    combined_obs = obs_base.join(obs_df, how="left", rsuffix="_seurat")
    if "seurat_clusters" in combined_obs:
        combined_obs["seurat_clusters"] = combined_obs["seurat_clusters"].astype(str)
        combined_obs["leiden"] = combined_obs["seurat_clusters"]
    if "nFeature_RNA" in combined_obs and "n_genes_by_counts" not in combined_obs:
        combined_obs["n_genes_by_counts"] = pd.to_numeric(combined_obs["nFeature_RNA"], errors="coerce")
    if "nCount_RNA" in combined_obs and "total_counts" not in combined_obs:
        combined_obs["total_counts"] = pd.to_numeric(combined_obs["nCount_RNA"], errors="coerce")
    if "percent.mt" in combined_obs and "pct_counts_mt" not in combined_obs:
        combined_obs["pct_counts_mt"] = pd.to_numeric(combined_obs["percent.mt"], errors="coerce")
    combined_obs["preprocess_method"] = workflow

    hvg_set = set()
    if "gene" in hvg_df.columns:
        hvg_set = {str(gene) for gene in hvg_df["gene"].dropna().astype(str)}
    var_base["highly_variable"] = [gene in hvg_set for gene in var_base.index.astype(str)]

    result = sc.AnnData(X=norm_df.to_numpy(), obs=combined_obs, var=var_base)
    result.layers["counts"] = export_adata[ordered_cells, ordered_genes].X.copy()

    pca_aligned = pca_df.reindex(ordered_cells)
    umap_aligned = umap_df.reindex(ordered_cells)
    if pca_aligned.isna().any().any():
        raise RuntimeError("Seurat preprocessing returned PCA rows that do not align with exported cells")
    if umap_aligned.isna().any().any():
        raise RuntimeError("Seurat preprocessing returned UMAP rows that do not align with exported cells")
    result.obsm["X_pca"] = pca_aligned.to_numpy(dtype=float)
    result.obsm["X_umap"] = umap_aligned.to_numpy(dtype=float)

    if result.obsm["X_pca"].size:
        variance = np.var(result.obsm["X_pca"], axis=0, ddof=1)
        variance = np.clip(variance, a_min=0.0, a_max=None)
        total = float(variance.sum())
        result.uns["pca"] = {
            "variance": variance,
            "variance_ratio": (variance / total) if total > 0 else variance,
        }

    if result.obsm["X_pca"].shape[1] > 0:
        try:
            sc.pp.neighbors(
                result,
                use_rep="X_pca",
                n_neighbors=n_neighbors,
                n_pcs=min(n_pcs, result.obsm["X_pca"].shape[1]),
            )
        except Exception as exc:
            logger.warning("Neighbor graph reconstruction after Seurat failed: %s", exc)

    result.uns["seurat_info"] = info
    return result


def run_seurat_preprocessing(
    adata,
    *,
    workflow: str,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
):
    """Run the Seurat / SCTransform preprocessing backend via the shared R script."""
    required_packages = ["Seurat", "SingleCellExperiment", "zellkonverter"]
    if workflow == "sctransform":
        required_packages.append("sctransform")
    validate_r_environment(required_r_packages=required_packages)

    export_adata = _build_export_adata(adata)
    logger.info("Running R-backed %s preprocessing on %d cells x %d genes", workflow, export_adata.n_obs, export_adata.n_vars)

    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_sc_preprocess_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        r_output_dir = tmpdir / "output"
        basilisk_dir = tmpdir / "basilisk"
        r_output_dir.mkdir(parents=True, exist_ok=True)
        basilisk_dir.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)

        runner.run_script(
            "sc_seurat_preprocess.R",
            args=[
                str(input_h5ad),
                str(r_output_dir),
                workflow,
                str(min_genes),
                str(min_cells),
                str(max_mt_pct),
                str(n_top_hvg),
                str(n_pcs),
                str(n_neighbors),
                str(leiden_resolution),
            ],
            expected_outputs=["obs.csv", "pca.csv", "umap.csv", "hvg.csv", "X_norm.csv", "info.json"],
            output_dir=r_output_dir,
            env={"BASILISK_EXTERNAL_DIR": str(basilisk_dir)},
        )

        return _load_seurat_result(
            export_adata,
            output_dir=r_output_dir,
            workflow=workflow,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
        )


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

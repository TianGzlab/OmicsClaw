#!/usr/bin/env python3
"""Single-Cell Batch Integration - Python and R-backed methods."""

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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.singlecell.adata_utils import ensure_pca, store_analysis_metadata
from omicsclaw.singlecell.method_config import MethodConfig, validate_method_choice, check_data_requirements
from omicsclaw.singlecell.r_bridge import run_seurat_integration
from omicsclaw.singlecell.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-integrate"
SKILL_VERSION = "0.4.0"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "harmony": MethodConfig(
        name="harmony",
        description="Harmony — fast linear batch correction (harmony-pytorch)",
        dependencies=("harmony-pytorch",),
    ),
    "scvi": MethodConfig(
        name="scvi",
        description="scVI — variational autoencoder integration",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "scanvi": MethodConfig(
        name="scanvi",
        description="scANVI — semi-supervised scVI",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "bbknn": MethodConfig(
        name="bbknn",
        description="BBKNN — batch-balanced k-nearest neighbors",
        dependencies=("bbknn",),
    ),
    "fastmnn": MethodConfig(
        name="fastmnn",
        description="fastMNN — batchelor mutual nearest neighbors (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
    "seurat_cca": MethodConfig(
        name="seurat_cca",
        description="Seurat CCA integration (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
    "seurat_rpca": MethodConfig(
        name="seurat_rpca",
        description="Seurat RPCA integration (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
    "scanorama": MethodConfig(
        name="scanorama",
        description="Scanorama — panoramic stitching integration",
        dependencies=("scanorama",),
    ),
}

DEFAULT_METHOD = "harmony"


def integrate_harmony(adata, batch_key="batch", **kwargs):
    from harmony import harmonize

    ensure_pca(adata)
    logger.info("Running Harmony on %d batches", adata.obs[batch_key].nunique())
    Z = harmonize(adata.obsm["X_pca"], adata.obs, batch_key=batch_key)
    adata.obsm["X_harmony"] = Z
    sc.pp.neighbors(adata, use_rep="X_harmony")
    sc.tl.umap(adata)
    return {"method": "harmony", "embedding_key": "X_harmony", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scvi(adata, batch_key="batch", n_epochs=None, use_gpu=True, **kwargs):
    import scvi

    scvi.model.SCVI.setup_anndata(adata, batch_key=batch_key)
    model = scvi.model.SCVI(adata)
    train_kwargs = {}
    if n_epochs is not None:
        train_kwargs["max_epochs"] = n_epochs
    model.train(**train_kwargs)

    adata.obsm["X_scvi"] = model.get_latent_representation()
    sc.pp.neighbors(adata, use_rep="X_scvi")
    sc.tl.umap(adata)
    return {"method": "scvi", "embedding_key": "X_scvi", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scanvi(adata, batch_key="batch", n_epochs=None, use_gpu=True, **kwargs):
    import scvi

    scvi.model.SCVI.setup_anndata(adata, batch_key=batch_key)
    scvi_model = scvi.model.SCVI(adata)
    scvi_model.train(max_epochs=max(100, (n_epochs or 400) // 2))

    model = scvi.model.SCANVI.from_scvi_model(scvi_model, unlabeled_category="Unknown")
    model.train(max_epochs=n_epochs or 200)

    adata.obsm["X_scanvi"] = model.get_latent_representation()
    sc.pp.neighbors(adata, use_rep="X_scanvi")
    sc.tl.umap(adata)
    return {"method": "scanvi", "embedding_key": "X_scanvi", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_bbknn(adata, batch_key="batch", **kwargs):
    import bbknn

    ensure_pca(adata)
    logger.info("Running BBKNN on %d batches", adata.obs[batch_key].nunique())
    bbknn.bbknn(adata, batch_key=batch_key)
    sc.tl.umap(adata)
    return {"method": "bbknn", "embedding_key": "X_pca", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scanorama(adata, batch_key="batch", **kwargs):
    import scanorama

    logger.info("Running Scanorama on %d batches", adata.obs[batch_key].nunique())
    batches = []
    for batch in adata.obs[batch_key].unique():
        batches.append(adata[adata.obs[batch_key] == batch].copy())
    corrected = scanorama.correct_scanpy(batches, return_dimred=True)
    adata.obsm["X_scanorama"] = np.concatenate(corrected[1])
    sc.pp.neighbors(adata, use_rep="X_scanorama")
    sc.tl.umap(adata)
    return {"method": "scanorama", "embedding_key": "X_scanorama", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_r_method(adata, *, method: str, batch_key: str):
    updated = run_seurat_integration(adata, method=method, batch_key=batch_key)
    embedding_key = f"X_{method}"
    if embedding_key in updated.obsm:
        sc.pp.neighbors(updated, use_rep=embedding_key)
        if "X_umap" not in updated.obsm:
            sc.tl.umap(updated)
    return updated, {"method": method, "embedding_key": embedding_key, "n_batches": int(updated.obs[batch_key].nunique())}


_METHOD_DISPATCH = {
    "harmony": integrate_harmony,
    "scvi": integrate_scvi,
    "scanvi": integrate_scanvi,
    "bbknn": integrate_bbknn,
    "scanorama": integrate_scanorama,
}


def generate_figures(adata, output_dir: Path, batch_key: str) -> list[str]:
    figures = []
    try:
        if "X_umap" in adata.obsm:
            sc.pl.umap(adata, color=batch_key, show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_batches.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("Batch UMAP plot failed: %s", exc)

    try:
        if "X_umap" in adata.obsm and "leiden" in adata.obs:
            sc.pl.umap(adata, color="leiden", show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_clusters.png")
            figures.append(str(p))
            plt.close()
    except Exception as exc:
        logger.warning("Cluster UMAP plot failed: %s", exc)
    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Single-Cell Batch Integration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Batches": str(summary["n_batches"]),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Batches**: {summary['n_batches']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Embedding key**: {summary['embedding_key']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_integrate.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Batch Integration")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--batch-key", default="batch")
    parser.add_argument("--n-epochs", type=int, default=None)
    parser.add_argument("--no-gpu", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_raw.h5ad"
        if demo_path.exists():
            adata = sc.read_h5ad(demo_path)
        else:
            logger.warning("Local demo data not found, downloading from scanpy")
            adata = sc.datasets.pbmc3k()
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        sc.pp.pca(adata)
        adata.obs[args.batch_key] = np.random.choice(["batch1", "batch2"], adata.n_obs)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    cfg = METHOD_REGISTRY[method]
    check_data_requirements(adata, cfg)

    kwargs = {"batch_key": args.batch_key}
    if cfg.supports_gpu:
        kwargs["use_gpu"] = not args.no_gpu
    if args.n_epochs is not None and "torch" in cfg.dependencies:
        kwargs["n_epochs"] = args.n_epochs

    if method in {"fastmnn", "seurat_cca", "seurat_rpca"}:
        adata, summary = integrate_r_method(adata, method=method, batch_key=args.batch_key)
    else:
        summary = _METHOD_DISPATCH[method](adata, **kwargs)

    summary["n_cells"] = int(adata.n_obs)
    params = {"method": method, "batch_key": args.batch_key}
    if args.n_epochs is not None:
        params["n_epochs"] = args.n_epochs

    generate_figures(adata, output_dir, args.batch_key)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)
    store_analysis_metadata(adata, SKILL_NAME, method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Integration complete: {summary['method']} on {summary['n_batches']} batches")


if __name__ == "__main__":
    main()

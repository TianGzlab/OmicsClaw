#!/usr/bin/env python3
"""Spatial Genes — find spatially variable genes via multiple methods.

Supported methods:
  - morans:    Moran's I spatial autocorrelation via Squidpy (default)
  - spatialde: Gaussian process regression via SpatialDE2
  - sparkx:    Non-parametric kernel test via SPARK-X in R
  - flashs:    Randomized kernel approximation (Python native, fast)

Usage:
    python spatial_genes.py --input <processed.h5ad> --output <dir>
    python spatial_genes.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer, generate_report_header, write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.genes import METHOD_DISPATCH, SUPPORTED_METHODS
from skills.spatial._lib.viz import VizParams, plot_features, plot_spatial_stats
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-genes"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, top_genes: list[str]) -> list[str]:
    figures = []
    spatial_key = get_spatial_key(adata)

    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    genes_to_plot = [g for g in top_genes[:8] if g in adata.var_names]

    if genes_to_plot and spatial_key is not None:
        try:
            fig = plot_features(adata, VizParams(
                feature=genes_to_plot, basis="spatial", colormap="magma",
                title="Top Spatially Variable Genes", show_colorbar=True,
            ))
            p = save_figure(fig, output_dir, "top_svg_spatial.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate SVG spatial plot: %s", exc)

    if "moranI" in adata.uns:
        try:
            fig = plot_spatial_stats(adata, subtype="moran")
            p = save_figure(fig, output_dir, "moran_ranking.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate Moran ranking: %s", exc)

    if genes_to_plot and "X_umap" in adata.obsm:
        try:
            fig = plot_features(adata, VizParams(
                feature=genes_to_plot[:6], basis="umap", colormap="magma",
                title="Top SVGs on UMAP", show_colorbar=True,
            ))
            p = save_figure(fig, output_dir, "top_svg_umap.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate SVG UMAP: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, svg_df: pd.DataFrame, summary: dict,
                 input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Spatially Variable Genes Report", skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary["method"], "FDR threshold": str(summary["fdr_threshold"])},
    )

    body_lines = ["## Summary\n",
        f"- **Method**: {summary['method']}", f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Significant SVGs** (FDR < {summary['fdr_threshold']}): {summary['n_significant']}",
        f"- **Top genes reported**: {summary['n_top_reported']}"]

    body_lines.extend(["", "### Top spatially variable genes\n"])
    has_pval = "pval_norm" in svg_df.columns
    if has_pval:
        body_lines.extend(["| Rank | Gene | Moran's I | p-value |", "|------|------|-----------|---------|"])
    else:
        body_lines.extend(["| Rank | Gene | Score |", "|------|------|-------|"])

    for rank, gene in enumerate(summary["top_genes"][:20], 1):
        if gene in svg_df.index:
            row = svg_df.loc[gene]
            if has_pval:
                body_lines.append(f"| {rank} | {gene} | {row['I']:.4f} | {row.get('pval_norm', float('nan')):.2e} |")
            else:
                body_lines.append(f"| {rank} | {gene} | {row['I']:.4f} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary, data={"params": params, **summary}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    csv_df = svg_df.copy()
    if "gene" not in csv_df.columns:
        csv_df["gene"] = csv_df.index
    cols = ["gene", "I"] + [c for c in ["pval_norm", "var_norm", "pval_z_sim"] if c in csv_df.columns]
    csv_df[[c for c in cols if c in csv_df.columns]].to_csv(tables_dir / "svg_results.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_genes.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data(output_dir: Path):
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="svg_demo_") as tmpdir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmpdir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        h5ad_path = Path(tmpdir) / "processed.h5ad"
        adata = sc.read_h5ad(h5ad_path)
        dest = output_dir / "processed.h5ad"
        if not dest.exists():
            import shutil
            shutil.copy2(h5ad_path, dest)
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Genes — SVG detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="morans")
    parser.add_argument("--n-top-genes", type=int, default=20)
    parser.add_argument("--fdr-threshold", type=float, default=0.05)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data(output_dir)
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr); sys.exit(1)

    params = {"method": args.method, "n_top_genes": args.n_top_genes, "fdr_threshold": args.fdr_threshold}

    run_fn = METHOD_DISPATCH[args.method]
    svg_df, summary = run_fn(adata, n_top_genes=args.n_top_genes, fdr_threshold=args.fdr_threshold)

    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    generate_figures(adata, output_dir, summary.get("top_genes", []))
    write_report(output_dir, svg_df, summary, input_file, params)

    adata.write_h5ad(output_dir / "processed.h5ad")
    print(f"SVG detection complete: {summary['n_significant']} significant genes ({summary['method']})")


if __name__ == "__main__":
    main()

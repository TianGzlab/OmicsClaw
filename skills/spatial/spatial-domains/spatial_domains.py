#!/usr/bin/env python3
"""Spatial Domains — identify tissue regions and spatial niches.

Supports multiple algorithms with distinct strengths:
  - leiden:   Graph-based clustering with spatial-weighted neighbors (default, fast)
  - louvain:  Classic graph-based clustering (requires: pip install louvain)
  - spagcn:   Spatial Graph Convolutional Network (integrates histology)
  - stagate:  Graph attention auto-encoder (PyTorch Geometric)
  - graphst:  Self-supervised contrastive learning (PyTorch)
  - banksy:   Explicit spatial feature augmentation (interpretable)

Usage:
    python spatial_domains.py --input <preprocessed.h5ad> --output <dir>
    python spatial_domains.py --demo --output <dir>
    python spatial_domains.py --input <file> --method spagcn --n-domains 7 --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
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
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.domains import (
    SUPPORTED_METHODS,
    dispatch_method,
    refine_spatial_domains,
)
from skills.spatial._lib.viz import VizParams, plot_features
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-domains"
SKILL_VERSION = "0.4.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate spatial domain map and UMAP domain plot."""
    figures = []
    spatial_key = get_spatial_key(adata)

    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    domain_col = "spatial_domain" if "spatial_domain" in adata.obs.columns else None
    if domain_col is None:
        logger.warning("No 'spatial_domain' column found; skipping domain figures")
        return figures

    if spatial_key is not None:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=domain_col, basis="spatial",
                    colormap="tab20", title="Spatial Domains", show_legend=True,
                ),
            )
            p = save_figure(fig, output_dir, "spatial_domains.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate spatial domain figure: %s", exc)

    if "X_umap" not in adata.obsm:
        try:
            sc.tl.umap(adata)
        except Exception as exc:
            logger.warning("Could not compute UMAP: %s", exc)

    if "X_umap" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=domain_col, basis="umap",
                    colormap="tab20", title="UMAP — Spatial Domains", show_legend=True,
                ),
            )
            p = save_figure(fig, output_dir, "umap_domains.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate UMAP domain figure: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report.md, result.json, tables, reproducibility."""
    header = generate_report_header(
        title="Spatial Domain Identification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Domains identified": str(summary["n_domains"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Domains identified**: {summary['n_domains']}",
    ]
    if "resolution" in summary:
        body_lines.append(f"- **Leiden resolution**: {summary['resolution']}")
    if "n_domains_requested" in summary:
        body_lines.append(f"- **Domains requested**: {summary['n_domains_requested']}")

    body_lines.extend([
        "",
        "### Domain sizes\n",
        "| Domain | Cells | Proportion |",
        "|--------|-------|------------|",
    ])

    total_cells = sum(summary["domain_counts"].values())
    for domain, count in sorted(
        summary["domain_counts"].items(),
        key=lambda x: int(x[0]) if x[0].isdigit() else x[0],
    ):
        pct = count / total_cells * 100 if total_cells > 0 else 0
        body_lines.append(f"| {domain} | {count} | {pct:.1f}% |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        if v is not None:
            body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary, data={"params": params, **summary}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    rows = []
    for domain, count in summary["domain_counts"].items():
        pct = count / total_cells * 100 if total_cells > 0 else 0
        rows.append({"domain": domain, "n_cells": count, "proportion": round(pct, 2)})
    pd.DataFrame(rows).to_csv(tables_dir / "domain_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_domains.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None and not isinstance(v, bool):
            cmd += f" --{k.replace('_', '-')} {v}"
        elif isinstance(v, bool) and v:
            cmd += f" --{k.replace('_', '-')}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["scanpy", "anndata", "squidpy", "numpy", "pandas", "matplotlib", "torch", "banksy", "SpaGCN"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium
    return generate_demo_visium(), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Domains — multi-method tissue region identification",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="leiden")
    parser.add_argument("--n-domains", type=int, default=None)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--spatial-weight", type=float, default=0.3)
    # STAGATE network params
    parser.add_argument("--rad-cutoff", type=float, default=None)
    parser.add_argument("--k-nn", type=int, default=6)
    # BANKSY param
    parser.add_argument("--lambda-param", type=float, default=0.2)
    parser.add_argument("--refine", action="store_true", default=False)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
        if "X_pca" not in adata.obsm:
            logger.warning(
                "Input data lacks 'X_pca' in obsm. "
                "Some internal spatial domain tools require dimension reduction first."
            )
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Dispatch to the chosen algorithm via _lib
    summary = dispatch_method(
        args.method, adata,
        resolution=args.resolution,
        spatial_weight=args.spatial_weight,
        n_domains=args.n_domains,  # Critical: Do NOT mask with 'or 7'
        rad_cutoff=args.rad_cutoff,
        k_nn=args.k_nn,
        lambda_param=args.lambda_param,
    )

    if args.refine:
        logger.info("Applying spatial KNN refinement ...")
        refined = refine_spatial_domains(adata)
        adata.obs["spatial_domain"] = pd.Categorical(refined)
        summary["domain_counts"] = adata.obs["spatial_domain"].value_counts().to_dict()
        summary["n_domains"] = adata.obs["spatial_domain"].nunique()
        summary["refined"] = True

    params = {"method": args.method, "resolution": args.resolution,
              "spatial_weight": args.spatial_weight, "refine": args.refine}
    if args.n_domains is not None:
        params["n_domains"] = args.n_domains
    if args.method == "stagate":
        params["rad_cutoff"] = args.rad_cutoff
        params["k_nn"] = args.k_nn
    if args.method == "banksy":
        params["lambda_param"] = args.lambda_param

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Domain identification complete: {summary['n_domains']} domains ({summary['method']})")


if __name__ == "__main__":
    main()

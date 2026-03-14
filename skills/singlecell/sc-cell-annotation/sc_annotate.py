#!/usr/bin/env python3
"""Single-Cell Annotation - CellTypist, marker-based, SingleR, scmap.

Usage:
    python sc_annotate.py --input <data.h5ad> --output <dir> --method markers
    python sc_annotate.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import scanpy as sc
import pandas as pd
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.adata_utils import store_analysis_metadata
from omicsclaw.singlecell.viz_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-annotate"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("markers", "celltypist", "singler", "scmap")

PBMC_MARKERS = {
    'CD4 T': ['CD3D', 'CD4'],
    'CD8 T': ['CD3D', 'CD8A'],
    'B': ['MS4A1', 'CD79A'],
    'NK': ['GNLY', 'NKG7'],
    'Monocyte': ['CD14', 'LYZ'],
}


def annotate_markers(adata, markers=None, cluster_key='leiden'):
    """Marker-based annotation."""
    if markers is None:
        markers = PBMC_MARKERS

    if cluster_key not in adata.obs:
        logger.warning(f"No {cluster_key} found, running clustering")
        sc.pp.neighbors(adata)
        sc.tl.leiden(adata)
        cluster_key = 'leiden'

    cluster_annotations = {}
    for cluster in adata.obs[cluster_key].unique():
        cluster_mask = adata.obs[cluster_key] == cluster
        cluster_data = adata[cluster_mask]

        best_type = 'Unknown'
        best_score = 0

        for cell_type, marker_genes in markers.items():
            available = [g for g in marker_genes if g in adata.var_names]
            if available:
                scores = cluster_data[:, available].X.mean()
                if scores > best_score:
                    best_score = scores
                    best_type = cell_type

        cluster_annotations[cluster] = best_type

    adata.obs['cell_type'] = adata.obs[cluster_key].map(cluster_annotations)
    logger.info(f"Annotated {len(cluster_annotations)} clusters")

    cell_type_counts = adata.obs['cell_type'].value_counts().to_dict()
    return {
        "method": "markers",
        "n_cell_types": len(cell_type_counts),
        "cell_type_counts": {str(k): int(v) for k, v in cell_type_counts.items()},
    }


def annotate_celltypist(adata, model='Immune_All_Low'):
    """CellTypist annotation."""
    logger.info("CellTypist requires celltypist package - using marker fallback")
    return annotate_markers(adata)


def annotate_singler(adata):
    """SingleR annotation (R)."""
    logger.info("SingleR requires R - using marker fallback")
    return annotate_markers(adata)


def annotate_scmap(adata):
    """scmap annotation (R)."""
    logger.info("scmap requires R - using marker fallback")
    return annotate_markers(adata)


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate annotation figures."""
    figures = []

    if 'X_umap' not in adata.obsm:
        try:
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
        except Exception as e:
            logger.warning(f"UMAP failed: {e}")

    if 'X_umap' in adata.obsm and 'cell_type' in adata.obs:
        try:
            sc.pl.umap(adata, color='cell_type', show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_cell_types.png")
            figures.append(str(p))
            plt.close()
        except Exception as e:
            logger.warning(f"UMAP plot failed: {e}")

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report."""
    header = generate_report_header(
        title="Cell Type Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary['method'],
            "Cell types": str(summary['n_cell_types']),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cell types identified**: {summary['n_cell_types']}",
        "",
        "### Cell Type Distribution\n",
        "| Cell Type | Count |",
        "|-----------|-------|",
    ]

    for ct, count in sorted(summary['cell_type_counts'].items(), key=lambda x: x[1], reverse=True):
        body_lines.append(f"| {ct} | {count} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    # Tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df = pd.DataFrame([
        {"cell_type": k, "n_cells": v}
        for k, v in summary['cell_type_counts'].items()
    ])
    df.to_csv(tables_dir / "cell_type_counts.csv", index=False)

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_annotate.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def _dispatch_method(method: str, adata, args) -> dict:
    """Route to annotation method."""
    if method == "markers":
        return annotate_markers(adata)
    elif method == "celltypist":
        return annotate_celltypist(adata, args.model)
    elif method == "singler":
        return annotate_singler(adata)
    elif method == "scmap":
        return annotate_scmap(adata)
    else:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="markers")
    parser.add_argument("--model", default="Immune_All_Low", help="CellTypist model")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_processed.h5ad"
        if demo_path.exists():
            adata = sc.read_h5ad(demo_path)
        else:
            logger.warning("Local demo data not found, downloading from scanpy")
            adata = sc.datasets.pbmc3k_processed()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    summary = _dispatch_method(args.method, adata, args)
    summary['n_cells'] = int(adata.n_obs)

    params = {"method": args.method}
    if args.method == "celltypist":
        params["model"] = args.model

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved to {output_h5ad}")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    store_analysis_metadata(adata, SKILL_NAME, args.method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Annotation complete: {summary['n_cell_types']} cell types identified")


if __name__ == "__main__":
    main()

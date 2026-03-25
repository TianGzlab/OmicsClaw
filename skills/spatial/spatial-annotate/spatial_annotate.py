#!/usr/bin/env python3
"""Spatial Annotate — cell type annotation for spatial transcriptomics.

Supported methods:
  - marker_based: Marker gene scoring (no reference needed, fast, default)
  - tangram:      Deep learning mapping from scRNA-seq reference (tangram-sc)
  - scanvi:       Semi-supervised VAE transfer learning (scvi-tools)
  - cellassign:   Probabilistic marker-based assignment (scvi-tools)

Usage:
    python spatial_annotate.py --input <preprocessed.h5ad> --output <dir>
    python spatial_annotate.py --demo --output <dir>
    python spatial_annotate.py --input <file> --method tangram --reference <sc_ref.h5ad> --output <dir>
"""

from __future__ import annotations

import argparse
import json
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
from skills.spatial._lib.annotation import (
    SUPPORTED_METHODS,
    annotate_cellassign,
    annotate_marker_based,
    annotate_scanvi,
    annotate_tangram,
    get_default_signatures,
)
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-annotate"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate cell type annotation visualizations."""
    import matplotlib.pyplot as plt

    figures = []
    spatial_key = get_spatial_key(adata)

    if "cell_type" not in adata.obs.columns:
        return figures

    # Spatial cell type plot
    try:
        if spatial_key:
            if "spatial" in adata.uns and len(adata.uns["spatial"]) > 0:
                sc.pl.spatial(adata, color="cell_type", show=False)
            else:
                if "X_spatial" not in adata.obsm and spatial_key == "spatial":
                    adata.obsm["X_spatial"] = adata.obsm["spatial"]
                sc.pl.embedding(adata, basis="spatial", color="cell_type", show=False)
            p = save_figure(plt.gcf(), output_dir, "cell_type_spatial.png")
            figures.append(str(p))
            plt.close("all")
    except Exception as e:
        logger.warning("Could not generate spatial annotation plot: %s", e)

    # UMAP cell type plot
    try:
        if "X_umap" not in adata.obsm:
            sc.tl.umap(adata)
        if "X_umap" in adata.obsm:
            sc.pl.umap(adata, color="cell_type", show=False)
            p = save_figure(plt.gcf(), output_dir, "cell_type_umap.png")
            figures.append(str(p))
            plt.close("all")
    except Exception as e:
        logger.warning("Could not generate UMAP annotation plot: %s", e)

    # Barplot
    try:
        counts = adata.obs["cell_type"].value_counts()
        fig, ax = plt.subplots(figsize=(8, max(4, len(counts) * 0.35)))
        counts.plot.barh(ax=ax, color="steelblue")
        ax.set_xlabel("Number of cells")
        ax.set_title("Cell Type Distribution")
        fig.tight_layout()
        p = save_figure(fig, output_dir, "cell_type_barplot.png")
        figures.append(str(p))
        plt.close("all")
    except Exception as e:
        logger.warning("Could not generate barplot: %s", e)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Cell Type Annotation Report", skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary["method"]},
    )

    body_lines = ["## Summary\n", f"- **Method**: {summary['method']}",
                  f"- **Cell types identified**: {summary['n_cell_types']}"]

    body_lines.extend(["", "### Cell type distribution\n",
                        "| Cell Type | Cells | Proportion |",
                        "|-----------|-------|------------|"])
    total = sum(summary["cell_type_counts"].values())
    for ct, count in sorted(summary["cell_type_counts"].items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total else 0
        body_lines.append(f"| {ct} | {count} | {pct:.1f}% |")

    if "cluster_annotations" in summary:
        body_lines.extend(["", "### Cluster to cell type mapping\n",
                            "| Cluster | Cell Type | Score |", "|---------|-----------|-------|"])
        for cl, ct in summary["cluster_annotations"].items():
            score = summary.get("cluster_scores", {}).get(cl, "")
            body_lines.append(f"| {cl} | {ct} | {score} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    summary_json = {k: v for k, v in summary.items() if k != "cluster_annotations"}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary_json, data={"params": params, **summary_json}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"cell_type": ct, "n_cells": n, "proportion": round(n / total * 100, 2)}
        for ct, n in summary["cell_type_counts"].items()
    ]).to_csv(tables_dir / "cell_type_counts.csv", index=False)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data():
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="annotate_demo_") as tmpdir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", tmpdir],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        adata = sc.read_h5ad(Path(tmpdir) / "processed.h5ad")
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Annotate — multi-method cell type annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="marker_based")
    parser.add_argument("--reference", default=None)
    parser.add_argument("--cell-type-key", default="cell_type")
    parser.add_argument("--cluster-key", default="leiden")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--batch-key", default=None)
    parser.add_argument("--layer", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params = {"method": args.method, "species": args.species}

    if args.method == "marker_based":
        summary = annotate_marker_based(adata, cluster_key=args.cluster_key, species=args.species)
    elif args.method == "tangram":
        if not args.reference:
            print("ERROR: --reference required for tangram", file=sys.stderr); sys.exit(1)
        summary = annotate_tangram(adata, reference_path=args.reference, cell_type_key=args.cell_type_key)
        params["reference"] = args.reference
    elif args.method == "scanvi":
        if not args.reference:
            print("ERROR: --reference required for scanvi", file=sys.stderr); sys.exit(1)
        summary = annotate_scanvi(adata, reference_path=args.reference, cell_type_key=args.cell_type_key)
        params["reference"] = args.reference
    elif args.method == "cellassign":
        if args.model and Path(args.model).exists():
            with open(args.model) as f:
                marker_genes = json.load(f)
        else:
            marker_genes = get_default_signatures(args.species)
        summary = annotate_cellassign(adata, marker_genes=marker_genes, batch_key=args.batch_key, layer=args.layer)
    else:
        print(f"ERROR: Unknown method {args.method}", file=sys.stderr); sys.exit(1)

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)
    print(f"Annotation complete: {summary['n_cell_types']} cell types ({summary['method']})")


if __name__ == "__main__":
    main()

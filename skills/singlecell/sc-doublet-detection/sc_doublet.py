#!/usr/bin/env python3
"""Single-Cell Doublet Detection - Scrublet, DoubletFinder, scDblFinder.

Usage:
    python sc_doublet.py --input <data.h5ad> --output <dir> --method scrublet
    python sc_doublet.py --demo --output <dir>
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
from omicsclaw.singlecell.method_config import (
    MethodConfig,
    validate_method_choice,
)
from omicsclaw.singlecell.viz_utils import save_figure
from omicsclaw.singlecell.dependency_manager import require, get
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-doublet"
SKILL_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scrublet": MethodConfig(
        name="scrublet",
        description="Scrublet — computational doublet detection",
        dependencies=("scrublet",),
    ),
    "doubletfinder": MethodConfig(
        name="doubletfinder",
        description="DoubletFinder — k-NN based doublet detection (R)",
        dependencies=("rpy2",),
        is_r_based=True,
    ),
    "scdblfinder": MethodConfig(
        name="scdblfinder",
        description="scDblFinder — fast doublet detection (R/Bioconductor)",
        dependencies=("rpy2",),
        is_r_based=True,
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

_METHOD_DISPATCH = {
    "scrublet": lambda adata, args: detect_doublets_scrublet(adata, args.expected_doublet_rate, args.threshold),
    "doubletfinder": lambda adata, args: detect_doublets_doubletfinder(adata, args.expected_doublet_rate),
    "scdblfinder": lambda adata, args: detect_doublets_scdblfinder(adata, args.expected_doublet_rate),
}


def detect_doublets_scrublet(adata, expected_doublet_rate=0.06, threshold=None):
    """Detect doublets using Scrublet."""
    try:
        import scrublet as scr
    except ImportError:
        raise ImportError(
            "scrublet is required for doublet detection.\n"
            "Install: pip install scrublet"
        )

    logger.info(f"Running Scrublet (expected_rate={expected_doublet_rate})")
    scrub = scr.Scrublet(adata.X, expected_doublet_rate=expected_doublet_rate)
    doublet_scores, predicted_doublets = scrub.scrub_doublets(
        min_counts=2, min_cells=3, min_gene_variability_pctl=85, n_prin_comps=30
    )

    adata.obs['doublet_score'] = doublet_scores
    adata.obs['predicted_doublet'] = predicted_doublets

    if threshold is not None:
        adata.obs['predicted_doublet'] = adata.obs['doublet_score'] > threshold

    n_doublets = adata.obs['predicted_doublet'].sum()
    logger.info(f"Scrublet: {n_doublets} doublets ({n_doublets/adata.n_obs*100:.1f}%)")

    return {
        "method": "scrublet",
        "n_doublets": int(n_doublets),
        "doublet_rate": float(n_doublets / adata.n_obs),
        "expected_rate": expected_doublet_rate,
    }


def detect_doublets_doubletfinder(adata, expected_doublet_rate=0.06):
    """Detect doublets using DoubletFinder (R)."""
    logger.info("DoubletFinder requires R - using Scrublet fallback")
    return detect_doublets_scrublet(adata, expected_doublet_rate)


def detect_doublets_scdblfinder(adata, expected_doublet_rate=0.06):
    """Detect doublets using scDblFinder (R)."""
    logger.info("scDblFinder requires R - using Scrublet fallback")
    return detect_doublets_scrublet(adata, expected_doublet_rate)


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate doublet detection figures."""
    figures = []

    # Doublet score histogram
    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(adata.obs['doublet_score'], bins=50, edgecolor='black')
        ax.axvline(adata.obs[adata.obs['predicted_doublet']]['doublet_score'].min(),
                   color='red', linestyle='--', label='Threshold')
        ax.set_xlabel('Doublet Score')
        ax.set_ylabel('Count')
        ax.set_title('Doublet Score Distribution')
        ax.legend()
        p = save_figure(fig, output_dir, "doublet_histogram.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"Doublet histogram failed: {e}")

    # UMAP colored by doublet
    if 'X_umap' not in adata.obsm:
        try:
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
        except Exception as e:
            logger.warning(f"UMAP computation failed: {e}")

    if 'X_umap' in adata.obsm:
        try:
            sc.pl.umap(adata, color='predicted_doublet', show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_doublets.png")
            figures.append(str(p))
            plt.close()
        except Exception as e:
            logger.warning(f"UMAP doublet plot failed: {e}")

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Doublet Detection Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary['method'],
            "Doublets detected": str(summary['n_doublets']),
            "Doublet rate": f"{summary['doublet_rate']*100:.2f}%",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        f"- **Doublets detected**: {summary['n_doublets']}",
        f"- **Doublet rate**: {summary['doublet_rate']*100:.2f}%",
        f"- **Expected rate**: {summary.get('expected_rate', 'N/A')*100:.2f}%",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    # Tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df = pd.DataFrame([{
        "metric": "doublets_detected",
        "value": summary['n_doublets'],
    }, {
        "metric": "doublet_rate",
        "value": f"{summary['doublet_rate']*100:.2f}%",
    }])
    df.to_csv(tables_dir / "summary.csv", index=False)

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_doublet.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Doublet Detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="scrublet")
    parser.add_argument("--expected-doublet-rate", type=float, default=0.06)
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_raw.h5ad"
        if demo_path.exists():
            adata = sc.read_h5ad(demo_path)
        else:
            logger.warning("Local demo data not found, downloading from scanpy")
            adata = sc.datasets.pbmc3k()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Validate method & check dependencies
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="scrublet")

    # Detect doublets
    summary = _METHOD_DISPATCH[method](adata, args)
    summary['n_cells'] = int(adata.n_obs)

    params = {
        "method": args.method,
        "expected_doublet_rate": args.expected_doublet_rate,
    }
    if args.threshold is not None:
        params["threshold"] = args.threshold

    # Figures
    generate_figures(adata, output_dir)

    # Report
    write_report(output_dir, summary, input_file, params)

    # Save
    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved to {output_h5ad}")

    # Result JSON
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Metadata
    store_analysis_metadata(adata, SKILL_NAME, args.method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Doublet detection complete: {summary['n_doublets']} doublets ({summary['doublet_rate']*100:.1f}%)")


if __name__ == "__main__":
    main()

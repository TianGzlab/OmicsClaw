#!/usr/bin/env python3
"""Single-Cell Ambient RNA Removal - CellBender, SoupX, or simple subtraction."""

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
from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from skills.singlecell._lib import ambient as sc_ambient_utils
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.r_bridge import run_soupx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-ambient-removal"
SKILL_VERSION = "0.4.0"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "cellbender": MethodConfig(
        name="cellbender",
        description="CellBender — deep generative model for ambient RNA removal",
        dependencies=("cellbender",),
        supports_gpu=True,
    ),
    "soupx": MethodConfig(
        name="soupx",
        description="SoupX — ambient RNA estimation and subtraction (R)",
        dependencies=("rpy2", "anndata2ri"),
        is_r_based=True,
    ),
    "simple": MethodConfig(
        name="simple",
        description="Simple ambient subtraction (Scanpy, no extra dependencies)",
        dependencies=("scanpy",),
    ),
}


def generate_ambient_figures(adata_before, adata_after, output_dir: Path) -> list[str]:
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    try:
        before_counts = np.array(adata_before.X.sum(axis=1)).flatten()
        after_counts = np.array(adata_after.X.sum(axis=1)).flatten()
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(before_counts, after_counts, alpha=0.3, s=1)
        ax.plot([before_counts.min(), before_counts.max()], [before_counts.min(), before_counts.max()], "r--", lw=2)
        ax.set_xlabel("Before Correction")
        ax.set_ylabel("After Correction")
        ax.set_title("Total Counts Before vs After Correction")
        fig.tight_layout()
        fig_path = figures_dir / "counts_comparison.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        figures.append(str(fig_path))
        plt.close(fig)
    except Exception as exc:
        logger.warning("Counts comparison plot failed: %s", exc)

    try:
        reduction = (1 - after_counts.mean() / before_counts.mean()) * 100
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(before_counts, bins=50, alpha=0.5, label="Before", density=True)
        ax.hist(after_counts, bins=50, alpha=0.5, label="After", density=True)
        ax.set_xlabel("Total Counts per Cell")
        ax.set_ylabel("Density")
        ax.set_title(f"Count Distribution (Ambient RNA Removed: {reduction:.1f}%)")
        ax.legend()
        fig.tight_layout()
        fig_path = figures_dir / "count_distribution.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        figures.append(str(fig_path))
        plt.close(fig)
    except Exception as exc:
        logger.warning("Count distribution plot failed: %s", exc)

    return figures


def estimate_contamination_simple(adata) -> float:
    if "cellbender" in adata.uns or "soupx" in adata.uns:
        return sc_ambient_utils.estimate_contamination(adata)
    if "pct_counts_mt" in adata.obs.columns:
        mt_median = adata.obs["pct_counts_mt"].median()
        if mt_median > 15:
            return 0.10
        if mt_median > 10:
            return 0.07
        return 0.05
    return 0.05


def apply_soupx_result(adata, corrected_matrix, cells, genes, contamination):
    common_cells = [c for c in cells if c in adata.obs_names]
    common_genes = [g for g in genes if g in adata.var_names]
    if not common_cells or not common_genes:
        raise ValueError("SoupX output could not be aligned to the input AnnData")
    adata = adata[common_cells, common_genes].copy()
    adata.layers["counts"] = adata.X.copy()
    adata.X = corrected_matrix
    adata.uns["soupx"] = {"contamination_fraction": float(contamination)}
    return adata


def write_ambient_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Ambient RNA Removal Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": params["method"],
            "Contamination Est.": f"{summary['contamination_estimate']:.1%}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method used**: {params['method']}",
        f"- **Estimated contamination**: {summary['contamination_estimate']:.1%}",
        f"- **Mean counts before**: {summary['mean_counts_before']:.0f}",
        f"- **Mean counts after**: {summary['mean_counts_after']:.0f}",
        f"- **Count reduction**: {summary['count_reduction_pct']:.1f}%",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        if v is not None:
            body_lines.append(f"- `{k}`: {v}")

    body_lines.extend([
        "",
        "## Methods\n",
        "### CellBender (Recommended for 10X data)",
        "CellBender uses a deep generative model to estimate and remove ambient RNA contamination.",
        "",
        "### SoupX (R)",
        "SoupX estimates the ambient RNA profile from raw/filtered 10X matrices and subtracts it from filtered counts.",
        "",
        "### Simple subtraction",
        "Uniform ambient profile subtraction used as the fallback when R or CellBender inputs are unavailable.",
        "",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Ambient RNA Removal")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="simple", choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--expected-cells", type=int, default=None)
    parser.add_argument("--raw-h5", type=str, default=None)
    parser.add_argument("--raw-matrix-dir", type=str, default=None, help="10x raw_feature_bc_matrix directory for SoupX")
    parser.add_argument("--filtered-matrix-dir", type=str, default=None, help="10x filtered_feature_bc_matrix directory for SoupX")
    parser.add_argument("--contamination", type=float, default=0.05)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        logger.info("Generating synthetic demo data with ambient RNA...")
        try:
            adata = sc.datasets.pbmc3k()
        except Exception:
            np.random.seed(42)
            counts = np.random.negative_binomial(2, 0.02, size=(500, 1000))
            adata = sc.AnnData(
                X=counts.astype(np.float32),
                obs=pd.DataFrame(index=[f"cell_{i}" for i in range(500)]),
                var=pd.DataFrame(index=[f"gene_{i}" for i in range(1000)]),
            )
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        adata = sc.read_h5ad(input_path) if input_path.suffix == ".h5ad" else sc.read_10x_h5(input_path)
        input_file = str(input_path)

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="simple")
    adata_before = adata.copy()
    mean_before = np.array(adata.X.sum(axis=1)).flatten().mean()

    params = {
        "method": method,
        "expected_cells": args.expected_cells,
        "contamination": args.contamination,
        "raw_matrix_dir": args.raw_matrix_dir,
        "filtered_matrix_dir": args.filtered_matrix_dir,
    }

    contamination_estimate = args.contamination

    if method == "cellbender" and args.raw_h5:
        logger.info("Running CellBender...")
        try:
            adata = sc_ambient_utils.run_cellbender(
                raw_h5=args.raw_h5,
                expected_cells=args.expected_cells or adata.n_obs,
                output_dir=output_dir / "cellbender_output",
            )
            contamination_estimate = estimate_contamination_simple(adata)
        except Exception as exc:
            logger.warning("CellBender failed: %s. Falling back to simple subtraction.", exc)
            method = "simple"
            params["method"] = method

    elif method == "soupx":
        if args.raw_matrix_dir and args.filtered_matrix_dir:
            corrected_matrix, cells, genes, contamination_estimate = run_soupx(
                raw_matrix_dir=args.raw_matrix_dir,
                filtered_matrix_dir=args.filtered_matrix_dir,
            )
            adata = apply_soupx_result(adata, corrected_matrix, cells, genes, contamination_estimate)
        else:
            logger.warning("SoupX requires --raw-matrix-dir and --filtered-matrix-dir. Falling back to simple subtraction.")
            method = "simple"
            params["method"] = method

    if method == "simple":
        logger.info("Applying simple ambient subtraction (contamination=%s)", args.contamination)
        ambient_profile = np.array(adata.X.mean(axis=0)).flatten()
        ambient_profile = ambient_profile / max(ambient_profile.sum(), 1e-8)
        corrected = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X).copy()
        corrected = corrected - args.contamination * ambient_profile
        corrected = np.maximum(corrected, 0)
        adata.layers["counts"] = adata.X.copy()
        adata.X = corrected.astype(np.float32)
        adata.uns["ambient_correction"] = {"method": "simple", "contamination_fraction": args.contamination}
        contamination_estimate = args.contamination

    mean_after = np.array(adata.X.sum(axis=1)).flatten().mean()
    summary = {
        "n_cells": int(adata.n_obs),
        "method": method,
        "contamination_estimate": float(contamination_estimate),
        "mean_counts_before": float(mean_before),
        "mean_counts_after": float(mean_after),
        "count_reduction_pct": float((1 - mean_after / max(mean_before, 1e-8)) * 100),
    }

    generate_ambient_figures(adata_before, adata, output_dir)
    write_ambient_report(output_dir, summary, params, input_file)

    output_h5ad = output_dir / "corrected.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Ambient correction complete: {summary['method']}, contamination ~ {summary['contamination_estimate']:.1%}")


if __name__ == "__main__":
    main()

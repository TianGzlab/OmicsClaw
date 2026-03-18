#!/usr/bin/env python3
"""Single-Cell Ambient RNA Removal - Remove ambient RNA contamination.

Usage:
    python sc_ambient.py --input <data.h5ad> --output <dir> --method cellbender
    python sc_ambient.py --input <raw.h5> --output <dir> --method cellbender --expected-cells 10000
    python sc_ambient.py --demo --output <dir>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Fix for anndata >= 0.11 with StringArray
try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.method_config import (
    MethodConfig,
    validate_method_choice,
)
from omicsclaw.singlecell.viz_utils import save_figure
from omicsclaw.singlecell import ambient as sc_ambient_utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-ambient-removal"
SKILL_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

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
        dependencies=("rpy2",),
        is_r_based=True,
    ),
    "simple": MethodConfig(
        name="simple",
        description="Simple ambient subtraction (scanpy, no extra dependencies)",
        dependencies=("scanpy",),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

# Note: ambient removal uses inline dispatch in main() due to complex
# fallback logic. _METHOD_DISPATCH is provided for structural consistency.
_METHOD_DISPATCH = {
    "cellbender": "cellbender",
    "soupx": "soupx",
    "simple": "simple",
}


def generate_ambient_figures(adata_before, adata_after, output_dir: Path) -> list[str]:
    """Generate ambient RNA correction comparison figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Count comparison
    try:
        before_counts = np.array(adata_before.X.sum(axis=1)).flatten()
        after_counts = np.array(adata_after.X.sum(axis=1)).flatten()

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(before_counts, after_counts, alpha=0.3, s=1)
        ax.plot([before_counts.min(), before_counts.max()],
                [before_counts.min(), before_counts.max()], 'r--', lw=2)
        ax.set_xlabel("Before Correction")
        ax.set_ylabel("After Correction")
        ax.set_title("Total Counts Before vs After Correction")

        fig.tight_layout()
        fig_path = figures_dir / "counts_comparison.png"
        fig.savefig(fig_path, dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close()
        logger.info(f"  Saved: counts_comparison.png")
    except Exception as e:
        logger.warning(f"Counts comparison plot failed: {e}")

    # Histogram of count reduction
    try:
        reduction = (1 - after_counts.mean() / before_counts.mean()) * 100

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(before_counts, bins=50, alpha=0.5, label='Before', density=True)
        ax.hist(after_counts, bins=50, alpha=0.5, label='After', density=True)
        ax.set_xlabel("Total Counts per Cell")
        ax.set_ylabel("Density")
        ax.set_title(f"Count Distribution (Ambient RNA Removed: {reduction:.1f}%)")
        ax.legend()

        fig.tight_layout()
        fig_path = figures_dir / "count_distribution.png"
        fig.savefig(fig_path, dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close()
        logger.info(f"  Saved: count_distribution.png")
    except Exception as e:
        logger.warning(f"Count distribution plot failed: {e}")

    return figures


def estimate_contamination_simple(adata) -> float:
    """Simple contamination fraction estimation."""
    # If CellBender/SoupX metadata exists, use it
    if "cellbender" in adata.uns or "soupx" in adata.uns:
        return sc_ambient_utils.estimate_contamination(adata)

    # Simple heuristic based on known ambient genes
    # This is a rough estimate
    if 'pct_counts_mt' in adata.obs.columns:
        # High MT samples often have higher ambient
        mt_median = adata.obs['pct_counts_mt'].median()
        if mt_median > 15:
            return 0.10
        elif mt_median > 10:
            return 0.07
        else:
            return 0.05
    return 0.05


def write_ambient_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    """Write ambient RNA removal report."""
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
        "It requires the raw Feature-Barcode Matrix (before CellRanger filtering).",
        "",
        "### SoupX (Alternative)",
        "SoupX estimates the ambient RNA profile from empty droplets and subtracts it from cell counts.",
        "Works with filtered count matrices.",
        "",
        "## Output Files\n",
        "- `corrected.h5ad` — AnnData with ambient-corrected counts",
        "- `figures/counts_comparison.png` — Before/after scatter plot",
        "- `figures/count_distribution.png` — Count distribution comparison",
        "",
        "## References\n",
        "- [CellBender](https://doi.org/10.1016/j.cels.2018.11.005) — Fleming et al.",
        "- [SoupX](https://doi.org/10.15252/msb.202110382) — Young & Behjati",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate synthetic demo data with ambient contamination."""
    import scanpy as sc

    logger.info("Generating synthetic demo data with ambient RNA...")

    try:
        adata = sc.datasets.pbmc3k()
        logger.info(f"Loaded pbmc3k: {adata.n_obs} cells x {adata.n_vars} genes")
    except Exception:
        np.random.seed(42)
        n_cells, n_genes = 500, 1000
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))
        adata = sc.AnnData(
            X=counts.astype(np.float32),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Ambient RNA Removal")
    parser.add_argument("--input", dest="input_path", help="Input file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--method", default="simple", choices=list(METHOD_REGISTRY.keys()),
                        help="Method for ambient RNA removal")
    parser.add_argument("--expected-cells", type=int, default=None, help="Expected cells (CellBender)")
    parser.add_argument("--raw-h5", type=str, default=None, help="Raw H5 file for CellBender")
    parser.add_argument("--contamination", type=float, default=0.05, help="Contamination fraction (simple)")
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

        import scanpy as sc
        logger.info(f"Loading: {input_path}")
        adata = sc.read_h5ad(input_path) if input_path.suffix == '.h5ad' else sc.read_10x_h5(input_path)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Validate method & check dependencies
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="simple")
    args.method = method

    # Store original for comparison
    adata_before = adata.copy()
    mean_before = np.array(adata.X.sum(axis=1)).flatten().mean()

    # Parameters
    params = {
        "method": args.method,
        "expected_cells": args.expected_cells,
        "contamination": args.contamination,
    }

    # Run ambient removal
    contamination_estimate = args.contamination

    if args.method == "cellbender" and args.raw_h5:
        logger.info("Running CellBender...")
        try:
            adata = sc_ambient_utils.run_cellbender(
                raw_h5=args.raw_h5,
                expected_cells=args.expected_cells or adata.n_obs,
                output_dir=output_dir / "cellbender_output",
            )
            contamination_estimate = estimate_contamination_simple(adata)
        except Exception as e:
            logger.warning(f"CellBender failed: {e}. Using simple subtraction.")
            args.method = "simple"

    elif args.method == "soupx":
        logger.info("Running SoupX-style correction...")
        # This requires raw and filtered matrices - simplified for now
        logger.warning("SoupX requires raw/filtered matrix pair. Using simple method.")
        args.method = "simple"

    # Simple ambient subtraction (default/fallback)
    if args.method == "simple":
        logger.info(f"Applying simple ambient subtraction (contamination={args.contamination:.1%})...")
        # Subtract uniform ambient profile
        ambient_profile = np.array(adata.X.mean(axis=0)).flatten()
        ambient_profile = ambient_profile / ambient_profile.sum()

        corrected = adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X.copy()
        corrected = corrected - args.contamination * ambient_profile
        corrected = np.maximum(corrected, 0)  # No negative counts

        adata.X = corrected.astype(np.float32)

        # Store metadata
        adata.uns['ambient_correction'] = {
            'method': 'simple',
            'contamination_fraction': args.contamination,
        }

    mean_after = np.array(adata.X.sum(axis=1)).flatten().mean()

    # Generate summary
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "mean_counts_before": float(mean_before),
        "mean_counts_after": float(mean_after),
        "count_reduction_pct": float((1 - mean_after / mean_before) * 100),
        "contamination_estimate": contamination_estimate,
    }

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_ambient_figures(adata_before, adata, output_dir)

    # Write report
    logger.info("Writing report...")
    write_ambient_report(output_dir, summary, params, input_file)

    # Save corrected data
    output_h5ad = output_dir / "corrected.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_ambient.py --output {output_dir} --method {args.method}"
    if input_file:
        cmd += f" --input {input_file}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Method: {args.method}")
    print(f"  Contamination estimate: {contamination_estimate:.1%}")
    print(f"  Count reduction: {summary['count_reduction_pct']:.1f}%")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()

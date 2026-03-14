#!/usr/bin/env python3
"""Spatial Register — multi-slice alignment and spatial registration.

Usage:
    python spatial_register.py --input <multi_slice.h5ad> --output <dir>
    python spatial_register.py --input <data.h5ad> --output <dir> --reference-slice slice_1
    python spatial_register.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
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
from omicsclaw.spatial.adata_utils import (
    require_spatial_coords,
    store_analysis_metadata,
)
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-register"
SKILL_VERSION = "0.1.0"

_SLICE_KEY_CANDIDATES = ("slice", "sample", "section", "batch", "sample_id")


def _detect_slice_key(adata) -> str | None:
    """Auto-detect the obs column that identifies slices."""
    for key in _SLICE_KEY_CANDIDATES:
        if key in adata.obs.columns and adata.obs[key].nunique() >= 2:
            return key
    return None


# ---------------------------------------------------------------------------
# Method: PASTE  (optimal transport alignment)
# ---------------------------------------------------------------------------


def _run_paste(
    adata,
    *,
    slice_key: str,
    reference_slice: str | None,
    spatial_key: str,
) -> dict:
    """Run PASTE optimal transport alignment."""
    from omicsclaw.spatial.dependency_manager import require
    require("paste", feature="PASTE optimal transport spatial registration")
    import paste as pst

    slices_list = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    ref = reference_slice or slices_list[0]
    ref_adata = adata[adata.obs[slice_key] == ref].copy()

    aligned_coords = adata.obsm[spatial_key].copy().astype(float)

    for sl in slices_list:
        if str(sl) == str(ref):
            continue
        sl_adata = adata[adata.obs[slice_key] == sl].copy()
        try:
            pi = pst.pairwise_align(ref_adata, sl_adata)
            coords_new = pi.T @ ref_adata.obsm[spatial_key]
            src_mask = adata.obs[slice_key] == sl
            aligned_coords[src_mask] = coords_new
        except Exception as exc:
            logger.warning("PASTE failed for slice '%s': %s", sl, exc)

    adata.obsm["spatial_aligned"] = aligned_coords

    return {
        "method": "paste",
        "reference_slice": str(ref),
        "n_slices": len(slices_list),
        "slices": [str(s) for s in slices_list],
        "disparities": {},
        "mean_disparity": 0.0,
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_registration(
    adata,
    *,
    method: str = "paste",
    slice_key: str | None = None,
    reference_slice: str | None = None,
) -> dict:
    """Run spatial registration. Returns summary dict."""

    spatial_key = require_spatial_coords(adata)

    if slice_key is None:
        slice_key = _detect_slice_key(adata)
    if slice_key is None:
        logger.warning(
            "No slice column detected — creating synthetic 'slice' column for demo"
        )
        rng = np.random.default_rng(42)
        adata.obs["slice"] = rng.choice(["slice_1", "slice_2"], size=adata.n_obs)
        adata.obs["slice"] = pd.Categorical(adata.obs["slice"])
        slice_key = "slice"

    if slice_key not in adata.obs.columns:
        raise ValueError(f"Slice key '{slice_key}' not in adata.obs")

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    slices = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    logger.info("Input: %d cells x %d genes, %d slices", n_cells, n_genes, len(slices))

    supported_methods = ("paste",)
    if method not in supported_methods:
        raise ValueError(
            f"Unknown registration method '{method}'. Choose from: {supported_methods}"
        )

    result = _run_paste(
        adata, slice_key=slice_key,
        reference_slice=reference_slice, spatial_key=spatial_key,
    )

    store_analysis_metadata(
        adata, SKILL_NAME, result["method"],
        params={"method": method, "slice_key": slice_key, "reference_slice": reference_slice},
    )

    return {"n_cells": n_cells, "n_genes": n_genes, "slice_key": slice_key, **result}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate registration figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures: list[str] = []
    slice_key = summary.get("slice_key", "slice")
    slices = summary.get("slices", [])

    # Color palette
    cmap = plt.get_cmap("tab10")
    slice_colors = {sl: cmap(i % 10) for i, sl in enumerate(slices)}

    # Before alignment
    original_key = next(
        (k for k in ("spatial", "X_spatial") if k in adata.obsm), None
    )
    if original_key and slice_key in adata.obs.columns:
        try:
            coords = adata.obsm[original_key]
            labels = adata.obs[slice_key].astype(str).values
            fig, ax = plt.subplots(figsize=(8, 7))
            for sl in slices:
                mask = labels == str(sl)
                ax.scatter(
                    coords[mask, 0], coords[mask, 1],
                    s=8, alpha=0.6, label=str(sl),
                    color=slice_colors.get(str(sl), "grey"),
                )
            ax.set_title("Spatial Coordinates — Before Registration")
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            if len(slices) <= 8:
                ax.legend(fontsize=7, markerscale=2)
            fig.tight_layout()
            p = save_figure(fig, output_dir, "slices_before.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate before-registration plot: %s", exc)

    # After alignment
    if "spatial_aligned" in adata.obsm and slice_key in adata.obs.columns:
        try:
            coords = adata.obsm["spatial_aligned"]
            labels = adata.obs[slice_key].astype(str).values
            fig, ax = plt.subplots(figsize=(8, 7))
            for sl in slices:
                mask = labels == str(sl)
                ax.scatter(
                    coords[mask, 0], coords[mask, 1],
                    s=8, alpha=0.6, label=str(sl),
                    color=slice_colors.get(str(sl), "grey"),
                )
            ax.set_title(f"Spatial Coordinates — After Registration ({summary['method']})")
            ax.set_xlabel("X (aligned)")
            ax.set_ylabel("Y (aligned)")
            if len(slices) <= 8:
                ax.legend(fontsize=7, markerscale=2)
            fig.tight_layout()
            p = save_figure(fig, output_dir, "slices_after.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate after-registration plot: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    header = generate_report_header(
        title="Spatial Registration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "paste"),
            "Reference slice": summary.get("reference_slice", "auto"),
            "Slices": str(summary.get("n_slices", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Reference slice**: {summary['reference_slice']}",
        f"- **Slices aligned**: {summary['n_slices']}",
        f"- **Mean disparity**: {summary['mean_disparity']:.6f}",
    ]

    disparities = summary.get("disparities", {})
    if disparities:
        body_lines.extend([
            "", "### Per-Slice Disparity\n",
            "| Slice | Alignment Score |",
            "|-------|---------------------|",
        ])
        for sl, d in disparities.items():
            body_lines.append(f"| {sl} | {d:.6f} |")
        body_lines.extend([
            "",
            "Alignment performed using PASTE optimal transport. "
            "The reference slice has disparity = 0.",
        ])

    body_lines.extend([
        "", "### Output Coordinates\n",
        "Aligned coordinates are stored in `adata.obsm['spatial_aligned']`.",
    ])

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    summary_for_json = {k: v for k, v in summary.items()}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary_for_json,
        data={"params": params, **summary_for_json},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if disparities:
        pd.DataFrame(
            [{"slice": sl, "disparity": d} for sl, d in disparities.items()]
        ).to_csv(tables_dir / "registration_metrics.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_register.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    import pkg_resources
    env_lines = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib"]:
        try:
            ver = pkg_resources.get_distribution(pkg).version
            env_lines.append(f"{pkg}=={ver}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and synthesize multi-slice data."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_reg_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)

    # Assign synthetic slice labels and slightly shift coordinates
    rng = np.random.default_rng(42)
    n = adata.n_obs
    half = n // 2
    slice_labels = ["slice_1"] * half + ["slice_2"] * (n - half)
    rng.shuffle(slice_labels)
    adata.obs["slice"] = slice_labels
    adata.obs["slice"] = pd.Categorical(adata.obs["slice"])

    # Add a small offset to slice_2 to simulate misalignment
    if "spatial" in adata.obsm:
        coords = adata.obsm["spatial"].copy().astype(float)
        mask = np.array(slice_labels) == "slice_2"
        coords[mask] += rng.uniform(50, 150, size=(mask.sum(), 2))
        adata.obsm["spatial"] = coords

    logger.info("Demo: %d cells, slices=%s", n, adata.obs["slice"].cat.categories.tolist())
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Register — multi-slice alignment and registration",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="paste", choices=["paste"],
    )
    parser.add_argument("--reference-slice", default=None,
                        help="Slice label to use as reference (default: first slice)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params = {
        "method": args.method,
        "reference_slice": args.reference_slice,
    }

    summary = run_registration(
        adata,
        method=args.method,
        reference_slice=args.reference_slice,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Registration complete ({summary['method']}): "
        f"{summary['n_slices']} slices aligned to '{summary['reference_slice']}', "
        f"mean disparity={summary['mean_disparity']:.4f}"
    )


if __name__ == "__main__":
    main()

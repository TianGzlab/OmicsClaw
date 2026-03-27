#!/usr/bin/env python3
"""Spatial CNV — copy number variation inference.

Core analysis functions are in skills.spatial._lib.cnv.

Supported methods:
  infercnvpy   Expression-based CNV inference using inferCNVpy (default)
  numbat       Haplotype-aware CNV analysis via R Numbat (requires R installation)

Usage:
    python spatial_cnv.py --input <preprocessed.h5ad> --output <dir>
    python spatial_cnv.py --demo --output <dir>
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
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.cnv import COUNT_BASED_METHODS, run_cnv, SUPPORTED_METHODS
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_cnv, plot_features

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-cnv"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    import matplotlib.pyplot as plt
    figures: list[str] = []

    try:
        fig = plot_cnv(adata, VizParams(), subtype="heatmap")
        figures.append(str(save_figure(fig, output_dir, "cnv_heatmap.png")))
        plt.close('all')
    except Exception as exc:
        logger.warning("CNV heatmap failed: %s", exc)

    if "spatial" in adata.obsm:
        try:
            fig = plot_cnv(adata, VizParams(colormap="RdBu_r"), subtype="spatial")
            figures.append(str(save_figure(fig, output_dir, "cnv_spatial.png")))
            plt.close('all')
        except Exception as exc:
            logger.warning("CNV spatial map failed: %s", exc)

    cnv_score_col = summary.get("cnv_score_key") or ("cnv_score" if "cnv_score" in adata.obs.columns else None)
    if cnv_score_col and cnv_score_col in adata.obs.columns and "X_umap" in adata.obsm:
        try:
            fig = plot_features(adata, VizParams(feature=cnv_score_col, basis="umap", colormap="RdBu_r", title="CNV Score (UMAP)"))
            figures.append(str(save_figure(fig, output_dir, "cnv_umap.png")))
            plt.close('all')
        except Exception as exc:
            logger.warning("CNV UMAP failed: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Spatial CNV Inference Report", skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary.get("method", "infercnvpy"), "Cells": str(summary.get("n_cells", 0))},
    )
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}", f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Mean CNV score**: {summary.get('mean_cnv_score', 0):.4f}",
        f"- **High-CNV cells (top 10%)**: {summary.get('high_cnv_fraction_pct', 0):.1f}%",
        "", "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool, type(None)))},
        data={"params": params}, input_checksum=checksum,
    )


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_cnv_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")
        adata = sc.read_h5ad(tmp_path / "processed.h5ad")
        rng = np.random.default_rng(42)
        adata.obs["cell_type"] = pd.Categorical(np.where(rng.random(adata.n_obs) < 0.3, "Normal", "Tumor"))
        
        # Add synthetic genomic positions required by inferCNVpy
        n_genes = adata.n_vars
        chromosomes = [f"chr{c}" for c in rng.integers(1, 23, size=n_genes)]
        starts = rng.integers(100000, 2000000, size=n_genes)
        ends = starts + rng.integers(5000, 50000, size=n_genes)
        adata.var["chromosome"] = chromosomes
        adata.var["start"] = starts
        adata.var["end"] = ends
        
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial CNV — copy number variation inference")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="infercnvpy", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--reference-key", default=None)
    parser.add_argument("--reference-cat", nargs="+", default=None)
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--step", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
        reference_key, reference_cat = "cell_type", ["Normal"]
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file, reference_key, reference_cat = args.input_path, args.reference_key, args.reference_cat
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr); sys.exit(1)

    params = {"method": args.method, "reference_key": reference_key, "reference_cat": reference_cat,
              "window_size": args.window_size, "step": args.step}

    # Validate input matrix availability per method.
    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "Method '%s' expects raw integer counts in adata.layers['counts']. "
                "Found adata.raw — will copy to layers['counts'].", args.method,
            )
        else:
            logger.warning(
                "Method '%s' expects raw integer counts in adata.layers['counts'], but none found. "
                "Falling back to adata.X — if this is log-normalized, results will be incorrect. "
                "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()",
                args.method,
            )

    summary = run_cnv(adata, method=args.method, reference_key=reference_key,
                      reference_cat=reference_cat, window_size=args.window_size, step=args.step)

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    adata.write_h5ad(output_dir / "processed.h5ad")
    print(f"CNV complete ({summary['method']}): mean score={summary.get('mean_cnv_score', 0):.4f}")


if __name__ == "__main__":
    main()

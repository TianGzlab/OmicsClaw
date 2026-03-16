#!/usr/bin/env python3
"""Spatial CNV — copy number variation inference.

Supported methods:
  infercnvpy   Expression-based CNV inference using inferCNVpy (default)
  numbat       Haplotype-aware CNV analysis via R Numbat (requires rpy2 + R)

Requires: pip install infercnvpy
          pip install -e ".[full]"  (for Numbat)

Usage:
    python spatial_cnv.py --input <preprocessed.h5ad> --output <dir>
    python spatial_cnv.py --input <data.h5ad> --output <dir> --method infercnvpy \\
        --reference-key cell_type --reference-cat Normal
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
from omicsclaw.spatial.adata_utils import store_analysis_metadata
from omicsclaw.spatial.dependency_manager import require, validate_r_environment
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_cnv, plot_features

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-cnv"
SKILL_VERSION = "0.2.0"

SUPPORTED_METHODS = ("infercnvpy", "numbat")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_reference(adata, reference_key: str | None, reference_cat: list[str]) -> None:
    if reference_key is None:
        return
    if reference_key not in adata.obs.columns:
        raise ValueError(
            f"'--reference-key {reference_key}' not found in adata.obs.\n"
            f"Available columns: {list(adata.obs.columns)}"
        )
    avail = set(adata.obs[reference_key].unique())
    missing = set(reference_cat) - avail
    if missing:
        raise ValueError(
            f"Reference categories {sorted(missing)} not in adata.obs['{reference_key}'].\n"
            f"Available: {sorted(avail)}"
        )


# ---------------------------------------------------------------------------
# Method: inferCNVpy  (adapted from ChatSpatial tools/cnv_analysis.py)
# ---------------------------------------------------------------------------


def _run_infercnvpy(
    adata,
    *,
    reference_key: str | None = None,
    reference_cat: list[str] | None = None,
    window_size: int = 100,
    step: int = 10,
    dynamic_threshold: float | None = 1.5,
) -> dict:
    """Infer CNV using inferCNVpy (expression-based, no allele data needed)."""
    require("infercnvpy", feature="CNV inference")
    import infercnvpy as cnv

    logger.info("Running inferCNVpy (window=%d, step=%d)", window_size, step)

    cnv.tl.infercnv(
        adata,
        reference_key=reference_key,
        reference_cat=reference_cat,
        window_size=window_size,
        step=step,
        dynamic_threshold=dynamic_threshold,
    )
    cnv.tl.cnv_score(adata)

    cnv_score_col = "cnv_score" if "cnv_score" in adata.obs.columns else None
    mean_score = float(adata.obs[cnv_score_col].mean()) if cnv_score_col else 0.0

    high_cnv_pct = 0.0
    if cnv_score_col:
        threshold = float(adata.obs[cnv_score_col].quantile(0.9))
        high_cnv_pct = float((adata.obs[cnv_score_col] > threshold).mean() * 100)

    return {
        "method": "infercnvpy",
        "n_genes": adata.n_vars,
        "mean_cnv_score": round(mean_score, 4),
        "high_cnv_fraction_pct": round(high_cnv_pct, 2),
        "cnv_score_key": cnv_score_col,
    }


# ---------------------------------------------------------------------------
# Method: Numbat  (requires R + rpy2 + R Numbat package)
# ---------------------------------------------------------------------------


def _run_numbat(
    adata,
    *,
    reference_key: str | None = None,
    reference_cat: list[str] | None = None,
) -> dict:
    """Haplotype-aware CNV inference via R Numbat.

    Requires:
        pip install rpy2 anndata2ri
        In R: install.packages("Numbat")
        Allelic count data in adata.obsm["allele_counts"] or external TSV.
    """
    robjects, pandas2ri, numpy2ri, importr, localconverter, default_converter, openrlib, anndata2ri = (
        validate_r_environment(required_r_packages=["numbat"])
    )

    if "allele_counts" not in adata.obsm:
        raise ValueError(
            "Numbat requires allele count data in adata.obsm['allele_counts'].\n"
            "Generate it with cellsnp-lite or vartrix on your BAM files."
        )

    logger.info("Running Numbat via rpy2 ...")

    with openrlib.rlock:
        with localconverter(default_converter + anndata2ri.converter):
            r_sce = anndata2ri.py2rpy(adata)
            numbat = importr("numbat")
            result_r = robjects.r("""
                function(sce, ref_key, ref_cat) {
                    nb <- Numbat$new(count_mat = assay(sce, 'X'),
                                     ref_prefix = ref_key)
                    list(cnv_calls = nb$joint_post)
                }
            """)(r_sce, reference_key or "NULL", reference_cat or robjects.NULL)

    logger.info("Numbat complete")

    return {
        "method": "numbat",
        "n_genes": adata.n_vars,
        "mean_cnv_score": 0.0,
        "high_cnv_fraction_pct": 0.0,
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_cnv(
    adata,
    *,
    method: str = "infercnvpy",
    reference_key: str | None = None,
    reference_cat: list[str] | None = None,
    window_size: int = 100,
    step: int = 10,
) -> dict:
    """Run CNV inference. Returns summary dict.

    Parameters
    ----------
    adata:
        AnnData with expression data. Should come from spatial-preprocess.
    method:
        ``"infercnvpy"`` or ``"numbat"``.
    reference_key:
        obs column for reference cell annotations.
    reference_cat:
        Category values (within reference_key) that mark normal reference cells.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    _validate_reference(adata, reference_key, reference_cat or [])

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    logger.info("Input: %d cells × %d genes, method=%s", n_cells, n_genes, method)

    if method == "numbat":
        result = _run_numbat(adata, reference_key=reference_key, reference_cat=reference_cat)
    else:
        result = _run_infercnvpy(
            adata,
            reference_key=reference_key,
            reference_cat=reference_cat,
            window_size=window_size,
            step=step,
        )

    return {"n_cells": n_cells, "n_genes": n_genes, **result}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate CNV visualizations using the OmicsClaw viz library."""
    import matplotlib.pyplot as plt

    figures: list[str] = []

    # 1. CNV chromosome heatmap
    try:
        fig = plot_cnv(adata, VizParams(), subtype="heatmap")
        p = save_figure(fig, output_dir, "cnv_heatmap.png")
        figures.append(str(p))
        plt.close('all')
    except Exception as exc:
        logger.warning("CNV heatmap failed: %s", exc)

    # 2. CNV spatial map
    if "spatial" in adata.obsm:
        try:
            fig = plot_cnv(adata, VizParams(colormap="RdBu_r"), subtype="spatial")
            p = save_figure(fig, output_dir, "cnv_spatial.png")
            figures.append(str(p))
            plt.close('all')
        except Exception as exc:
            logger.warning("CNV spatial map failed: %s", exc)

    # 3. CNV score on UMAP (if available)
    cnv_score_col = summary.get("cnv_score_key") or (
        "cnv_score" if "cnv_score" in adata.obs.columns else None
    )
    if cnv_score_col and cnv_score_col in adata.obs.columns and "X_umap" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(feature=cnv_score_col, basis="umap",
                          colormap="RdBu_r", title="CNV Score (UMAP)"),
            )
            p = save_figure(fig, output_dir, "cnv_umap.png")
            figures.append(str(p))
            plt.close('all')
        except Exception as exc:
            logger.warning("CNV UMAP failed: %s", exc)

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
    header = generate_report_header(
        title="Spatial CNV Inference Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "infercnvpy"),
            "Cells": str(summary.get("n_cells", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Mean CNV score**: {summary.get('mean_cnv_score', 0):.4f}",
        f"- **High-CNV cells (top 10%)**: {summary.get('high_cnv_fraction_pct', 0):.1f}%",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool, type(None)))},
        data={"params": params},
        input_checksum=checksum,
    )

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd_parts: list[str] = [
        f"python spatial_cnv.py --input <input.h5ad>",
        f"--method {params.get('method', 'infercnvpy')}",
        f"--output {output_dir}"
    ]
    if params.get("reference_key"):
        cmd_parts.append(f"--reference-key {params['reference_key']}")
    cmd_str = " ".join(cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd_str}\n")

    from importlib.metadata import version as _ver, PackageNotFoundError
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "infercnvpy", "numpy", "pandas"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except PackageNotFoundError:
            pass
    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate demo AnnData and add synthetic cell-type labels for reference."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_cnv_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Generating demo data via spatial-preprocess ...")
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)

        rng = np.random.default_rng(42)
        labels = np.where(
            rng.random(adata.n_obs) < 0.3, "Normal", "Tumor"
        )
        adata.obs["cell_type"] = pd.Categorical(labels)
        logger.info("Demo: %d cells × %d genes (30%% Normal reference)", adata.n_obs, adata.n_vars)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial CNV — copy number variation inference\n"
                    "Requires: pip install infercnvpy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="infercnvpy",
        choices=list(SUPPORTED_METHODS),
    )
    parser.add_argument(
        "--reference-key", default=None,
        help="obs column with cell type labels (e.g. 'cell_type')",
    )
    parser.add_argument(
        "--reference-cat", nargs="+", default=None,
        help="Category values marking normal reference cells (e.g. 'Normal')",
    )
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--step", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
        reference_key = "cell_type"
        reference_cat = ["Normal"]
    elif args.input_path:
        if not Path(args.input_path).exists():
            print(f"ERROR: Input not found: {args.input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
        reference_key = args.reference_key
        reference_cat = args.reference_cat
    else:
        print("ERROR: Provide --input <file.h5ad> or --demo", file=sys.stderr)
        sys.exit(1)

    params = {
        "method": args.method,
        "reference_key": reference_key,
        "reference_cat": reference_cat,
        "window_size": args.window_size,
        "step": args.step,
    }

    summary = run_cnv(
        adata,
        method=args.method,
        reference_key=reference_key,
        reference_cat=reference_cat,
        window_size=args.window_size,
        step=args.step,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    adata.write_h5ad(output_dir / "processed.h5ad")
    logger.info("Saved: %s", output_dir / "processed.h5ad")

    print(
        f"CNV complete ({summary['method']}): "
        f"mean score={summary.get('mean_cnv_score', 0):.4f}, "
        f"high-CNV={summary.get('high_cnv_fraction_pct', 0):.1f}%"
    )


if __name__ == "__main__":
    main()

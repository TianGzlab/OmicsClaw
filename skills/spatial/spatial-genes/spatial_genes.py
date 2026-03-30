#!/usr/bin/env python3
"""Spatial Genes — find spatially variable genes via multiple methods.

Supported methods:
  - morans:    Moran's I spatial autocorrelation via Squidpy (default)
  - spatialde: Gaussian process regression via SpatialDE
  - sparkx:    Non-parametric kernel test via SPARK-X in R
  - flashs:    Randomized kernel approximation (Python native, fast)

Usage:
    python spatial_genes.py --input <processed.h5ad> --output <dir>
    python spatial_genes.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import shlex
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

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer, generate_report_header, write_result_json,
)
from skills.spatial._lib.genes import (
    COUNT_BASED_METHODS,
    METHOD_DISPATCH,
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_MORANS_COORD_TYPES,
    VALID_MORANS_CORR_METHODS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-genes"
SKILL_VERSION = "0.2.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-genes/spatial_genes.py"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, top_genes: list[str]) -> list[str]:
    from skills.spatial._lib.adata_utils import get_spatial_key
    from skills.spatial._lib.viz import VizParams, plot_features, plot_spatial_stats
    from skills.spatial._lib.viz_utils import save_figure

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
    score_label = summary.get("score_label", "Score")
    score_column = summary.get("score_column", "I")
    significance_column = summary.get("significance_column")
    significance_label = summary.get("significance_label", "p-value")
    has_significance = bool(significance_column and significance_column in svg_df.columns)
    if has_significance:
        body_lines.extend([f"| Rank | Gene | {score_label} | {significance_label} |", "|------|------|-----------|---------|"])
    else:
        body_lines.extend([f"| Rank | Gene | {score_label} |", "|------|------|-------|"])

    for rank, gene in enumerate(summary["top_genes"][:20], 1):
        if gene in svg_df.index:
            row = svg_df.loc[gene]
            score_value = row.get(score_column, float("nan"))
            if has_significance:
                sig_value = row.get(significance_column, float("nan"))
                body_lines.append(f"| {rank} | {gene} | {score_value:.4f} | {sig_value:.2e} |")
            else:
                body_lines.append(f"| {rank} | {gene} | {score_value:.4f} |")

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
    preferred_cols = ["gene"]
    if score_column in csv_df.columns:
        preferred_cols.append(score_column)
    if significance_column and significance_column in csv_df.columns:
        preferred_cols.append(significance_column)
    preferred_cols.extend(
        c for c in ["pval", "pval_norm", "qval", "var_norm", "pval_z_sim"] if c in csv_df.columns and c not in preferred_cols
    )
    cols = preferred_cols
    csv_df[[c for c in cols if c in csv_df.columns]].to_csv(tables_dir / "svg_results.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python {SCRIPT_REL_PATH} --input <input.h5ad> --output {shlex.quote(str(output_dir))}"
    for k, v in params.items():
        flag = f"--{k.replace('_', '-')}"
        if isinstance(v, bool):
            if v:
                cmd += f" {flag}"
            continue
        if v is None or v == "":
            continue
        cmd += f" {flag} {shlex.quote(str(v))}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data(output_dir: Path):
    import scanpy as sc

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


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.morans_n_neighs < 1:
        parser.error("--morans-n-neighs must be >= 1")
    if args.morans_n_perms < 0:
        parser.error("--morans-n-perms must be >= 0")
    if args.spatialde_min_counts < 1:
        parser.error("--spatialde-min-counts must be >= 1")
    if args.spatialde_aeh_patterns is not None and args.spatialde_aeh_patterns < 2:
        parser.error("--spatialde-aeh-patterns must be >= 2")
    if args.spatialde_aeh_lengthscale is not None and args.spatialde_aeh_lengthscale <= 0:
        parser.error("--spatialde-aeh-lengthscale must be > 0")
    if args.sparkx_num_cores < 1:
        parser.error("--sparkx-num-cores must be >= 1")
    if args.sparkx_max_genes < 0:
        parser.error("--sparkx-max-genes must be >= 0")
    if args.flashs_n_rand_features < 1:
        parser.error("--flashs-n-rand-features must be >= 1")
    if args.flashs_bandwidth is not None and args.flashs_bandwidth <= 0:
        parser.error("--flashs-bandwidth must be > 0")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "n_top_genes": args.n_top_genes,
        "fdr_threshold": args.fdr_threshold,
    }

    if args.method == "morans":
        params.update(
            {
                "morans_n_neighs": args.morans_n_neighs,
                "morans_n_perms": args.morans_n_perms,
                "morans_corr_method": args.morans_corr_method,
                "morans_coord_type": args.morans_coord_type,
            }
        )
        method_kwargs = {
            "n_neighs": args.morans_n_neighs,
            "n_perms": args.morans_n_perms,
            "corr_method": args.morans_corr_method,
            "coord_type": args.morans_coord_type,
        }
    elif args.method == "spatialde":
        if args.spatialde_no_aeh and (
            args.spatialde_aeh_patterns is not None or args.spatialde_aeh_lengthscale is not None
        ):
            logger.warning(
                "Ignoring --spatialde-aeh-patterns / --spatialde-aeh-lengthscale because --spatialde-no-aeh was set."
            )
        run_aeh = not args.spatialde_no_aeh
        params.update(
            {
                "spatialde_no_aeh": args.spatialde_no_aeh,
                "spatialde_min_counts": args.spatialde_min_counts,
                "spatialde_aeh_patterns": args.spatialde_aeh_patterns if run_aeh else None,
                "spatialde_aeh_lengthscale": args.spatialde_aeh_lengthscale if run_aeh else None,
            }
        )
        method_kwargs = {
            "run_aeh": run_aeh,
            "min_counts_per_gene": args.spatialde_min_counts,
            "aeh_patterns": args.spatialde_aeh_patterns if run_aeh else None,
            "aeh_lengthscale": args.spatialde_aeh_lengthscale if run_aeh else None,
        }
    elif args.method == "sparkx":
        params.update(
            {
                "sparkx_num_cores": args.sparkx_num_cores,
                "sparkx_option": args.sparkx_option,
                "sparkx_max_genes": args.sparkx_max_genes,
            }
        )
        method_kwargs = {
            "num_cores": args.sparkx_num_cores,
            "option": args.sparkx_option,
            "n_max_genes": args.sparkx_max_genes,
        }
    elif args.method == "flashs":
        params.update(
            {
                "flashs_n_rand_features": args.flashs_n_rand_features,
                "flashs_bandwidth": args.flashs_bandwidth,
            }
        )
        method_kwargs = {
            "n_rand_features": args.flashs_n_rand_features,
            "bandwidth": args.flashs_bandwidth,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


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
    parser.add_argument(
        "--morans-n-neighs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["morans"]["n_neighs"],
    )
    parser.add_argument(
        "--morans-n-perms",
        type=int,
        default=METHOD_PARAM_DEFAULTS["morans"]["n_perms"],
        help="Permutation depth for Moran's I. Set to 0 to disable permutations.",
    )
    parser.add_argument(
        "--morans-corr-method",
        choices=list(VALID_MORANS_CORR_METHODS),
        default=METHOD_PARAM_DEFAULTS["morans"]["corr_method"],
    )
    parser.add_argument(
        "--morans-coord-type",
        choices=list(VALID_MORANS_COORD_TYPES),
        default=METHOD_PARAM_DEFAULTS["morans"]["coord_type"],
        help="Neighbor graph layout. 'auto' lets Squidpy infer grid vs generic coordinates.",
    )
    parser.add_argument("--spatialde-no-aeh", action="store_true")
    parser.add_argument(
        "--spatialde-min-counts",
        type=int,
        default=METHOD_PARAM_DEFAULTS["spatialde"]["min_counts_per_gene"],
        help="Minimum total counts per gene before running SpatialDE.",
    )
    parser.add_argument("--spatialde-aeh-patterns", type=int, default=None)
    parser.add_argument("--spatialde-aeh-lengthscale", type=float, default=None)
    parser.add_argument(
        "--sparkx-num-cores",
        type=int,
        default=METHOD_PARAM_DEFAULTS["sparkx"]["num_cores"],
    )
    parser.add_argument(
        "--sparkx-option",
        default=METHOD_PARAM_DEFAULTS["sparkx"]["option"],
        help="SPARK-X option argument. The official example uses 'mixture'.",
    )
    parser.add_argument(
        "--sparkx-max-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["sparkx"]["n_max_genes"],
        help="Wrapper-level cap for SPARK-X on very large matrices; 0 disables subsetting.",
    )
    parser.add_argument(
        "--flashs-n-rand-features",
        type=int,
        default=METHOD_PARAM_DEFAULTS["flashs"]["n_rand_features"],
    )
    parser.add_argument(
        "--flashs-bandwidth",
        type=float,
        default=METHOD_PARAM_DEFAULTS["flashs"]["bandwidth"],
        help="Optional kernel bandwidth override for FlashS. Default is data-adaptive.",
    )
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data(output_dir)
    elif args.input_path:
        import scanpy as sc

        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr); sys.exit(1)

    params, method_kwargs = _collect_run_configuration(args)

    # Validate input matrix availability for count-based methods.
    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "Method '%s' expects raw counts in adata.layers['counts']. "
                "Found adata.raw — will copy to layers['counts'].", args.method,
            )
        else:
            logger.warning(
                "Method '%s' expects raw counts in adata.layers['counts'], but none found. "
                "Falling back to adata.X — results may be suboptimal. "
                "Ensure preprocessing saves raw counts with: adata.layers['counts'] = adata.X.copy()",
                args.method,
            )

    run_fn = METHOD_DISPATCH[args.method]
    svg_df, summary = run_fn(
        adata,
        n_top_genes=args.n_top_genes,
        fdr_threshold=args.fdr_threshold,
        **method_kwargs,
    )

    from skills.spatial._lib.adata_utils import store_analysis_metadata

    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    generate_figures(adata, output_dir, summary.get("top_genes", []))
    write_report(output_dir, svg_df, summary, input_file, params)

    adata.write_h5ad(output_dir / "processed.h5ad")
    print(f"SVG detection complete: {summary['n_significant']} significant genes ({summary['method']})")


if __name__ == "__main__":
    main()

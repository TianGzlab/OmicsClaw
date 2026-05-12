#!/usr/bin/env python3
"""Single-Cell Ambient RNA Removal - CellBender, SoupX, or simple subtraction."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import tempfile
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc
import scipy.sparse as sp

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_result_json,
    write_replot_hint,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import ambient as sc_ambient_utils
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_input_contract,
    get_matrix_contract,
    record_matrix_contract,
    select_count_like_expression_source,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import (
    MethodConfig,
    check_method_available,
)
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_ambient_removal
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-ambient-removal"
SKILL_VERSION = "0.6.0"

R_ENHANCED_PLOTS: dict[str, str] = {
    # ambient-removal exports gene_expression.csv with before/after counts for top genes.
    # No UMAP/embedding at this pre-QC stage — embedding renderers not appropriate.
    "plot_feature_violin": "r_ambient_violin.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")



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
        dependencies=(),
    ),
    "simple": MethodConfig(
        name="simple",
        description="Simple ambient subtraction (Scanpy, no extra dependencies)",
        dependencies=("scanpy",),
    ),
}


def _get_count_like_matrix(adata):
    try:
        return select_count_like_expression_source(adata, preferred_layer="counts")
    except ValueError as exc:
        raise ValueError(
            "Ambient RNA removal requires a raw count-like matrix. "
            "Provide `adata.layers['counts']`, aligned `adata.raw`, or count-like `adata.X`. "
            "If the file provenance is unclear, run `oc run sc-standardize-input --input <file> --output <dir>` first."
        ) from exc


def _validate_inputs(args: argparse.Namespace) -> None:
    if not 0 <= float(args.contamination) < 1:
        raise ValueError("--contamination must be between 0 and 1 (for example 0.05).")
    if args.expected_cells is not None and int(args.expected_cells) <= 0:
        raise ValueError("--expected-cells must be a positive integer.")
    if (
        args.method == "cellbender"
        and args.raw_h5
        and not args.input_path
        and args.expected_cells is None
        and not args.demo
    ):
        raise ValueError(
            "When running CellBender without `--input`, please also provide `--expected-cells` "
            "so the prior reflects real cells rather than all droplets."
        )


def _make_axis_names_unique(adata, *, source_label: str):
    warnings: list[str] = []
    changed = False
    if not adata.obs_names.is_unique:
        if not changed:
            adata = adata.copy()
            changed = True
        adata.obs_names_make_unique()
        warnings.append(
            f"Cell barcodes from {source_label} were not unique; unique suffixes were added for stable processing."
        )
    if not adata.var_names.is_unique:
        if not changed:
            adata = adata.copy()
            changed = True
        adata.var_names_make_unique()
        warnings.append(
            f"Gene identifiers from {source_label} were not unique; unique suffixes were added for stable processing."
        )
    return adata, warnings


def _load_input_adata(path: Path, *, suggest_standardize: bool):
    adata = sc_io.smart_load(
        path,
        suggest_standardize=suggest_standardize,
        skill_name=SKILL_NAME,
        min_cells=0,
        min_genes=0,
    )
    adata, warnings = _make_axis_names_unique(adata, source_label=str(path))
    input_contract = get_input_contract(adata)
    prep = {
        "source_path": str(path),
        "loaded_via": "smart_load",
        "standardized": bool(input_contract.get("standardized")),
        "warnings": warnings,
    }
    if input_contract:
        prep["input_contract"] = input_contract
    return adata, prep


def _resolve_requested_method(requested_method: str) -> tuple[str, str | None]:
    if requested_method not in METHOD_REGISTRY:
        raise ValueError(
            f"Unknown method '{requested_method}'. Available: {', '.join(METHOD_REGISTRY.keys())}"
        )

    ok, msg = check_method_available(METHOD_REGISTRY[requested_method])
    if ok:
        return requested_method, None

    fb_ok, fb_msg = check_method_available(METHOD_REGISTRY["simple"])
    if not fb_ok:
        raise RuntimeError(msg or fb_msg)

    logger.warning(
        "Requested method '%s' is unavailable (%s). Falling back to simple subtraction.",
        requested_method,
        msg,
    )
    fallback_reason = (
        f"{requested_method} is unavailable in the current environment ({msg}); "
        "wrapper executed the simple subtraction path instead"
    )
    return "simple", fallback_reason


def _select_runtime_input(
    args: argparse.Namespace,
    *,
    requested_method: str,
    resolved_method: str,
):
    if args.demo:
        logger.info("Generating synthetic demo data with ambient RNA...")
        try:
            adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
            logger.info("Loaded demo dataset: %s", demo_path or "scanpy-pbmc3k")
        except Exception:
            np.random.seed(42)
            counts = np.random.negative_binomial(2, 0.02, size=(500, 1000))
            adata = sc.AnnData(
                X=counts.astype(np.float32),
                obs=pd.DataFrame(index=[f"cell_{i}" for i in range(500)]),
                var=pd.DataFrame(index=[f"gene_{i}" for i in range(1000)]),
            )
            demo_path = None
        adata, warnings = _make_axis_names_unique(adata, source_label="demo")
        prep = {
            "source_path": str(demo_path) if demo_path else None,
            "loaded_via": "demo",
            "standardized": False,
            "warnings": warnings,
        }
        return adata, str(demo_path) if demo_path else None, prep

    if args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        adata, prep = _load_input_adata(input_path, suggest_standardize=True)
        return adata, str(input_path), prep

    if args.raw_h5:
        raw_h5 = Path(args.raw_h5)
        if not raw_h5.exists():
            raise FileNotFoundError(f"Raw H5 file not found: {raw_h5}")
        adata, prep = _load_input_adata(raw_h5, suggest_standardize=False)
        if resolved_method == "cellbender":
            prep["warnings"].append(
                "No `--input` dataset was provided; diagnostics and prior estimation are using `--raw-h5` directly."
            )
        else:
            prep["warnings"].append(
                "No `--input` dataset was provided; the wrapper loaded `--raw-h5` as the available matrix source."
            )
        return adata, str(raw_h5), prep

    if requested_method == "soupx" and args.filtered_matrix_dir:
        filtered_dir = Path(args.filtered_matrix_dir)
        if not filtered_dir.exists():
            raise FileNotFoundError(f"Filtered matrix directory not found: {filtered_dir}")
        adata, prep = _load_input_adata(filtered_dir, suggest_standardize=False)
        prep["warnings"].append(
            "No `--input` dataset was provided; SoupX exports are being built from `--filtered-matrix-dir`."
        )
        return adata, str(filtered_dir), prep

    if args.raw_matrix_dir:
        raw_dir = Path(args.raw_matrix_dir)
        if raw_dir.exists():
            adata, prep = _load_input_adata(raw_dir, suggest_standardize=False)
            prep["warnings"].append(
                "No `--input` dataset was provided; fallback behavior is using `--raw-matrix-dir` as the loaded matrix source."
            )
            return adata, str(raw_dir), prep

    raise ValueError(
        "No usable input was provided. Pass `--input <h5ad|h5|loom|csv|tsv|10x_dir>`, "
        "or use method-specific assets such as `--raw-h5` for CellBender or "
        "`--filtered-matrix-dir` for SoupX."
    )


def run_soupx(raw_matrix_dir: str, filtered_matrix_dir: str):
    validate_r_environment(required_r_packages=["Seurat", "SoupX"])
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_soupx_") as tmpdir:
        tmpdir = Path(tmpdir)
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        runner.run_script(
            "sc_soupx.R",
            args=[raw_matrix_dir, filtered_matrix_dir, str(output_dir)],
            expected_outputs=["corrected_counts.csv", "cells.csv", "genes.csv", "contamination.json"],
            output_dir=output_dir,
        )
        corrected = pd.read_csv(output_dir / "corrected_counts.csv", index_col=0)
        cells = pd.read_csv(output_dir / "cells.csv")["cell"].astype(str).tolist()
        genes = pd.read_csv(output_dir / "genes.csv")["gene"].astype(str).tolist()
        contamination = json.loads((output_dir / "contamination.json").read_text(encoding="utf-8"))["contamination"]
    return corrected.T.to_numpy(dtype=np.float32), cells, genes, contamination


def _sum_counts_per_barcode(adata) -> np.ndarray:
    return np.asarray(adata.X.sum(axis=1)).ravel().astype(float)


def _shared_barcode_counts(adata_before, adata_after) -> tuple[np.ndarray, np.ndarray]:
    shared_obs = adata_after.obs_names[adata_after.obs_names.isin(adata_before.obs_names)]
    if len(shared_obs) == 0:
        return np.array([], dtype=float), np.array([], dtype=float)
    before_aligned = adata_before[shared_obs].copy()
    after_aligned = adata_after[shared_obs].copy()
    return _sum_counts_per_barcode(before_aligned), _sum_counts_per_barcode(after_aligned)


def _collect_cellbender_outputs(output_dir: Path) -> dict[str, str]:
    cellbender_dir = output_dir / "cellbender_output"
    if not cellbender_dir.exists():
        return {}

    candidates = {
        "cellbender_h5": cellbender_dir / "cellbender_output.h5",
        "cellbender_filtered_h5": cellbender_dir / "cellbender_output_filtered.h5",
        "cellbender_posterior_h5": cellbender_dir / "cellbender_output_posterior.h5",
        "cell_barcodes_csv": cellbender_dir / "cellbender_output_cell_barcodes.csv",
        "metrics_csv": cellbender_dir / "cellbender_output_metrics.csv",
        "report_html": cellbender_dir / "cellbender_output_report.html",
        "report_ipynb": cellbender_dir / "cellbender_output_report.ipynb",
        "run_log": cellbender_dir / "cellbender_output.log",
        "checkpoint_tarball": cellbender_dir / "ckpt.tar.gz",
    }
    return {
        name: str(path.relative_to(output_dir))
        for name, path in candidates.items()
        if path.exists()
    }


def generate_ambient_figures(adata_before, adata_after, output_dir: Path, *, method: str) -> list[str]:
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    before_counts = _sum_counts_per_barcode(adata_before)
    after_counts = _sum_counts_per_barcode(adata_after)
    shared_before_counts, shared_after_counts = _shared_barcode_counts(adata_before, adata_after)

    try:
        if shared_before_counts.size > 0 and shared_after_counts.size > 0:
            fig, ax = plt.subplots(figsize=(6, 6))
            max_count = max(shared_before_counts.max(), shared_after_counts.max(), 1.0)
            ax.scatter(shared_before_counts, shared_after_counts, alpha=0.3, s=4)
            ax.plot([0, max_count], [0, max_count], "r--", lw=2)
            ax.set_xlabel("Before Correction")
            ax.set_ylabel("After Correction")
            title = "Total Counts Before vs After Correction"
            if method == "cellbender":
                title += " (Shared Barcodes)"
            ax.set_title(title)
            fig.tight_layout()
            fig_path = figures_dir / "counts_comparison.png"
            fig.savefig(fig_path, dpi=300, bbox_inches="tight")
            figures.append(str(fig_path))
            plt.close(fig)
        else:
            logger.info("Skipping counts comparison scatter: no shared barcodes between before/after matrices.")
    except Exception as exc:
        logger.warning("Counts comparison plot failed: %s", exc)

    try:
        if shared_before_counts.size > 0 and shared_after_counts.size > 0:
            hist_before = shared_before_counts
            hist_after = shared_after_counts
            label_before = "Before (shared barcodes)"
            label_after = "After (shared barcodes)"
        else:
            hist_before = before_counts
            hist_after = after_counts
            label_before = "Before"
            label_after = "After"

        reduction = (1 - hist_after.mean() / max(hist_before.mean(), 1e-8)) * 100
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(hist_before, bins=50, alpha=0.5, label=label_before, density=True)
        ax.hist(hist_after, bins=50, alpha=0.5, label=label_after, density=True)
        ax.set_xlabel("Total Counts per Barcode")
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

    if method == "cellbender":
        try:
            before_rank = np.sort(before_counts)[::-1]
            after_rank = np.sort(after_counts)[::-1]
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.plot(np.arange(1, len(before_rank) + 1), before_rank, label=f"Before (n={len(before_rank)})", alpha=0.8)
            ax.plot(np.arange(1, len(after_rank) + 1), after_rank, label=f"After (n={len(after_rank)})", alpha=0.8)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("Barcode Rank")
            ax.set_ylabel("Total Counts per Barcode")
            ax.set_title("CellBender Barcode Rank Diagnostic")
            ax.legend()
            fig.tight_layout()
            fig_path = figures_dir / "barcode_rank.png"
            fig.savefig(fig_path, dpi=300, bbox_inches="tight")
            figures.append(str(fig_path))
            plt.close(fig)
        except Exception as exc:
            logger.warning("Barcode rank plot failed: %s", exc)

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
    cell_index = {str(cell): idx for idx, cell in enumerate(cells)}
    gene_index = {str(gene): idx for idx, gene in enumerate(genes)}
    common_cells = [str(cell) for cell in adata.obs_names if str(cell) in cell_index]
    common_genes = [str(gene) for gene in adata.var_names if str(gene) in gene_index]
    if not common_cells or not common_genes:
        raise ValueError("SoupX output could not be aligned to the input AnnData")
    row_idx = [cell_index[cell] for cell in common_cells]
    col_idx = [gene_index[gene] for gene in common_genes]
    aligned = corrected_matrix[np.ix_(row_idx, col_idx)]
    adata = adata[common_cells, common_genes].copy()
    adata.layers["counts"] = adata.X.copy()
    adata.X = aligned.astype(np.float32)
    adata.uns["soupx"] = {"contamination_fraction": float(contamination)}
    return adata


def write_ambient_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, *, degenerate_diag: dict | None = None) -> None:
    requested_method = str(summary.get("requested_method", params.get("method", summary["method"])))
    executed_method = str(summary.get("executed_method", summary["method"]))
    shared_barcode_count = int(summary.get("shared_barcode_count", 0))
    output_bundle = summary.get("output_bundle", {})
    method_outputs = output_bundle.get("method_specific", {})
    header = generate_report_header(
        title="Single-Cell Ambient RNA Removal Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": executed_method,
            "Contamination Est.": f"{summary['contamination_estimate']:.1%}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {requested_method}",
        f"- **Executed method**: {executed_method}",
        f"- **Input source**: {summary.get('input_source', 'unknown')}",
        f"- **Estimated contamination**: {summary['contamination_estimate']:.1%}",
        f"- **Mean counts before**: {summary['mean_counts_before']:.0f}",
        f"- **Mean counts after**: {summary['mean_counts_after']:.0f}",
        f"- **Count reduction**: {summary['count_reduction_pct']:.1f}%",
        f"- **Shared barcodes used for direct before/after comparison**: {shared_barcode_count}",
        "",
        "## Parameters\n",
    ]
    if summary.get("fallback_reason"):
        body_lines.insert(8, f"- **Fallback note**: {summary['fallback_reason']}")
    for warning in summary.get("input_preparation", {}).get("warnings", []):
        body_lines.append(f"- **Input note**: {warning}")
    for k, v in params.items():
        if v is not None:
            body_lines.append(f"- `{k}`: {v}")

    body_lines.extend([
        "",
        "## Outputs\n",
        f"- **OmicsClaw downstream export**: `{output_bundle.get('processed_h5ad', 'processed.h5ad')}`",
        f"- **Machine-readable summary**: `{output_bundle.get('result_json', 'result.json')}`",
        f"- **Human-readable report**: `{output_bundle.get('report_md', 'report.md')}`",
    ])
    if output_bundle.get("readme_md"):
        body_lines.append(f"- **Output guide**: `{output_bundle['readme_md']}`")
    if output_bundle.get("analysis_notebook"):
        body_lines.append(f"- **Analysis notebook**: `{output_bundle['analysis_notebook']}`")
    for figure_path in output_bundle.get("figures", []):
        body_lines.append(f"- **Figure**: `{figure_path}`")
    if method_outputs:
        body_lines.extend([
            "",
            "### Method-specific artifacts",
        ])
        if executed_method == "cellbender":
            body_lines.append("- `processed.h5ad` is OmicsClaw's wrapped AnnData export for downstream skills.")
            body_lines.append("- The files below are the original CellBender-style matrix and log artifacts preserved under `cellbender_output/`.")
        for name, rel_path in method_outputs.items():
            body_lines.append(f"- `{name}`: `{rel_path}`")

    body_lines.extend([
        "",
        "## Methods\n",
        "### CellBender (Recommended for 10X data)",
        "CellBender uses a deep generative model to estimate and remove ambient RNA contamination.",
        "OmicsClaw preserves the original CellBender matrix outputs and additionally writes `processed.h5ad` for downstream interoperability.",
        "",
        "### SoupX (R)",
        "SoupX estimates the ambient RNA profile from raw/filtered 10X matrices and subtracts it from filtered counts.",
        "",
        "### Simple subtraction",
        "Uniform ambient profile subtraction used as the fallback when R or CellBender inputs are unavailable.",
        "",
    ])

    # Troubleshooting section for degenerate output
    if degenerate_diag and degenerate_diag.get("degenerate"):
        body_lines.extend([
            "## Troubleshooting: Ambient Removal Output Issues\n",
        ])
        for issue in degenerate_diag.get("issues", []):
            body_lines.append(f"- **Issue**: {issue}")
        body_lines.append("")
        for i, action in enumerate(degenerate_diag.get("suggested_actions", []), 1):
            body_lines.append(f"### Fix {i}")
            body_lines.append(f"{action}")
            body_lines.append("")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def _ensure_output_contract(adata, *, source_path: str | None) -> tuple[dict, dict]:
    """Write omicsclaw_input_contract and omicsclaw_matrix_contract into adata.uns."""
    input_contract = ensure_input_contract(adata, source_path=source_path)
    existing = get_matrix_contract(adata)

    # After ambient removal, X contains corrected counts (count-like)
    x_kind = "raw_counts"
    layers = dict(existing.get("layers") or {})

    if "counts" in adata.layers:
        layers["counts"] = "raw_counts"

    raw_kind = existing.get("raw")
    if adata.raw is not None:
        raw_kind = "raw_counts_snapshot"
    elif "counts" in adata.layers:
        # Create raw snapshot from pre-correction counts
        try:
            raw_snapshot = sc.AnnData(
                X=adata.layers["counts"].copy(),
                obs=adata.obs.copy(),
                var=adata.var.copy(),
            )
            raw_snapshot.obs_names = adata.obs_names.copy()
            raw_snapshot.var_names = adata.var_names.copy()
            adata.raw = raw_snapshot
            raw_kind = "raw_counts_snapshot"
        except Exception:
            pass

    matrix_contract = record_matrix_contract(
        adata,
        x_kind=x_kind,
        raw_kind=raw_kind,
        layers=layers,
        producer_skill=SKILL_NAME,
    )
    return input_contract, matrix_contract


def _detect_degenerate_output(adata, *, summary: dict) -> dict:
    """Detect degenerate ambient removal output and return diagnostic info."""
    diagnostics: dict = {
        "degenerate": False,
        "issues": [],
        "suggested_actions": [],
    }

    mean_after = summary.get("mean_counts_after", 0)
    mean_before = summary.get("mean_counts_before", 1)
    reduction_pct = summary.get("count_reduction_pct", 0)

    # Check: all zeros after correction
    if mean_after < 1e-6:
        diagnostics["degenerate"] = True
        diagnostics["all_zero"] = True
        diagnostics["issues"].append("All counts are zero after correction.")
        diagnostics["suggested_actions"].extend([
            "Lower the contamination fraction: --contamination 0.02",
            "Check if input already had very low counts — run sc-qc first",
        ])

    # Check: excessive removal (>50% reduction is suspicious)
    if reduction_pct > 50:
        diagnostics["issues"].append(
            f"Ambient removal reduced counts by {reduction_pct:.1f}%, which is unusually high."
        )
        diagnostics["suggested_actions"].append(
            "Consider lowering --contamination (default 0.05). "
            "Typical ambient contamination is 2-10%."
        )

    # Check: no reduction at all
    if abs(reduction_pct) < 0.01 and mean_before > 0:
        diagnostics["issues"].append("No counts were removed — correction had no effect.")
        diagnostics["suggested_actions"].append(
            "Verify the input contains raw counts (not already corrected). "
            "Run sc-qc to inspect the count distribution."
        )

    # Check: very few cells
    if adata.n_obs < 10:
        diagnostics["issues"].append(f"Only {adata.n_obs} cells in output — very small dataset.")
        diagnostics["suggested_actions"].append(
            "Check input file — ambient removal expects a full count matrix."
        )

    if diagnostics["issues"]:
        diagnostics["degenerate"] = True

    return diagnostics


def _write_figures_manifest(output_dir: Path, figure_files: list[str]) -> None:
    """Write figures/manifest.json listing all generated figure files."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "skill": SKILL_NAME,
        "available_files": {
            Path(f).stem: Path(f).name for f in figure_files
        },
    }
    (figures_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_figure_data(output_dir: Path, adata_before, adata_after, *, summary: dict) -> dict:
    """Write figure_data/ CSV files and manifest.json for downstream customization."""
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    # Per-cell count summary
    before_counts = np.asarray(adata_before.X.sum(axis=1)).ravel()
    after_counts = np.asarray(adata_after.X.sum(axis=1)).ravel()

    count_summary = pd.DataFrame({
        "mean_before": [float(before_counts.mean())],
        "mean_after": [float(after_counts.mean())],
        "reduction_pct": [summary.get("count_reduction_pct", 0)],
        "contamination_estimate": [summary.get("contamination_estimate", 0)],
        "method": [summary.get("executed_method", "simple")],
    })
    files["correction_summary"] = "correction_summary.csv"
    count_summary.to_csv(figure_data_dir / files["correction_summary"], index=False)

    # Write gene_expression.csv for plot_feature_violin R renderer.
    # Compares before/after expression for top high-expression genes.
    try:
        import scipy.sparse as sp_local
        # Get top genes by mean expression in after matrix
        X_after = adata_after.X
        if sp_local.issparse(X_after):
            X_after = X_after.toarray()
        gene_means = np.asarray(X_after).mean(axis=0)
        top_idx = np.argsort(gene_means)[::-1][:10]
        top_genes = adata_after.var_names[top_idx].tolist()

        sample_n = min(adata_after.n_obs, 500)
        rng = np.random.default_rng(42)
        cell_idx = rng.choice(adata_after.n_obs, size=sample_n, replace=False)
        cell_ids = adata_after.obs_names[cell_idx].tolist()

        X_sub_after = np.asarray(X_after)[cell_idx][:, top_idx]

        long_rows = []
        for gi, gene in enumerate(top_genes):
            for ci, cell_id in enumerate(cell_ids):
                long_rows.append({
                    "cell_id": cell_id,
                    "gene": f"{gene}_after",
                    "expression": float(X_sub_after[ci, gi]),
                })
        gene_expr_df = pd.DataFrame(long_rows)
        gene_expr_df.to_csv(figure_data_dir / "gene_expression.csv", index=False)
        files["gene_expression"] = "gene_expression.csv"
    except Exception:
        pass

    (figure_data_dir / "manifest.json").write_text(
        json.dumps({"skill": SKILL_NAME, "available_files": files}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return files


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
    parser.add_argument("--r-enhanced", action="store_true", default=False,
                        help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()
    _validate_inputs(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    requested_method = args.method
    method, fallback_reason = _resolve_requested_method(requested_method)
    adata, input_file, input_preparation = _select_runtime_input(
        args,
        requested_method=requested_method,
        resolved_method=method,
    )

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    apply_preflight(
        preflight_sc_ambient_removal(
            adata,
            method=requested_method,
            raw_h5=args.raw_h5,
            raw_matrix_dir=args.raw_matrix_dir,
            filtered_matrix_dir=args.filtered_matrix_dir,
            contamination=args.contamination,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )
    # For simple method on raw/unfiltered input (e.g. 10x raw_feature_bc_matrix.h5),
    # the matrix can contain millions of empty droplets.  Filter to cells with at
    # least 1 detected gene so downstream dense-chunk operations stay memory-safe.
    # The ambient profile is estimated from all barcodes (before filtering) for
    # CellBender/SoupX; for simple we use what's already loaded here which is fine
    # because empty droplets barely affect the mean profile and we're not
    # doing proper background modelling anyway.
    if method == "simple" and adata.n_obs > 500_000:
        n_before_filter = adata.n_obs
        sc.pp.filter_cells(adata, min_genes=1)
        logger.info(
            "Filtered raw/unfiltered matrix from %d to %d barcodes (min_genes=1) "
            "before simple subtraction to avoid OOM.",
            n_before_filter,
            adata.n_obs,
        )

    adata_before = adata.copy()
    mean_before = np.array(adata.X.sum(axis=1)).flatten().mean()

    params = {
        "method": requested_method,
        "expected_cells": args.expected_cells,
        "raw_h5": args.raw_h5,
        "contamination": args.contamination,
        "raw_matrix_dir": args.raw_matrix_dir,
        "filtered_matrix_dir": args.filtered_matrix_dir,
    }

    contamination_estimate = args.contamination
    method_outputs: dict[str, str] = {}
    simple_expression_source = None
    simple_input_warnings: list[str] = []

    if method == "cellbender":
        if not args.raw_h5:
            logger.warning("CellBender requires --raw-h5. Falling back to simple subtraction.")
            fallback_reason = (
                "cellbender requires `--raw-h5`; wrapper executed the simple subtraction path instead"
            )
            method = "simple"
        raw_h5 = Path(args.raw_h5) if args.raw_h5 else None
        if method == "cellbender" and not raw_h5.exists():
            logger.warning("Raw H5 file not found. Falling back to simple subtraction.")
            fallback_reason = (
                f"cellbender raw input was not found at `{raw_h5}`; "
                "wrapper executed the simple subtraction path instead"
            )
            method = "simple"
        if method == "cellbender" and raw_h5.suffix.lower() != ".h5":
            raise ValueError("CellBender only accepts raw 10x .h5 input in this wrapper; processed .h5ad is not supported.")
        if method == "cellbender" and args.expected_cells is None and not args.input_path:
            raise ValueError(
                "When running CellBender without `--input`, please also provide `--expected-cells` "
                "so the prior reflects real cells rather than all droplets."
            )
        if method == "cellbender":
            logger.info("Running CellBender...")
            adata = sc_ambient_utils.run_cellbender(
                raw_h5=raw_h5,
                expected_cells=args.expected_cells or adata.n_obs,
                output_dir=output_dir / "cellbender_output",
            )
            method_outputs = _collect_cellbender_outputs(output_dir)
            contamination_estimate = estimate_contamination_simple(adata)

    elif method == "soupx":
        raw_dir = Path(args.raw_matrix_dir) if args.raw_matrix_dir else None
        filtered_dir = Path(args.filtered_matrix_dir) if args.filtered_matrix_dir else None
        if raw_dir and filtered_dir and raw_dir.exists() and filtered_dir.exists():
            try:
                corrected_matrix, cells, genes, contamination_estimate = run_soupx(
                    raw_matrix_dir=str(raw_dir),
                    filtered_matrix_dir=str(filtered_dir),
                )
                adata = apply_soupx_result(adata, corrected_matrix, cells, genes, contamination_estimate)
            except Exception as exc:
                logger.warning("SoupX failed (%s). Falling back to simple subtraction.", exc)
                fallback_reason = (
                    f"soupx failed ({exc}); wrapper executed the simple subtraction path instead"
                )
                method = "simple"
        else:
            logger.warning("SoupX requires --raw-matrix-dir and --filtered-matrix-dir. Falling back to simple subtraction.")
            fallback_reason = (
                "soupx requires both --raw-matrix-dir and --filtered-matrix-dir; "
                "wrapper executed the simple subtraction path instead"
            )
            method = "simple"
            params["method"] = method

    if method == "simple":
        logger.info("Applying simple ambient subtraction (contamination=%s)", args.contamination)
        count_matrix, expression_source, count_warnings = _get_count_like_matrix(adata)
        simple_expression_source = expression_source
        simple_input_warnings.extend(count_warnings)
        ambient_profile = np.array(count_matrix.mean(axis=0)).flatten()
        ambient_profile = ambient_profile / max(ambient_profile.sum(), 1e-8)
        # Use chunk-wise sparse arithmetic to avoid OOM on large raw/unfiltered matrices.
        # The correction is: corrected[i,j] = max(0, X[i,j] - contamination * sum(X[i,:]) * ambient_profile[j])
        # Processing in row-chunks keeps peak memory proportional to chunk_size * n_genes, not n_cells * n_genes.
        if sp.issparse(count_matrix):
            csr = count_matrix.tocsr().astype(np.float32)
            n_cells, n_genes = csr.shape
            chunk_size = max(1, min(50_000, n_cells))
            corrected_chunks: list[sp.csr_matrix] = []
            ambient_profile_f32 = ambient_profile.astype(np.float32)
            for start in range(0, n_cells, chunk_size):
                chunk = csr[start : start + chunk_size].toarray()  # shape: (chunk, n_genes) — safe size
                cell_totals_chunk = chunk.sum(axis=1, keepdims=True)
                chunk -= args.contamination * cell_totals_chunk * ambient_profile_f32[np.newaxis, :]
                np.maximum(chunk, 0, out=chunk)
                corrected_chunks.append(sp.csr_matrix(chunk, dtype=np.float32))
                del chunk
            corrected_sparse = sp.vstack(corrected_chunks, format="csr")
            del corrected_chunks
            adata.layers["counts"] = count_matrix.copy()
            adata.X = corrected_sparse
        else:
            corrected = np.asarray(count_matrix, dtype=np.float32).copy()
            cell_totals = corrected.sum(axis=1, keepdims=True)
            corrected = corrected - (args.contamination * cell_totals * ambient_profile[np.newaxis, :])
            corrected = np.maximum(corrected, 0)
            adata.layers["counts"] = count_matrix.copy()
            adata.X = corrected.astype(np.float32)
        adata.uns["ambient_correction"] = {"method": "simple", "contamination_fraction": args.contamination, "expression_source": expression_source}
        contamination_estimate = args.contamination

    mean_after = np.array(adata.X.sum(axis=1)).flatten().mean()
    shared_before_counts, _ = _shared_barcode_counts(adata_before, adata)
    summary = {
        "n_cells": int(adata.n_obs),
        "method": method,
        "requested_method": requested_method,
        "executed_method": method,
        "fallback_used": requested_method != method,
        "fallback_reason": fallback_reason,
        "input_source": input_file or "demo",
        "input_preparation": input_preparation,
        "contamination_estimate": float(contamination_estimate),
        "mean_counts_before": float(mean_before),
        "mean_counts_after": float(mean_after),
        "count_reduction_pct": float((1 - mean_after / max(mean_before, 1e-8)) * 100),
        "shared_barcode_count": int(shared_before_counts.size),
        "output_bundle": {
            "processed_h5ad": "processed.h5ad",
            "report_md": "report.md",
            "result_json": "result.json",
            "method_specific": method_outputs,
        },
    }
    params["requested_method"] = requested_method
    params["executed_method"] = method
    if fallback_reason:
        params["fallback_reason"] = fallback_reason
    if simple_expression_source:
        params["simple_expression_source"] = simple_expression_source
        input_preparation["expression_source"] = simple_expression_source
    if simple_input_warnings:
        input_preparation.setdefault("warnings", []).extend(simple_input_warnings)

    # --- Degenerate output detection ---
    degenerate_diag = _detect_degenerate_output(adata, summary=summary)

    figures = generate_ambient_figures(adata_before, adata, output_dir, method=method)
    summary["output_bundle"]["figures"] = [str(Path(fig).relative_to(output_dir)) for fig in figures]

    # --- Write figures/manifest.json ---
    figure_rel_paths = summary["output_bundle"]["figures"]
    _write_figures_manifest(output_dir, figure_rel_paths)

    # --- Write figure_data/ ---
    figure_data_files = _write_figure_data(output_dir, adata_before, adata, summary=summary)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd_parts = ["python", "sc_ambient.py", "--output", str(output_dir), "--method", requested_method]
    if input_file:
        cmd_parts.extend(["--input", input_file])
    if args.raw_h5:
        cmd_parts.extend(["--raw-h5", args.raw_h5])
    if args.raw_matrix_dir:
        cmd_parts.extend(["--raw-matrix-dir", args.raw_matrix_dir])
    if args.filtered_matrix_dir:
        cmd_parts.extend(["--filtered-matrix-dir", args.filtered_matrix_dir])
    if args.expected_cells is not None:
        cmd_parts.extend(["--expected-cells", str(args.expected_cells)])
    if args.contamination is not None:
        cmd_parts.extend(["--contamination", str(args.contamination)])
    if args.demo:
        cmd_parts.append("--demo")
    cmd = " ".join(shlex.quote(part) for part in cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )

    # --- Write contracts and processed.h5ad ---
    input_contract, matrix_contract = _ensure_output_contract(adata, source_path=input_file)
    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).exists() and Path(input_file).is_file()
        else ""
    )
    result_data = {
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "fallback_used": bool(summary.get("fallback_used")),
        "fallback_reason": summary.get("fallback_reason"),
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "input_preparation": input_preparation,
        "output_bundle": summary.get("output_bundle", {}),
        "visualization": {
            "available_figure_data": figure_data_files,
        },
        "ambient_diagnostics": degenerate_diag,
    }
    result_data["next_steps"] = [
        {"skill": "sc-qc", "reason": "Re-compute QC metrics after ambient RNA removal", "priority": "recommended"},
    ]
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    if (output_dir / "README.md").exists():
        summary["output_bundle"]["readme_md"] = "README.md"
    for candidate in ["analysis_notebook.ipynb", "analysis.ipynb"]:
        if (output_dir / candidate).exists():
            summary["output_bundle"]["analysis_notebook"] = candidate
            break
    result_data["output_bundle"] = summary.get("output_bundle", {})
    write_ambient_report(output_dir, summary, params, input_file, degenerate_diag=degenerate_diag)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    # --- Degenerate output stdout guidance ---
    if degenerate_diag.get("degenerate"):
        print()
        print("  *** WARNING: Ambient removal output may be problematic. ***")
        for issue in degenerate_diag.get("issues", []):
            print(f"  - {issue}")
        print()
        print("  How to fix:")
        for i, action in enumerate(degenerate_diag.get("suggested_actions", []), 1):
            print(f"    Option {i}: {action}")
        print()

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Ambient correction complete: requested={summary['requested_method']}, "
        f"executed={summary['executed_method']}, contamination ~ {summary['contamination_estimate']:.1%}"
    )

    # --- Next-step guidance ---
    print()
    print(">> Next step: Run sc-qc with the cleaned counts")
    print(f"  python omicsclaw.py run sc-qc --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()

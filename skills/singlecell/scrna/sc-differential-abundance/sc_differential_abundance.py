#!/usr/bin/env python3
"""Single-cell differential abundance and compositional analysis.

Usage:
    python sc_differential_abundance.py --input <data.h5ad> --output <dir>
    python sc_differential_abundance.py --demo --output <dir>

Methods: milo (neighborhood-level DA), sccoda (Bayesian compositional), simple (proportion screen).
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_repro_requirements,
    write_result_json,
    write_replot_hint,
    write_standard_run_artifacts,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad, write_h5ad_aliases
from skills.singlecell._lib.differential_abundance import (
    build_composition_summary,
    make_demo_da_adata,
    run_milo_da,
    run_sccoda_da,
    run_simple_da,
    save_heatmap,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-differential-abundance"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py"
R_SCRIPTS_DIR = _PROJECT_ROOT / "omicsclaw" / "r_scripts"

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_cell_barplot": "r_cell_barplot.png",
    "plot_proportion_test": "r_proportion_test.png",
    "plot_cell_density": "r_cell_density.png",
}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_backend(result_obj, default: str) -> str:
    if isinstance(result_obj, dict):
        return str(result_obj.get("backend", default))
    if hasattr(result_obj, "uns") and isinstance(getattr(result_obj, "uns"), dict):
        return str(result_obj.uns.get("backend", default))
    return default


def _obs_column_candidates(adata, family: str) -> list[str]:
    """Return adata.obs columns matching a keyword family."""
    from skills.singlecell._lib.preflight import _OBS_FAMILY_KEYWORDS
    keywords = _OBS_FAMILY_KEYWORDS.get(family, ())
    return [c for c in adata.obs.columns if any(kw in c.lower() for kw in keywords)]


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def _preflight_da(adata, *, method: str, condition_key: str, sample_key: str, cell_type_key: str) -> list[str]:
    """Validate metadata columns exist and have meaningful content. Returns list of problems."""
    problems: list[str] = []

    # --- condition_key ---
    if condition_key not in adata.obs.columns:
        candidates = _obs_column_candidates(adata, "condition")
        hint = f" Candidate condition columns: {candidates}" if candidates else ""
        problems.append(
            f"Condition column '{condition_key}' not found in adata.obs.{hint}\n"
            f"  Fix: --condition-key <column_name>\n"
            f"  Available columns: {list(adata.obs.columns[:20])}"
        )
    else:
        n_levels = adata.obs[condition_key].nunique()
        if n_levels < 2:
            problems.append(
                f"Condition column '{condition_key}' has only {n_levels} level(s). "
                f"DA requires at least 2 conditions to compare."
            )

    # --- sample_key ---
    if sample_key not in adata.obs.columns:
        candidates = _obs_column_candidates(adata, "batch")
        hint = f" Candidate sample columns: {candidates}" if candidates else ""
        problems.append(
            f"Sample column '{sample_key}' not found in adata.obs.{hint}\n"
            f"  Fix: --sample-key <column_name>"
        )
    else:
        n_samples = adata.obs[sample_key].nunique()
        if n_samples < 2:
            problems.append(
                f"Sample column '{sample_key}' has only {n_samples} unique value(s). "
                f"DA requires replicate samples."
            )
        elif method in ("milo", "sccoda"):
            # Check at least 2 samples per condition
            if condition_key in adata.obs.columns:
                sample_per_cond = (
                    adata.obs.groupby(condition_key, observed=True)[sample_key]
                    .nunique()
                )
                under_represented = sample_per_cond[sample_per_cond < 2]
                if not under_represented.empty:
                    problems.append(
                        f"Conditions with < 2 samples: {dict(under_represented)}. "
                        f"Milo/scCODA need >=2 biological replicates per condition for meaningful inference. "
                        f"Consider --method simple for exploratory analysis."
                    )

    # --- cell_type_key ---
    if cell_type_key not in adata.obs.columns:
        candidates = _obs_column_candidates(adata, "cell_type")
        hint = f" Candidate cell-type columns: {candidates}" if candidates else ""
        problems.append(
            f"Cell-type column '{cell_type_key}' not found in adata.obs.{hint}\n"
            f"  Fix: --cell-type-key <column_name>"
        )
    else:
        n_types = adata.obs[cell_type_key].nunique()
        if n_types < 2:
            problems.append(
                f"Cell-type column '{cell_type_key}' has only {n_types} type(s). "
                f"DA compares changes across cell types/neighborhoods — at least 2 are expected."
            )

    return problems


# ---------------------------------------------------------------------------
# Degenerate output detection
# ---------------------------------------------------------------------------

def _check_degenerate(summary: dict, method: str) -> dict:
    """Detect degenerate DA output. Returns diagnostic dict."""
    diag: dict = {"degenerate": False, "suggested_actions": []}
    n_sig = summary.get("n_significant", 0)
    n_total = summary.get("n_nhoods", summary.get("n_cell_types", summary.get("n_effect_rows", 0)))

    if n_total == 0:
        diag["degenerate"] = True
        diag["empty_result"] = True
        diag["suggested_actions"] = [
            "Check that --condition-key, --sample-key, --cell-type-key point to correct columns.",
            "Ensure at least 2 conditions with >=2 samples each.",
            "Try --method simple for an exploratory proportion screen.",
        ]
    elif n_sig == 0 and method != "simple":
        diag["no_significant"] = True
        diag["suggested_actions"] = [
            f"No significant DA hits at the current FDR threshold. Consider relaxing --fdr.",
            "This may reflect genuine biological similarity between conditions.",
            "Try --method simple for an unsupervised exploratory screen.",
        ]

    return diag


# ---------------------------------------------------------------------------
# Figures / manifests
# ---------------------------------------------------------------------------

def _write_figures_manifest(output_dir: Path, plots: list[dict]) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "recipe_id": "standard-sc-da-gallery",
        "skill_name": SKILL_NAME,
        "title": "Differential abundance gallery",
        "description": "Composition and DA result plots.",
        "backend": "python",
        "plots": plots,
    }
    (figures_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_figure_data_manifest(output_dir: Path, available_files: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": "standard-sc-da-gallery",
        "available_files": available_files,
    }
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _export_figure_data(output_dir: Path, *, counts: pd.DataFrame, props: pd.DataFrame, mean_props: pd.DataFrame) -> dict:
    """Export plot-ready CSVs to figure_data/ and return file mapping."""
    fd_dir = output_dir / "figure_data"
    fd_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "sample_by_celltype_counts": "sample_by_celltype_counts.csv",
        "sample_by_celltype_proportions": "sample_by_celltype_proportions.csv",
        "condition_mean_proportions": "condition_mean_proportions.csv",
    }
    counts.to_csv(fd_dir / files["sample_by_celltype_counts"])
    props.to_csv(fd_dir / files["sample_by_celltype_proportions"])
    mean_props.to_csv(fd_dir / files["condition_mean_proportions"])
    return files


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None, diagnostics: dict) -> None:
    backend = str(summary.get("backend", summary.get("method", "NA")))
    header = generate_report_header(
        title="Single-Cell Differential Abundance Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(params.get("method", "NA")),
            "Backend": backend,
            "Condition key": str(params.get("condition_key", "condition")),
            "Sample key": str(params.get("sample_key", "sample")),
            "Cell type key": str(params.get("cell_type_key", "cell_type")),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Execution backend: `{backend}`",
        f"- Samples: `{summary.get('n_samples', 'NA')}`",
        f"- Cell types: `{summary.get('n_cell_types', 'NA')}`",
        f"- Significant hits: `{summary.get('n_significant', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- Differential abundance is a sample-aware comparison of cell-state or cell-type prevalence between biological conditions.",
        "- Prefer replicate-aware methods such as Milo or scCODA when you have multiple samples per condition.",
        "- Treat the exploratory `simple` mode as a lightweight proportion screen, not as a replacement for neighborhood- or Bayesian compositional models.",
        "",
        "## Output Files",
        "",
        "- `processed.h5ad` -- AnnData with DA metadata",
        "- `annotated_input.h5ad` -- compatibility alias",
        "- `figures/` -- composition and DA visualizations",
        "- `tables/` -- count/proportion tables and method results",
        "- `figure_data/` -- plot-ready CSVs for customization",
        "- `result.json` -- machine-readable summary",
    ]

    # Troubleshooting section for degenerate output
    if diagnostics.get("degenerate") or diagnostics.get("no_significant"):
        body.extend([
            "",
            "## Troubleshooting",
            "",
        ])
        if diagnostics.get("empty_result"):
            body.extend([
                "### Empty results",
                "",
                "The analysis produced no results. Common causes:",
                "1. Wrong metadata column names -- verify --condition-key, --sample-key, --cell-type-key",
                "2. Insufficient replicates -- Milo/scCODA need >=2 samples per condition",
                "3. Try `--method simple` for exploratory analysis without strict sample requirements",
            ])
        if diagnostics.get("no_significant"):
            body.extend([
                "### No significant hits",
                "",
                "No cell types/neighborhoods passed the FDR threshold. This may mean:",
                "1. The conditions are genuinely similar in composition",
                "2. Insufficient statistical power (too few replicates)",
                "3. Try relaxing `--fdr 0.1` or using `--method simple` for an exploratory screen",
            ])

    body.append("")
    (output_dir / "report.md").write_text(
        header + "\n" + "\n".join(body) + "\n" + generate_report_footer(),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def _write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    command_parts.extend([
        "--output", str(output_dir),
        "--method", params["method"],
        "--condition-key", params["condition_key"],
        "--sample-key", params["sample_key"],
        "--cell-type-key", params["cell_type_key"],
    ])
    if params.get("contrast"):
        command_parts.extend(["--contrast", params["contrast"]])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "pertpy", "statsmodels"])


# ---------------------------------------------------------------------------
# proportion_test_r (R bridge)
# ---------------------------------------------------------------------------

def _run_proportion_test_r(adata, condition_key: str, cell_type_key: str, output_dir: Path, params: dict) -> dict:
    """Run base-R Monte Carlo permutation test via RScriptRunner."""
    import warnings
    from omicsclaw.core.r_script_runner import RScriptRunner, RScriptError

    r_script = R_SCRIPTS_DIR / "sc_proportion_test_r.R"
    if not r_script.exists():
        raise FileNotFoundError(f"R script not found: {r_script}")

    r_work_dir = output_dir / "r_work"
    r_work_dir.mkdir(parents=True, exist_ok=True)

    # Export cell metadata for R (cell_id + relevant columns only)
    meta_cols = [cell_type_key, condition_key]
    meta_df = adata.obs[meta_cols].copy().reset_index()
    meta_df.columns = ["cell_id"] + meta_cols
    meta_csv = r_work_dir / "cell_meta.csv"
    meta_df.to_csv(meta_csv, index=False)

    comparison = params.get("contrast", None) or "auto"
    n_perm = str(params.get("n_permutations", 1000))

    runner = RScriptRunner(timeout=300)
    result_csv = r_work_dir / "proportion_test_results.csv"
    r_success = True
    try:
        runner.run_script(
            r_script,
            args=[str(meta_csv), str(r_work_dir), cell_type_key,
                  condition_key, comparison, n_perm],
            expected_outputs=["proportion_test_results.csv"],
            output_dir=r_work_dir,
        )
    except (RScriptError, FileNotFoundError) as exc:
        warnings.warn(f"proportion_test_r R script failed: {exc}")
        r_success = False

    result_df = pd.DataFrame()
    if r_success and result_csv.exists():
        try:
            result_df = pd.read_csv(result_csv)
        except Exception as exc:
            warnings.warn(f"Could not read proportion_test_r results: {exc}")

    # Store in adata.uns
    if not result_df.empty:
        adata.uns["proportion_test_r_results"] = result_df.to_dict(orient="list")

    return {
        "method": "proportion_test_r",
        "backend": "base_R",
        "r_success": r_success,
        "n_comparisons": int(result_df["comparison"].nunique()) if not result_df.empty else 0,
        "n_cell_types": int(result_df["clusters"].nunique()) if not result_df.empty else 0,
        "n_significant": int((result_df["FDR"] < 0.05).sum()) if not result_df.empty and "FDR" in result_df.columns else 0,
    }


def _plot_proportion_test_r(result_df: pd.DataFrame, output_dir: Path) -> list[dict]:
    """Generate lollipop plot with bootstrap CI error bars from R output."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    plots: list[dict] = []

    if result_df.empty:
        # Placeholder figure for empty results
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No proportion test results available",
                ha="center", va="center", fontsize=12, color="#999999")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        out_path = figures_dir / "proportion_test_r_no_results.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plots.append({
            "plot_id": "proportion_test_r_no_results",
            "role": "result",
            "backend": "python",
            "renderer": "proportion_test_r_lollipop",
            "filename": "proportion_test_r_no_results.png",
            "title": "Proportion Test (no results)",
            "description": "No valid results from R permutation test.",
            "status": "rendered",
            "path": str(out_path),
        })
        return plots

    # One plot per comparison
    for comp_name, comp_df in result_df.groupby("comparison"):
        comp_df = comp_df.sort_values("obs_log2FD", ascending=True).copy()
        n_types = len(comp_df)

        fig, ax = plt.subplots(figsize=(8, max(3, 0.35 * n_types)))

        colors = ["#D73027" if fdr < 0.05 else "#999999" for fdr in comp_df["FDR"]]
        y_pos = np.arange(n_types)

        # Error bars (bootstrap CI)
        xerr_lo = comp_df["obs_log2FD"].values - comp_df["boot_CI_2.5"].values
        xerr_hi = comp_df["boot_CI_97.5"].values - comp_df["obs_log2FD"].values
        xerr = np.array([xerr_lo, xerr_hi])
        # Clamp negative error bar widths to 0
        xerr = np.maximum(xerr, 0)

        ax.errorbar(
            comp_df["obs_log2FD"].values, y_pos,
            xerr=xerr,
            fmt="none", ecolor="#666666", elinewidth=1, capsize=3,
        )
        ax.scatter(
            comp_df["obs_log2FD"].values, y_pos,
            c=colors, s=60, zorder=5, edgecolors="white", linewidths=0.5,
        )
        ax.axvline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(comp_df["clusters"].values)
        ax.set_xlabel("Observed log2(Fold Difference)")
        ax.set_title(f"Proportion Test: {comp_name}")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        safe_name = str(comp_name).replace(" ", "_")
        out_path = figures_dir / f"proportion_test_r_{safe_name}.png"
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        plots.append({
            "plot_id": f"proportion_test_r_{safe_name}",
            "role": "result",
            "backend": "python",
            "renderer": "proportion_test_r_lollipop",
            "filename": f"proportion_test_r_{safe_name}.png",
            "title": f"Proportion Test: {comp_name}",
            "description": f"Lollipop plot with bootstrap 95% CI. Red = FDR < 0.05.",
            "status": "rendered",
            "path": str(out_path),
        })

    return plots


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell differential abundance and compositional analysis")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="milo", choices=["milo", "sccoda", "simple", "proportion_test_r"])
    p.add_argument("--condition-key", type=str, default="condition",
                    help="obs column for condition/treatment groups (common: 'condition', 'treatment', 'disease', 'group')")
    p.add_argument("--sample-key", type=str, default="sample",
                    help="obs column for biological replicates (common: 'sample', 'batch', 'donor', 'patient', 'replicate')")
    p.add_argument("--cell-type-key", type=str, default="cell_type",
                    help="obs column for cell type labels (common: 'cell_type', 'celltype', 'annotation', 'leiden')")
    p.add_argument("--contrast", type=str, default=None, help="Example: control vs stim")
    p.add_argument("--reference-cell-type", type=str, default="automatic")
    p.add_argument("--fdr", type=float, default=0.05)
    p.add_argument("--prop", type=float, default=0.1)
    p.add_argument("--n-neighbors", type=int, default=30)
    p.add_argument("--min-count", type=int, default=10)
    p.add_argument("--n-permutations", type=int, default=1000, help="Permutations for proportion_test_r")
    p.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.fraction("fdr", args.fdr)
    v.positive("n_neighbors", args.n_neighbors, min_val=2)
    v.non_negative("min_count", args.min_count)
    v.positive("n_permutations", args.n_permutations, min_val=1)
    v.in_range("prop", args.prop, low=0, high=1)
    v.check()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)

    # ---- Load data ----
    if args.demo:
        adata = make_demo_da_adata()
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)

    # ---- Preflight checks ----
    problems = _preflight_da(
        adata,
        method=args.method,
        condition_key=args.condition_key,
        sample_key=args.sample_key,
        cell_type_key=args.cell_type_key,
    )
    if problems:
        print()
        print("  *** PREFLIGHT FAILED ***")
        for i, prob in enumerate(problems, 1):
            print(f"  {i}. {prob}")
        print()
        raise SystemExit(1)

    # ---- Composition summary ----
    counts, props, mean_props = build_composition_summary(
        adata,
        sample_key=args.sample_key,
        condition_key=args.condition_key,
        celltype_key=args.cell_type_key,
    )
    counts.to_csv(tables_dir / "sample_by_celltype_counts.csv")
    props.to_csv(tables_dir / "sample_by_celltype_proportions.csv")
    mean_props.to_csv(tables_dir / "condition_mean_proportions.csv")

    # Heatmap figure
    figures: list[dict] = []
    hm_path = save_heatmap(props, figures_dir / "sample_celltype_proportions.png", "Sample-by-cell-type proportions")
    if hm_path:
        figures.append({
            "plot_id": "sample_celltype_proportions",
            "role": "overview",
            "backend": "python",
            "renderer": "save_heatmap",
            "filename": "sample_celltype_proportions.png",
            "title": "Sample-by-cell-type proportions",
            "description": "Heatmap of cell-type proportions across samples.",
            "status": "rendered",
            "path": str(hm_path),
        })

    # ---- Method dispatch ----
    result_tables: dict[str, str] = {}
    summary: dict = {
        "method": args.method,
        "backend": args.method,
        "n_samples": int(counts.shape[0]),
        "n_cell_types": int(counts.shape[1]),
    }

    if args.method == "simple":
        da = run_simple_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            contrast=args.contrast,
            fdr=args.fdr,
        )
        da.to_csv(tables_dir / "simple_da_results.csv", index=False)
        result_tables["simple_da_results"] = "tables/simple_da_results.csv"
        summary.update({
            "n_significant": int(da["significant"].sum()) if not da.empty and "significant" in da.columns else 0,
            "contrast": args.contrast or "auto",
        })

    elif args.method == "milo":
        mdata, nhood = run_milo_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            prop=args.prop,
            n_neighbors=args.n_neighbors,
            contrast=args.contrast,
        )
        summary["backend"] = _extract_backend(mdata, args.method)
        nhood.to_csv(tables_dir / "milo_nhood_results.csv", index=False)
        result_tables["milo_nhood_results"] = "tables/milo_nhood_results.csv"

        # Milo barplot
        if {"nhood_annotation", "SpatialFDR", "logFC"}.issubset(nhood.columns):
            plot_df = nhood[["nhood_annotation", "SpatialFDR", "logFC"]].copy()
            plot_df = plot_df.dropna().sort_values("logFC")
            if not plot_df.empty:
                fig, ax = plt.subplots(figsize=(8, max(4, 0.25 * len(plot_df))))
                colors = ["#d73027" if x <= args.fdr else "#bdbdbd" for x in plot_df["SpatialFDR"]]
                ax.barh(plot_df["nhood_annotation"].astype(str), plot_df["logFC"], color=colors)
                ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
                ax.set_title("Milo neighborhood logFC by annotation")
                fig.tight_layout()
                fig.savefig(figures_dir / "milo_logfc_barplot.png", dpi=200)
                plt.close(fig)
                figures.append({
                    "plot_id": "milo_logfc_barplot",
                    "role": "result",
                    "backend": "python",
                    "renderer": "milo_barplot",
                    "filename": "milo_logfc_barplot.png",
                    "title": "Milo neighborhood logFC",
                    "description": "Horizontal bar plot of per-neighborhood log-fold changes. Red = FDR significant.",
                    "status": "rendered",
                    "path": str(figures_dir / "milo_logfc_barplot.png"),
                })

        summary.update({
            "n_nhoods": int(len(nhood)),
            "n_significant": int((nhood.get("SpatialFDR", pd.Series(dtype=float)) <= args.fdr).sum()) if not nhood.empty else 0,
        })

    elif args.method == "proportion_test_r":
        prop_params = {
            "contrast": args.contrast,
            "n_permutations": args.n_permutations,
        }
        prop_summary = _run_proportion_test_r(adata, args.condition_key, args.cell_type_key, output_dir, prop_params)
        result_df = pd.DataFrame(adata.uns.get("proportion_test_r_results", {}))
        if not result_df.empty:
            result_df.to_csv(tables_dir / "proportion_test_results.csv", index=False)
            result_tables["proportion_test_results"] = "tables/proportion_test_results.csv"
            # Also export to figure_data/ for R Enhanced plot_proportion_test renderer
            fd_dir = output_dir / "figure_data"
            fd_dir.mkdir(parents=True, exist_ok=True)
            result_df.to_csv(fd_dir / "proportion_test_results.csv", index=False)
        prop_plots = _plot_proportion_test_r(result_df, output_dir)
        figures.extend(prop_plots)
        summary.update(prop_summary)

    else:  # sccoda
        mdata, effect_df = run_sccoda_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            reference_cell_type=args.reference_cell_type,
            fdr=args.fdr,
        )
        summary["backend"] = _extract_backend(mdata, args.method)
        effect_df.to_csv(tables_dir / "sccoda_effects.csv", index=False)
        result_tables["sccoda_effects"] = "tables/sccoda_effects.csv"

        if "log2-fold change" in effect_df.columns:
            plot_df = effect_df.dropna(subset=["log2-fold change"]).copy()
            if not plot_df.empty:
                fig, ax = plt.subplots(figsize=(8, max(4, 0.3 * len(plot_df))))
                ax.barh(plot_df["Cell Type"].astype(str), plot_df["log2-fold change"].astype(float), color="#3182bd")
                ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
                ax.set_title("scCODA log2-fold change")
                fig.tight_layout()
                fig.savefig(figures_dir / "sccoda_log2fc_barplot.png", dpi=200)
                plt.close(fig)
                figures.append({
                    "plot_id": "sccoda_log2fc_barplot",
                    "role": "result",
                    "backend": "python",
                    "renderer": "sccoda_barplot",
                    "filename": "sccoda_log2fc_barplot.png",
                    "title": "scCODA log2-fold change",
                    "description": "Horizontal bar plot of scCODA effect sizes per cell type.",
                    "status": "rendered",
                    "path": str(figures_dir / "sccoda_log2fc_barplot.png"),
                })

        summary.update({
            "reference_cell_type": args.reference_cell_type,
            "n_effect_rows": int(len(effect_df)),
            "n_significant": int((effect_df.get("Final Parameter", pd.Series(dtype=float)) != 0).sum()) if not effect_df.empty and "Final Parameter" in effect_df.columns else 0,
        })

    # ---- Degenerate output check ----
    diagnostics = _check_degenerate(summary, args.method)
    if diagnostics.get("degenerate"):
        print()
        print("  *** DEGENERATE OUTPUT: DA analysis produced empty results. ***")
        for i, action in enumerate(diagnostics["suggested_actions"], 1):
            print(f"  {i}. {action}")
        print()
    elif diagnostics.get("no_significant"):
        print()
        print(f"  *** NOTE: No significant DA hits at FDR <= {args.fdr}. ***")
        for i, action in enumerate(diagnostics["suggested_actions"], 1):
            print(f"  {i}. {action}")
        print()

    # ---- Write figures/manifest and figure_data/manifest ----
    _write_figures_manifest(output_dir, figures)
    fd_files = _export_figure_data(output_dir, counts=counts, props=props, mean_props=mean_props)
    _write_figure_data_manifest(output_dir, fd_files)

    # ---- Persist h5ad with contracts ----
    adata.uns["differential_abundance"] = summary.copy()

    # Ensure layers["counts"] exists
    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
    if adata.raw is None:
        adata.raw = adata.copy()

    params = {
        "method": args.method,
        "condition_key": args.condition_key,
        "sample_key": args.sample_key,
        "cell_type_key": args.cell_type_key,
        "contrast": args.contrast,
        "reference_cell_type": args.reference_cell_type,
        "fdr": args.fdr,
        "prop": args.prop,
        "n_neighbors": args.n_neighbors,
        "min_count": args.min_count,
    }

    store_analysis_metadata(adata, SKILL_NAME, args.method, params)
    _, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind="raw_counts_snapshot",
    )

    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    alias_paths = write_h5ad_aliases(output_h5ad, [output_dir / "annotated_input.h5ad"])
    logger.info("Saved: %s", output_h5ad)

    # ---- result.json ----
    result_data = {
        "method": args.method,
        "params": params,
        "tables": result_tables,
        "input_contract": adata.uns.get("omicsclaw_input_contract", {}),
        "matrix_contract": matrix_contract,
        "visualization": {
            "recipe_id": "standard-sc-da-gallery",
            "available_figure_data": fd_files,
        },
        "output_files": {
            "processed_h5ad": str(output_h5ad),
            "compatibility_aliases": [str(p) for p in alias_paths],
            "figures_dir": str(figures_dir),
            "tables_dir": str(tables_dir),
        },
    }
    if diagnostics.get("degenerate") or diagnostics.get("no_significant"):
        result_data["da_diagnostics"] = diagnostics

    result_data["next_steps"] = [
        {"skill": "sc-de", "reason": "Differential expression in abundance-changed populations", "priority": "optional"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, input_checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    # ---- report.md ----
    _write_report(output_dir, summary, params, input_path, diagnostics)

    # ---- Reproducibility ----
    _write_reproducibility(output_dir, params, input_path, demo_mode=args.demo)

    # ---- Standard artifacts (README, notebook) ----
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Sample-aware differential abundance and compositional analysis for scRNA-seq.",
        result_payload=result_payload,
        preferred_method=args.method,
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    # ---- Final stdout summary ----
    print(f"\n{'='*60}")
    print(f"{'Success' if not diagnostics.get('degenerate') else 'Completed with warnings'}: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Method: {args.method} (backend: {summary.get('backend', 'NA')})")
    print(f"  Samples: {summary.get('n_samples', 'NA')}")
    print(f"  Cell types: {summary.get('n_cell_types', 'NA')}")
    print(f"  Significant hits: {summary.get('n_significant', 'NA')}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete. Consider sc-de for gene-level differences:")
    print(f"  python omicsclaw.py run sc-de --input {output_dir}/processed.h5ad --output <dir>")

    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

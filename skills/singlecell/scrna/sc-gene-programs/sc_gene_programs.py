#!/usr/bin/env python3
"""Single-cell gene program discovery.

Template-aligned skill following SC-DEVELOPMENT-CHECKLIST.md.
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_result_json,
    write_replot_hint,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gene_programs import (
    make_demo_gene_program_adata,
    run_cnmf_programs,
    run_nmf_programs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-gene-programs"
SKILL_VERSION = "0.2.0"

# R Enhanced plotting configuration
R_ENHANCED_PLOTS = {
    # gene-programs exports program usage as gene_expression.csv (programs as features).
    # No UMAP/embedding data — embedding renderers are not appropriate here.
    "plot_feature_violin": "r_feature_violin.png",
    "plot_feature_cor": "r_feature_cor.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
    """Render R Enhanced plots if requested. Returns list of generated paths."""
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
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell gene program discovery")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="cnmf", choices=["cnmf", "nmf"])
    p.add_argument("--n-programs", type=int, default=6)
    p.add_argument("--n-iter", type=int, default=400)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--layer", type=str, default=None)
    p.add_argument("--top-genes", type=int, default=30)
    p.add_argument("--r-enhanced", action="store_true", help="Generate R Enhanced plots (requires R + ggplot2)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def _preflight(adata, *, method: str, layer: str | None) -> list[str]:
    """Validate matrix semantics. Returns list of warning strings."""
    warnings: list[str] = []

    matrix_contract = get_matrix_contract(adata)
    x_kind = matrix_contract.get("X") or infer_x_matrix_kind(adata, fallback="normalized_expression")

    # NMF requires non-negative input.  Normalized + log1p data is fine.
    # Raw counts are also fine.  Scaled data with negatives is NOT fine.
    source_layer = layer
    if source_layer is None and method == "cnmf" and "counts" in adata.layers:
        source_layer = "counts"

    if source_layer:
        mat = adata.layers.get(source_layer)
        if mat is None:
            raise SystemExit(
                f"Layer '{source_layer}' not found in adata.layers.\n"
                f"Available layers: {list(adata.layers.keys())}\n"
                "Use --layer <name> to specify a different layer, or omit --layer to use adata.X."
            )
    else:
        mat = adata.X

    if hasattr(mat, "toarray"):
        sample = mat[:100].toarray()
    else:
        sample = np.asarray(mat[:100])

    if np.any(sample < 0):
        raise SystemExit(
            "NMF/cNMF requires non-negative input, but the data matrix contains negative values.\n"
            "This usually means the data has been z-score scaled.\n\n"
            "How to fix:\n"
            "  Option 1 -- Use the 'counts' layer:  --layer counts\n"
            "  Option 2 -- Re-run sc-preprocessing without scaling, then use the output.\n"
            "  Option 3 -- Provide a raw counts or log-normalized AnnData file.\n"
        )

    if x_kind == "raw_counts" and method == "nmf" and layer is None:
        warnings.append(
            "adata.X appears to be raw counts. NMF can work on raw counts but "
            "results may be dominated by library-size effects. Consider using "
            "normalized data or specifying --layer counts for cNMF."
        )

    n_cells, n_genes = adata.shape
    if n_genes < 50:
        warnings.append(
            f"Only {n_genes} genes detected. Gene program discovery works best "
            "with >= 500 highly variable genes."
        )

    for w in warnings:
        logger.warning(w)

    return warnings


# ---------------------------------------------------------------------------
# Degenerate output detection
# ---------------------------------------------------------------------------

def _check_degenerate(usage_df: pd.DataFrame, weights_df: pd.DataFrame, top_df: pd.DataFrame) -> dict:
    """Check for degenerate output and return diagnostics dict."""
    diag: dict = {"degenerate": False, "issues": [], "suggested_actions": []}

    if usage_df.empty:
        diag["degenerate"] = True
        diag["issues"].append("Usage matrix is empty -- no programs were inferred.")
        diag["suggested_actions"].append("Check input data has enough cells and genes.")
        return diag

    # Check if all programs are identical (collapsed)
    usage_corr = usage_df.corr()
    np.fill_diagonal(usage_corr.values, 0)
    if usage_df.shape[1] > 1 and (usage_corr.abs() > 0.99).all().all():
        diag["degenerate"] = True
        diag["issues"].append("All programs are nearly identical (correlation > 0.99).")
        diag["suggested_actions"].extend([
            "Try fewer programs: --n-programs 3",
            "Try more iterations: --n-iter 800",
            "Use a different method: --method nmf  or  --method cnmf",
        ])

    # Check if any program has zero variance
    zero_var = (usage_df.std() < 1e-10).sum()
    if zero_var > 0:
        diag["degenerate"] = True
        diag["issues"].append(f"{zero_var} program(s) have zero variance across cells.")
        diag["suggested_actions"].append(
            "Reduce --n-programs (current data may not support that many latent programs)."
        )

    # Check top genes -- are they meaningful?
    if top_df.empty:
        diag["degenerate"] = True
        diag["issues"].append("No top genes were returned for any program.")

    return diag


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _render_figures(output_dir: Path, usage_df: pd.DataFrame) -> list[str]:
    """Render gallery figures. Returns list of figure file names."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []

    if usage_df.empty:
        return rendered

    # 1. Mean program usage bar chart
    fig, ax = plt.subplots(figsize=(8, 4))
    usage_df.mean(axis=0).plot.bar(ax=ax, color="#756bb1")
    ax.set_title("Mean program usage across cells")
    ax.set_ylabel("Mean usage score")
    ax.set_xlabel("Program")
    fig.tight_layout()
    fig.savefig(figures_dir / "mean_program_usage.png", dpi=200)
    plt.close(fig)
    rendered.append("mean_program_usage.png")

    # 2. Program correlation heatmap
    if usage_df.shape[1] > 1:
        fig, ax = plt.subplots(figsize=(6, 5))
        corr = usage_df.corr()
        im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(corr.columns)))
        ax.set_yticks(range(len(corr.columns)))
        ax.set_xticklabels(corr.columns, rotation=45, ha="right")
        ax.set_yticklabels(corr.columns)
        ax.set_title("Program-program correlation")
        fig.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        fig.savefig(figures_dir / "program_correlation.png", dpi=200)
        plt.close(fig)
        rendered.append("program_correlation.png")

    return rendered


def _write_figure_manifest(output_dir: Path, figure_names: list[str]) -> None:
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": "standard-sc-gene-programs-gallery",
        "figures": figure_names,
    }
    (output_dir / "figures" / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Figure data
# ---------------------------------------------------------------------------

def _write_figure_data(
    output_dir: Path,
    usage_df: pd.DataFrame,
    top_df: pd.DataFrame,
) -> dict[str, str]:
    fd_dir = output_dir / "figure_data"
    fd_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    files["program_usage"] = "program_usage.csv"
    usage_df.to_csv(fd_dir / files["program_usage"])

    files["top_program_genes"] = "top_program_genes.csv"
    top_df.to_csv(fd_dir / files["top_program_genes"], index=False)

    if not usage_df.empty and usage_df.shape[1] > 1:
        corr = usage_df.corr()
        files["program_correlation"] = "program_correlation.csv"
        corr.to_csv(fd_dir / files["program_correlation"])

    # Write gene_expression.csv in long format for plot_feature_violin / plot_feature_cor.
    # Pivots program_usage wide -> long, treating each program as a "gene" feature.
    if not usage_df.empty:
        try:
            # Sample cells to keep CSV manageable
            sample_n = min(len(usage_df), 1000)
            sampled = usage_df.sample(n=sample_n, random_state=42) if len(usage_df) > sample_n else usage_df
            # usage_df index is cell_id
            long_rows = []
            for prog in sampled.columns:
                for cell_id, val in sampled[prog].items():
                    long_rows.append({"cell_id": str(cell_id), "gene": prog, "expression": float(val)})
            pd.DataFrame(long_rows).to_csv(fd_dir / "gene_expression.csv", index=False)
            files["gene_expression"] = "gene_expression.csv"
        except Exception:
            pass

    manifest = {"skill": SKILL_NAME, "available_files": files}
    (fd_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return files


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_path: str | None,
    top_df: pd.DataFrame,
    diagnostics: dict,
) -> None:
    backend = str(summary.get("backend", summary.get("method", "NA")))
    header = generate_report_header(
        title="Single-Cell Gene Programs Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(params.get("method", "NA")),
            "Backend": backend,
            "Programs": str(params.get("n_programs", 0)),
        },
    )
    body: list[str] = [
        "## Summary\n",
        f"- Requested method: `{params.get('method')}`",
        f"- Execution backend: `{backend}`",
        f"- Programs inferred: `{summary.get('n_programs', 'NA')}`",
        f"- Reconstruction error: `{summary.get('reconstruction_err', 'NA')}`",
        "",
        "## Interpretation\n",
        "- Gene programs summarize coordinated expression modules across cells.",
        "- Each program captures a group of genes that tend to be co-expressed.",
        "- `nmf` is a lightweight factorization baseline; `cnmf` runs a consensus-style pipeline with multiple replicates for more robust programs.",
        "",
        "## Output Files\n",
        "| File | Description |",
        "|------|-------------|",
        "| `processed.h5ad` | AnnData with `X_gene_programs` in obsm and program metadata in uns |",
        "| `tables/program_usage.csv` | Per-cell usage scores for each program |",
        "| `tables/program_weights.csv` | Gene weights for each program |",
        "| `tables/top_program_genes.csv` | Top genes per program ranked by weight |",
        "| `figures/mean_program_usage.png` | Bar chart of mean program usage |",
        "| `figures/program_correlation.png` | Heatmap of program-program correlations |",
        "",
    ]

    # Top genes table
    if not top_df.empty:
        body.append("## Top Genes Per Program\n")
        programs = top_df["program"].unique()
        for prog in programs[:4]:  # Show first 4 programs in report
            sub = top_df[top_df["program"] == prog].head(10)
            body.append(f"### {prog}\n")
            body.append("| Rank | Gene | Weight |")
            body.append("|------|------|--------|")
            for _, row in sub.iterrows():
                body.append(f"| {row['rank']} | {row['gene']} | {row['weight']:.4f} |")
            body.append("")

    # Troubleshooting section for degenerate output
    if diagnostics.get("degenerate"):
        body.extend([
            "## Troubleshooting: Degenerate Output Detected\n",
            "The analysis produced potentially problematic results:\n",
        ])
        for issue in diagnostics.get("issues", []):
            body.append(f"- {issue}")
        body.append("")
        body.append("### Suggested Fixes\n")
        for i, action in enumerate(diagnostics.get("suggested_actions", []), 1):
            body.append(f"{i}. {action}")
        body.append("")

    report_text = header + "\n" + "\n".join(body) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_programs", args.n_programs, min_val=2)
    v.positive("n_iter", args.n_iter, min_val=1)
    v.positive("top_genes", args.top_genes, min_val=1)
    v.check()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # ---- Auto-fallback: if cnmf is requested but not installed, use nmf ----
    if args.method == "cnmf":
        try:
            import cnmf  # noqa: F401
        except ImportError:
            logger.warning("cnmf package not installed. Falling back to --method nmf (sklearn NMF).")
            args.method = "nmf"

    # ---- Load data ----
    if args.demo:
        adata = make_demo_gene_program_adata(seed=args.seed)
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    # ---- Preflight ----
    preflight_warnings = _preflight(adata, method=args.method, layer=args.layer)

    # ---- Ensure input contract ----
    ensure_input_contract(adata, source_path=input_path)

    # ---- Run method ----
    if args.method == "cnmf":
        result = run_cnmf_programs(
            adata,
            n_programs=args.n_programs,
            seed=args.seed,
            max_iter=args.n_iter,
            layer=args.layer,
            top_genes=args.top_genes,
        )
    else:
        result = run_nmf_programs(
            adata,
            n_programs=args.n_programs,
            seed=args.seed,
            max_iter=args.n_iter,
            layer=args.layer,
            top_genes=args.top_genes,
        )

    usage_df = result["usage"]
    weights_df = result["weights"]
    top_df = result["top_genes"]
    spectra_tpm_df = result.get("spectra_tpm")

    # ---- Degenerate output detection ----
    diagnostics = _check_degenerate(usage_df, weights_df, top_df)

    if diagnostics["degenerate"]:
        print()
        print("  *** Gene program discovery produced degenerate output. ***")
        for issue in diagnostics["issues"]:
            print(f"  Problem: {issue}")
        print()
        print("  How to fix:")
        for i, action in enumerate(diagnostics["suggested_actions"], 1):
            print(f"    Option {i} -- {action}")
        print()

    # ---- Persist results into adata ----
    adata.obsm["X_gene_programs"] = usage_df.to_numpy()
    adata.uns["gene_programs"] = {
        "method": result.get("method", args.method),
        "program_names": usage_df.columns.tolist(),
        "top_genes_csv": "tables/top_program_genes.csv",
    }

    # ---- Write tables ----
    usage_df.to_csv(tables_dir / "program_usage.csv")
    weights_df.to_csv(tables_dir / "program_weights.csv")
    top_df.to_csv(tables_dir / "top_program_genes.csv", index=False)
    table_files = {
        "program_usage": "tables/program_usage.csv",
        "program_weights": "tables/program_weights.csv",
        "top_program_genes": "tables/top_program_genes.csv",
    }
    if spectra_tpm_df is not None:
        spectra_tpm_df.to_csv(tables_dir / "program_tpm.csv")
        table_files["program_tpm"] = "tables/program_tpm.csv"

    # ---- Figures ----
    figure_names = _render_figures(output_dir, usage_df)
    _write_figure_manifest(output_dir, figure_names)

    # ---- Figure data ----
    figure_data_files = _write_figure_data(output_dir, usage_df, top_df)

    # ---- Contracts & metadata ----
    params = {
        "method": args.method,
        "n_programs": args.n_programs,
        "n_iter": args.n_iter,
        "seed": args.seed,
        "layer": args.layer,
        "top_genes": args.top_genes,
    }

    # Determine x_kind: gene programs don't change the expression matrix
    matrix_contract = get_matrix_contract(adata)
    x_kind = matrix_contract.get("X") or infer_x_matrix_kind(adata, fallback="normalized_expression")
    raw_kind = matrix_contract.get("raw")

    propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=x_kind,
        raw_kind=raw_kind,
    )
    store_analysis_metadata(adata, SKILL_NAME, args.method, params)

    # ---- Save processed.h5ad ----
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved processed object to %s", output_h5ad)

    # ---- Summary & result.json ----
    summary = {
        "method": args.method,
        "backend": result.get("method", args.method),
        "n_programs": int(usage_df.shape[1]),
        "reconstruction_err": float(result.get("reconstruction_err", float("nan"))),
    }
    if diagnostics["degenerate"]:
        summary["degenerate_output"] = True
        summary["degenerate_issues"] = diagnostics["issues"]

    result_data = {
        "params": params,
        "output_files": {
            "processed_h5ad": "processed.h5ad",
            "report": "report.md",
            "tables": table_files,
            "figure_data": figure_data_files,
            "figures": figure_names,
        },
        "matrix_contract": {
            "X": x_kind,
            "raw": raw_kind,
            "layers": {"counts": "raw_counts" if "counts" in adata.layers else None},
            "producer_skill": SKILL_NAME,
        },
    }
    if diagnostics["degenerate"]:
        result_data["diagnostics"] = {
            "degenerate": True,
            "issues": diagnostics["issues"],
            "suggested_actions": diagnostics["suggested_actions"],
        }

    result_data["next_steps"] = [
        {"skill": "sc-enrichment", "reason": "Pathway enrichment on discovered gene programs", "priority": "optional"},
    ]
    result_data["r_enhanced_figures"] = []
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        result_data,
        input_checksum=input_checksum,
    )

    # ---- R Enhanced plots ----
    r_enhanced_figures = _render_r_enhanced(
        output_dir, output_dir / "figure_data", args.r_enhanced
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures
        write_result_json(
            output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data,
            input_checksum=input_checksum,
        )
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    # ---- Report ----
    _write_report(output_dir, summary, params, input_path, top_df, diagnostics)

    # ---- Success banner ----
    print(f"\n{'=' * 60}")
    if diagnostics["degenerate"]:
        print(f"WARNING: {SKILL_NAME} v{SKILL_VERSION} completed with issues")
    else:
        print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Method: {args.method} (backend: {result.get('method', args.method)})")
    print(f"  Programs: {usage_df.shape[1]}")
    print(f"  Output: {output_dir}")
    print(f"  Key files:")
    print(f"    processed.h5ad  -- AnnData with X_gene_programs in obsm")
    print(f"    tables/top_program_genes.csv  -- ranked gene lists per program")
    print(f"    figures/mean_program_usage.png  -- usage overview")
    if preflight_warnings:
        print(f"\n  Preflight warnings:")
        for w in preflight_warnings:
            print(f"    - {w}")
    print()

    # --- Next-step guidance ---
    print(">> Next steps:")
    print(f"  - sc-enrichment: python omicsclaw.py run sc-enrichment --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-pseudotime: python omicsclaw.py run sc-pseudotime --input {output_dir}/processed.h5ad --output <dir>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

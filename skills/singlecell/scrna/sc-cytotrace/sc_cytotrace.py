#!/usr/bin/env python3
"""Single-cell CytoTRACE-style potency prediction.

Predicts cell differentiation potency (Totipotent -> Differentiated)
using gene expression complexity as a proxy for stemness.
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
import scanpy as sc
from scipy import sparse
from scipy.stats import rankdata

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
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
from skills.singlecell._lib.preflight import apply_preflight, PreflightDecision

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cytotrace"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py"

# R Enhanced plotting configuration
R_ENHANCED_PLOTS = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_cytotrace_boxplot": "r_cytotrace_boxplot.png",
    "plot_cell_density": "r_cell_density.png",
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


POTENCY_LABELS = [
    "Differentiated",
    "Unipotent",
    "Oligopotent",
    "Multipotent",
    "Pluripotent",
    "Totipotent",
]
POTENCY_BINS = np.linspace(0, 1, len(POTENCY_LABELS) + 1)

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def preflight_sc_cytotrace(
    adata,
    *,
    method: str,
    n_neighbors: int,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision(SKILL_NAME)
    ensure_input_contract(adata, source_path=source_path)

    matrix_contract = get_matrix_contract(adata)
    x_kind = matrix_contract.get("X") or infer_x_matrix_kind(adata)
    if x_kind not in ("normalized_expression", "raw_counts"):
        decision.add_guidance(
            "`sc-cytotrace` works best with normalized expression or raw counts. "
            "The current `X` semantics could not be confirmed. Proceeding cautiously."
        )

    if method not in ("cytotrace_simple",):
        decision.block(
            f"Unknown method '{method}'. Currently supported: `cytotrace_simple`."
        )

    if adata.n_obs < 50:
        decision.add_guidance(
            "The dataset has fewer than 50 cells. CytoTRACE-style scoring may be unreliable on very small datasets."
        )

    # Check for UMAP (needed for visualization)
    if "X_umap" not in adata.obsm:
        decision.add_guidance(
            "No UMAP embedding found. The skill will compute one for visualization. "
            "For better results, run `sc-clustering` first."
        )

    decision.add_guidance(
        f"Current settings: `method={method}`, `n_neighbors={n_neighbors}`."
    )
    decision.add_guidance(
        "`sc-cytotrace` predicts cell differentiation potency. "
        "Higher scores indicate more stem-like (totipotent) cells. "
        "After this, consider `sc-pseudotime` for trajectory analysis."
    )

    return decision


# ---------------------------------------------------------------------------
# Core: cytotrace_simple
# ---------------------------------------------------------------------------


def _compute_gene_counts(adata) -> np.ndarray:
    """Count the number of detected genes per cell (genes with expression > 0)."""
    X = adata.X
    if sparse.issparse(X):
        return np.asarray((X > 0).sum(axis=1)).ravel().astype(float)
    return np.asarray((X > 0).sum(axis=1)).ravel().astype(float)


def _knn_smooth(values: np.ndarray, adata, n_neighbors: int = 30) -> np.ndarray:
    """Smooth values using KNN from the neighbor graph.

    If a neighbor graph already exists it is reused; otherwise one is built
    from ``X_pca`` or ``X``.
    """
    if "neighbors" not in adata.uns:
        if "X_pca" in adata.obsm:
            sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep="X_pca")
        else:
            sc.pp.neighbors(adata, n_neighbors=n_neighbors)

    connectivities = adata.obsp.get("connectivities")
    if connectivities is None:
        logger.warning("No connectivities found; skipping KNN smoothing.")
        return values

    # Row-normalize the connectivities
    if sparse.issparse(connectivities):
        row_sums = np.asarray(connectivities.sum(axis=1)).ravel()
        row_sums[row_sums == 0] = 1.0
        # Diagonal (self) + neighbors
        smoothed = np.asarray(connectivities.dot(values.reshape(-1, 1))).ravel()
        smoothed = (smoothed + values) / (row_sums + 1)
    else:
        row_sums = connectivities.sum(axis=1)
        row_sums[row_sums == 0] = 1.0
        smoothed = (connectivities @ values + values) / (row_sums + 1)

    return smoothed


def run_cytotrace_simple(
    adata,
    *,
    n_neighbors: int = 30,
) -> dict:
    """CytoTRACE-simple: gene expression complexity as a potency proxy.

    Steps:
    1. Count genes detected per cell (gene_count).
    2. Rank-normalize to [0, 1] to produce the CytoTRACE score.
    3. Smooth with KNN graph.
    4. Bin into 6 potency categories.

    Parameters
    ----------
    adata
        AnnData object (normalized or raw counts).
    n_neighbors
        Number of neighbors for KNN smoothing.

    Returns
    -------
    Summary dictionary with method info and score statistics.
    """
    logger.info("Running cytotrace_simple on %d cells x %d genes", adata.n_obs, adata.n_vars)

    # Step 1: Gene detection counts
    gene_counts = _compute_gene_counts(adata)
    logger.info(
        "Gene detection range: %d - %d (mean %.1f)",
        int(gene_counts.min()),
        int(gene_counts.max()),
        gene_counts.mean(),
    )

    # Step 2: Rank-normalize to [0, 1]
    ranked = rankdata(gene_counts)
    raw_score = (ranked - ranked.min()) / max(ranked.max() - ranked.min(), 1)

    # Step 3: KNN smoothing
    smoothed_score = _knn_smooth(raw_score, adata, n_neighbors=n_neighbors)

    # Re-normalize after smoothing
    smoothed_ranked = rankdata(smoothed_score)
    cytotrace_score = (smoothed_ranked - smoothed_ranked.min()) / max(
        smoothed_ranked.max() - smoothed_ranked.min(), 1
    )

    # Step 4: Potency binning
    potency = pd.cut(
        cytotrace_score,
        bins=POTENCY_BINS,
        labels=POTENCY_LABELS,
        include_lowest=True,
    )

    # Store in adata
    adata.obs["cytotrace_score"] = cytotrace_score
    adata.obs["cytotrace_potency"] = potency
    adata.obs["cytotrace_gene_count"] = gene_counts.astype(int)

    # Potency composition
    potency_counts = adata.obs["cytotrace_potency"].value_counts().to_dict()

    # Check for degenerate output
    unique_potency = adata.obs["cytotrace_potency"].nunique()
    degenerate = unique_potency <= 1

    summary = {
        "method": "cytotrace_simple",
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_neighbors": n_neighbors,
        "score_mean": float(np.mean(cytotrace_score)),
        "score_std": float(np.std(cytotrace_score)),
        "score_min": float(np.min(cytotrace_score)),
        "score_max": float(np.max(cytotrace_score)),
        "potency_counts": {str(k): int(v) for k, v in potency_counts.items()},
        "n_potency_categories": unique_potency,
        "degenerate": degenerate,
    }

    if degenerate:
        summary["suggested_actions"] = [
            "The dataset may have too few cells or insufficient gene expression diversity.",
            "Try preprocessing with sc-preprocessing first.",
            "Consider using the full cytotrace2 method with pretrained models.",
        ]
        logger.warning(
            "  *** DEGENERATE OUTPUT: Only %d potency category detected. ***\n"
            "  This usually means the gene expression complexity is too uniform.\n"
            "  How to fix:\n"
            "    Option 1 — Ensure the data has been properly preprocessed (sc-preprocessing).\n"
            "    Option 2 — Check if the data has sufficient gene diversity (>1000 genes).\n",
            unique_potency,
        )

    logger.info("CytoTRACE-simple complete: %d potency categories", unique_potency)
    return summary


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def _ensure_umap(adata) -> None:
    """Compute UMAP if missing."""
    if "X_umap" in adata.obsm:
        return
    logger.info("Computing UMAP for visualization...")
    if "neighbors" not in adata.uns:
        if "X_pca" in adata.obsm:
            sc.pp.neighbors(adata, use_rep="X_pca")
        else:
            sc.pp.neighbors(adata)
    sc.tl.umap(adata)


def plot_potency_umap(adata, output_dir: Path) -> Path:
    """UMAP colored by cytotrace_score (continuous)."""
    _ensure_umap(adata)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Score overlay
    ax = axes[0]
    coords = np.asarray(adata.obsm["X_umap"])
    score = adata.obs["cytotrace_score"].to_numpy()
    scatter = ax.scatter(
        coords[:, 0], coords[:, 1],
        c=score, cmap="RdYlBu_r", s=5, alpha=0.8,
        rasterized=True,
    )
    plt.colorbar(scatter, ax=ax, label="CytoTRACE Score", shrink=0.8)
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.set_title("CytoTRACE Score (higher = more stem-like)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Potency category overlay
    ax = axes[1]
    potency = adata.obs["cytotrace_potency"].astype(str)
    potency_colors = {
        "Differentiated": "#2166AC",
        "Unipotent": "#67A9CF",
        "Oligopotent": "#D1E5F0",
        "Multipotent": "#FDDBC7",
        "Pluripotent": "#EF8A62",
        "Totipotent": "#B2182B",
    }
    for label in POTENCY_LABELS:
        mask = potency == label
        if mask.sum() == 0:
            continue
        color = potency_colors.get(label, "#999999")
        ax.scatter(
            coords[mask, 0], coords[mask, 1],
            c=color, s=5, alpha=0.8, label=label,
            rasterized=True,
        )
    ax.legend(loc="upper right", fontsize=8, markerscale=3, framealpha=0.9)
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.set_title("CytoTRACE Potency Categories")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.suptitle("Cell Potency Prediction", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / "potency_umap.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_score_distribution(adata, output_dir: Path) -> Path:
    """Histogram of cytotrace_score."""
    fig, ax = plt.subplots(figsize=(8, 4))
    score = adata.obs["cytotrace_score"].to_numpy()
    ax.hist(score, bins=50, color="#4c72b0", edgecolor="white", linewidth=0.5, alpha=0.9)
    ax.axvline(np.median(score), color="#d62728", linestyle="--", linewidth=1.5, label=f"Median: {np.median(score):.3f}")
    ax.set_xlabel("CytoTRACE Score", fontsize=12)
    ax.set_ylabel("Number of Cells", fontsize=12)
    ax.set_title("CytoTRACE Score Distribution", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / "score_distribution.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_potency_composition(adata, output_dir: Path) -> Path:
    """Bar chart of potency category proportions."""
    potency_counts = adata.obs["cytotrace_potency"].value_counts()
    # Reindex to ensure order
    potency_counts = potency_counts.reindex(POTENCY_LABELS).fillna(0).astype(int)
    total = potency_counts.sum()
    proportions = potency_counts / max(total, 1) * 100

    potency_colors = [
        "#2166AC", "#67A9CF", "#D1E5F0",
        "#FDDBC7", "#EF8A62", "#B2182B",
    ]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        range(len(POTENCY_LABELS)),
        proportions.values,
        color=potency_colors,
        edgecolor="white",
        linewidth=0.8,
    )
    for bar, count, pct in zip(bars, potency_counts.values, proportions.values):
        if count > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{int(count)}\n({pct:.1f}%)",
                ha="center", va="bottom", fontsize=9,
            )
    ax.set_xticks(range(len(POTENCY_LABELS)))
    ax.set_xticklabels(POTENCY_LABELS, rotation=30, ha="right", fontsize=10)
    ax.set_xlabel("Potency Category", fontsize=12)
    ax.set_ylabel("Proportion (%)", fontsize=12)
    ax.set_title("Cell Potency Composition", fontsize=13, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / "potency_composition.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Report / output
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell CytoTRACE Potency Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Potency categories": str(summary["n_potency_categories"]),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: `{summary['method']}`",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Score mean**: {summary['score_mean']:.4f}",
        f"- **Score std**: {summary['score_std']:.4f}",
        f"- **Potency categories detected**: {summary['n_potency_categories']}",
        "",
        "## Potency Distribution\n",
    ]
    for label in POTENCY_LABELS:
        count = summary["potency_counts"].get(label, 0)
        body_lines.append(f"- **{label}**: {count} cells")
    body_lines.extend([
        "",
        "## Method Description\n",
        "The `cytotrace_simple` method estimates cell differentiation potency using",
        "gene expression complexity (number of detected genes per cell) as a proxy",
        "for stemness. The key steps are:",
        "",
        "1. Count genes detected per cell (expression > 0)",
        "2. Rank-normalize to [0, 1]",
        "3. Smooth with KNN graph for local consistency",
        "4. Bin into 6 potency categories: Differentiated, Unipotent, Oligopotent,",
        "   Multipotent, Pluripotent, Totipotent",
        "",
        "Higher scores indicate more stem-like (less differentiated) cells.",
        "",
        "## Parameters\n",
        f"- `method`: {params['method']}",
        f"- `n_neighbors`: {params['n_neighbors']}",
        "",
        "## Output Files\n",
        "- `processed.h5ad` -- AnnData with `cytotrace_score`, `cytotrace_potency`, and `cytotrace_gene_count` in `obs`.",
        "- `figures/potency_umap.png` -- UMAP colored by score and potency.",
        "- `figures/score_distribution.png` -- Score histogram.",
        "- `figures/potency_composition.png` -- Potency category bar chart.",
        "- `tables/cytotrace_scores.csv` -- Per-cell scores and potency labels.",
        "",
        "## Recommended Next Steps\n",
        "- If you want trajectory analysis: run `sc-pseudotime`.",
        "- If you want to see markers of each potency level: run `sc-de --groupby cytotrace_potency`.",
        "",
    ])

    if summary.get("degenerate"):
        body_lines.extend([
            "## Troubleshooting: Degenerate Output\n",
            "Only one potency category was detected. Possible causes:",
            "",
            "### Cause 1: Insufficient gene diversity",
            "The data may have too few genes or very uniform expression.",
            "Solution: ensure proper preprocessing with `sc-preprocessing`.",
            "",
            "### Cause 2: Very small dataset",
            "Fewer than 50 cells may produce unreliable scores.",
            "Solution: use a larger dataset.",
            "",
        ])

    report = header + "\n".join(body_lines) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def write_reproducibility(output_dir: Path, params: dict, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        parts.append("--demo")
    else:
        parts.extend(["--input", "<input.h5ad>"])
    parts.extend(["--output", str(output_dir)])
    parts.extend(["--method", params["method"]])
    parts.extend(["--n-neighbors", str(params["n_neighbors"])])
    command = " ".join(shlex.quote(p) for p in parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load PBMC3k processed as demo data for cytotrace."""
    adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
    return adata


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Single-Cell CytoTRACE Potency Prediction")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=["cytotrace_simple"], default="cytotrace_simple")
    parser.add_argument("--n-neighbors", type=int, default=30)
    parser.add_argument("--r-enhanced", action="store_true", help="Generate R Enhanced plots (requires R + ggplot2)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    apply_preflight(
        preflight_sc_cytotrace(
            adata,
            method=args.method,
            n_neighbors=args.n_neighbors,
            source_path=input_file,
        ),
        logger,
    )

    # Run analysis
    if args.method == "cytotrace_simple":
        summary = run_cytotrace_simple(adata, n_neighbors=args.n_neighbors)
    else:
        raise ValueError(f"Unknown method: {args.method}")

    # Propagate contracts
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=get_matrix_contract(adata).get("X") or infer_x_matrix_kind(adata),
        raw_kind=get_matrix_contract(adata).get("raw"),
    )

    # Visualization
    plot_potency_umap(adata, output_dir)
    plot_score_distribution(adata, output_dir)
    plot_potency_composition(adata, output_dir)

    # Tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    scores_df = adata.obs[["cytotrace_score", "cytotrace_potency", "cytotrace_gene_count"]].copy()
    scores_df.to_csv(tables_dir / "cytotrace_scores.csv")

    # Export embedding + cytotrace scores to figure_data/ for R Enhanced renderers
    fd_dir = output_dir / "figure_data"
    fd_dir.mkdir(parents=True, exist_ok=True)
    embed_df = pd.DataFrame(index=adata.obs_names)
    # Add embedding coordinates
    if "X_umap" in adata.obsm:
        embed_df["dim1"] = adata.obsm["X_umap"][:, 0]
        embed_df["dim2"] = adata.obsm["X_umap"][:, 1]
    elif "X_pca" in adata.obsm:
        embed_df["dim1"] = adata.obsm["X_pca"][:, 0]
        embed_df["dim2"] = adata.obsm["X_pca"][:, 1]
    # Add cell type if available
    for ct_col in ["cell_type", "leiden", "louvain", "cluster"]:
        if ct_col in adata.obs.columns:
            embed_df["cell_type"] = adata.obs[ct_col].values
            break
    # Add cytotrace columns
    for col in ["cytotrace_score", "cytotrace_potency", "cytotrace_gene_count"]:
        if col in adata.obs.columns:
            embed_df[col] = adata.obs[col].values
    embed_df.index.name = "cell_id"
    embed_df.to_csv(fd_dir / "cytotrace_embedding.csv")

    # Params
    params = {
        "method": args.method,
        "n_neighbors": args.n_neighbors,
    }

    # Report
    write_report(output_dir, summary, params, input_file)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    # Store metadata and save
    store_analysis_metadata(adata, SKILL_NAME, args.method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    # result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        **summary,
    }
    if summary.get("degenerate"):
        result_data["cytotrace_diagnostics"] = {
            "degenerate": True,
            "n_potency_categories": summary["n_potency_categories"],
            "suggested_actions": summary.get("suggested_actions", []),
        }
    result_data["next_steps"] = [
        {"skill": "sc-pseudotime", "reason": "Trajectory inference using stemness ordering", "priority": "optional"},
    ]
    result_data["r_enhanced_figures"] = []
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)

    # R Enhanced plots
    r_enhanced_figures = _render_r_enhanced(
        output_dir, output_dir / "figure_data", args.r_enhanced
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures
        write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Cell potency prediction using gene expression complexity.",
        result_payload=result_payload,
        preferred_method=args.method,
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Method: {summary['method']}")
    print(f"  Potency categories: {summary['n_potency_categories']}")
    print(f"  Score range: [{summary['score_min']:.3f}, {summary['score_max']:.3f}]")

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete. Further exploration:")
    print(f"  - sc-pseudotime: python omicsclaw.py run sc-pseudotime --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-velocity:   python omicsclaw.py run sc-velocity --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()

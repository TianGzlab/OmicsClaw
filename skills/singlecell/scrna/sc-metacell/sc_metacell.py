#!/usr/bin/env python3
"""Single-cell metacell construction."""

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
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_output_readme, write_result_json, write_replot_hint
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad, write_h5ad_aliases
from skills.singlecell._lib.metacell import make_demo_metacell_adata, run_kmeans_metacells, run_seacells_metacells

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-metacell"
SKILL_VERSION = "0.1.0"

# R Enhanced plotting configuration
R_ENHANCED_PLOTS = {
    # centroid_points.csv is exported as embedding_points.csv (x->dim1, y->dim2).
    # plot_embedding_discrete colors by the metacell label column.
    # plot_cell_barplot removed — no cell_type_counts.csv at this stage.
    "plot_embedding_discrete": "r_embedding_discrete.png",
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell metacell construction")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="seacells", choices=["seacells", "kmeans"])
    p.add_argument("--use-rep", type=str, default="X_pca")
    p.add_argument("--n-metacells", type=int, default=30)
    p.add_argument("--celltype-key", type=str, default="leiden")
    p.add_argument("--min-iter", type=int, default=10)
    p.add_argument("--max-iter", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-neighbors", type=int, default=15,
                    help="Number of neighbors for SEACells graph construction (default: 15)")
    p.add_argument("--n-pcs", type=int, default=20,
                    help="Number of PCs for SEACells neighbor computation (default: 20)")
    p.add_argument("--r-enhanced", action="store_true", help="Generate R Enhanced plots (requires R + ggplot2)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def _preflight(adata, *, use_rep: str, n_metacells: int, method: str, n_neighbors: int = 15, n_pcs: int = 20) -> list[str]:
    """Validate inputs before running metacell construction.

    Returns a list of warnings (empty if everything looks fine).
    Raises SystemExit on fatal issues.
    """
    warnings: list[str] = []

    # 1. Embedding check
    if use_rep not in adata.obsm:
        available = list(adata.obsm.keys())
        print()
        print(f"  *** Embedding '{use_rep}' not found in adata.obsm. ***")
        print(f"  Available embeddings: {available or 'none'}")
        print()
        print("  How to fix:")
        print("    Option 1 -- Run preprocessing first:")
        print("      python omicsclaw.py run sc-preprocessing --input data.h5ad --output preproc/")
        print("    Option 2 -- Specify a different embedding:")
        print(f"      python omicsclaw.py run sc-metacell --input data.h5ad --output out/ --use-rep X_umap")
        raise SystemExit(1)

    # 2. n_metacells sanity
    if n_metacells >= adata.n_obs:
        print()
        print(f"  *** Requested {n_metacells} metacells but data only has {adata.n_obs} cells. ***")
        print("  n_metacells must be smaller than the number of cells.")
        print()
        print("  How to fix:")
        print(f"    python omicsclaw.py run sc-metacell --input data.h5ad --output out/ --n-metacells {max(5, adata.n_obs // 10)}")
        raise SystemExit(1)

    if n_metacells < 2:
        print()
        print("  *** n_metacells must be >= 2. ***")
        raise SystemExit(1)

    # 3. Matrix semantics check
    has_counts = "counts" in adata.layers
    if not has_counts:
        warnings.append("No 'counts' layer found; metacell aggregation will use adata.X directly.")
        logger.warning("No 'counts' layer found. Aggregation will use adata.X.")

    # 4. Warn if too few cells per metacell
    expected_ratio = adata.n_obs / n_metacells
    if expected_ratio < 3:
        warnings.append(
            f"Only ~{expected_ratio:.1f} cells per metacell on average. "
            "Consider reducing --n-metacells for more stable summaries."
        )
        logger.warning("Low cells-per-metacell ratio (%.1f). Consider reducing --n-metacells.", expected_ratio)

    # 5. SEACells-specific: needs neighbors graph
    if method == "seacells" and "neighbors" not in adata.uns:
        logger.info("Computing neighbors graph (required by SEACells)...")
        import scanpy as sc
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, adata.obsm[use_rep].shape[1]))

    return warnings


# ---------------------------------------------------------------------------
# Degenerate output detection
# ---------------------------------------------------------------------------

def _check_degenerate(madata, labels: pd.Series) -> dict:
    """Check for degenerate metacell results and return diagnostics."""
    diagnostics: dict = {
        "degenerate": False,
        "suggested_actions": [],
    }

    n_metacells = madata.n_obs
    cells_per_mc = labels.value_counts()

    # Single metacell
    if n_metacells <= 1:
        diagnostics["degenerate"] = True
        diagnostics["reason"] = "only_one_metacell"
        diagnostics["suggested_actions"] = [
            "Check that the embedding has meaningful structure (run UMAP visualization first).",
            "Increase --n-metacells (e.g., --n-metacells 20).",
        ]

    # Extremely imbalanced: one metacell has >80% of cells
    if not diagnostics["degenerate"] and cells_per_mc.max() > 0.8 * labels.shape[0]:
        diagnostics["degenerate"] = True
        diagnostics["reason"] = "extremely_imbalanced"
        diagnostics["suggested_actions"] = [
            "The embedding may lack structure. Try a different --use-rep or re-run preprocessing.",
            "Consider using --method kmeans as a simpler alternative.",
        ]

    # Empty metacells (shouldn't happen but check)
    empty_count = (cells_per_mc == 0).sum() if hasattr(cells_per_mc, 'sum') else 0
    if empty_count > 0:
        diagnostics["empty_metacells"] = int(empty_count)

    return diagnostics


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_figure_data(output_dir: Path, *, points_df: pd.DataFrame, summary_df: pd.DataFrame) -> dict[str, str]:
    """Write plot-ready CSV files and manifest."""
    fd_dir = output_dir / "figure_data"
    fd_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    if not points_df.empty:
        files["centroid_points"] = "centroid_points.csv"
        points_df.to_csv(fd_dir / files["centroid_points"], index=False)

        # Write embedding_points.csv with normalized dim1/dim2 for R embedding renderers.
        embed_df = points_df.copy()
        if "x" in embed_df.columns and "dim1" not in embed_df.columns:
            embed_df = embed_df.rename(columns={"x": "dim1", "y": "dim2"})
        if "cell_id" not in embed_df.columns:
            embed_df.insert(0, "cell_id", embed_df.index.astype(str))
        embed_df.to_csv(fd_dir / "embedding_points.csv", index=False)
        files["embedding_points"] = "embedding_points.csv"

    files["metacell_summary"] = "metacell_summary.csv"
    summary_df.to_csv(fd_dir / files["metacell_summary"], index=False)

    manifest = {"skill": SKILL_NAME, "available_files": files}
    (fd_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return files


def _write_figures_manifest(output_dir: Path, figure_files: list[str]) -> None:
    """Write figures/manifest.json."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "skill": SKILL_NAME,
        "figures": {Path(f).stem: f for f in figure_files},
    }
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_path: str | None,
    diagnostics: dict,
    preflight_warnings: list[str],
) -> None:
    header = generate_report_header(
        title="Single-Cell Metacell Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(summary.get("method", "NA")),
            "Embedding": str(params.get("use_rep", "X_pca")),
            "Requested metacells": str(params.get("n_metacells", 0)),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Executed method: `{summary.get('method')}`",
        f"- Metacells produced: `{summary.get('n_metacells', 'NA')}`",
        f"- Mean cells per metacell: `{summary.get('mean_cells_per_metacell', 'NA'):.1f}`"
        if isinstance(summary.get('mean_cells_per_metacell'), (int, float))
        else f"- Mean cells per metacell: `{summary.get('mean_cells_per_metacell', 'NA')}`",
        "",
    ]

    if preflight_warnings:
        body.extend(["## Preflight Warnings", ""])
        for w in preflight_warnings:
            body.append(f"- {w}")
        body.append("")

    body.extend([
        "## Output Files",
        "",
        "- `processed.h5ad` -- metacell-aware object (original cells + metacell assignment in `.obs['metacell']`)",
        "- `tables/metacells.h5ad` -- aggregated metacell expression profiles",
        "- `tables/cell_to_metacell.csv` -- cell-to-metacell mapping",
        "- `tables/metacell_summary.csv` -- metacell-level summary statistics",
        "",
        "## Interpretation",
        "",
        "- Metacells compress noisy single-cell profiles into more stable neighborhood summaries.",
        "- Use SEACells when you need structure-aware aggregation; use k-means as a lightweight baseline.",
        "- The `processed.h5ad` retains the original cell-level object with metacell labels for downstream use.",
    ])

    if diagnostics.get("degenerate"):
        body.extend([
            "",
            f"## Troubleshooting: {diagnostics.get('reason', 'degenerate output')}",
            "",
            "The metacell result appears degenerate. Possible fixes:",
            "",
        ])
        for i, action in enumerate(diagnostics.get("suggested_actions", []), 1):
            body.append(f"{i}. {action}")

    (output_dir / "report.md").write_text(
        header + "\n" + "\n".join(body) + "\n" + generate_report_footer(),
        encoding="utf-8",
    )


def main() -> int:
    args = _parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_metacells", args.n_metacells, min_val=2)
    v.positive("n_neighbors", args.n_neighbors, min_val=2)
    v.positive("n_pcs", args.n_pcs, min_val=1)
    v.positive("min_iter", args.min_iter, min_val=1)
    v.positive("max_iter", args.max_iter, min_val=1)
    v.min_max_consistent("min_iter", args.min_iter, "max_iter", args.max_iter)
    v.check()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)

    # -- Auto-fallback: if seacells is requested but not installed, use kmeans --
    if args.method == "seacells":
        try:
            import SEACells  # noqa: F401
        except ImportError:
            logger.warning("SEACells package not installed. Falling back to --method kmeans.")
            args.method = "kmeans"

    # -- Load data --
    if args.demo:
        adata = make_demo_metacell_adata(seed=args.seed)
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    # -- Write input contract --
    ensure_input_contract(adata, source_path=input_path)

    # -- Preflight --
    preflight_warnings = _preflight(
        adata,
        use_rep=args.use_rep,
        n_metacells=args.n_metacells,
        method=args.method,
        n_neighbors=args.n_neighbors,
        n_pcs=args.n_pcs,
    )

    # -- Run method --
    if args.method == "seacells":
        madata, labels, _model = run_seacells_metacells(
            adata,
            use_rep=args.use_rep,
            n_metacells=args.n_metacells,
            min_iter=args.min_iter,
            max_iter=args.max_iter,
            celltype_key=args.celltype_key,
        )
        executed = "seacells"
    else:
        madata, labels = run_kmeans_metacells(
            adata,
            use_rep=args.use_rep,
            n_metacells=args.n_metacells,
            seed=args.seed,
        )
        executed = "kmeans"

    # -- Assign labels to original object --
    adata.obs["metacell"] = labels.reindex(adata.obs_names).astype(str)

    # -- Degenerate output check --
    diagnostics = _check_degenerate(madata, adata.obs["metacell"])
    if diagnostics.get("degenerate"):
        print()
        print(f"  *** Metacell result is degenerate: {diagnostics.get('reason')} ***")
        print()
        print("  How to fix:")
        for i, action in enumerate(diagnostics.get("suggested_actions", []), 1):
            print(f"    Option {i} -- {action}")
        print()

    # -- Save metacell aggregate (secondary output in tables/) --
    madata.write_h5ad(tables_dir / "metacells.h5ad")
    madata.obs.to_csv(tables_dir / "metacell_summary.csv")
    pd.DataFrame({
        "cell": adata.obs_names,
        "metacell": adata.obs["metacell"].astype(str),
    }).to_csv(tables_dir / "cell_to_metacell.csv", index=False)

    # -- Figures --
    figure_files: list[str] = []
    points_df = pd.DataFrame()
    if args.use_rep in adata.obsm:
        emb = pd.DataFrame(adata.obsm[args.use_rep], index=adata.obs_names)
        mc_labels = adata.obs["metacell"]
        centers = emb.join(mc_labels).groupby("metacell").mean(numeric_only=True)
        if centers.shape[1] >= 2:
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.scatter(emb.iloc[:, 0], emb.iloc[:, 1], s=5, alpha=0.15, color="#bdbdbd", label="cells")
            ax.scatter(centers.iloc[:, 0], centers.iloc[:, 1], s=35, color="#d95f0e", label="metacell centroids")
            ax.set_title("Metacell centroids")
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(figures_dir / "metacell_centroids.png", dpi=200)
            plt.close(fig)
            figure_files.append("metacell_centroids.png")

            # Build figure_data for centroid plot
            points_df = pd.DataFrame({
                "x": emb.iloc[:, 0].values,
                "y": emb.iloc[:, 1].values,
                "metacell": mc_labels.values,
            })

    # Size distribution figure
    cells_per_mc = adata.obs["metacell"].value_counts().sort_index()
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.hist(cells_per_mc.values, bins=min(30, len(cells_per_mc)), color="#5e81ac", edgecolor="white")
    ax2.set_xlabel("Cells per metacell")
    ax2.set_ylabel("Count")
    ax2.set_title("Metacell size distribution")
    fig2.tight_layout()
    fig2.savefig(figures_dir / "metacell_size_distribution.png", dpi=200)
    plt.close(fig2)
    figure_files.append("metacell_size_distribution.png")

    # -- Manifests --
    _write_figures_manifest(output_dir, figure_files)
    summary_df = cells_per_mc.reset_index()
    summary_df.columns = ["metacell", "n_cells"]
    figure_data_files = _write_figure_data(output_dir, points_df=points_df, summary_df=summary_df)

    # -- Contracts on the original adata (primary output) --
    params = {
        "method": args.method,
        "use_rep": args.use_rep,
        "n_metacells": args.n_metacells,
        "celltype_key": args.celltype_key,
        "min_iter": args.min_iter,
        "max_iter": args.max_iter,
        "seed": args.seed,
    }
    store_analysis_metadata(adata, SKILL_NAME, executed, params)
    _, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
    )

    # -- Save processed.h5ad (primary output: original cells + metacell labels) --
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    alias_paths = write_h5ad_aliases(output_h5ad, [output_dir / "metacells_annotated.h5ad"])
    logger.info("Saved processed object to %s", output_h5ad)

    # -- Summary --
    summary = {
        "method": executed,
        "n_metacells": int(madata.n_obs),
        "n_cells": int(adata.n_obs),
        "mean_cells_per_metacell": float(adata.obs["metacell"].value_counts().mean()),
    }

    # -- result.json --
    result_data = {
        "params": params,
        "input_contract": adata.uns.get("omicsclaw_input_contract", {}),
        "matrix_contract": matrix_contract,
        "metacell_diagnostics": diagnostics,
        "output_files": {
            "processed_h5ad": "processed.h5ad",
            "metacell_h5ad": str(tables_dir / "metacells.h5ad"),
            "cell_to_metacell": str(tables_dir / "cell_to_metacell.csv"),
            "metacell_summary": str(tables_dir / "metacell_summary.csv"),
            "compatibility_aliases": [str(p) for p in alias_paths],
            "figure_data": figure_data_files,
            "figures": figure_files,
        },
        "visualization": {
            "recipe_id": "standard-sc-metacell-gallery",
            "available_figure_data": figure_data_files,
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-de", "reason": "Differential expression at metacell resolution", "priority": "optional"},
        {"skill": "sc-enrichment", "reason": "Pathway enrichment on metacell signatures", "priority": "optional"},
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

    # -- R Enhanced plots --
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

    # -- Report --
    _write_report(output_dir, summary, params, input_path, diagnostics, preflight_warnings)

    # -- README --
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Metacell construction and compression for scRNA-seq.",
        preferred_method=args.method,
    )

    if diagnostics.get("degenerate"):
        logger.warning("Metacell result is DEGENERATE (%s). See report.md for troubleshooting.", diagnostics.get("reason"))
    else:
        logger.info("Done: %d metacells from %d cells -> %s", madata.n_obs, adata.n_obs, output_dir)

    # --- Next-step guidance ---
    print()
    print(">> Next step: Use metacell AnnData for downstream analysis:")
    print(f"  • sc-de:         python omicsclaw.py run sc-de --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  • sc-enrichment: python omicsclaw.py run sc-enrichment --input {output_dir}/processed.h5ad --output <dir>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

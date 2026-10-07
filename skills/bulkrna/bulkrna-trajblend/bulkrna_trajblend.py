#!/usr/bin/env python3
"""bulkrna-trajblend — Bulk→single-cell trajectory interpolation.

Estimates cell fractions with NNLS and places bulk samples on a supplied
reference trajectory with joint PCA and nearest neighbors.

Usage:
    python bulkrna_trajblend.py --demo --output results/
    python bulkrna_trajblend.py --input bulk.csv --reference ref.h5ad --output results/
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

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-trajblend"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Core Analysis
# ---------------------------------------------------------------------------


def generate_figures(output_dir: Path, fractions: pd.DataFrame,
                     pt_results: pd.DataFrame,
                     ref_pcs: np.ndarray, bulk_pcs: np.ndarray,
                     ref_pt: np.ndarray, ref_labels: pd.Series) -> list[str]:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1. Fraction heatmap
    fig, ax = plt.subplots(figsize=(8, max(4, fractions.shape[0] * 0.4)))
    im = ax.imshow(fractions.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(fractions.shape[1]))
    ax.set_xticklabels(fractions.columns, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(fractions.shape[0]))
    ax.set_yticklabels(fractions.index, fontsize=9)
    plt.colorbar(im, ax=ax, label="Fraction")
    ax.set_title("Estimated Cell Type Fractions")
    fig.tight_layout()
    p = fig_dir / "fraction_heatmap.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 2. Trajectory embedding (reference + bulk overlay)
    fig, ax = plt.subplots(figsize=(9, 7))
    sc = ax.scatter(ref_pcs[:, 0], ref_pcs[:, 1], c=ref_pt,
                    cmap="viridis", s=8, alpha=0.4, label="Reference cells")
    ax.scatter(bulk_pcs[:, 0], bulk_pcs[:, 1], c="red", s=80,
               marker="*", edgecolor="black", linewidth=0.5,
               label="Bulk samples", zorder=5)
    for i, sample in enumerate(pt_results.index):
        ax.annotate(sample, (bulk_pcs[i, 0], bulk_pcs[i, 1]),
                    fontsize=6, alpha=0.7, xytext=(5, 5),
                    textcoords="offset points")
    plt.colorbar(sc, ax=ax, label="Pseudotime")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("Bulk Samples on Reference Trajectory")
    ax.legend(fontsize=9)
    fig.tight_layout()
    p = fig_dir / "bulk_on_trajectory.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 3. Pseudotime distribution
    fig, ax = plt.subplots(figsize=(7, 5))
    pts = pt_results["pseudotime"].values
    stds = pt_results["pseudotime_std"].values
    y = range(len(pts))
    ax.barh(y, pts, xerr=stds, color="#4878CF", alpha=0.7,
            edgecolor="white", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels(pt_results.index, fontsize=9)
    ax.set_xlabel("Estimated Pseudotime")
    ax.set_title("Bulk Sample Pseudotime Estimates")
    ax.invert_yaxis()
    fig.tight_layout()
    p = fig_dir / "pseudotime_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 4. Trajectory embedding colored by cell type
    fig, ax = plt.subplots(figsize=(9, 7))
    cts = sorted(ref_labels.unique())
    colors = plt.cm.tab10(np.linspace(0, 1, len(cts)))
    for ci, ct in enumerate(cts):
        mask = ref_labels.values == ct
        ax.scatter(ref_pcs[mask, 0], ref_pcs[mask, 1], c=[colors[ci]],
                   s=8, alpha=0.5, label=ct)
    ax.scatter(bulk_pcs[:, 0], bulk_pcs[:, 1], c="red", s=80,
               marker="*", edgecolor="black", linewidth=0.5,
               label="Bulk", zorder=5)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("Cell Type Composition in Trajectory Space")
    ax.legend(fontsize=8, markerscale=2)
    fig.tight_layout()
    p = fig_dir / "trajectory_embedding.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    return paths


def write_report(output_dir: Path, fractions: pd.DataFrame,
                 pt_results: pd.DataFrame, params: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk→Single-Cell Trajectory Interpolation Report",
        skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Bulk samples**: {fractions.shape[0]}",
        f"- **Cell types**: {fractions.shape[1]} ({', '.join(fractions.columns)})",
        f"- **Pseudotime range**: [{pt_results['pseudotime'].min():.3f}, "
        f"{pt_results['pseudotime'].max():.3f}]",
        "",
        "## Cell Type Fractions\n",
        fractions.round(4).to_csv(sep="\t"),
        "",
        "## Pseudotime Estimates\n",
        pt_results[["pseudotime", "pseudotime_std", "mean_neighbor_dist"]].round(4).to_csv(sep="\t"),
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        "\n".join([header, "\n".join(body_lines), footer]), encoding="utf-8")

    fractions.to_csv(tables_dir / "cell_fractions.csv")
    pt_results.to_csv(tables_dir / "pseudotime_estimates.csv")

    metrics = {
        "n_samples": fractions.shape[0],
        "n_cell_types": fractions.shape[1],
        "cell_types": list(fractions.columns),
        "pseudotime_summary": {
            "min": float(pt_results["pseudotime"].min()),
            "max": float(pt_results["pseudotime"].max()),
            "mean": float(pt_results["pseudotime"].mean()),
        },
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, metrics, params)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_trajblend.py "
        f"--input {params.get('input', '<BULK_COUNTS>')} "
        f"--reference {params.get('reference', '<REF_H5AD>')} "
        f"--output {params.get('output', '<OUTPUT>')}\n", encoding="utf-8")


def main():
    from skills._sdk.notebook import load_skill
    library = load_skill(SKILL_NAME)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Bulk count matrix (CSV/TSV)")
    ap.add_argument("--reference", type=str, help="scRNA-seq reference (h5ad or CSV)")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--n-epochs", type=int, default=50, help="Unused compatibility option; no model training occurs")
    args = ap.parse_args()

    output_dir = Path(args.output)
    params = {"output": str(output_dir)}

    if args.demo:
        logger.info("Generating demo data...")
        bulk, ref, ref_labels, ref_pt = library.demo_data(random_state=args.random_state)
        params["input"] = "demo"
        params["reference"] = "demo"
    else:
        if not args.input or not args.reference:
            ap.error("--input and --reference required (or use --demo)")
        bulk = pd.read_csv(args.input, index_col=0, sep="\t" if Path(args.input).suffix == ".tsv" else ",")
        params["input"] = args.input
        params["reference"] = args.reference

        ref, ref_labels, ref_pt = library.read_reference(args.reference)

    pt_results = library.map_trajectory(bulk, reference=ref, labels=ref_labels,
                                        pseudotime=ref_pt, random_state=args.random_state)
    fractions = library.fractions(pt_results)
    diagnostics = library.run_info(pt_results, keep=False)
    ref_pcs, bulk_pcs = diagnostics['reference_pcs'], diagnostics['bulk_pcs']
    ref_pt = ref_pt.to_numpy()
    params['random_state'] = args.random_state
    params['method'] = diagnostics['method']

    # 3. Generate figures
    logger.info("Step 3: Generating visualizations...")
    generate_figures(output_dir, fractions, pt_results,
                     ref_pcs, bulk_pcs, ref_pt, ref_labels)

    # 4. Write report
    logger.info("Step 4: Writing report...")
    write_report(output_dir, fractions, pt_results, params)

    logger.info("✓ TrajBlend complete → %s", output_dir)


if __name__ == "__main__":
    main()

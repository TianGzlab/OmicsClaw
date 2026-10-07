#!/usr/bin/env python3
"""bulkrna-batch-correction — ComBat batch effect correction for bulk RNA-seq.

Removes batch effects from multi-cohort expression matrices using the ComBat
algorithm (parametric empirical Bayes). Generates PCA visualizations
before and after correction and exports the corrected matrix.

Usage:
    python bulkrna_batch_correction.py --input expr.csv --batch-info batches.csv --output results/
    python bulkrna_batch_correction.py --demo --output /tmp/batch_demo
"""
from __future__ import annotations

import argparse
import json
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

import sys, os
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
from skills.bulkrna._lib.batch_correction import _run_pca, _silhouette_score

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-batch-correction"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _generate_demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic multi-batch expression data."""
    np.random.seed(42)
    n_genes = 500
    genes = [f"GENE_{i:04d}" for i in range(1, n_genes + 1)]

    # Batch 1: 4 samples, Batch 2: 4 samples
    samples_b1 = [f"batch1_s{i}" for i in range(1, 5)]
    samples_b2 = [f"batch2_s{i}" for i in range(1, 5)]
    all_samples = samples_b1 + samples_b2

    # Base expression (lognormal)
    base = np.random.lognormal(3.0, 2.0, size=(n_genes, 1))

    # Generate expression with batch effect
    expr = np.zeros((n_genes, len(all_samples)))
    for j, s in enumerate(all_samples):
        noise = np.random.normal(0, 0.3, size=n_genes)
        if s.startswith("batch2"):
            batch_shift = np.random.normal(1.5, 0.5, size=n_genes)  # batch effect
        else:
            batch_shift = np.zeros(n_genes)
        expr[:, j] = np.maximum(0, base.ravel() + batch_shift + noise)

    expr_df = pd.DataFrame(expr, index=genes, columns=all_samples)

    # Batch metadata
    batch_df = pd.DataFrame({
        "sample": all_samples,
        "batch": ["batch1"] * 4 + ["batch2"] * 4,
    })
    return expr_df, batch_df


def get_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    """Load or generate demo data."""
    project_root = Path(__file__).resolve().parents[3]
    demo_expr = project_root / "examples" / "demo_bulkrna_batch_expr.csv"
    demo_batch = project_root / "examples" / "demo_bulkrna_batch_info.csv"

    if demo_expr.exists() and demo_batch.exists():
        return pd.read_csv(demo_expr, index_col=0), pd.read_csv(demo_batch), demo_expr

    expr_df, batch_df = _generate_demo_data()
    demo_expr.parent.mkdir(parents=True, exist_ok=True)
    expr_df.to_csv(demo_expr)
    batch_df.to_csv(demo_batch, index=False)
    logger.info("Generated demo data: %s, %s", demo_expr, demo_batch)
    return expr_df, batch_df, demo_expr


# ---------------------------------------------------------------------------
# R sva::ComBat integration (primary method)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# ComBat implementation (Python fallback, parametric EB)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# PCA + visualization
# ---------------------------------------------------------------------------







def generate_figures(output_dir: Path, expr_before: pd.DataFrame,
                     expr_after: pd.DataFrame, batch_labels: pd.Series,
                     metrics: dict) -> list[str]:
    """Generate PCA plots before/after correction."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    unique_batches = np.unique(batch_labels.values)
    palette = ["#4878CF", "#E8A02F", "#5BA05B", "#E84D60", "#9467BD",
               "#8C564B", "#BCBD22", "#17BECF"]
    batch_colors = {b: palette[i % len(palette)] for i, b in enumerate(unique_batches)}

    for label, expr in [("before", expr_before), ("after", expr_after)]:
        pc = _run_pca(expr, n_components=2)
        fig, ax = plt.subplots(figsize=(7, 5))
        for b in unique_batches:
            mask = batch_labels.values == b
            ax.scatter(pc[mask, 0], pc[mask, 1], c=batch_colors[b],
                       label=b, s=60, alpha=0.8, edgecolors="white", linewidth=0.5)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        sil_key = f"silhouette_{label}"
        sil_val = metrics.get(sil_key, 0)
        ax.set_title(f"PCA — {label.capitalize()} Correction (silhouette={sil_val:.3f})")
        ax.legend(fontsize=9)
        fig.tight_layout()
        p = fig_dir / f"pca_{label}_correction.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # Side-by-side comparison
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax_idx, (label, expr) in enumerate([("Before", expr_before), ("After", expr_after)]):
        ax = axes[ax_idx]
        pc = _run_pca(expr, n_components=2)
        for b in unique_batches:
            mask = batch_labels.values == b
            ax.scatter(pc[mask, 0], pc[mask, 1], c=batch_colors[b],
                       label=b, s=60, alpha=0.8, edgecolors="white", linewidth=0.5)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.set_title(f"{label} Correction")
        ax.legend(fontsize=8)
    fig.suptitle("Batch Effect Correction Assessment", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    p = fig_dir / "batch_assessment.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    return paths


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, summary: dict, params: dict,
                 corrected_expr: pd.DataFrame) -> None:
    """Write markdown report, result.json, and tables."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk RNA-seq Batch Correction Report",
        skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Batches**: {summary['n_batches']} ({', '.join(summary['batch_names'])})",
        f"- **Mode**: {summary['mode']}",
        "",
        "## Batch-Effect Metrics\n",
        "| Metric | Before | After | Change |",
        "|--------|--------|-------|--------|",
        f"| Silhouette Score | {summary['silhouette_before']:.4f} | "
        f"{summary['silhouette_after']:.4f} | "
        f"{summary['silhouette_after'] - summary['silhouette_before']:+.4f} |",
        "",
        "> **Interpretation**: A lower silhouette score after correction indicates better "
        "batch mixing. Negative values suggest batches are well-integrated.",
        "",
        "## Figures\n",
        "- `figures/pca_before_correction.png` — PCA before correction",
        "- `figures/pca_after_correction.png` — PCA after correction",
        "- `figures/batch_assessment.png` — Side-by-side comparison",
        "",
    ]

    footer = generate_report_footer()
    report_text = "\n".join([header, "\n".join(body_lines), footer])
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")

    # result.json
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, params)

    # Tables
    corrected_expr.to_csv(tables_dir / "corrected_expression.csv")
    metrics_df = pd.DataFrame([{
        "metric": "silhouette_score",
        "before": summary["silhouette_before"],
        "after": summary["silhouette_after"],
    }])
    metrics_df.to_csv(tables_dir / "batch_metrics.csv", index=False)

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env bash
# Reproducibility script for {SKILL_NAME} v{SKILL_VERSION}
python bulkrna_batch_correction.py \\
    --input {params.get('input', '<INPUT>')} \\
    --batch-info {params.get('batch_info', '<BATCH_INFO>')} \\
    --output {params.get('output', '<OUTPUT>')} \\
    --mode {params.get('mode', 'parametric')}
"""
    (repro_dir / "commands.sh").write_text(script, encoding="utf-8")
    logger.info("Report written to %s", output_dir / "report.md")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Expression matrix CSV")
    ap.add_argument("--batch-info", type=str, help="Batch metadata CSV (sample, batch)")
    ap.add_argument("--output", type=str, required=True, help="Output directory")
    ap.add_argument("--mode", choices=["parametric", "non-parametric"],
                    default="parametric", help="ComBat mode")
    ap.add_argument("--demo", action="store_true", help="Run with demo data")
    args = ap.parse_args()

    output_dir = Path(args.output)

    if args.demo:
        expr_df, batch_df, input_path = get_demo_data()
    else:
        if not args.input or not args.batch_info:
            ap.error("--input and --batch-info are required (or use --demo)")
        expr_df = pd.read_csv(args.input, index_col=0)
        batch_df = pd.read_csv(args.batch_info)
        input_path = Path(args.input)

    # Align batch labels to samples
    batch_df = batch_df.set_index("sample")
    batch_labels = batch_df.loc[expr_df.columns, "batch"]

    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    corrected_df = api.correct(expr_df, batches=batch_df.reset_index(), mode=args.mode)
    diagnostics = api.run_info(corrected_df, keep=False)
    summary = diagnostics.pop("summary")
    sil_before = summary["silhouette_before"]
    sil_after = summary["silhouette_after"]
    params = {
        "input": str(input_path),
        "batch_info": args.batch_info or "demo",
        "output": str(output_dir),
        "mode": args.mode,
        "run_info": diagnostics,
    }

    # Figures & report
    generate_figures(output_dir, expr_df, corrected_df, batch_labels,
                     {"silhouette_before": sil_before, "silhouette_after": sil_after})
    write_report(output_dir, summary, params, corrected_df)
    logger.info("✓ Batch correction complete → %s", output_dir)


if __name__ == "__main__":
    main()

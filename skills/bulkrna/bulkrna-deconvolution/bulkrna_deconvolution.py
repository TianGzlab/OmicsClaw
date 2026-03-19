#!/usr/bin/env python3
"""Bulk RNA-seq Deconvolution — estimate cell type proportions via NNLS.

Usage:
    python bulkrna_deconvolution.py --input <counts.csv> --output <dir> --reference <signature.csv>
    python bulkrna_deconvolution.py --demo --output <dir>
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
from scipy.optimize import nnls

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-deconvolution"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Demo / synthetic data
# ---------------------------------------------------------------------------
def _generate_demo_signature() -> pd.DataFrame:
    """Create a synthetic cell type signature matrix (genes x cell_types).

    200 genes (GENE_001..GENE_200) and 5 cell types.  Each cell type has
    ~40 marker genes with high expression (200-500); remaining genes have
    low baseline expression (10-50).
    """
    np.random.seed(42)
    genes = [f"GENE_{i:03d}" for i in range(1, 201)]
    cell_types = ["T_cells", "B_cells", "Macrophages", "Fibroblasts", "Epithelial"]

    # Low baseline expression for every gene in every cell type
    sig = np.random.randint(10, 51, size=(200, 5)).astype(float)

    # Assign ~40 marker genes per cell type with high expression
    for ct_idx in range(5):
        start = ct_idx * 40
        end = start + 40
        sig[start:end, ct_idx] = np.random.randint(200, 501, size=40).astype(float)

    df = pd.DataFrame(sig, index=genes, columns=cell_types)
    df.index.name = "gene"
    return df


def get_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    """Load the demo bulk count matrix and generate a demo signature.

    Returns (counts_df, signature_df, counts_path).
    """
    counts_path = _PROJECT_ROOT / "examples" / "demo_bulkrna_counts.csv"
    if not counts_path.exists():
        raise FileNotFoundError(
            f"Demo count matrix not found at {counts_path}. "
            "Ensure the examples/ directory is present."
        )

    counts_df = pd.read_csv(counts_path, index_col=0)
    logger.info("Loaded demo counts: %d genes x %d samples", *counts_df.shape)

    signature_df = _generate_demo_signature()
    logger.info(
        "Generated demo signature: %d genes x %d cell types",
        *signature_df.shape,
    )
    return counts_df, signature_df, counts_path


# ---------------------------------------------------------------------------
# Core NNLS deconvolution
# ---------------------------------------------------------------------------
def _run_nnls(mixture: np.ndarray, signature: np.ndarray) -> np.ndarray:
    """Run NNLS for a single sample and normalize to proportions.

    Parameters
    ----------
    mixture : 1-D array of expression values for one sample.
    signature : 2-D array (genes x cell_types).

    Returns
    -------
    Proportions array summing to 1.
    """
    coeffs, residual = nnls(signature, mixture)
    total = coeffs.sum()
    if total > 0:
        coeffs = coeffs / total
    return coeffs


def core_analysis(
    counts: pd.DataFrame,
    signature: pd.DataFrame,
) -> dict:
    """Deconvolve every sample via NNLS.

    Parameters
    ----------
    counts : DataFrame with genes as rows and samples as columns.
    signature : DataFrame with genes as rows and cell types as columns.

    Returns
    -------
    Summary dict with proportions, dominant types, mean proportions, etc.
    """
    shared_genes = sorted(set(counts.index) & set(signature.index))
    if not shared_genes:
        raise ValueError(
            "No shared genes between count matrix and signature matrix. "
            "Check that both use the same gene identifier format."
        )
    logger.info("Shared genes: %d", len(shared_genes))

    sig_mat = signature.loc[shared_genes].values.astype(float)
    cell_types = list(signature.columns)
    samples = list(counts.columns)

    proportions = np.zeros((len(samples), len(cell_types)))
    residuals = np.zeros(len(samples))

    for i, sample in enumerate(samples):
        mix = counts.loc[shared_genes, sample].values.astype(float)
        # Run raw NNLS (before normalizing to proportions) for residual
        raw_coeffs, _ = nnls(sig_mat, mix)
        total = raw_coeffs.sum()
        proportions[i] = raw_coeffs / total if total > 0 else raw_coeffs
        # Reconstruction residual: RMSE between raw mix and NNLS reconstruction
        reconstructed = sig_mat @ raw_coeffs
        residuals[i] = float(np.sqrt(np.mean((mix - reconstructed) ** 2)))

    proportions_df = pd.DataFrame(proportions, index=samples, columns=cell_types)
    proportions_df.index.name = "sample"

    # Dominant cell type per sample
    dominant_types = proportions_df.idxmax(axis=1).to_dict()

    # Mean proportions across all samples
    mean_proportions = proportions_df.mean(axis=0).to_dict()

    summary = {
        "n_genes_shared": len(shared_genes),
        "n_samples": len(samples),
        "n_cell_types": len(cell_types),
        "cell_types": cell_types,
        "proportions_df": proportions_df,
        "dominant_types": dominant_types,
        "mean_proportions": mean_proportions,
        "residuals": residuals.tolist(),
    }
    return summary


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Generate deconvolution visualisation figures.

    Returns list of figure filenames created.
    """
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(exist_ok=True)
    figures: list[str] = []

    props = summary["proportions_df"]
    cell_types = summary["cell_types"]

    # 1. Stacked bar chart --------------------------------------------------
    fig, ax = plt.subplots(figsize=(max(8, len(props) * 0.6), 5))
    bottom = np.zeros(len(props))
    x = np.arange(len(props))
    for ct in cell_types:
        vals = props[ct].values
        ax.bar(x, vals, bottom=bottom, label=ct, width=0.8)
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(props.index, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Proportion")
    ax.set_title("Cell Type Proportions per Sample")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fname = "proportions_stacked.png"
    fig.savefig(fig_dir / fname, dpi=150)
    plt.close(fig)
    figures.append(fname)

    # 2. Heatmap -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(max(6, len(cell_types) * 0.8), max(4, len(props) * 0.4)))
    im = ax.imshow(props.values, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(range(len(cell_types)))
    ax.set_xticklabels(cell_types, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(props)))
    ax.set_yticklabels(props.index, fontsize=8)
    ax.set_title("Proportion Heatmap")
    fig.colorbar(im, ax=ax, label="Proportion")
    fig.tight_layout()
    fname = "proportions_heatmap.png"
    fig.savefig(fig_dir / fname, dpi=150)
    plt.close(fig)
    figures.append(fname)

    # 3. Mean proportions pie chart ------------------------------------------
    mean_vals = [summary["mean_proportions"][ct] for ct in cell_types]
    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        mean_vals,
        labels=cell_types,
        autopct="%1.1f%%",
        startangle=90,
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.set_title("Mean Cell Type Proportions")
    fig.tight_layout()
    fname = "mean_proportions_pie.png"
    fig.savefig(fig_dir / fname, dpi=150)
    plt.close(fig)
    figures.append(fname)

    logger.info("Generated %d figures in %s", len(figures), fig_dir)
    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write markdown report, result.json, tables, and reproducibility script."""

    # --- Markdown report ---
    header = generate_report_header(
        title="Bulk RNA-seq Deconvolution Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Shared genes": str(summary["n_genes_shared"]),
            "Samples": str(summary["n_samples"]),
            "Cell types": str(summary["n_cell_types"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: NNLS (scipy.optimize.nnls)",
        f"- **Shared genes**: {summary['n_genes_shared']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Cell types**: {summary['n_cell_types']} ({', '.join(summary['cell_types'])})",
        "",
        "### Mean Cell Type Proportions\n",
    ]
    for ct, val in summary["mean_proportions"].items():
        body_lines.append(f"- **{ct}**: {val:.3f}")

    body_lines.extend([
        "",
        "### Dominant Cell Type per Sample\n",
    ])
    for sample, ct in summary["dominant_types"].items():
        body_lines.append(f"- `{sample}`: {ct}")

    body_lines.extend([
        "",
        "## Methodology\n",
        "- **Deconvolution**: Non-negative least squares (NNLS) via scipy",
        "- **Normalization**: Proportions scaled to sum to 1 per sample",
        "- **Signature**: External reference matrix of cell-type-specific gene expression",
        "",
        "## Parameters\n",
    ])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        header + "\n".join(body_lines) + "\n" + footer
    )

    # --- Tables ---
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    summary["proportions_df"].to_csv(tables_dir / "proportions.csv")
    dom_df = pd.DataFrame(
        list(summary["dominant_types"].items()),
        columns=["sample", "dominant_cell_type"],
    )
    dom_df.to_csv(tables_dir / "dominant_types.csv", index=False)

    # --- result.json ---
    json_summary = {
        k: v
        for k, v in summary.items()
        if k != "proportions_df"
    }
    write_result_json(
        output_dir, SKILL_NAME, SKILL_VERSION, json_summary, {"params": params}
    )

    # --- Reproducibility ---
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd_parts = [
        f"python bulkrna_deconvolution.py --output {output_dir}",
    ]
    if input_file:
        cmd_parts.append(f"  --input {input_file}")
    if params.get("reference"):
        cmd_parts.append(f"  --reference {params['reference']}")
    if params.get("demo"):
        cmd_parts.append("  --demo")
    cmd = " \\\n".join(cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk RNA-seq cell type deconvolution via NNLS"
    )
    parser.add_argument("--input", dest="input_path", help="Bulk count matrix CSV")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with built-in demo data")
    parser.add_argument(
        "--reference",
        dest="reference_path",
        help="Signature matrix CSV (genes x cell_types)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        counts, signature, counts_path = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input is required when not using --demo")
        if not args.reference_path:
            raise ValueError("--reference is required when not using --demo")
        counts = pd.read_csv(args.input_path, index_col=0)
        signature = pd.read_csv(args.reference_path, index_col=0)
        input_file = args.input_path

    summary = core_analysis(counts, signature)
    figures = generate_figures(output_dir, summary)

    params = {
        "method": "NNLS",
        "demo": args.demo,
        "reference": args.reference_path or "built-in demo signature",
    }
    write_report(output_dir, summary, input_file, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Deconvolution complete: {summary['n_samples']} samples, "
        f"{summary['n_cell_types']} cell types, "
        f"{summary['n_genes_shared']} shared genes"
    )


if __name__ == "__main__":
    main()

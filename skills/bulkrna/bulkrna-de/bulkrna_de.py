#!/usr/bin/env python3
"""Bulk RNA-seq Differential Expression -- PyDESeq2, with fallback to scipy t-test.

Usage:
    python bulkrna_de.py --input <counts.csv> --output <dir> --control-prefix ctrl --treat-prefix treat
    python bulkrna_de.py --demo --output <dir>
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
from scipy import stats

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk import REPO_ROOT as _PROJECT_ROOT  # noqa: E402

from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-de"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("deseq2", "ttest")


def get_demo_data() -> tuple[pd.DataFrame, Path]:
    """Load the bundled demo count matrix. Returns (DataFrame, path)."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_bulkrna_counts.csv"
    if not demo_path.exists():
        raise FileNotFoundError(f"Demo data not found at {demo_path}")
    df = pd.read_csv(demo_path)
    logger.info("Loaded demo data: %s (%d genes, %d columns)", demo_path, len(df), len(df.columns))
    return df, demo_path








from skills.bulkrna._lib.de import core_analysis


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Create volcano plot, MA plot, and DE bar chart. Return list of figure paths."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    de_df = summary["de_df"]
    padj_cutoff, lfc_cutoff = summary["padj_cutoff"], summary["lfc_cutoff"]
    is_sig = (de_df["padj"] < padj_cutoff) & (de_df["log2FoldChange"].abs() > lfc_cutoff)
    colours = np.where(is_sig, np.where(de_df["log2FoldChange"] > 0, "firebrick", "steelblue"), "grey")

    # Volcano plot
    fig, ax = plt.subplots(figsize=(8, 6))
    neg_log10p = -np.log10(de_df["pvalue"].clip(lower=1e-300))
    ax.scatter(de_df["log2FoldChange"], neg_log10p, c=colours, s=12, alpha=0.7, edgecolors="none")
    ax.axhline(-np.log10(padj_cutoff), color="black", ls="--", lw=0.8)
    ax.axvline(-lfc_cutoff, color="black", ls="--", lw=0.8)
    ax.axvline(lfc_cutoff, color="black", ls="--", lw=0.8)
    ax.set_xlabel("log2 Fold Change")
    ax.set_ylabel("-log10(p-value)")
    ax.set_title("Volcano Plot")
    # Label top 10 genes
    if "gene" in de_df.columns:
        top_genes = de_df.dropna(subset=["padj"]).nsmallest(10, "padj")
        for _, row in top_genes.iterrows():
            y_val = -np.log10(max(row["pvalue"], 1e-300))
            ax.annotate(row["gene"], (row["log2FoldChange"], y_val),
                        fontsize=6, alpha=0.8, ha="center", va="bottom",
                        textcoords="offset points", xytext=(0, 4))
    plt.tight_layout()
    fig.savefig(fig_dir / "volcano_plot.png", dpi=150)
    plt.close(fig)
    created.append(str(fig_dir / "volcano_plot.png"))

    # MA plot
    fig, ax = plt.subplots(figsize=(8, 6))
    log10_base = np.log10(de_df["baseMean"].clip(lower=1e-1))
    ax.scatter(log10_base, de_df["log2FoldChange"], c=colours, s=12, alpha=0.7, edgecolors="none")
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(lfc_cutoff, color="grey", ls="--", lw=0.6, alpha=0.5)
    ax.axhline(-lfc_cutoff, color="grey", ls="--", lw=0.6, alpha=0.5)
    ax.set_xlabel("log10(baseMean)")
    ax.set_ylabel("log2 Fold Change")
    ax.set_title("MA Plot")
    plt.tight_layout()
    fig.savefig(fig_dir / "ma_plot.png", dpi=150)
    plt.close(fig)
    created.append(str(fig_dir / "ma_plot.png"))

    # DE bar chart
    fig, ax = plt.subplots(figsize=(6, 4))
    n_up, n_down = summary["n_up"], summary["n_down"]
    n_ns = summary["n_genes"] - n_up - n_down
    cats = ["Up-regulated", "Down-regulated", "Not significant"]
    vals = [n_up, n_down, n_ns]
    ax.bar(cats, vals, color=["firebrick", "steelblue", "grey"], edgecolor="black", linewidth=0.5)
    ax.set_ylabel("Number of genes")
    ax.set_title("Differential Expression Summary")
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.01, str(v), ha="center", fontsize=10)
    plt.tight_layout()
    fig.savefig(fig_dir / "de_barplot.png", dpi=150)
    plt.close(fig)
    created.append(str(fig_dir / "de_barplot.png"))

    # P-value distribution histogram (diagnostic)
    fig, ax = plt.subplots(figsize=(7, 4))
    pvals = de_df["pvalue"].dropna()
    ax.hist(pvals, bins=50, color="steelblue", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("P-value")
    ax.set_ylabel("Frequency")
    ax.set_title("P-value Distribution (expect uniform + peak near 0)")
    plt.tight_layout()
    fig.savefig(fig_dir / "pvalue_histogram.png", dpi=150)
    plt.close(fig)
    created.append(str(fig_dir / "pvalue_histogram.png"))

    return created


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report.md, result.json, DE tables, and reproducibility script."""
    header = generate_report_header(
        title="Bulk RNA-seq Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary["method_used"], "DE genes": str(summary["n_de_genes"])},
    )
    body_lines = [
        "## Summary\n",
        f"- **Total genes (raw)**: {summary.get('n_genes_raw', summary['n_genes'])}",
        f"- **Genes after pre-filtering**: {summary['n_genes']} (removed {summary.get('n_genes_prefiltered', 0)} low-count genes)",
        f"- **Samples**: {summary['n_samples']} ({summary['n_ctrl']} control, {summary['n_treat']} treatment)",
        f"- **Method**: {summary['method_used']}",
        f"- **DE genes (padj < {summary['padj_cutoff']}, |log2FC| > {summary['lfc_cutoff']})**: {summary['n_de_genes']}",
        f"  - Up-regulated: {summary['n_up']}",
        f"  - Down-regulated: {summary['n_down']}",
        f"- **Fraction significant**: {summary.get('frac_significant', 0):.1%}",
        "",
        f"> **Note**: {summary.get('lfc_note', '')}",
        "", "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + generate_report_footer())

    # result.json
    diagnostic_keys = ('requested_method', 'executed_method', 'fallback_reason')
    json_summary = {k: v for k, v in summary.items() if k not in ('de_df', *diagnostic_keys)}
    diagnostics = {k: summary[k] for k in diagnostic_keys if k in summary}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, json_summary, {"params": params, "diagnostics": diagnostics})

    # Tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    de_df = summary["de_df"]
    de_df.to_csv(tables_dir / "de_results.csv", index=False)
    sig = de_df.dropna(subset=["padj"])
    sig = sig[(sig["padj"] < summary["padj_cutoff"]) & (sig["log2FoldChange"].abs() > summary["lfc_cutoff"])]
    sig.to_csv(tables_dir / "de_significant.csv", index=False)

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["python bulkrna_de.py"]
    if params.get("input_file"):
        cmd.append(f"--input {params['input_file']}")
    cmd += [
        f"--method {params.get('method', 'pydeseq2')}",
        f"--control-prefix {params.get('control_prefix', 'ctrl')}",
        f"--treat-prefix {params.get('treat_prefix', 'treat')}",
        f"--padj-cutoff {params.get('padj_cutoff', 0.05)}",
        f"--lfc-cutoff {params.get('lfc_cutoff', 1.0)}",
        f"--output {output_dir}",
    ]
    (repro_dir / "commands.sh").write_text("#!/bin/bash\n" + " \\\n  ".join(cmd) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Bulk RNA-seq Differential Expression (PyDESeq2 / t-test)")
    parser.add_argument("--input", dest="input_path", help="Path to counts CSV (gene x sample)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with bundled demo data")
    parser.add_argument("--method", default="deseq2", choices=SUPPORTED_METHODS, help="DE method (deseq2=R DESeq2, ttest=fallback)")
    parser.add_argument("--control-prefix", default="ctrl", help="Column prefix for control samples")
    parser.add_argument("--treat-prefix", default="treat", help="Column prefix for treatment samples")
    parser.add_argument("--padj-cutoff", type=float, default=0.05, help="Adjusted p-value cutoff")
    parser.add_argument("--lfc-cutoff", type=float, default=1.0, help="Absolute log2FC cutoff")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        counts, data_path = get_demo_data()
        input_file = str(data_path)
    else:
        if not args.input_path:
            parser.error("--input is required when not using --demo")
        data_path = Path(args.input_path)
        if not data_path.exists():
            raise FileNotFoundError(f"Input file not found: {data_path}")
        counts = pd.read_csv(data_path)
        input_file = str(data_path)

    from skills._sdk.notebook import load_skill
    library = load_skill(SKILL_NAME)
    result = library.differential_expression(
        counts.set_index(counts.columns[0]), method=args.method, control_prefix=args.control_prefix,
        treat_prefix=args.treat_prefix, padj_cutoff=args.padj_cutoff, lfc_cutoff=args.lfc_cutoff,
    )
    summary = library.run_info(result, keep=False)
    figures = generate_figures(output_dir, summary)
    logger.info("Generated %d figures.", len(figures))

    params = {
        "method": args.method, "control_prefix": args.control_prefix,
        "treat_prefix": args.treat_prefix, "padj_cutoff": args.padj_cutoff,
        "lfc_cutoff": args.lfc_cutoff, "input_file": input_file,
    }
    write_report(output_dir, summary, input_file if not args.demo else None, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Method: {summary['method_used']}")
    print(f"  DE genes: {summary['n_de_genes']} (up={summary['n_up']}, down={summary['n_down']})")


if __name__ == "__main__":
    main()

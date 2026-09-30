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


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction with NaN handling."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    # Handle NaN: track non-NaN positions
    nan_mask = np.isnan(pv)
    non_nan_indices = np.where(~nan_mask)[0]
    pv_clean = pv[non_nan_indices]
    m = len(pv_clean)
    if m == 0:
        return pv
    order = np.argsort(pv_clean)
    sorted_p = pv_clean[order]
    adjusted = np.empty(m, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(m - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * m / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)
    result_clean = np.empty(m, dtype=float)
    result_clean[order] = adjusted
    result = np.full(n, np.nan)
    result[non_nan_indices] = result_clean
    return result


def _run_deseq2_r(
    counts: pd.DataFrame,
    gene_col: str,
    control_prefix: str,
    treat_prefix: str,
) -> pd.DataFrame:
    """Run real DESeq2 in R via subprocess. Raises ImportError if R/DESeq2 unavailable."""
    import tempfile
    from skills._sdk.deps import validate_r_environment
    from skills._sdk.r_script_runner import RScriptRunner
    from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR

    validate_r_environment(required_r_packages=["DESeq2"])

    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_bulkde_") as tmpdir:
        tmpdir = Path(tmpdir)
        # Write counts with gene names as row index
        counts_for_r = counts.set_index(gene_col)
        counts_for_r.to_csv(tmpdir / "counts.csv")

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "bulkrna_deseq2.R",
            args=[str(tmpdir / "counts.csv"), str(output_dir),
                  control_prefix, treat_prefix],
            expected_outputs=["deseq2_results.csv"],
            output_dir=output_dir,
        )

        de_df = pd.read_csv(output_dir / "deseq2_results.csv")

    # Standardize column names
    rename_map = {}
    for col in de_df.columns:
        lc = col.lower()
        if lc == "basemean":
            rename_map[col] = "baseMean"
        elif lc in ("log2foldchange", "log2_fold_change"):
            rename_map[col] = "log2FoldChange"
        elif lc == "pvalue":
            rename_map[col] = "pvalue"
        elif lc == "padj":
            rename_map[col] = "padj"
    if rename_map:
        de_df = de_df.rename(columns=rename_map)

    return de_df


def _run_ttest(counts: pd.DataFrame, ctrl_cols: list[str], treat_cols: list[str]) -> pd.DataFrame:
    """Welch's t-test per gene with BH FDR correction.
    *counts*: genes-as-rows DataFrame; first column is gene name.

    Produces output columns consistent with DESeq2: gene, baseMean,
    log2FoldChange, lfcSE, stat, pvalue, padj.
    """
    gene_col = counts.columns[0]
    records: list[dict] = []
    for _, row in counts.iterrows():
        ctrl_vals = row[ctrl_cols].values.astype(float)
        treat_vals = row[treat_cols].values.astype(float)
        mean_ctrl = float(np.mean(ctrl_vals))
        mean_treat = float(np.mean(treat_vals))
        base_mean = (mean_ctrl + mean_treat) / 2.0
        log2fc = np.log2(mean_treat + 1) - np.log2(mean_ctrl + 1)

        # Standard error of log2FC (delta method approximation)
        se_ctrl = float(np.std(ctrl_vals, ddof=1)) / (mean_ctrl + 1) / np.log(2) if len(ctrl_vals) > 1 else 0.0
        se_treat = float(np.std(treat_vals, ddof=1)) / (mean_treat + 1) / np.log(2) if len(treat_vals) > 1 else 0.0
        lfc_se = float(np.sqrt(se_ctrl**2 / max(len(ctrl_vals), 1) + se_treat**2 / max(len(treat_vals), 1)))

        if np.std(ctrl_vals) == 0 and np.std(treat_vals) == 0:
            pval = 1.0
            t_stat = 0.0
        else:
            t_stat_val, pval = stats.ttest_ind(ctrl_vals, treat_vals, equal_var=False)
            t_stat = float(t_stat_val) if not np.isnan(t_stat_val) else 0.0
            pval = float(pval) if not np.isnan(pval) else 1.0

        records.append({
            "gene": row[gene_col],
            "baseMean": round(base_mean, 4),
            "log2FoldChange": round(float(log2fc), 6),
            "lfcSE": round(lfc_se, 6),
            "stat": round(t_stat, 6),
            "pvalue": pval,
        })
    result = pd.DataFrame(records)
    result["padj"] = _benjamini_hochberg(result["pvalue"].values)
    return result.sort_values("pvalue").reset_index(drop=True)


def core_analysis(
    counts: pd.DataFrame,
    *,
    method: str = "pydeseq2",
    control_prefix: str = "ctrl",
    treat_prefix: str = "treat",
    padj_cutoff: float = 0.05,
    lfc_cutoff: float = 1.0,
    min_count: int = 10,
) -> dict:
    """Run DE analysis and return a summary dict."""
    gene_col = counts.columns[0]
    sample_cols = [c for c in counts.columns if c != gene_col]
    ctrl_cols = [c for c in sample_cols if c.startswith(control_prefix)]
    treat_cols = [c for c in sample_cols if c.startswith(treat_prefix)]
    if not ctrl_cols:
        raise ValueError(f"No columns matching control prefix '{control_prefix}'")
    if not treat_cols:
        raise ValueError(f"No columns matching treatment prefix '{treat_prefix}'")

    # Design validation (from Biomni basic_workflow.R best practices)
    n_ctrl, n_treat = len(ctrl_cols), len(treat_cols)
    if n_ctrl < 2 or n_treat < 2:
        logger.warning(
            "Insufficient replicates: %d control, %d treatment. "
            "DESeq2 requires >= 2 replicates per condition (>= 3 recommended).",
            n_ctrl, n_treat,
        )
    elif n_ctrl < 3 or n_treat < 3:
        logger.info(
            "Low replication: %d control, %d treatment. "
            "Consider >= 3 replicates per condition for reliable dispersion estimation.",
            n_ctrl, n_treat,
        )
    else:
        logger.info("Design: %d control, %d treatment samples", n_ctrl, n_treat)

    # Gene pre-filtering: remove low-count genes (from Biomni basic_workflow.R)
    n_genes_raw = len(counts)
    numeric_cols = ctrl_cols + treat_cols
    row_sums = counts[numeric_cols].sum(axis=1)
    counts_filtered = counts[row_sums >= min_count].copy()
    n_genes_filtered = len(counts_filtered)
    n_removed = n_genes_raw - n_genes_filtered
    if n_removed > 0:
        logger.info(
            "Pre-filtered genes: %d → %d (removed %d with rowSum < %d)",
            n_genes_raw, n_genes_filtered, n_removed, min_count,
        )
    counts = counts_filtered
    method_used = method
    if method == "deseq2":
        try:
            de_df = _run_deseq2_r(counts, gene_col, control_prefix, treat_prefix)
            method_used = "deseq2"
            logger.info("R DESeq2 completed successfully.")
        except Exception as exc:
            logger.warning("R DESeq2 failed (%s); falling back to t-test.", exc)
            de_df = _run_ttest(counts, ctrl_cols, treat_cols)
            method_used = "ttest"
    elif method == "ttest":
        de_df = _run_ttest(counts, ctrl_cols, treat_cols)
        method_used = "ttest"
    else:
        raise ValueError(f"Unknown method '{method}'. Choose from {SUPPORTED_METHODS}")

    sig = de_df.dropna(subset=["padj"])
    sig = sig[(sig["padj"] < padj_cutoff) & (sig["log2FoldChange"].abs() > lfc_cutoff)]
    n_up = int((sig["log2FoldChange"] > 0).sum())
    n_down = int((sig["log2FoldChange"] < 0).sum())
    n_tested = int(de_df["padj"].notna().sum())
    frac_sig = len(sig) / max(n_tested, 1)

    return {
        "n_genes": len(de_df), "n_genes_raw": n_genes_raw,
        "n_genes_filtered": n_genes_filtered, "n_genes_prefiltered": n_removed,
        "n_samples": len(ctrl_cols) + len(treat_cols),
        "n_ctrl": len(ctrl_cols), "n_treat": len(treat_cols),
        "method_used": method_used, "n_de_genes": len(sig),
        "n_up": n_up, "n_down": n_down,
        "n_tested": n_tested, "frac_significant": round(frac_sig, 4),
        "padj_cutoff": padj_cutoff, "lfc_cutoff": lfc_cutoff,
        "lfc_note": (
            "LFCs are unshrunk (suitable for hypothesis testing). "
            "For visualization/ranking, consider apeglm or ashr shrinkage."
        ),
        "de_df": de_df,
    }


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
    json_summary = {k: v for k, v in summary.items() if k != "de_df"}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, json_summary, {"params": params})

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

    summary = core_analysis(
        counts, method=args.method, control_prefix=args.control_prefix,
        treat_prefix=args.treat_prefix, padj_cutoff=args.padj_cutoff, lfc_cutoff=args.lfc_cutoff,
    )
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

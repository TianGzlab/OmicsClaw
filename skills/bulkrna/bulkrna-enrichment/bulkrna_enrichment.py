#!/usr/bin/env python3
"""Bulk RNA-seq Pathway Enrichment — ORA/GSEA via GSEApy with hypergeometric fallback.

Usage:
    python bulkrna_enrichment.py --input <de_results.csv> --output <dir> --method ora
    python bulkrna_enrichment.py --demo --output <dir>
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
from scipy import stats as scipy_stats

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (  # noqa: E402
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-enrichment"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("ora", "gsea", "ora_r", "gsea_r")

# Ranking metric preference order (from Biomni prepare_gene_lists.R)
RANKING_METRIC_PREFERENCE = ("stat", "scores", "logfoldchanges", "log2FoldChange")


def _run_enrichment_r(
    _de_df: pd.DataFrame,
    *,
    method: str,
    padj_cutoff: float,
    lfc_cutoff: float,
) -> dict:
    """Closed R-backend seam until a clusterProfiler adapter is implemented."""
    raise RuntimeError(
        "clusterProfiler backend is not implemented; "
        f"falling back from {method} (padj={padj_cutoff}, lfc={lfc_cutoff})"
    )




# ---------------------------------------------------------------------------
# Demo gene sets
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Demo DE results
# ---------------------------------------------------------------------------




def get_demo_data() -> tuple[pd.DataFrame, None]:
    """Return synthetic DE results for demonstration purposes."""
    return _generate_demo_de_results(), None


# ---------------------------------------------------------------------------
# Benjamini-Hochberg correction
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Built-in hypergeometric ORA
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Built-in rank-based GSEA fallback
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


from skills.bulkrna._lib.enrichment import core_analysis, _build_demo_gene_sets, _generate_demo_de_results


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Create enrichment bar plot and dot plot. Return list of figure paths."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    enrichment_df = summary["enrichment_df"]
    if enrichment_df.empty or "padj" not in enrichment_df.columns:
        logger.warning("No enrichment results to plot.")
        return created

    # Filter to significant terms and take top 15
    plot_df = enrichment_df.dropna(subset=["padj"]).copy()
    plot_df["neg_log10_padj"] = -np.log10(plot_df["padj"].clip(lower=1e-300))
    plot_df = plot_df.sort_values("neg_log10_padj", ascending=False).head(15)

    if plot_df.empty:
        logger.warning("No terms with valid padj to plot.")
        return created

    # --- Enrichment bar plot ---
    fig, ax = plt.subplots(figsize=(10, max(6, len(plot_df) * 0.4)))
    y_pos = np.arange(len(plot_df))
    ax.barh(
        y_pos, plot_df["neg_log10_padj"].values,
        color="steelblue", edgecolor="black", linewidth=0.5, height=0.7,
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(plot_df["term"].values, fontsize=9)
    ax.set_xlabel("-log10(adjusted p-value)")
    ax.set_title("Top Enriched Terms (by adjusted p-value)")
    ax.invert_yaxis()
    plt.tight_layout()
    path = fig_dir / "enrichment_barplot.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    # --- Enrichment dot plot ---
    fig, ax = plt.subplots(figsize=(10, max(6, len(plot_df) * 0.4)))

    # Determine dot size from overlap or n_genes column
    size_col = None
    for candidate in ("overlap", "n_genes", "term_size"):
        if candidate in plot_df.columns:
            size_col = candidate
            break

    if size_col is not None:
        sizes = pd.to_numeric(plot_df[size_col], errors="coerce").fillna(1).values
        # Scale dot sizes for readability
        min_size, max_size = 50, 400
        s_range = sizes.max() - sizes.min() if sizes.max() != sizes.min() else 1.0
        dot_sizes = min_size + (sizes - sizes.min()) / s_range * (max_size - min_size)
    else:
        dot_sizes = np.full(len(plot_df), 150)
        sizes = np.ones(len(plot_df))

    scatter = ax.scatter(
        plot_df["neg_log10_padj"].values,
        np.arange(len(plot_df)),
        s=dot_sizes,
        c=plot_df["neg_log10_padj"].values,
        cmap="RdYlBu_r",
        edgecolors="black",
        linewidth=0.5,
        alpha=0.85,
    )
    ax.set_yticks(np.arange(len(plot_df)))
    ax.set_yticklabels(plot_df["term"].values, fontsize=9)
    ax.set_xlabel("-log10(adjusted p-value)")
    ax.set_title("Enrichment Dot Plot")
    ax.invert_yaxis()
    plt.colorbar(scatter, ax=ax, label="-log10(padj)", shrink=0.7)

    # Add size legend if we have meaningful sizes
    if size_col is not None:
        legend_sizes = [int(sizes.min()), int(np.median(sizes)), int(sizes.max())]
        legend_sizes = sorted(set(max(s, 1) for s in legend_sizes))
        for ls in legend_sizes:
            s_scaled = min_size + (ls - sizes.min()) / s_range * (max_size - min_size)
            ax.scatter([], [], s=s_scaled, c="grey", edgecolors="black",
                       linewidth=0.5, label=f"{size_col}={ls}")
        ax.legend(loc="lower right", framealpha=0.8, fontsize=8)

    plt.tight_layout()
    path = fig_dir / "enrichment_dotplot.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    return created


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
        title="Bulk RNA-seq Pathway Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method_used"],
            "Enriched terms": str(summary["n_enriched_terms"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Input genes**: {summary['n_input_genes']}",
        f"- **Significant genes** (pre-filter): {summary['n_significant']}",
        f"- **Method**: {summary['method_used']}",
        f"- **Terms tested**: {summary['n_terms_tested']}",
        f"- **Enriched terms (padj < 0.05)**: {summary['n_enriched_terms']}",
    ]

    enrichment_df = summary["enrichment_df"]
    sort_columns = [
        column for column in ("padj", "pvalue", "term") if column in enrichment_df
    ]
    if sort_columns:
        enrichment_df = enrichment_df.sort_values(sort_columns).reset_index(drop=True)
    if not enrichment_df.empty and "padj" in enrichment_df.columns:
        sig = enrichment_df[enrichment_df["padj"] < 0.05].head(15)
        if not sig.empty:
            body_lines.extend(["", "### Top Enriched Terms\n"])
            body_lines.append("| Term | Overlap/Size | Adj. p-value |")
            body_lines.append("|------|-------------|--------------|")
            for _, r in sig.iterrows():
                term = str(r.get("term", ""))
                overlap = r.get("overlap", r.get("n_genes", ""))
                t_size = r.get("term_size", "")
                size_str = (
                    str(overlap)
                    if "/" in str(overlap)
                    else f"{overlap}/{t_size}" if t_size else str(overlap)
                )
                body_lines.append(f"| {term} | {size_str} | {r['padj']:.2e} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    # --- result.json ---
    diagnostic_keys = ('requested_method', 'executed_method', 'fallback_reason')
    json_summary = {k: v for k, v in summary.items() if k not in ('enrichment_df', *diagnostic_keys)}
    write_result_json(
        output_dir, SKILL_NAME, SKILL_VERSION,
        json_summary, {"params": params, **json_summary,
                       "diagnostics": {k: summary[k] for k in diagnostic_keys if k in summary}},
    )

    # --- Tables ---
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    if not enrichment_df.empty:
        enrichment_df.to_csv(tables_dir / "enrichment_results.csv", index=False)
        sig_df = enrichment_df[enrichment_df["padj"] < 0.05] if "padj" in enrichment_df.columns else pd.DataFrame()
        if not sig_df.empty:
            sig_df.to_csv(tables_dir / "enrichment_significant.csv", index=False)

    # --- Reproducibility ---
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    cmd_parts = [
        "python bulkrna_enrichment.py",
        f"--method {params.get('method', 'ora')}",
        f"--padj-cutoff {params.get('padj_cutoff', 0.05)}",
        f"--lfc-cutoff {params.get('lfc_cutoff', 1.0)}",
    ]
    if params.get("input_file"):
        cmd_parts.insert(1, f"--input {params['input_file']}")
    if params.get("gene_set_file"):
        cmd_parts.append(f"--gene-set-file {params['gene_set_file']}")
    cmd_parts.append(f"--output {output_dir}")
    (repro_dir / "commands.sh").write_text("#!/bin/bash\n" + " \\\n  ".join(cmd_parts) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Bulk RNA-seq Pathway Enrichment (ORA / GSEA)",
    )
    parser.add_argument("--input", dest="input_path",
                        help="Path to DE results CSV (gene, log2FoldChange, pvalue, padj)")
    parser.add_argument("--output", dest="output_dir", required=True,
                        help="Output directory")
    parser.add_argument("--demo", action="store_true",
                        help="Run with synthetic demo data")
    parser.add_argument("--method", default="ora", choices=SUPPORTED_METHODS,
                        help="Enrichment method (default: ora)")
    parser.add_argument("--padj-cutoff", type=float, default=0.05,
                        help="Adjusted p-value cutoff (default: 0.05)")
    parser.add_argument("--lfc-cutoff", type=float, default=1.0,
                        help="Absolute log2FC cutoff for ORA gene filter (default: 1.0)")
    parser.add_argument("--gene-set-file", default=None,
                        help="Path to custom gene sets JSON (keys=term, values=gene list)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        de_df, _ = get_demo_data()
        input_file = None
        logger.info("Running in demo mode with synthetic DE results.")
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        de_df = pd.read_csv(input_path)
        input_file = str(input_path)
        logger.info("Loaded DE results: %s (%d genes)", input_path, len(de_df))
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Validate required columns
    required_cols = {"gene", "log2FoldChange", "pvalue", "padj"}
    missing = required_cols - set(de_df.columns)
    if missing:
        print(f"ERROR: Missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    # Load custom gene sets if provided
    gene_sets = _build_demo_gene_sets() if args.demo else None
    if args.gene_set_file:
        gs_path = Path(args.gene_set_file)
        if not gs_path.exists():
            print(f"ERROR: Gene set file not found: {gs_path}", file=sys.stderr)
            sys.exit(1)
        with open(gs_path) as f:
            gene_sets = json.load(f)
        logger.info("Loaded %d custom gene sets from %s.", len(gene_sets), gs_path)

    # Run analysis
    from skills._sdk.notebook import load_skill
    library = load_skill(SKILL_NAME)
    result = library.enrich(
        de_df,
        method=args.method,
        gene_sets=gene_sets,
        padj_cutoff=args.padj_cutoff,
        lfc_cutoff=args.lfc_cutoff,
    )
    summary = library.run_info(result, keep=False)

    # Generate outputs
    figures = generate_figures(output_dir, summary)
    logger.info("Generated %d figures.", len(figures))

    params = {
        "method": args.method,
        "padj_cutoff": args.padj_cutoff,
        "lfc_cutoff": args.lfc_cutoff,
        "gene_set_file": args.gene_set_file,
        "input_file": input_file,
    }
    write_report(output_dir, summary, input_file, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output:  {output_dir}")
    print(f"  Method:  {summary['method_used']}")
    print(f"  Tested:  {summary['n_terms_tested']} terms")
    print(f"  Enriched: {summary['n_enriched_terms']} terms (padj < 0.05)")


if __name__ == "__main__":
    main()

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

SKILL_NAME = "bulkrna-enrichment"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("ora", "gsea")


# ---------------------------------------------------------------------------
# Demo gene sets
# ---------------------------------------------------------------------------


def _build_demo_gene_sets() -> dict[str, list[str]]:
    """Create synthetic pathway gene sets using GENE_XXX names from demo data."""
    return {
        "Cell_Cycle": [f"GENE_{i:03d}" for i in range(51, 61)],
        "Apoptosis": [f"GENE_{i:03d}" for i in range(61, 71)],
        "Immune_Response": [f"GENE_{i:03d}" for i in range(71, 81)],
        "Metabolism": [f"GENE_{i:03d}" for i in range(81, 91)],
        "Signal_Transduction": [f"GENE_{i:03d}" for i in range(91, 101)],
        "DNA_Repair": [f"GENE_{i:03d}" for i in range(101, 111)],
        "Transcription": [f"GENE_{i:03d}" for i in range(111, 121)],
        "Translation": [f"GENE_{i:03d}" for i in range(121, 131)],
        "Transport": [f"GENE_{i:03d}" for i in range(131, 141)],
        "Cytoskeleton": [f"GENE_{i:03d}" for i in range(141, 151)],
        "Extracellular_Matrix": [f"GENE_{i:03d}" for i in range(151, 161)],
        "Lipid_Metabolism": [f"GENE_{i:03d}" for i in range(161, 171)],
        "Amino_Acid_Metabolism": [f"GENE_{i:03d}" for i in range(171, 181)],
        "Oxidative_Phosphorylation": [f"GENE_{i:03d}" for i in range(181, 191)],
        "mRNA_Processing": [f"GENE_{i:03d}" for i in range(191, 201)],
    }


# ---------------------------------------------------------------------------
# Demo DE results
# ---------------------------------------------------------------------------


def _generate_demo_de_results() -> pd.DataFrame:
    """Create a synthetic DE results table for demonstration.

    Returns a DataFrame with columns: gene, log2FoldChange, pvalue, padj.
    - GENE_051-100: upregulated (log2FC ~ N(2.5, 0.5), padj < 0.05)
    - GENE_101-150: downregulated (log2FC ~ N(-2.5, 0.5), padj < 0.05)
    - GENE_001-050, GENE_151-200: not significant (log2FC ~ N(0, 0.3), padj > 0.1)
    """
    np.random.seed(42)

    records: list[dict] = []

    # Not significant: GENE_001-050
    for i in range(1, 51):
        lfc = np.random.normal(0, 0.3)
        pval = np.random.uniform(0.1, 1.0)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": round(float(pval), 6),
            "padj": round(float(np.random.uniform(0.1, 1.0)), 6),
        })

    # Upregulated: GENE_051-100
    for i in range(51, 101):
        lfc = np.random.normal(2.5, 0.5)
        pval = float(10 ** np.random.uniform(-10, -2))
        padj = float(pval * np.random.uniform(1.0, 5.0))
        padj = min(padj, 0.049)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": pval,
            "padj": padj,
        })

    # Downregulated: GENE_101-150
    for i in range(101, 151):
        lfc = np.random.normal(-2.5, 0.5)
        pval = float(10 ** np.random.uniform(-10, -2))
        padj = float(pval * np.random.uniform(1.0, 5.0))
        padj = min(padj, 0.049)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": pval,
            "padj": padj,
        })

    # Not significant: GENE_151-200
    for i in range(151, 201):
        lfc = np.random.normal(0, 0.3)
        pval = np.random.uniform(0.1, 1.0)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": round(float(pval), 6),
            "padj": round(float(np.random.uniform(0.1, 1.0)), 6),
        })

    return pd.DataFrame(records)


def get_demo_data() -> tuple[pd.DataFrame, None]:
    """Return synthetic DE results for demonstration purposes."""
    return _generate_demo_de_results(), None


# ---------------------------------------------------------------------------
# Benjamini-Hochberg correction
# ---------------------------------------------------------------------------


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]

    adjusted = np.empty(n, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * n / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)

    result = np.empty(n, dtype=float)
    result[order] = adjusted
    return result


# ---------------------------------------------------------------------------
# Built-in hypergeometric ORA
# ---------------------------------------------------------------------------


def _run_hypergeometric_ora(
    gene_list: list[str],
    gene_sets: dict[str, list[str]],
    background_size: int,
) -> pd.DataFrame:
    """Run over-representation analysis using the hypergeometric test.

    For each pathway, compute the probability of observing at least k
    overlapping genes by chance.

    Parameters
    ----------
    gene_list : list[str]
        Significant genes to test for enrichment.
    gene_sets : dict[str, list[str]]
        Pathway name to gene list mapping.
    background_size : int
        Total number of genes in the background (N).

    Returns
    -------
    pd.DataFrame with columns: term, overlap, term_size, pvalue, padj, genes.
    """
    gene_set_query = set(gene_list)
    n = len(gene_list)
    records: list[dict] = []

    for term, pathway_genes in gene_sets.items():
        pathway_set = set(pathway_genes)
        overlap_genes = gene_set_query & pathway_set
        k = len(overlap_genes)
        K = len(pathway_set)

        # P(X >= k) using hypergeometric survival function
        # sf(k-1, N, K, n) = P(X >= k)
        pval = float(scipy_stats.hypergeom.sf(k - 1, background_size, K, n))

        records.append({
            "term": term,
            "overlap": k,
            "term_size": K,
            "pvalue": pval,
            "genes": ",".join(sorted(overlap_genes)) if overlap_genes else "",
        })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df["padj"] = _benjamini_hochberg(df["pvalue"].values)
    else:
        df["padj"] = pd.Series(dtype=float)
    return df.sort_values("pvalue").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Built-in rank-based GSEA fallback
# ---------------------------------------------------------------------------


def _run_gsea_fallback(
    de_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
) -> pd.DataFrame:
    """Simple rank-based enrichment via permutation testing.

    Ranks genes by log2FC * -log10(pvalue), then for each gene set computes
    the mean rank versus the distribution of mean ranks from random gene sets
    of the same size (100 permutations).

    Parameters
    ----------
    de_df : pd.DataFrame
        DE results with columns: gene, log2FoldChange, pvalue.
    gene_sets : dict[str, list[str]]
        Pathway name to gene list mapping.

    Returns
    -------
    pd.DataFrame with columns: term, es, nes, pvalue, padj, n_genes.
    """
    np.random.seed(42)

    # Compute ranking score: log2FC * -log10(pvalue)
    df = de_df.copy()
    df["rank_score"] = df["log2FoldChange"] * (-np.log10(df["pvalue"].clip(lower=1e-300)))
    df = df.sort_values("rank_score", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(len(df))

    gene_to_rank = dict(zip(df["gene"], df["rank"]))
    n_genes_total = len(df)
    n_perms = 100

    records: list[dict] = []
    for term, pathway_genes in gene_sets.items():
        # Get ranks for genes in this set that are in the DE results
        ranks = [gene_to_rank[g] for g in pathway_genes if g in gene_to_rank]
        n_in_set = len(ranks)
        if n_in_set == 0:
            continue

        observed_mean_rank = float(np.mean(ranks))

        # Permutation test: sample random gene sets of same size
        null_means = np.array([
            float(np.mean(np.random.choice(n_genes_total, size=n_in_set, replace=False)))
            for _ in range(n_perms)
        ])

        null_std = float(np.std(null_means))
        null_mean = float(np.mean(null_means))

        # Enrichment score: negative because lower rank = higher score
        es = null_mean - observed_mean_rank
        nes = es / null_std if null_std > 0 else 0.0

        # Two-sided p-value from permutation
        n_extreme = int(np.sum(np.abs(null_means - null_mean) >= abs(es)))
        pval = (n_extreme + 1) / (n_perms + 1)

        records.append({
            "term": term,
            "es": round(float(es), 4),
            "nes": round(float(nes), 4),
            "pvalue": float(pval),
            "n_genes": n_in_set,
        })

    df_result = pd.DataFrame(records)
    if len(df_result) > 0:
        df_result["padj"] = _benjamini_hochberg(df_result["pvalue"].values)
    else:
        df_result["padj"] = pd.Series(dtype=float)
    return df_result.sort_values("pvalue").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def core_analysis(
    de_df: pd.DataFrame,
    *,
    method: str = "ora",
    gene_sets: dict[str, list[str]] | None = None,
    padj_cutoff: float = 0.05,
    lfc_cutoff: float = 1.0,
) -> dict:
    """Run pathway enrichment analysis on DE results.

    Parameters
    ----------
    de_df : pd.DataFrame
        DE results with columns: gene, log2FoldChange, pvalue, padj.
    method : str
        ``"ora"`` for over-representation analysis, ``"gsea"`` for
        rank-based gene set enrichment.
    gene_sets : dict or None
        Pathway name to gene list mapping. If None, uses built-in demo sets.
    padj_cutoff : float
        Adjusted p-value cutoff for filtering significant genes (ORA).
    lfc_cutoff : float
        Absolute log2FC cutoff for filtering significant genes (ORA).

    Returns
    -------
    dict with keys: n_input_genes, n_significant, method_used,
        n_terms_tested, n_enriched_terms, enrichment_df.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if gene_sets is None:
        gene_sets = _build_demo_gene_sets()
        logger.info("Using built-in demo gene sets (%d pathways).", len(gene_sets))

    n_input = len(de_df)
    method_used = method

    if method == "ora":
        # Filter significant genes
        sig = de_df.dropna(subset=["padj"])
        sig = sig[(sig["padj"] < padj_cutoff) & (sig["log2FoldChange"].abs() > lfc_cutoff)]
        sig_genes = sig["gene"].tolist()
        n_significant = len(sig_genes)
        background_size = n_input

        logger.info(
            "ORA: %d significant genes (padj < %s, |log2FC| > %s) out of %d.",
            n_significant, padj_cutoff, lfc_cutoff, n_input,
        )

        # Try gseapy first, fall back to built-in hypergeometric
        try:
            import gseapy as gp
            logger.info("Using gseapy for ORA (Enrichr).")
            enr = gp.enrichr(
                gene_list=sig_genes,
                gene_sets=gene_sets,
                organism="human",
                outdir=None,
                no_plot=True,
            )
            enrichment_df = enr.results.copy() if hasattr(enr, "results") else enr.res2d.copy()
            col_map = {
                "Term": "term",
                "Adjusted P-value": "padj",
                "P-value": "pvalue",
                "Genes": "genes",
                "Overlap": "overlap",
            }
            enrichment_df = enrichment_df.rename(
                columns={k: v for k, v in col_map.items() if k in enrichment_df.columns}
            )
            if "term_size" not in enrichment_df.columns:
                enrichment_df["term_size"] = enrichment_df.get("overlap", 0)
            method_used = "ora_gseapy"
        except (ImportError, Exception) as exc:
            if isinstance(exc, ImportError):
                logger.info("gseapy not available; using built-in hypergeometric ORA.")
            else:
                logger.warning("gseapy ORA failed (%s); using built-in fallback.", exc)
            enrichment_df = _run_hypergeometric_ora(sig_genes, gene_sets, background_size)
            method_used = "ora_builtin"

    else:  # gsea
        n_significant = 0  # GSEA uses all genes, not pre-filtered
        logger.info("GSEA: ranking %d genes.", n_input)

        # Try gseapy first, fall back to built-in rank-based method
        try:
            import gseapy as gp
            logger.info("Using gseapy for pre-ranked GSEA.")
            rnk = de_df.set_index("gene")["log2FoldChange"].sort_values(ascending=False)
            pre_res = gp.prerank(
                rnk=rnk,
                gene_sets=gene_sets,
                min_size=3,
                max_size=1000,
                permutation_num=100,
                outdir=None,
                seed=42,
                verbose=False,
            )
            enrichment_df = pre_res.res2d.copy()
            enrichment_df = enrichment_df.rename(columns={
                "Term": "term",
                "NES": "nes",
                "NOM p-val": "pvalue",
                "FDR q-val": "padj",
            })
            if "es" not in enrichment_df.columns:
                enrichment_df["es"] = enrichment_df.get("ES", 0.0)
            if "n_genes" not in enrichment_df.columns:
                enrichment_df["n_genes"] = enrichment_df.get("Tag %", "").apply(
                    lambda x: int(str(x).split("/")[0]) if "/" in str(x) else 0
                )
            method_used = "gsea_gseapy"
        except (ImportError, Exception) as exc:
            if isinstance(exc, ImportError):
                logger.info("gseapy not available; using built-in rank-based GSEA.")
            else:
                logger.warning("gseapy GSEA failed (%s); using built-in fallback.", exc)
            enrichment_df = _run_gsea_fallback(de_df, gene_sets)
            method_used = "gsea_builtin"

    # Count enriched terms
    n_enriched = 0
    if not enrichment_df.empty and "padj" in enrichment_df.columns:
        n_enriched = int(enrichment_df["padj"].dropna().lt(padj_cutoff).sum())

    logger.info(
        "Enrichment complete: %d terms tested, %d enriched (padj < %s).",
        len(enrichment_df), n_enriched, padj_cutoff,
    )

    return {
        "n_input_genes": n_input,
        "n_significant": n_significant,
        "method_used": method_used,
        "n_terms_tested": len(enrichment_df),
        "n_enriched_terms": n_enriched,
        "enrichment_df": enrichment_df,
    }


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
    bars = ax.barh(
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
                size_str = f"{overlap}/{t_size}" if t_size else str(overlap)
                body_lines.append(f"| {term} | {size_str} | {r['padj']:.2e} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    # --- result.json ---
    json_summary = {k: v for k, v in summary.items() if k != "enrichment_df"}
    write_result_json(
        output_dir, SKILL_NAME, SKILL_VERSION,
        json_summary, {"params": params, **json_summary},
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
    gene_sets = None
    if args.gene_set_file:
        gs_path = Path(args.gene_set_file)
        if not gs_path.exists():
            print(f"ERROR: Gene set file not found: {gs_path}", file=sys.stderr)
            sys.exit(1)
        with open(gs_path) as f:
            gene_sets = json.load(f)
        logger.info("Loaded %d custom gene sets from %s.", len(gene_sets), gs_path)

    # Run analysis
    summary = core_analysis(
        de_df,
        method=args.method,
        gene_sets=gene_sets,
        padj_cutoff=args.padj_cutoff,
        lfc_cutoff=args.lfc_cutoff,
    )

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

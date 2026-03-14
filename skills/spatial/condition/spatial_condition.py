#!/usr/bin/env python3
"""Spatial Condition — pseudobulk condition comparison.

Usage:
    python spatial_condition.py --input <data.h5ad> --output <dir> \
        --condition-key treatment --sample-key sample_id
    python spatial_condition.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse, stats

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import store_analysis_metadata
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-condition"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Pseudobulk aggregation
# ---------------------------------------------------------------------------


def pseudobulk_aggregate(
    adata,
    *,
    sample_key: str,
    cluster_key: str = "leiden",
) -> dict[str, pd.DataFrame]:
    """Aggregate raw counts to pseudobulk per (sample, cluster).

    Returns dict mapping cluster label -> DataFrame (samples x genes).
    """
    if sample_key not in adata.obs.columns:
        raise ValueError(f"Sample key '{sample_key}' not in adata.obs")
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not in adata.obs")

    X = adata.X
    if sparse.issparse(X):
        X = X.toarray()
    X = np.asarray(X, dtype=np.float64)

    clusters = sorted(adata.obs[cluster_key].unique().tolist(), key=str)
    samples = sorted(adata.obs[sample_key].unique().tolist(), key=str)
    gene_names = list(adata.var_names)

    result: dict[str, pd.DataFrame] = {}
    for cl in clusters:
        rows = []
        row_labels = []
        for samp in samples:
            mask = (adata.obs[cluster_key].values == cl) & (
                adata.obs[sample_key].values == samp
            )
            if mask.sum() == 0:
                continue
            row_labels.append(samp)
            rows.append(X[mask].sum(axis=0))
        if len(rows) >= 2:
            result[str(cl)] = pd.DataFrame(rows, index=row_labels, columns=gene_names)
    return result


# ---------------------------------------------------------------------------
# DE methods: PyDESeq2 (primary), Wilcoxon (alternative, available for explicit use)
# ---------------------------------------------------------------------------


def _run_pydeseq2(
    count_df: pd.DataFrame,
    condition_labels: pd.Series,
    reference: str,
) -> pd.DataFrame:
    """Run PyDESeq2 on pseudobulk counts."""
    from omicsclaw.spatial.dependency_manager import require
    require("pydeseq2", feature="DESeq2-style pseudobulk analysis")
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    metadata = pd.DataFrame({"condition": condition_labels}, index=count_df.index)
    dds = DeseqDataSet(
        counts=count_df.astype(int),
        metadata=metadata,
        design_factors="condition",
        refit_cooks=True,
    )
    dds.deseq2()
    stat = DeseqStats(dds, contrast=["condition", "other", reference])
    stat.summary()
    res = stat.results_df.copy()
    res = res.rename(columns={"log2FoldChange": "log2fc", "padj": "pvalue_adj"})
    res["gene"] = res.index
    return res[["gene", "log2fc", "pvalue_adj"]].reset_index(drop=True)


def _run_wilcoxon_pseudobulk(
    count_df: pd.DataFrame,
    condition_labels: pd.Series,
    reference: str,
) -> pd.DataFrame:
    """Wilcoxon rank-sum on pseudobulk log-CPM values (alternative DEA method)."""
    lib_size = count_df.sum(axis=1)
    lib_size = lib_size.replace(0, 1)
    cpm = count_df.div(lib_size, axis=0) * 1e6
    log_cpm = np.log1p(cpm)

    ref_mask = condition_labels == reference
    other_mask = ~ref_mask

    if ref_mask.sum() < 1 or other_mask.sum() < 1:
        return pd.DataFrame(columns=["gene", "log2fc", "pvalue_adj"])

    ref_vals = log_cpm.loc[ref_mask]
    other_vals = log_cpm.loc[other_mask]

    records = []
    for gene in count_df.columns:
        a = other_vals[gene].values
        b = ref_vals[gene].values
        if np.std(a) < 1e-10 and np.std(b) < 1e-10:
            continue
        try:
            stat, pval = stats.ranksums(a, b)
        except Exception:
            continue
        lfc = float(np.mean(a) - np.mean(b))
        records.append({"gene": gene, "log2fc": lfc, "pvalue_adj": pval})

    df = pd.DataFrame(records)
    if not df.empty:
        from statsmodels.stats.multitest import multipletests
        try:
            _, adj, _, _ = multipletests(df["pvalue_adj"], method="fdr_bh")
            df["pvalue_adj"] = adj
        except Exception:
            pass
        df = df.sort_values("pvalue_adj").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_condition_comparison(
    adata,
    *,
    condition_key: str,
    sample_key: str,
    reference_condition: str | None = None,
    cluster_key: str = "leiden",
) -> dict:
    """Run pseudobulk condition comparison. Returns summary dict."""

    conditions = sorted(adata.obs[condition_key].unique().tolist(), key=str)
    if len(conditions) < 2:
        raise ValueError(
            f"Need >= 2 conditions in '{condition_key}', found {conditions}"
        )

    ref = reference_condition or conditions[0]
    if ref not in conditions:
        raise ValueError(f"Reference '{ref}' not in conditions: {conditions}")

    samples = sorted(adata.obs[sample_key].unique().tolist(), key=str)
    logger.info(
        "Condition comparison: %d conditions (%s), %d samples, ref='%s'",
        len(conditions), conditions, len(samples), ref,
    )

    pb_dict = pseudobulk_aggregate(
        adata, sample_key=sample_key, cluster_key=cluster_key,
    )
    logger.info("Pseudobulk aggregated for %d clusters", len(pb_dict))

    sample_condition = (
        adata.obs[[sample_key, condition_key]]
        .drop_duplicates()
        .set_index(sample_key)[condition_key]
    )

    all_de: dict[str, pd.DataFrame] = {}
    global_de = pd.DataFrame()

    for cl, count_df in pb_dict.items():
        cond_labels = sample_condition.loc[count_df.index]

        gene_sums = count_df.sum(axis=0)
        keep = gene_sums >= 10
        filtered = count_df.loc[:, keep]

        if filtered.shape[1] < 5:
            logger.warning("Cluster %s: too few genes after filtering, skipping", cl)
            continue

        de_df = _run_pydeseq2(filtered, cond_labels, ref)
        de_df["method"] = "pydeseq2"

        de_df["cluster"] = cl
        all_de[cl] = de_df

    if all_de:
        global_de = pd.concat(all_de.values(), ignore_index=True)

    sig_count = int((global_de["pvalue_adj"] < 0.05).sum()) if not global_de.empty else 0

    store_analysis_metadata(
        adata, SKILL_NAME, "pseudobulk",
        params={
            "condition_key": condition_key,
            "sample_key": sample_key,
            "reference_condition": ref,
            "cluster_key": cluster_key,
        },
    )

    return {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "conditions": conditions,
        "reference": ref,
        "n_samples": len(samples),
        "n_clusters_tested": len(all_de),
        "n_de_genes_total": len(global_de),
        "n_significant": sig_count,
        "global_de": global_de,
        "per_cluster_de": all_de,
        "cluster_key": cluster_key,
        "condition_key": condition_key,
        "sample_key": sample_key,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Generate condition comparison figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures: list[str] = []
    de = summary["global_de"]

    if de.empty:
        logger.warning("No DE results to plot")
        return figures

    # Volcano plot
    try:
        plot_df = de.dropna(subset=["log2fc", "pvalue_adj"]).copy()
        if not plot_df.empty:
            lfc = plot_df["log2fc"].values.astype(float)
            pvals = plot_df["pvalue_adj"].values.astype(float)
            pvals = np.clip(pvals, 1e-300, 1.0)
            neg_log_p = -np.log10(pvals)

            sig_mask = (np.abs(lfc) > 1.0) & (pvals < 0.05)

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.scatter(lfc[~sig_mask], neg_log_p[~sig_mask], c="grey", s=6, alpha=0.5, label="NS")
            ax.scatter(lfc[sig_mask], neg_log_p[sig_mask], c="red", s=10, alpha=0.7, label="Significant")
            ax.axhline(-np.log10(0.05), ls="--", c="grey", lw=0.8)
            ax.axvline(-1.0, ls="--", c="grey", lw=0.8)
            ax.axvline(1.0, ls="--", c="grey", lw=0.8)
            ax.set_xlabel("Log2 Fold Change")
            ax.set_ylabel("-log10(adj. p-value)")
            ax.set_title(f"Pseudobulk DE: conditions vs {summary['reference']}")
            ax.legend(fontsize=8)
            fig.tight_layout()
            p = save_figure(fig, output_dir, "pseudobulk_volcano.png")
            figures.append(str(p))
    except Exception as exc:
        logger.warning("Could not generate volcano: %s", exc)

    # Per-cluster significant gene counts
    try:
        cluster_counts = {}
        for cl, cl_df in summary["per_cluster_de"].items():
            if not cl_df.empty:
                cluster_counts[cl] = int((cl_df["pvalue_adj"] < 0.05).sum())
        if cluster_counts:
            clusters = list(cluster_counts.keys())
            counts = [cluster_counts[c] for c in clusters]
            fig, ax = plt.subplots(figsize=(8, max(3, len(clusters) * 0.4)))
            ax.barh(clusters, counts, color="steelblue")
            ax.set_xlabel("# significant DE genes (padj < 0.05)")
            ax.set_ylabel("Cluster")
            ax.set_title("Condition-responsive genes per cluster")
            fig.tight_layout()
            p = save_figure(fig, output_dir, "condition_pca.png")
            figures.append(str(p))
    except Exception as exc:
        logger.warning("Could not generate cluster bar plot: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    header = generate_report_header(
        title="Spatial Condition Comparison Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Condition key": params.get("condition_key", ""),
            "Sample key": params.get("sample_key", ""),
            "Reference": summary.get("reference", ""),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Conditions**: {', '.join(str(c) for c in summary['conditions'])}",
        f"- **Reference condition**: {summary['reference']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Clusters tested**: {summary['n_clusters_tested']}",
        f"- **Total DE entries**: {summary['n_de_genes_total']}",
        f"- **Significant (padj < 0.05)**: {summary['n_significant']}",
    ]

    if summary["n_samples"] < 6:
        body_lines.extend([
            "",
            "⚠️ **Warning**: Fewer than 3 samples per condition detected. "
            "Statistical power is limited; interpret results with caution.",
        ])

    global_de = summary["global_de"]
    if not global_de.empty:
        sig = global_de[global_de["pvalue_adj"] < 0.05].head(20)
        if not sig.empty:
            body_lines.extend(["", "### Top DE Genes (across clusters)\n"])
            body_lines.append("| Gene | Cluster | Log2FC | Adj. p-value | Method |")
            body_lines.append("|------|---------|--------|--------------|--------|")
            for _, r in sig.iterrows():
                body_lines.append(
                    f"| {r['gene']} | {r.get('cluster', '')} "
                    f"| {r['log2fc']:.2f} | {r['pvalue_adj']:.2e} | {r.get('method', '')} |"
                )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    summary_for_json = {
        k: v for k, v in summary.items()
        if k not in ("global_de", "per_cluster_de")
    }
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary_for_json,
        data={"params": params, **summary_for_json},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if not global_de.empty:
        global_de.to_csv(tables_dir / "pseudobulk_de.csv", index=False)

    per_cluster_summary = []
    for cl, cl_df in summary["per_cluster_de"].items():
        n_sig = int((cl_df["pvalue_adj"] < 0.05).sum()) if not cl_df.empty else 0
        per_cluster_summary.append({"cluster": cl, "n_sig_genes": n_sig, "n_tested": len(cl_df)})
    if per_cluster_summary:
        pd.DataFrame(per_cluster_summary).to_csv(
            tables_dir / "per_cluster_summary.csv", index=False,
        )
    logger.info("Wrote tables to %s", tables_dir)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_condition.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data — creates synthetic multi-sample / multi-condition data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate synthetic multi-condition data for demo."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_cond_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)

    n = adata.n_obs
    rng = np.random.default_rng(42)
    adata.obs["condition"] = rng.choice(["treatment", "control"], size=n)
    adata.obs["sample_id"] = [
        f"{c}_s{i}" for c, i in zip(
            adata.obs["condition"],
            rng.integers(1, 4, size=n),
        )
    ]

    logger.info("Demo: %d cells, conditions=%s", n, adata.obs["condition"].unique().tolist())
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Condition — pseudobulk condition comparison",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--condition-key", default="condition")
    parser.add_argument("--sample-key", default="sample_id")
    parser.add_argument("--reference-condition", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    cluster_key = "leiden"
    if cluster_key not in adata.obs.columns:
        logger.info("No '%s' column — running minimal preprocessing", cluster_key)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        n_hvg = min(2000, adata.n_vars - 1)
        sc.pp.highly_variable_genes(adata, n_top_genes=max(n_hvg, 2), flavor="seurat")
        adata_hvg = adata[:, adata.var["highly_variable"]].copy()
        sc.pp.scale(adata_hvg, max_value=10)
        n_comps = min(50, adata_hvg.n_vars - 1, adata_hvg.n_obs - 1)
        sc.tl.pca(adata_hvg, n_comps=n_comps)
        adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
        sc.pp.neighbors(adata, n_neighbors=15, n_pcs=min(n_comps, 30))
        sc.tl.leiden(adata, resolution=1.0, flavor="igraph")

    params = {
        "condition_key": args.condition_key,
        "sample_key": args.sample_key,
        "reference_condition": args.reference_condition,
    }

    summary = run_condition_comparison(
        adata,
        condition_key=args.condition_key,
        sample_key=args.sample_key,
        reference_condition=args.reference_condition,
        cluster_key=cluster_key,
    )

    generate_figures(output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Condition comparison complete: {summary['n_clusters_tested']} clusters tested, "
        f"{summary['n_significant']} significant DE genes"
    )


if __name__ == "__main__":
    main()

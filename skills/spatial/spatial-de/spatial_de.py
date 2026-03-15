#!/usr/bin/env python3
"""Spatial DE — differential expression and marker gene discovery.

Supported methods:
  - wilcoxon:  Wilcoxon rank-sum test via Scanpy (default, non-parametric)
  - t-test:    Welch's t-test via Scanpy (parametric, fast)
  - pydeseq2:  Pseudobulk DE via PyDESeq2 (negative binomial GLM, gold standard)

Usage:
    python spatial_de.py --input <processed.h5ad> --output <dir>
    python spatial_de.py --input <data.h5ad> --output <dir> --group1 0 --group2 1
    python spatial_de.py --input <file> --method pydeseq2 --group1 0 --group2 1 --output <dir>
    python spatial_de.py --demo --output <dir>
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
from omicsclaw.spatial.adata_utils import (
    require_preprocessed,
    store_analysis_metadata,
)
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-de"
SKILL_VERSION = "0.2.0"

SUPPORTED_METHODS = ("wilcoxon", "t-test", "pydeseq2")




# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def run_de(
    adata,
    *,
    groupby: str = "leiden",
    method: str = "wilcoxon",
    n_top_genes: int = 10,
    group1: str | None = None,
    group2: str | None = None,
) -> dict:
    """Run differential expression analysis. Returns a summary dict."""

    if groupby not in adata.obs.columns:
        raise ValueError(
            f"Groupby column '{groupby}' not found in adata.obs. "
            f"Available columns: {list(adata.obs.columns)}"
        )

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    n_groups = adata.obs[groupby].nunique()
    groups_list = sorted(adata.obs[groupby].unique().tolist(), key=str)
    logger.info(
        "Input: %d cells x %d genes, %d groups in '%s'",
        n_cells, n_genes, n_groups, groupby,
    )

    if n_groups < 2:
        raise ValueError(
            f"Need at least 2 groups for DE, found {n_groups} in '{groupby}'."
        )

    two_group = group1 is not None and group2 is not None

    if two_group:
        for label, grp in [("group1", group1), ("group2", group2)]:
            if str(grp) not in [str(g) for g in groups_list]:
                raise ValueError(
                    f"--{label} '{grp}' not found in '{groupby}'. "
                    f"Available groups: {groups_list}"
                )
        logger.info("Two-group comparison: %s vs %s (reference)", group1, group2)
        sc.tl.rank_genes_groups(
            adata,
            groupby=groupby,
            groups=[group1],
            reference=group2,
            method=method,
            n_genes=n_top_genes,
        )
    else:
        logger.info("Cluster-vs-rest marker discovery (%s)", method)
        sc.tl.rank_genes_groups(
            adata,
            groupby=groupby,
            method=method,
            n_genes=n_top_genes,
        )

    # scanpy >= 1.10 dropped the 'group' column from rank_genes_groups_df when
    # group=None; iterate per group and add the label manually instead.
    tested_groups = list(adata.uns["rank_genes_groups"]["names"].dtype.names)
    group_dfs = []
    for grp in tested_groups:
        grp_df = sc.get.rank_genes_groups_df(adata, group=grp)
        grp_df.insert(0, "group", grp)
        group_dfs.append(grp_df)
    markers_df = pd.concat(group_dfs, ignore_index=True) if group_dfs else pd.DataFrame()

    if markers_df.empty:
        logger.warning("No DE genes found — results will be empty")

    full_df = markers_df.copy()
    top_df = (
        markers_df
        .groupby("group", sort=False)
        .head(n_top_genes)
        .reset_index(drop=True)
    )

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        method,
        params={
            "groupby": groupby,
            "method": method,
            "n_top_genes": n_top_genes,
            "group1": group1,
            "group2": group2,
            "two_group": two_group,
        },
    )

    return {
        "n_cells": n_cells,
        "n_genes": n_genes,
        "n_groups": n_groups,
        "groups": groups_list,
        "groupby": groupby,
        "method": method,
        "n_top_genes": n_top_genes,
        "two_group": two_group,
        "group1": group1,
        "group2": group2,
        "n_de_genes": len(markers_df),
        "markers_df": top_df,
        "full_df": full_df,
    }


# ---------------------------------------------------------------------------
# PyDESeq2 pseudobulk DE
# ---------------------------------------------------------------------------


def _get_raw_counts(adata) -> np.ndarray:
    """Extract raw integer counts, preferring adata.raw or adata.layers['counts']."""
    if "counts" in adata.layers:
        X = adata.layers["counts"]
    elif adata.raw is not None:
        X = adata.raw.X
    else:
        X = adata.X

    from scipy import sparse
    if sparse.issparse(X):
        X = X.toarray()
    X = np.asarray(X)

    if np.any(X < 0):
        raise ValueError("PyDESeq2 requires non-negative counts. Found negative values.")

    if X.dtype.kind == "f" and np.allclose(X, np.round(X)):
        X = np.round(X).astype(int)
    elif X.dtype.kind == "f":
        logger.warning(
            "Non-integer counts detected (max=%.2f). Rounding to integers for PyDESeq2.",
            X.max(),
        )
        X = np.round(X).astype(int)

    return X


def run_pydeseq2(
    adata,
    *,
    groupby: str = "leiden",
    group1: str,
    group2: str,
    n_top_genes: int = 10,
    min_cells_per_sample: int = 10,
) -> dict:
    """Run pseudobulk differential expression using PyDESeq2.

    Aggregates single-cell counts into pseudobulk samples per spatial domain,
    then applies the DESeq2 negative binomial GLM for robust DE testing.
    PyDESeq2 is a pure-Python implementation of the DESeq2 framework.
    """
    from omicsclaw.spatial.dependency_manager import require

    require("pydeseq2", feature="PyDESeq2 pseudobulk differential expression")

    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    if groupby not in adata.obs.columns:
        raise ValueError(f"Groupby column '{groupby}' not found in adata.obs")

    groups_list = sorted(adata.obs[groupby].unique().tolist(), key=str)
    for label, grp in [("group1", group1), ("group2", group2)]:
        if str(grp) not in [str(g) for g in groups_list]:
            raise ValueError(
                f"--{label} '{grp}' not found in '{groupby}'. Available: {groups_list}"
            )

    raw_counts = _get_raw_counts(adata)
    logger.info("Aggregating pseudobulk samples for PyDESeq2 ...")

    mask = adata.obs[groupby].isin([str(group1), str(group2)])
    adata_sub = adata[mask].copy()
    raw_sub = raw_counts[mask.values]

    group_labels = adata_sub.obs[groupby].astype(str).values
    unique_groups = [str(group1), str(group2)]

    sample_ids = []
    sample_conditions = []
    pseudobulk_counts = []

    for grp in unique_groups:
        grp_mask = group_labels == str(grp)
        grp_counts = raw_sub[grp_mask]

        n_cells_in_group = grp_counts.shape[0]
        n_samples = max(1, n_cells_in_group // min_cells_per_sample)
        n_samples = min(n_samples, 10)

        indices = np.arange(n_cells_in_group)
        rng = np.random.RandomState(42)
        rng.shuffle(indices)

        splits = np.array_split(indices, n_samples)
        for i, split_idx in enumerate(splits):
            if len(split_idx) < 3:
                continue
            pseudo_sample = grp_counts[split_idx].sum(axis=0)
            pseudobulk_counts.append(pseudo_sample)
            sample_ids.append(f"{grp}_rep{i}")
            sample_conditions.append(str(grp))

    if len(sample_ids) < 4:
        raise ValueError(
            f"Insufficient pseudobulk samples ({len(sample_ids)}). "
            f"Need at least 2 samples per group. Try a dataset with more cells."
        )

    counts_matrix = np.vstack(pseudobulk_counts)
    counts_df = pd.DataFrame(
        counts_matrix,
        index=sample_ids,
        columns=adata_sub.var_names,
    )
    metadata = pd.DataFrame(
        {"condition": sample_conditions},
        index=sample_ids,
    )

    gene_sums = counts_df.sum(axis=0)
    keep_genes = gene_sums > 10
    counts_df = counts_df.loc[:, keep_genes]

    logger.info(
        "PyDESeq2: %d pseudobulk samples, %d genes after filtering",
        len(sample_ids), counts_df.shape[1],
    )

    dds = DeseqDataSet(
        counts=counts_df,
        metadata=metadata,
        design_factors="condition",
        refit_cooks=True,
    )
    dds.deseq2()

    stat_res = DeseqStats(dds, contrast=["condition", str(group1), str(group2)])
    stat_res.summary()

    results_df = stat_res.results_df.copy()
    results_df["gene"] = results_df.index
    results_df = results_df.rename(columns={
        "log2FoldChange": "logfoldchanges",
        "pvalue": "pvals",
        "padj": "pvals_adj",
        "baseMean": "scores",
    })

    results_df["names"] = results_df["gene"]
    results_df["group"] = str(group1)
    results_df = results_df.sort_values("pvals_adj", na_position="last")

    top_df = results_df.head(n_top_genes).copy()
    full_df = results_df.copy()

    n_sig = (results_df["pvals_adj"].dropna() < 0.05).sum()

    logger.info(
        "PyDESeq2: %d significant DE genes (padj < 0.05) out of %d tested",
        n_sig, len(results_df),
    )

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        "pydeseq2",
        params={
            "groupby": groupby,
            "method": "pydeseq2",
            "group1": group1,
            "group2": group2,
            "n_pseudobulk_samples": len(sample_ids),
            "n_genes_tested": len(results_df),
        },
    )

    return {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "n_groups": len(unique_groups),
        "groups": unique_groups,
        "groupby": groupby,
        "method": "pydeseq2",
        "n_top_genes": n_top_genes,
        "two_group": True,
        "group1": group1,
        "group2": group2,
        "n_de_genes": len(results_df),
        "n_significant": n_sig,
        "n_pseudobulk_samples": len(sample_ids),
        "markers_df": top_df,
        "full_df": full_df,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict,
) -> list[str]:
    """Generate DE-related figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures: list[str] = []

    # Dot plot of top markers per cluster
    try:
        n_show = min(5, summary["n_top_genes"])
        sc.pl.rank_genes_groups_dotplot(
            adata,
            n_genes=n_show,
            show=False,
        )
        fig = plt.gcf()
        p = save_figure(fig, output_dir, "marker_dotplot.png")
        figures.append(str(p))
    except Exception as exc:
        logger.warning("Scanpy dotplot failed (%s), falling back to heatmap", exc)
        try:
            top_df = summary["markers_df"]
            top_genes = top_df["names"].unique()[:20]
            if len(top_genes) > 0:
                fig, ax = plt.subplots(figsize=(10, max(4, len(top_genes) * 0.3)))
                sub = adata[:, [g for g in top_genes if g in adata.var_names]]
                if hasattr(sub.X, "toarray"):
                    mat = sub.X.toarray()
                else:
                    mat = np.asarray(sub.X)
                ax.imshow(mat.T, aspect="auto", cmap="viridis")
                ax.set_yticks(range(len(sub.var_names)))
                ax.set_yticklabels(sub.var_names, fontsize=7)
                ax.set_xlabel("Cells")
                ax.set_title("Top marker gene expression")
                fig.tight_layout()
                p = save_figure(fig, output_dir, "marker_dotplot.png")
                figures.append(str(p))
        except Exception as inner_exc:
            logger.warning("Fallback heatmap also failed: %s", inner_exc)

    # Volcano plot for two-group comparison
    if summary["two_group"]:
        try:
            df = summary["full_df"]
            if "logfoldchanges" in df.columns and "pvals_adj" in df.columns:
                fig, ax = plt.subplots(figsize=(8, 6))

                lfc = df["logfoldchanges"].values.astype(float)
                pvals = df["pvals_adj"].values.astype(float)
                pvals = np.clip(pvals, 1e-300, 1.0)
                neg_log_p = -np.log10(pvals)

                sig_mask = (np.abs(lfc) > 1.0) & (pvals < 0.05)
                ax.scatter(
                    lfc[~sig_mask], neg_log_p[~sig_mask],
                    c="grey", s=8, alpha=0.5, label="NS",
                )
                ax.scatter(
                    lfc[sig_mask], neg_log_p[sig_mask],
                    c="red", s=12, alpha=0.7, label="Significant",
                )
                ax.axhline(-np.log10(0.05), ls="--", c="grey", lw=0.8)
                ax.axvline(-1.0, ls="--", c="grey", lw=0.8)
                ax.axvline(1.0, ls="--", c="grey", lw=0.8)
                ax.set_xlabel("Log2 Fold Change")
                ax.set_ylabel("-log10(adj. p-value)")
                ax.set_title(
                    f"Volcano: {summary['group1']} vs {summary['group2']}"
                )
                ax.legend(loc="upper right", fontsize=8)
                fig.tight_layout()
                p = save_figure(fig, output_dir, "de_volcano.png")
                figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate volcano plot: %s", exc)

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
        title="Spatial Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": params.get("method", "wilcoxon"),
            "Groupby": params.get("groupby", "leiden"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Groups in `{summary['groupby']}`**: {summary['n_groups']}",
        f"- **Method**: {summary['method']}",
        f"- **Top genes per group**: {summary['n_top_genes']}",
    ]

    if summary["two_group"]:
        body_lines.extend([
            "",
            f"### Two-group comparison: {summary['group1']} vs {summary['group2']}\n",
            f"- DE genes tested: {summary['n_de_genes']}",
        ])
    else:
        body_lines.extend([
            "",
            "### Cluster-vs-rest markers\n",
            f"- Total marker entries: {summary['n_de_genes']}",
        ])

    markers_df = summary["markers_df"]
    if not markers_df.empty:
        body_lines.extend(["", "### Top markers per group\n"])
        for grp in summary["groups"][:10]:
            grp_df = markers_df[markers_df["group"] == str(grp)].head(5)
            if grp_df.empty:
                continue
            body_lines.append(f"\n**Group {grp}**:\n")
            body_lines.append("| Gene | Score | Log2FC | Adj. p-value |")
            body_lines.append("|------|-------|--------|--------------|")
            for _, row in grp_df.iterrows():
                body_lines.append(
                    f"| {row['names']} | {row['scores']:.2f} "
                    f"| {row['logfoldchanges']:.2f} | {row['pvals_adj']:.2e} |"
                )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json — exclude large DataFrames
    summary_for_json = {
        k: v for k, v in summary.items()
        if k not in ("markers_df", "full_df")
    }
    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).exists()
        else ""
    )
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_for_json,
        data={"params": params, **summary_for_json},
        input_checksum=checksum,
    )

    # tables/
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    markers_df.to_csv(tables_dir / "markers_top.csv", index=False)
    logger.info("Wrote %s", tables_dir / "markers_top.csv")

    full_df = summary.get("full_df")
    if full_df is not None and not full_df.empty:
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        logger.info("Wrote %s", tables_dir / "de_full.csv")

    # reproducibility/
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_de.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data via spatial-preprocess
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and load the resulting processed.h5ad."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(
            f"spatial-preprocess script not found at {preprocess_script}. "
            "Cannot run demo mode."
        )

    with tempfile.TemporaryDirectory(prefix="spatial_de_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)

        result = subprocess.run(
            [
                sys.executable,
                str(preprocess_script),
                "--demo",
                "--output", str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

        processed_path = tmp_path / "processed.h5ad"
        if not processed_path.exists():
            raise FileNotFoundError(
                f"Expected {processed_path} from spatial-preprocess --demo, "
                "but it was not created."
            )

        adata = sc.read_h5ad(processed_path)
        logger.info(
            "Loaded demo data: %d cells x %d genes", adata.n_obs, adata.n_vars,
        )
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial DE — differential expression and marker gene discovery",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default="leiden")
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    parser.add_argument(
        "--method", default="wilcoxon", choices=list(SUPPORTED_METHODS),
        help=f"DE method (default: wilcoxon). Options: {', '.join(SUPPORTED_METHODS)}",
    )
    parser.add_argument("--n-top-genes", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
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

    if args.groupby not in adata.obs.columns:
        raise ValueError(
            f"'--groupby {args.groupby}' not found in adata.obs.\n"
            f"Available columns: {list(adata.obs.columns)}\n"
            "Run spatial-preprocess first to compute clusters, or specify --groupby <column>."
        )

    params = {
        "groupby": args.groupby,
        "method": args.method,
        "n_top_genes": args.n_top_genes,
        "group1": args.group1,
        "group2": args.group2,
    }

    if args.method == "pydeseq2":
        if args.group1 is None or args.group2 is None:
            groups_available = sorted(adata.obs[args.groupby].unique().tolist(), key=str)
            if len(groups_available) >= 2:
                args.group1 = str(groups_available[0])
                args.group2 = str(groups_available[1])
                logger.info(
                    "PyDESeq2 requires two groups; auto-selected: %s vs %s",
                    args.group1, args.group2,
                )
            else:
                print("ERROR: PyDESeq2 requires --group1 and --group2", file=sys.stderr)
                sys.exit(1)
        summary = run_pydeseq2(
            adata,
            groupby=args.groupby,
            group1=args.group1,
            group2=args.group2,
            n_top_genes=args.n_top_genes,
        )
    else:
        summary = run_de(
            adata,
            groupby=args.groupby,
            method=args.method,
            n_top_genes=args.n_top_genes,
            group1=args.group1,
            group2=args.group2,
        )

    # Generate outputs
    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    # Save processed h5ad
    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    n_sig = summary["n_de_genes"]
    mode = (
        f"{summary['group1']} vs {summary['group2']}"
        if summary["two_group"]
        else "cluster-vs-rest"
    )
    print(f"DE complete: {n_sig} marker entries ({mode}, {summary['method']})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Spatial DE — differential expression and marker gene discovery.

Supported methods:
  - wilcoxon:  Wilcoxon rank-sum test via Scanpy (default)
  - t-test:    Welch's t-test via Scanpy
  - pydeseq2:  Pseudobulk DE via PyDESeq2

Usage:
    python spatial_de.py --input <processed.h5ad> --output <dir>
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
    generate_report_footer, generate_report_header, write_result_json,
)
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.de import SUPPORTED_METHODS, run_de, run_pydeseq2
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-de"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures: list[str] = []

    # Dot plot
    try:
        n_show = min(5, summary["n_top_genes"])
        sc.pl.rank_genes_groups_dotplot(adata, n_genes=n_show, show=False)
        p = save_figure(plt.gcf(), output_dir, "marker_dotplot.png")
        figures.append(str(p))
        plt.close("all")
    except Exception as exc:
        logger.warning("Dotplot failed: %s", exc)
        try:
            top_df = summary["markers_df"]
            top_genes = top_df["names"].unique()[:20]
            if len(top_genes) > 0:
                fig, ax = plt.subplots(figsize=(10, max(4, int(len(top_genes) * 0.3))))
                sub = adata[:, [g for g in top_genes if g in adata.var_names]]
                mat = sub.X.toarray() if hasattr(sub.X, "toarray") else np.asarray(sub.X)
                ax.imshow(mat.T, aspect="auto", cmap="viridis")
                ax.set_yticks(range(len(sub.var_names)))
                ax.set_yticklabels(sub.var_names, fontsize=7)
                ax.set_xlabel("Cells"); ax.set_title("Top marker gene expression")
                fig.tight_layout()
                p = save_figure(fig, output_dir, "marker_dotplot.png")
                figures.append(str(p))
                plt.close("all")
        except Exception:
            pass

    # Volcano plot
    if summary.get("two_group"):
        try:
            df = summary["full_df"]
            if "logfoldchanges" in df.columns and "pvals_adj" in df.columns:
                fig, ax = plt.subplots(figsize=(8, 6))
                lfc = df["logfoldchanges"].values.astype(float)
                pvals = np.clip(df["pvals_adj"].values.astype(float), 1e-300, 1.0)
                neg_log_p = -np.log10(pvals)
                sig_mask = (np.abs(lfc) > 1.0) & (pvals < 0.05)
                ax.scatter(lfc[~sig_mask], neg_log_p[~sig_mask], c="grey", s=8, alpha=0.5, label="NS")
                ax.scatter(lfc[sig_mask], neg_log_p[sig_mask], c="red", s=12, alpha=0.7, label="Significant")
                ax.axhline(-np.log10(0.05), ls="--", c="grey", lw=0.8)
                ax.axvline(-1.0, ls="--", c="grey", lw=0.8)
                ax.axvline(1.0, ls="--", c="grey", lw=0.8)
                ax.set_xlabel("Log2 Fold Change"); ax.set_ylabel("-log10(adj. p-value)")
                ax.set_title(f"Volcano: {summary['group1']} vs {summary['group2']}")
                ax.legend(loc="upper right", fontsize=8); fig.tight_layout()
                p = save_figure(fig, output_dir, "de_volcano.png")
                figures.append(str(p))
                plt.close("all")
        except Exception as exc:
            logger.warning("Volcano plot failed: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Spatial Differential Expression Report", skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": params.get("method", "wilcoxon"), "Groupby": params.get("groupby", "leiden")},
    )

    body_lines = ["## Summary\n",
        f"- **Cells**: {summary['n_cells']}", f"- **Genes**: {summary['n_genes']}",
        f"- **Groups in `{summary['groupby']}`**: {summary['n_groups']}",
        f"- **Method**: {summary['method']}", f"- **Top genes per group**: {summary['n_top_genes']}"]

    if summary["two_group"]:
        body_lines.extend(["", f"### Two-group comparison: {summary['group1']} vs {summary['group2']}\n",
                           f"- DE genes tested: {summary['n_de_genes']}"])
    else:
        body_lines.extend(["", "### Cluster-vs-rest markers\n", f"- Total marker entries: {summary['n_de_genes']}"])

    markers_df = summary["markers_df"]
    if not markers_df.empty:
        body_lines.extend(["", "### Top markers per group\n"])
        for grp in summary["groups"][:10]:
            grp_df = markers_df[markers_df["group"] == str(grp)].head(5)
            if grp_df.empty:
                continue
            body_lines.append(f"\n**Group {grp}**:\n")
            body_lines.extend(["| Gene | Score | Log2FC | Adj. p-value |", "|------|-------|--------|--------------|"])
            for _, row in grp_df.iterrows():
                body_lines.append(f"| {row['names']} | {row['scores']:.2f} | {row['logfoldchanges']:.2f} | {row['pvals_adj']:.2e} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    summary_for_json = {k: v for k, v in summary.items() if k not in ("markers_df", "full_df")}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary_for_json, data={"params": params, **summary_for_json}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    markers_df.to_csv(tables_dir / "markers_top.csv", index=False)
    full_df = summary.get("full_df")
    if full_df is not None and not full_df.empty:
        full_df.to_csv(tables_dir / "de_full.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_de.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data():
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="spatial_de_demo_") as tmp_dir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_dir)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        adata = sc.read_h5ad(Path(tmp_dir) / "processed.h5ad")
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial DE — differential expression")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default="leiden")
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    parser.add_argument("--method", default="wilcoxon", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--n-top-genes", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr); sys.exit(1)

    params = {"groupby": args.groupby, "method": args.method, "n_top_genes": args.n_top_genes,
              "group1": args.group1, "group2": args.group2}

    if args.method == "pydeseq2":
        if args.group1 is None or args.group2 is None:
            groups = sorted(adata.obs[args.groupby].unique().tolist(), key=str)
            if len(groups) >= 2:
                args.group1, args.group2 = str(groups[0]), str(groups[1])
            else:
                print("ERROR: PyDESeq2 requires --group1 and --group2", file=sys.stderr); sys.exit(1)
        summary = run_pydeseq2(adata, groupby=args.groupby, group1=args.group1, group2=args.group2, n_top_genes=args.n_top_genes)
    else:
        summary = run_de(adata, groupby=args.groupby, method=args.method, n_top_genes=args.n_top_genes,
                         group1=args.group1, group2=args.group2)

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)
    store_analysis_metadata(adata, SKILL_NAME, args.method, params=params)

    adata.write_h5ad(output_dir / "processed.h5ad")
    mode = f"{summary['group1']} vs {summary['group2']}" if summary.get("two_group") else "cluster-vs-rest"
    print(f"DE complete: {summary['n_de_genes']} marker entries ({mode}, {summary['method']})")


if __name__ == "__main__":
    main()

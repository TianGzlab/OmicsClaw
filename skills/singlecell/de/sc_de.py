#!/usr/bin/env python3
"""Single-Cell Differential Expression - Wilcoxon, t-test, MAST, DESeq2.

Usage:
    python sc_de.py --input <data.h5ad> --output <dir> --groupby leiden
    python sc_de.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import scanpy as sc
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.adata_utils import store_analysis_metadata
from omicsclaw.singlecell.viz_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-de"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("wilcoxon", "t-test", "mast", "deseq2")


def run_de(adata, groupby="leiden", method="wilcoxon", group1=None, group2=None):
    """Run differential expression."""
    logger.info(f"Running DE: method={method}, groupby={groupby}")

    if groupby not in adata.obs.columns:
        raise ValueError(f"Column '{groupby}' not found in adata.obs")

    if group1 and group2:
        sc.tl.rank_genes_groups(
            adata, groupby=groupby, groups=[group1],
            reference=group2, method=method, pts=True,
        )
        logger.info(f"Pairwise DE: {group1} vs {group2}")
    else:
        sc.tl.rank_genes_groups(
            adata, groupby=groupby, method=method, pts=True,
        )
        logger.info(f"Cluster-vs-rest DE: {len(adata.obs[groupby].unique())} groups")

    result_df = sc.get.rank_genes_groups_df(adata, group=None)
    n_groups = len(result_df['group'].unique()) if 'group' in result_df.columns else 0

    return {
        "method": method,
        "n_groups": n_groups,
        "n_genes_tested": int(adata.n_vars),
    }


def generate_figures(adata, output_dir: Path, n_top_genes=5) -> list[str]:
    """Generate DE figures."""
    figures = []

    try:
        sc.pl.rank_genes_groups_dotplot(adata, n_genes=n_top_genes, show=False)
        p = save_figure(plt.gcf(), output_dir, "marker_dotplot.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"Dotplot failed: {e}")

    try:
        sc.pl.rank_genes_groups(adata, n_genes=n_top_genes, show=False)
        p = save_figure(plt.gcf(), output_dir, "rank_genes_groups.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"Rank genes plot failed: {e}")

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report."""
    header = generate_report_header(
        title="Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary['method'],
            "Groups": str(summary['n_groups']),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Groups compared**: {summary['n_groups']}",
        f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_de.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Differential Expression")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default="louvain")
    parser.add_argument("--method", default="wilcoxon", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--n-top-genes", type=int, default=10)
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = sc.datasets.pbmc3k_processed()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    summary = run_de(adata, args.groupby, args.method, args.group1, args.group2)
    summary['n_cells'] = int(adata.n_obs)

    # Extract and save markers
    full_df = sc.get.rank_genes_groups_df(adata, group=None)
    top_df = full_df.groupby("group").head(args.n_top_genes)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    full_df.to_csv(tables_dir / "de_full.csv", index=False)
    top_df.to_csv(tables_dir / "markers_top.csv", index=False)

    params = {
        "groupby": args.groupby,
        "method": args.method,
        "n_top_genes": args.n_top_genes,
    }
    if args.group1:
        params["group1"] = args.group1
    if args.group2:
        params["group2"] = args.group2

    generate_figures(adata, output_dir, min(5, args.n_top_genes))
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved to {output_h5ad}")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    store_analysis_metadata(adata, SKILL_NAME, args.method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"DE complete: {summary['n_groups']} groups, method={args.method}")


if __name__ == "__main__":
    main()

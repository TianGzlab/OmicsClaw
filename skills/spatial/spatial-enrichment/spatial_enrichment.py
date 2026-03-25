#!/usr/bin/env python3
"""Spatial Enrichment — pathway and gene set enrichment analysis.

Usage:
    python spatial_enrichment.py --input <preprocessed.h5ad> --output <dir>
    python spatial_enrichment.py --input <data.h5ad> --output <dir> --method gsea
    python spatial_enrichment.py --demo --output <dir>
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
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.enrichment import run_enrichment, SUPPORTED_METHODS
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_enrichment

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-enrichment"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate pathway enrichment figures using the SpatialClaw viz library."""
    figures: list[str] = []

    # 1. Barplot of top enriched pathways
    if "enrichment_results" in adata.uns or any(
        k in adata.uns for k in ("gsea_results", "enrichr_results", "ora_results")
    ):
        try:
            fig = plot_enrichment(adata, VizParams(), subtype="barplot", top_n=20)
            p = save_figure(fig, output_dir, "enrichment_barplot.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate enrichment barplot: %s", exc)

        try:
            fig = plot_enrichment(adata, VizParams(), subtype="dotplot", top_n=20)
            p = save_figure(fig, output_dir, "enrichment_dotplot.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate enrichment dotplot: %s", exc)

    # 2. Spatial enrichment score maps
    score_cols = [
        c for c in adata.obs.columns
        if any(tok in c.lower() for tok in ("score", "enrichment", "ssgsea"))
        and adata.obs[c].dtype.kind in ("f", "i")
    ]
    if score_cols and "spatial" in adata.obsm:
        try:
            fig = plot_enrichment(adata, VizParams(), subtype="spatial", top_n=6)
            p = save_figure(fig, output_dir, "enrichment_spatial.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate spatial enrichment map: %s", exc)

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
        title="Spatial Pathway Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "ora"),
            "Source": summary.get("source", "builtin"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Clusters**: {summary['n_clusters']}",
        f"- **Method**: {summary['method']}",
        f"- **Terms tested**: {summary['n_terms_tested']}",
        f"- **Significant (padj < 0.05)**: {summary['n_significant']}",
    ]

    enrich_df = summary["enrich_df"]
    if not enrich_df.empty:
        sig = enrich_df[enrich_df["pvalue_adj"] < 0.05].head(15)
        if not sig.empty:
            body_lines.extend(["", "### Top Enriched Terms\n"])
            body_lines.append("| Cluster | Gene Set | Overlap | Adj. p-value |")
            body_lines.append("|---------|----------|---------|--------------|")
            for _, r in sig.iterrows():
                gs = str(r.get("gene_set", ""))
                ol = str(r.get("overlap", ""))
                body_lines.append(
                    f"| {r.get('cluster', '')} | {gs} | {ol} | {r['pvalue_adj']:.2e} |"
                )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    summary_for_json = {k: v for k, v in summary.items() if k != "enrich_df"}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary_for_json,
        data={"params": params, **summary_for_json},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if not enrich_df.empty:
        enrich_df.to_csv(tables_dir / "enrichment_results.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    
    cmd_parts: list[str] = [f"python spatial_enrichment.py --input <input.h5ad> --output {output_dir}"]
    for k, v in params.items():
        if v is not None:
            cmd_parts.append(f"--{str(k).replace('_', '-')} {v}")
    
    cmd_str = " ".join(cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd_str}\n")

    try:
        from importlib.metadata import version as _ver
    except ImportError:
        from importlib_metadata import version as _ver  # type: ignore
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and load the resulting processed.h5ad."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_enrich_demo_") as tmp_dir:
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
        logger.info("Loaded demo: %d cells x %d genes", adata.n_obs, adata.n_vars)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Enrichment — pathway and gene set enrichment analysis",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="enrichr", choices=["enrichr", "gsea", "ssgsea"],
    )
    parser.add_argument("--gene-set", default=None, help="Custom gene set name")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument(
        "--source", default="GO_Biological_Process",
        help="Gene set database key (default: GO_Biological_Process)",
    )
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

    params = {
        "method": args.method,
        "gene_set": args.gene_set,
        "species": args.species,
        "source": args.source,
    }

    summary = run_enrichment(
        adata,
        method=args.method,
        source=args.source,
        species=args.species,
        gene_set=args.gene_set,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Enrichment complete ({summary['method']}): "
        f"{summary['n_terms_tested']} terms tested, {summary['n_significant']} significant"
    )


if __name__ == "__main__":
    main()

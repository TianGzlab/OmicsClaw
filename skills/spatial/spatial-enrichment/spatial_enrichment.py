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
from omicsclaw.spatial.adata_utils import store_analysis_metadata
from omicsclaw.spatial.dependency_manager import require
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_enrichment

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-enrichment"
SKILL_VERSION = "0.2.0"

# Preferred library versions — fall through to next candidate if unavailable
_GENESET_LIBRARY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "GO_Biological_Process": ("GO_Biological_Process_2025", "GO_Biological_Process_2023"),
    "GO_Molecular_Function": ("GO_Molecular_Function_2025", "GO_Molecular_Function_2023"),
    "GO_Cellular_Component": ("GO_Cellular_Component_2025", "GO_Cellular_Component_2023"),
    "KEGG_Pathways":         ("KEGG_2021_Human",),
    "Reactome_Pathways":     ("Reactome_Pathways_2024", "Reactome_2022"),
    "MSigDB_Hallmark":       ("MSigDB_Hallmark_2020",),
}


def _resolve_library(key: str, organism: str = "human") -> dict:
    """Load first available library variant from gseapy."""
    import gseapy as gp
    if key in _GENESET_LIBRARY_CANDIDATES:
        last_err: Exception = Exception("Not found")
        for lib in _GENESET_LIBRARY_CANDIDATES[key]:
            try:
                return gp.get_library(lib, organism=organism)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Could not load gene set '{key}': {last_err}") from last_err
    return gp.get_library(key, organism=organism)


# ---------------------------------------------------------------------------
# Core methods (all require gseapy)
# ---------------------------------------------------------------------------


def _run_enrichr(
    adata,
    *,
    groupby: str = "leiden",
    source: str = "GO_Biological_Process",
    species: str = "human",
    n_top_genes: int = 100,
) -> pd.DataFrame:
    """Run per-cluster Enrichr via gseapy."""
    require("gseapy", feature="pathway enrichment (Enrichr)")
    import gseapy as gp

    sc.tl.rank_genes_groups(adata, groupby=groupby, method="wilcoxon", n_genes=n_top_genes)
    markers_df = sc.get.rank_genes_groups_df(adata, group=None)

    # Resolve versioned library name through fallback system
    candidates = _GENESET_LIBRARY_CANDIDATES.get(source, (source,))
    lib_name = candidates[0]

    all_records = []
    for grp in sorted(markers_df["group"].unique().tolist(), key=str):
        gene_list = markers_df[markers_df["group"] == grp].head(n_top_genes)["names"].tolist()
        if not gene_list:
            continue
        try:
            enr = gp.enrichr(
                gene_list=gene_list,
                gene_sets=lib_name,
                organism=species,
                outdir=None,
                no_plot=True,
            )
            res = enr.results.copy() if hasattr(enr, 'results') else enr.res2d.copy()
            res["cluster"] = str(grp)
            all_records.append(res)
        except Exception as exc:
            logger.warning("Enrichr failed for cluster %s: %s", grp, exc)

    if all_records:
        df = pd.concat(all_records, ignore_index=True)
        col_map = {"Term": "gene_set", "Adjusted P-value": "pvalue_adj", "P-value": "pvalue",
                   "Genes": "genes", "Overlap": "overlap"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        return df
    return pd.DataFrame()


def _run_gsea(
    adata,
    *,
    groupby: str = "leiden",
    source: str = "MSigDB_Hallmark",
    species: str = "human",
) -> pd.DataFrame:
    """Run GSEA pre-ranked via gseapy."""
    require("gseapy", feature="GSEA")
    import gseapy as gp

    sc.tl.rank_genes_groups(adata, groupby=groupby, method="wilcoxon")
    markers_df = sc.get.rank_genes_groups_df(adata, group=None)

    gene_sets = _resolve_library(source, organism=species)

    all_records = []
    for grp in sorted(markers_df["group"].unique().tolist(), key=str):
        grp_df = markers_df[markers_df["group"] == grp].dropna(subset=["scores"])
        rnk = grp_df.set_index("names")["scores"].sort_values(ascending=False)
        if len(rnk) < 10:
            continue
        try:
            pre_res = gp.prerank(
                rnk=rnk, gene_sets=gene_sets, min_size=5, max_size=1000,
                permutation_num=100, outdir=None, seed=42, verbose=False,
            )
            res = pre_res.res2d.copy()
            res["cluster"] = str(grp)
            res = res.rename(columns={"Term": "gene_set", "NES": "nes",
                                       "NOM p-val": "pvalue", "FDR q-val": "pvalue_adj"})
            all_records.append(res)
        except Exception as exc:
            logger.warning("GSEA failed for cluster %s: %s", grp, exc)

    if all_records:
        return pd.concat(all_records, ignore_index=True)
    return pd.DataFrame()


def _run_ssgsea(
    adata,
    *,
    groupby: str = "leiden",
    source: str = "MSigDB_Hallmark",
    species: str = "human",
) -> pd.DataFrame:
    """Run ssGSEA via gseapy."""
    require("gseapy", feature="ssGSEA")
    import gseapy as gp
    import scipy.sparse as sp

    gene_sets = _resolve_library(source, organism=species)

    X = adata.X
    if sp.issparse(X):
        X = X.toarray()
    expr_df = pd.DataFrame(X.T, index=adata.var_names, columns=adata.obs_names)

    try:
        ss = gp.ssgsea(
            data=expr_df, gene_sets=gene_sets, outdir=None, no_plot=True,
            min_size=5, max_size=1000,
        )
        score_df = ss.res2d.copy()
        score_df = score_df.rename(columns={"Term": "gene_set", "NES": "score"})
        score_df["pvalue"] = float("nan")
        score_df["pvalue_adj"] = float("nan")
        score_df["cluster"] = "all"
        return score_df
    except Exception as exc:
        raise RuntimeError(f"ssGSEA failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_enrichment(
    adata,
    *,
    method: str = "enrichr",
    groupby: str = "leiden",
    source: str = "GO_Biological_Process",
    species: str = "human",
    gene_set: str | None = None,
) -> dict:
    """Run pathway enrichment analysis.

    Parameters
    ----------
    adata:
        Preprocessed AnnData with cluster labels.
    method:
        ``"enrichr"``, ``"gsea"``, or ``"ssgsea"``.
    groupby:
        obs column with cluster / cell type labels.
    source:
        Gene set database key (e.g. ``"GO_Biological_Process"``,
        ``"MSigDB_Hallmark"``, ``"KEGG_Pathways"``).
    species:
        ``"human"`` or ``"mouse"``.

    Requires: pip install gseapy
    """
    require("gseapy", feature="pathway enrichment")

    supported = ("enrichr", "gsea", "ssgsea")
    if method not in supported:
        raise ValueError(f"Unknown method '{method}'. Choose from: {supported}")

    if groupby not in adata.obs.columns:
        raise ValueError(
            f"groupby column '{groupby}' not found in adata.obs.\n"
            f"Available columns: {list(adata.obs.columns)}\n"
            "Run spatial-preprocess first or specify --groupby."
        )

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    n_clusters = adata.obs[groupby].nunique()
    logger.info(
        "Input: %d cells × %d genes, %d clusters, method=%s, source=%s",
        n_cells, n_genes, n_clusters, method, source,
    )

    effective_source = gene_set or source

    if method == "gsea":
        enrich_df = _run_gsea(adata, groupby=groupby, source=effective_source, species=species)
        used_method = "gsea"
    elif method == "ssgsea":
        enrich_df = _run_ssgsea(adata, groupby=groupby, source=effective_source, species=species)
        used_method = "ssgsea"
    else:
        enrich_df = _run_enrichr(
            adata, groupby=groupby, source=effective_source,
            species=species,
        )
        used_method = "enrichr"

    n_sig = int(enrich_df["pvalue_adj"].dropna().lt(0.05).sum()) if not enrich_df.empty else 0

    return {
        "n_cells": n_cells,
        "n_genes": n_genes,
        "n_clusters": n_clusters,
        "method": used_method,
        "source": source,
        "groupby": groupby,
        "n_terms_tested": len(enrich_df),
        "n_significant": n_sig,
        "enrich_df": enrich_df,
    }


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

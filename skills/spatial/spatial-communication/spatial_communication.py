#!/usr/bin/env python3
"""Spatial Communication — ligand-receptor interaction analysis.

Supported methods:
  liana        LIANA+ multi-method consensus ranking (default)
  cellphonedb  CellPhoneDB statistical permutation test
  fastccc      FastCCC FFT-based communication (no permutation, fastest)
  cellchat_r   CellChat via R (requires rpy2 + R CellChat package)

Requires: pip install liana
          pip install -e ".[full]"  (for all methods)

Usage:
    python spatial_communication.py --input <preprocessed.h5ad> --output <dir>
    python spatial_communication.py --input <data.h5ad> --output <dir> --method liana
    python spatial_communication.py --demo --output <dir>
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
from omicsclaw.spatial.dependency_manager import require, validate_r_environment
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_communication

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-communication"
SKILL_VERSION = "0.2.0"

SUPPORTED_METHODS = ("liana", "cellphonedb", "fastccc", "cellchat_r")


# ---------------------------------------------------------------------------
# Method: LIANA+  (adapted from ChatSpatial tools/cell_communication.py)
# ---------------------------------------------------------------------------


def _run_liana(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    n_perms: int = 100,
) -> pd.DataFrame:
    """Run LIANA+ multi-method consensus ranking."""
    li = require("liana", feature="LIANA+ cell communication")

    logger.info("Running LIANA+ rank_aggregate (n_perms=%d) ...", n_perms)
    li.mt.rank_aggregate(
        adata,
        groupby=cell_type_key,
        use_raw=False,
        n_perms=n_perms,
        verbose=True,
    )

    df = adata.uns["liana_res"].copy()

    col_map = {}
    if "ligand_complex" in df.columns:
        col_map["ligand_complex"] = "ligand"
    if "receptor_complex" in df.columns:
        col_map["receptor_complex"] = "receptor"
    if "sender" in df.columns and "source" not in df.columns:
        col_map["sender"] = "source"
    if "receiver" in df.columns and "target" not in df.columns:
        col_map["receiver"] = "target"
    if col_map:
        df = df.rename(columns=col_map)

    if "magnitude_rank" in df.columns:
        df["score"] = 1.0 - df["magnitude_rank"]
    elif "lr_means" in df.columns:
        df["score"] = df["lr_means"]
    else:
        df["score"] = 0.0

    df["pvalue"] = df.get("specificity_rank", 0.5)

    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns:
            df[col] = ""

    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()


# ---------------------------------------------------------------------------
# Method: CellPhoneDB
# ---------------------------------------------------------------------------


def _run_cellphonedb(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    n_perms: int = 1000,
) -> pd.DataFrame:
    """Run CellPhoneDB statistical method."""
    require("cellphonedb", feature="CellPhoneDB cell communication")
    from cellphonedb.src.core.methods import cpdb_statistical_analysis_method

    if species != "human":
        raise ValueError("CellPhoneDB supports human data only. Use '--method liana' for mouse.")

    logger.info("Running CellPhoneDB (n_perms=%d) ...", n_perms)

    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="cpdb_") as tmp:
        tmp_path = Path(tmp)

        counts_path = tmp_path / "counts.tsv"
        meta_path = tmp_path / "meta.tsv"

        if hasattr(adata.X, "toarray"):
            counts_df = pd.DataFrame(
                adata.X.toarray().T, index=adata.var_names, columns=adata.obs_names
            )
        else:
            counts_df = pd.DataFrame(
                adata.X.T, index=adata.var_names, columns=adata.obs_names
            )
        counts_df.to_csv(counts_path, sep="\t")

        meta_df = pd.DataFrame({
            "Cell": adata.obs_names,
            "cell_type": adata.obs[cell_type_key].values,
        })
        meta_df.to_csv(meta_path, sep="\t", index=False)

        result = cpdb_statistical_analysis_method.call(
            cpdb_file_path=None,
            meta_file_path=str(meta_path),
            counts_file_path=str(counts_path),
            counts_data="hgnc_symbol",
            output_path=str(tmp_path),
            iterations=n_perms,
            threshold=0.1,
        )

    means_df = result.get("means")
    pvalues_df = result.get("pvalues")

    if means_df is None:
        return pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue"])

    records = []
    for _, row in means_df.iterrows():
        pair = str(row.get("interacting_pair", ""))
        parts = pair.split("|")
        ligand = parts[0] if len(parts) >= 1 else pair
        receptor = parts[1] if len(parts) >= 2 else ""
        for col in means_df.columns[10:]:
            score = float(row.get(col, 0) or 0)
            if score < 1e-6:
                continue
            src_tgt = str(col).split("|")
            source = src_tgt[0] if len(src_tgt) >= 1 else col
            target = src_tgt[1] if len(src_tgt) >= 2 else ""
            pval = 1.0
            if pvalues_df is not None and col in pvalues_df.columns:
                pval = float(pvalues_df.loc[row.name, col]) if row.name in pvalues_df.index else 1.0
            records.append({
                "ligand": ligand, "receptor": receptor,
                "source": source, "target": target,
                "score": round(score, 4), "pvalue": round(pval, 4),
            })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Method: FastCCC
# ---------------------------------------------------------------------------


def _run_fastccc(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
) -> pd.DataFrame:
    """Run FastCCC — FFT-based communication without permutation testing."""
    require("fastccc", feature="FastCCC cell communication")
    import fastccc

    if species != "human":
        raise ValueError("FastCCC currently supports human data only.")

    logger.info("Running FastCCC ...")

    result = fastccc.run(adata, groupby=cell_type_key)
    df = pd.DataFrame(result.copy())

    for old, new in [
        ("ligand_complex", "ligand"), ("receptor_complex", "receptor"),
        ("sender", "source"), ("receiver", "target"),
    ]:
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    df["score"] = df.get("lr_mean", df.get("score", 0.0))
    df["pvalue"] = df.get("pvalue", 0.0)

    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns:
            df[col] = ""

    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()


# ---------------------------------------------------------------------------
# Method: CellChat-R
# ---------------------------------------------------------------------------


def _run_cellchat_r(adata, *, cell_type_key: str = "leiden", species: str = "human") -> pd.DataFrame:
    """Run CellChat via rpy2 (requires R package CellChat)."""
    validate_r_environment(required_r_packages=["CellChat"])
    robjects, pandas2ri, numpy2ri, importr, localconverter, default_converter, openrlib, anndata2ri = (
        validate_r_environment(required_r_packages=["CellChat"])
    )

    logger.info("Running CellChat-R ...")

    db_species = {"human": "human", "mouse": "mouse", "zebrafish": "zebrafish"}.get(species, "human")

    with openrlib.rlock:
        with localconverter(default_converter + anndata2ri.converter):
            r_sce = anndata2ri.py2rpy(adata)
            cellchat_r = importr("CellChat")

            r_result = robjects.r(f"""
                function(sce) {{
                    library(CellChat)
                    counts <- assay(sce, 'X')
                    meta <- as.data.frame(colData(sce))
                    cellchat <- createCellChat(object=counts, meta=meta, group.by='{cell_type_key}')
                    CellChatDB <- CellChatDB.{db_species}
                    cellchat@DB <- CellChatDB
                    cellchat <- subsetData(cellchat)
                    cellchat <- identifyOverExpressedGenes(cellchat)
                    cellchat <- identifyOverExpressedInteractions(cellchat)
                    cellchat <- computeCommunProb(cellchat, raw.use=TRUE)
                    df.net <- subsetCommunication(cellchat)
                    df.net
                }}
            """)(r_sce)

            with localconverter(default_converter + pandas2ri.converter):
                df = pandas2ri.rpy2py(r_result)

    col_map = {
        "ligand": "ligand", "receptor": "receptor",
        "source": "source", "target": "target",
        "prob": "score", "pval": "pvalue",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns and v != k})
    df["score"] = df.get("score", 0.0)
    df["pvalue"] = df.get("pvalue", 0.5)

    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns:
            df[col] = ""

    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_communication(
    adata,
    *,
    method: str = "liana",
    cell_type_key: str = "leiden",
    species: str = "human",
    n_perms: int = 100,
) -> dict:
    """Run cell-cell communication analysis.

    Parameters
    ----------
    adata:
        Preprocessed AnnData with cell type labels.
    method:
        One of ``liana``, ``cellphonedb``, ``fastccc``, ``cellchat_r``.
    cell_type_key:
        obs column with cell type / cluster labels.
    species:
        ``"human"`` or ``"mouse"`` (method-dependent).
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if cell_type_key not in adata.obs.columns:
        raise ValueError(
            f"Cell type key '{cell_type_key}' not in adata.obs.\n"
            f"Available: {list(adata.obs.columns)}"
        )

    n_cells, n_genes = adata.n_obs, adata.n_vars
    cell_types = sorted(adata.obs[cell_type_key].unique().tolist(), key=str)
    logger.info(
        "Input: %d cells × %d genes, %d cell types, method=%s",
        n_cells, n_genes, len(cell_types), method,
    )

    dispatch = {
        "liana":       lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species, n_perms=n_perms),
        "cellphonedb": lambda: _run_cellphonedb(adata, cell_type_key=cell_type_key, species=species, n_perms=n_perms),
        "fastccc":     lambda: _run_fastccc(adata, cell_type_key=cell_type_key, species=species),
        "cellchat_r":  lambda: _run_cellchat_r(adata, cell_type_key=cell_type_key, species=species),
    }
    lr_df = dispatch[method]()

    sig_df = lr_df[lr_df["pvalue"] < 0.05] if not lr_df.empty else lr_df

    return {
        "n_cells": n_cells,
        "n_genes": n_genes,
        "n_cell_types": len(cell_types),
        "cell_types": cell_types,
        "cell_type_key": cell_type_key,
        "method": method,
        "species": species,
        "n_interactions_tested": len(lr_df),
        "n_significant": len(sig_df),
        "lr_df": lr_df,
        "top_df": lr_df.head(50) if not lr_df.empty else lr_df,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate CCC visualizations using the SpatialClaw viz library."""
    figures: list[str] = []

    # 1. LR pair dotplot
    try:
        fig = plot_communication(adata, VizParams(), subtype="dotplot", top_n=20)
        p = save_figure(fig, output_dir, "lr_dotplot.png")
        figures.append(str(p))
    except Exception as exc:
        logger.warning("LR dotplot failed: %s", exc)

    # 2. Sender × receiver heatmap
    try:
        fig = plot_communication(adata, VizParams(), subtype="heatmap", top_n=20)
        p = save_figure(fig, output_dir, "lr_heatmap.png")
        figures.append(str(p))
    except Exception as exc:
        logger.warning("LR heatmap failed: %s", exc)

    # 3. Spatial LR score maps (if spatial scores available)
    if any("spatial_scores" in k for k in adata.obsm.keys()):
        try:
            fig = plot_communication(adata, VizParams(), subtype="spatial", top_n=5)
            p = save_figure(fig, output_dir, "lr_spatial.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("LR spatial map failed: %s", exc)

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
    header = generate_report_header(
        title="Spatial Cell-Cell Communication Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Cell type key": summary.get("cell_type_key", ""),
        },
    )

    top_df = summary.get("top_df", pd.DataFrame())
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Method**: {summary['method']}",
        f"- **L-R pairs tested**: {summary['n_interactions_tested']}",
        f"- **Significant (p < 0.05)**: {summary['n_significant']}",
    ]

    if not top_df.empty:
        body_lines.extend(["", "### Top Interactions\n"])
        body_lines.append("| Ligand | Receptor | Source | Target | Score |")
        body_lines.append("|--------|----------|--------|--------|-------|")
        for _, r in top_df.head(15).iterrows():
            body_lines.append(
                f"| {r['ligand']} | {r['receptor']} | {r['source']} | {r['target']} | {r['score']:.4f} |"
            )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if k not in ("lr_df", "top_df")},
        data={"params": params},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    lr_df = summary.get("lr_df", pd.DataFrame())
    if not lr_df.empty:
        lr_df.to_csv(tables_dir / "lr_interactions.csv", index=False)
        if not top_df.empty:
            top_df.head(50).to_csv(tables_dir / "top_interactions.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = (
        f"python spatial_communication.py --input <input.h5ad>"
        f" --method {params.get('method', 'liana')}"
        f" --cell-type-key {params.get('cell_type_key', 'leiden')}"
        f" --output {output_dir}"
    )
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    from importlib.metadata import version as _ver, PackageNotFoundError
    env_lines = []
    for pkg in ["scanpy", "anndata", "liana", "numpy", "pandas"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except PackageNotFoundError:
            pass
    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_comm_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Generating demo data via spatial-preprocess ...")
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
        logger.info("Demo: %d cells × %d genes", adata.n_obs, adata.n_vars)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Communication — ligand-receptor interaction analysis\n"
                    "Requires: pip install liana  (for default LIANA+ method)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="liana", choices=list(SUPPORTED_METHODS),
    )
    parser.add_argument("--cell-type-key", default="leiden")
    parser.add_argument("--species", default="human", choices=["human", "mouse", "zebrafish"])
    parser.add_argument("--n-perms", type=int, default=100)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        if not Path(args.input_path).exists():
            print(f"ERROR: Input not found: {args.input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input <file.h5ad> or --demo", file=sys.stderr)
        sys.exit(1)

    params = {
        "method": args.method,
        "cell_type_key": args.cell_type_key,
        "species": args.species,
        "n_perms": args.n_perms,
    }

    summary = run_communication(
        adata,
        method=args.method,
        cell_type_key=args.cell_type_key,
        species=args.species,
        n_perms=args.n_perms,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata, SKILL_NAME, summary["method"],
        params=params,
    )

    adata.write_h5ad(output_dir / "processed.h5ad")
    logger.info("Saved: %s", output_dir / "processed.h5ad")

    print(
        f"Communication complete ({summary['method']}): "
        f"{summary['n_interactions_tested']} L-R pairs, "
        f"{summary['n_significant']} significant (p<0.05)"
    )


if __name__ == "__main__":
    main()

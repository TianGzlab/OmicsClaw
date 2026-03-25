"""Spatial cell-cell communication analysis functions.

Provides LIANA, CellPhoneDB, FastCCC, and CellChat (R) for ligand-receptor analysis.

Usage::

    from skills.spatial._lib.communication import run_communication, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc

from .adata_utils import get_spatial_key
from .dependency_manager import require, validate_r_environment

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("liana", "cellphonedb", "fastccc", "cellchat_r")


def _run_liana(adata, *, cell_type_key: str = "leiden", species: str = "human", n_perms: int = 100) -> pd.DataFrame:
    """Run LIANA+ multi-method consensus ranking."""
    li = require("liana", feature="LIANA+ cell communication")
    use_raw = adata.raw is not None
    logger.info("Running LIANA+ rank_aggregate (n_perms=%d, use_raw=%s) ...", n_perms, use_raw)
    li.mt.rank_aggregate(adata, groupby=cell_type_key, use_raw=use_raw, n_perms=n_perms, verbose=True)
    df = adata.uns["liana_res"].copy()

    col_map = {}
    if "ligand_complex" in df.columns: col_map["ligand_complex"] = "ligand"
    if "receptor_complex" in df.columns: col_map["receptor_complex"] = "receptor"
    if "sender" in df.columns and "source" not in df.columns: col_map["sender"] = "source"
    if "receiver" in df.columns and "target" not in df.columns: col_map["receiver"] = "target"
    if col_map: df = df.rename(columns=col_map)

    if "magnitude_rank" in df.columns: df["score"] = 1.0 - df["magnitude_rank"]
    elif "lr_means" in df.columns: df["score"] = df["lr_means"]
    else: df["score"] = 0.0

    if "specificity_rank" in df.columns: df["pvalue"] = df["specificity_rank"]
    else: df["pvalue"] = 0.5

    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns: df[col] = ""

    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy().sort_values("score", ascending=False).reset_index(drop=True)


def _run_cellphonedb(adata, *, cell_type_key: str = "leiden", species: str = "human", n_perms: int = 1000) -> pd.DataFrame:
    """Run CellPhoneDB statistical method."""
    cpdb = require("cellphonedb", feature="CellPhoneDB cell communication")
    from cellphonedb.src.core.methods import cpdb_statistical_analysis_method
    from pathlib import Path
    import tempfile as _tf

    if species != "human":
        raise ValueError("CellPhoneDB supports human data only.")

    cpdb_db_path = None
    try:
        import cellphonedb
        cpdb_pkg_dir = Path(cellphonedb.__file__).parent
        for candidate in [cpdb_pkg_dir / "src" / "core" / "data" / "cellphonedb.zip", cpdb_pkg_dir / "data" / "cellphonedb.zip"]:
            if candidate.exists():
                cpdb_db_path = str(candidate); break
    except Exception: pass

    with _tf.TemporaryDirectory(prefix="cpdb_") as tmp:
        tmp_path = Path(tmp)
        counts_df = pd.DataFrame(adata.X.toarray().T if hasattr(adata.X, "toarray") else adata.X.T, index=adata.var_names, columns=adata.obs_names)
        counts_df.to_csv(tmp_path / "counts.tsv", sep="\t")
        meta_df = pd.DataFrame({"Cell": adata.obs_names, "cell_type": adata.obs[cell_type_key].values})
        meta_df.to_csv(tmp_path / "meta.tsv", sep="\t", index=False)

        result = cpdb_statistical_analysis_method.call(
            cpdb_file_path=cpdb_db_path, meta_file_path=str(tmp_path / "meta.tsv"),
            counts_file_path=str(tmp_path / "counts.tsv"), counts_data="hgnc_symbol",
            output_path=str(tmp_path), iterations=n_perms, threshold=0.1,
        )

    means_df = result.get("means")
    pvalues_df = result.get("pvalues")
    if means_df is None:
        return pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue"])

    records = []
    for _, row in means_df.iterrows():
        pair = str(row.get("interacting_pair", ""))
        parts = pair.split("|")
        ligand, receptor = (parts[0] if len(parts) >= 1 else pair), (parts[1] if len(parts) >= 2 else "")
        for col in means_df.columns[10:]:
            score = float(row.get(col, 0) or 0)
            if score < 1e-6: continue
            src_tgt = str(col).split("|")
            source, target = (src_tgt[0] if len(src_tgt) >= 1 else col), (src_tgt[1] if len(src_tgt) >= 2 else "")
            pval = float(pvalues_df.loc[row.name, col]) if pvalues_df is not None and col in pvalues_df.columns and row.name in pvalues_df.index else 1.0
            records.append({"ligand": ligand, "receptor": receptor, "source": source, "target": target, "score": round(score, 4), "pvalue": round(pval, 4)})

    df = pd.DataFrame(records)
    return df.sort_values("score", ascending=False).reset_index(drop=True) if not df.empty else df


def _run_fastccc(adata, *, cell_type_key: str = "leiden", species: str = "human") -> pd.DataFrame:
    """Run FastCCC — FFT-based communication without permutation testing."""
    require("fastccc", feature="FastCCC cell communication")
    import fastccc
    if species != "human": raise ValueError("FastCCC currently supports human data only.")
    result = fastccc.run(adata, groupby=cell_type_key)
    df = pd.DataFrame(result.copy())
    for old, new in [("ligand_complex", "ligand"), ("receptor_complex", "receptor"), ("sender", "source"), ("receiver", "target")]:
        if old in df.columns and new not in df.columns: df = df.rename(columns={old: new})
    df["score"] = df.get("lr_mean", df.get("score", 0.0))
    df["pvalue"] = df.get("pvalue", 0.0)
    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns: df[col] = ""
    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()


def _run_cellchat_r(adata, *, cell_type_key: str = "leiden", species: str = "human") -> pd.DataFrame:
    """Run CellChat via rpy2 (requires R package CellChat)."""
    robjects, pandas2ri, numpy2ri, importr, localconverter, default_converter, openrlib, anndata2ri = (
        validate_r_environment(required_r_packages=["CellChat"])
    )
    db_species = {"human": "human", "mouse": "mouse", "zebrafish": "zebrafish"}.get(species, "human")
    with openrlib.rlock:
        with localconverter(default_converter + anndata2ri.converter):
            r_sce = anndata2ri.py2rpy(adata)
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
    col_map = {"prob": "score", "pval": "pvalue"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns and v != k})
    df["score"] = df.get("score", 0.0); df["pvalue"] = df.get("pvalue", 0.5)
    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns: df[col] = ""
    return df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()


def run_communication(adata, *, method: str = "liana", cell_type_key: str = "leiden", species: str = "human", n_perms: int = 100) -> dict:
    """Run cell-cell communication analysis."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    if cell_type_key not in adata.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in adata.obs")

    n_cells, n_genes = adata.n_obs, adata.n_vars
    cell_types = sorted(adata.obs[cell_type_key].unique().tolist(), key=str)

    dispatch = {
        "liana": lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species, n_perms=n_perms),
        "cellphonedb": lambda: _run_cellphonedb(adata, cell_type_key=cell_type_key, species=species, n_perms=n_perms),
        "fastccc": lambda: _run_fastccc(adata, cell_type_key=cell_type_key, species=species),
        "cellchat_r": lambda: _run_cellchat_r(adata, cell_type_key=cell_type_key, species=species),
    }
    lr_df = dispatch[method]()
    sig_df = lr_df[lr_df["pvalue"] < 0.05] if not lr_df.empty else lr_df

    return {
        "n_cells": n_cells, "n_genes": n_genes, "n_cell_types": len(cell_types),
        "cell_types": cell_types, "cell_type_key": cell_type_key, "method": method,
        "species": species, "n_interactions_tested": len(lr_df), "n_significant": len(sig_df),
        "lr_df": lr_df, "top_df": lr_df.head(50) if not lr_df.empty else lr_df,
    }

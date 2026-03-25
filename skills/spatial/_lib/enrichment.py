"""Spatial enrichment analysis functions.

Provides enrichR, GSEA, and ssGSEA for pathway enrichment analysis.

Usage::

    from skills.spatial._lib.enrichment import run_enrichment, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc

from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("enrichr", "gsea", "ssgsea")

_GENESET_LIBRARY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "GO_Biological_Process": ("GO_Biological_Process_2025", "GO_Biological_Process_2023"),
    "GO_Molecular_Function": ("GO_Molecular_Function_2025", "GO_Molecular_Function_2023"),
    "GO_Cellular_Component": ("GO_Cellular_Component_2025", "GO_Cellular_Component_2023"),
    "KEGG_Pathways": ("KEGG_2021_Human",),
    "Reactome_Pathways": ("Reactome_Pathways_2024", "Reactome_2022"),
    "MSigDB_Hallmark": ("MSigDB_Hallmark_2020",),
}


def resolve_library(key: str, organism: str = "human") -> dict:
    """Load first available library variant from gseapy."""
    import gseapy as gp
    if key in _GENESET_LIBRARY_CANDIDATES:
        for lib in _GENESET_LIBRARY_CANDIDATES[key]:
            try:
                return gp.get_library(lib, organism=organism)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Could not load gene set '{key}': {last_err}")
    return gp.get_library(key, organism=organism)


def run_enrichr(adata, *, groupby: str = "leiden", source: str = "GO_Biological_Process",
                species: str = "human", n_top_genes: int = 100) -> pd.DataFrame:
    """Run per-cluster Enrichr via gseapy."""
    require("gseapy", feature="pathway enrichment (Enrichr)")
    import gseapy as gp

    sc.tl.rank_genes_groups(adata, groupby=groupby, method="wilcoxon", n_genes=n_top_genes)
    markers_df = sc.get.rank_genes_groups_df(adata, group=None)
    candidates = _GENESET_LIBRARY_CANDIDATES.get(source, (source,))
    lib_name = candidates[0]

    all_records = []
    for grp in sorted(markers_df["group"].unique().tolist(), key=str):
        gene_list = markers_df[markers_df["group"] == grp].head(n_top_genes)["names"].tolist()
        if not gene_list: continue
        try:
            enr = gp.enrichr(gene_list=gene_list, gene_sets=lib_name, organism=species, outdir=None, no_plot=True)
            res = enr.results.copy() if hasattr(enr, 'results') else enr.res2d.copy()
            res["cluster"] = str(grp)
            all_records.append(res)
        except Exception as exc:
            logger.warning("Enrichr failed for cluster %s: %s", grp, exc)

    if all_records:
        df = pd.concat(all_records, ignore_index=True)
        col_map = {"Term": "gene_set", "Adjusted P-value": "pvalue_adj", "P-value": "pvalue",
                   "Genes": "genes", "Overlap": "overlap"}
        return df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return pd.DataFrame()


def run_gsea(adata, *, groupby: str = "leiden", source: str = "MSigDB_Hallmark",
             species: str = "human") -> pd.DataFrame:
    """Run GSEA pre-ranked via gseapy."""
    require("gseapy", feature="GSEA")
    import gseapy as gp

    sc.tl.rank_genes_groups(adata, groupby=groupby, method="wilcoxon")
    markers_df = sc.get.rank_genes_groups_df(adata, group=None)
    gene_sets = resolve_library(source, organism=species)

    all_records = []
    for grp in sorted(markers_df["group"].unique().tolist(), key=str):
        grp_df = markers_df[markers_df["group"] == grp].dropna(subset=["scores"])
        rnk = grp_df.set_index("names")["scores"].sort_values(ascending=False)
        if len(rnk) < 10: continue
        try:
            pre_res = gp.prerank(rnk=rnk, gene_sets=gene_sets, min_size=5, max_size=1000,
                                 permutation_num=100, outdir=None, seed=42, verbose=False)
            res = pre_res.res2d.copy()
            res["cluster"] = str(grp)
            res = res.rename(columns={"Term": "gene_set", "NES": "nes", "NOM p-val": "pvalue", "FDR q-val": "pvalue_adj"})
            all_records.append(res)
        except Exception as exc:
            logger.warning("GSEA failed for cluster %s: %s", grp, exc)

    return pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()


def run_ssgsea(adata, *, groupby: str = "leiden", source: str = "MSigDB_Hallmark",
               species: str = "human") -> pd.DataFrame:
    """Run ssGSEA via gseapy."""
    require("gseapy", feature="ssGSEA")
    import gseapy as gp
    from scipy import sparse

    gene_sets = resolve_library(source, organism=species)
    X = adata.X.toarray() if sparse.issparse(adata.X) else adata.X
    expr_df = pd.DataFrame(X.T, index=adata.var_names, columns=adata.obs_names)

    ss = gp.ssgsea(data=expr_df, gene_sets=gene_sets, outdir=None, no_plot=True, min_size=5, max_size=1000)
    score_df = ss.res2d.copy()
    score_df = score_df.rename(columns={"Term": "gene_set", "NES": "score"})
    score_df["pvalue"] = float("nan")
    score_df["pvalue_adj"] = float("nan")
    score_df["cluster"] = "all"
    return score_df


def run_enrichment(adata, *, method: str = "enrichr", groupby: str = "leiden",
                   source: str = "GO_Biological_Process", species: str = "human",
                   gene_set: str | None = None) -> dict:
    """Run pathway enrichment analysis."""
    require("gseapy", feature="pathway enrichment")

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    if groupby not in adata.obs.columns:
        raise ValueError(f"groupby column '{groupby}' not found in adata.obs")

    effective_source = gene_set or source
    dispatch = {
        "enrichr": lambda: run_enrichr(adata, groupby=groupby, source=effective_source, species=species),
        "gsea": lambda: run_gsea(adata, groupby=groupby, source=effective_source, species=species),
        "ssgsea": lambda: run_ssgsea(adata, groupby=groupby, source=effective_source, species=species),
    }
    enrich_df = dispatch[method]()
    n_sig = int(enrich_df["pvalue_adj"].dropna().lt(0.05).sum()) if not enrich_df.empty else 0

    return {
        "n_cells": adata.n_obs, "n_genes": adata.n_vars,
        "n_clusters": int(adata.obs[groupby].nunique()),
        "method": method, "source": source, "groupby": groupby,
        "n_terms_tested": len(enrich_df), "n_significant": n_sig,
        "enrich_df": enrich_df,
    }

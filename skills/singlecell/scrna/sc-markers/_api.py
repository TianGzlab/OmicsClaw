"""Cluster marker discovery and table summaries without changing the input."""

from __future__ import annotations

import logging
from copy import deepcopy

import numpy as np
import pandas as pd
import scanpy as sc

from skills.singlecell._lib.markers import find_cosg_markers

__all__ = ["find_markers", "run_info", "top_markers", "cluster_summary", "marker_dotplot_figure"]

logger = logging.getLogger(__name__)
_RUN_KEY = "omicsclaw_sc_markers_run"
_METHODS = ("wilcoxon", "t-test", "logreg", "cosg")


def find_markers(
    adata,
    *,
    groupby: str,
    method: str = "wilcoxon",
    n_genes: int | None = None,
    min_in_group_fraction: float = 0.25,
    min_fold_change: float = 0.25,
    max_out_group_fraction: float = 0.5,
    mu: float = 1.0,
) -> pd.DataFrame:
    """Rank marker genes for each group against the rest using adata.X.

    X should contain normalized expression. Computation uses a copy, so the
    input's matrices, obs and uns are unchanged. Scanpy methods apply the
    expression-fraction and fold-change filters; when filtering fails or
    removes every row, the unfiltered ranking is returned and run_info records
    filter_fallback and its reason. COSG scores specificity without p-values.

    :param groupby: The obs column defining clusters or cell types.
    :param method: wilcoxon (default), t-test, logreg or cosg.
    :param n_genes: Genes ranked per group. None means all genes for Scanpy
        methods and 50 for COSG, matching the CLI defaults.
    :param min_in_group_fraction: Minimum expressing fraction within a group.
        Default 0.25; unused by COSG.
    :param min_fold_change: Fold-change filter passed to Scanpy. Default 0.25;
        unused by COSG.
    :param max_out_group_fraction: Maximum expressing fraction outside a group.
        Default 0.5; unused by COSG.
    :param mu: COSG specificity penalty. Default 1.0; unused by Scanpy methods.
    :returns: A DataFrame with group, names, scores and method-dependent effect,
        p-value and fraction columns. COSG pvals and pvals_adj are NaN. The
        table's attrs hold the run record; use run_info before CSV export.
    :raises ValueError: Unknown method or missing grouping column.
    """
    if method not in _METHODS:
        raise ValueError(f"Unknown marker method {method!r}; choose one of {_METHODS}")
    if groupby not in adata.obs:
        raise ValueError(f"Grouping column {groupby!r} not found in adata.obs")
    working = adata.copy()
    info = {"method": method, "groupby": groupby, "expression_source": "adata.X",
            "filter_fallback": False, "fallback_reason": None}
    if method == "cosg":
        table = find_cosg_markers(working, cluster_key=groupby,
                                  n_genes=n_genes if n_genes is not None else 50,
                                  mu=mu, use_raw=False)
        table[["pvals", "pvals_adj"]] = np.nan
    else:
        kwargs = dict(groupby=groupby, method=method, pts=True, use_raw=False)
        if n_genes is not None:
            kwargs["n_genes"] = n_genes
        sc.tl.rank_genes_groups(working, **kwargs)
        try:
            sc.tl.filter_rank_genes_groups(
                working, min_in_group_fraction=min_in_group_fraction,
                min_fold_change=min_fold_change, max_out_group_fraction=max_out_group_fraction,
            )
            key = "rank_genes_groups_filtered"
            if key in working.uns:
                table = sc.get.rank_genes_groups_df(working, group=None, key=key).dropna(subset=["names"])
                if table.empty:
                    info["fallback_reason"] = "Filtered marker table is empty"
            else:
                info["fallback_reason"] = "Scanpy did not produce a filtered marker table"
        except Exception as exc:
            info["fallback_reason"] = f"filter_rank_genes_groups failed: {exc}"
        if info["fallback_reason"]:
            info["filter_fallback"] = True
            logger.warning("%s; returning the unfiltered ranking", info["fallback_reason"])
            table = sc.get.rank_genes_groups_df(working, group=None)
    info["n_clusters"] = int(table["group"].nunique()) if not table.empty else 0
    info["n_markers"] = len(table)
    table.attrs[_RUN_KEY] = info
    return table


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return the method, grouping and filter-fallback record attached to a marker table.

    :param keep: False removes the record from table.attrs; default True keeps it.
    :returns: A copy of the run record, or an empty dict for an unrecorded table.
        CSV files do not preserve attrs; write this record separately if needed.
    """
    info = table.attrs.get(_RUN_KEY, {}) if keep else table.attrs.pop(_RUN_KEY, {})
    return deepcopy(info)


def _ranked(table):
    frame = table.copy()
    valid_p = "pvals_adj" in frame and pd.to_numeric(frame["pvals_adj"], errors="coerce").notna().any()
    no_p_values = "pvals_adj" in frame and not valid_p
    effect = "logfoldchanges" if (
        not no_p_values and "logfoldchanges" in frame
        and pd.to_numeric(frame["logfoldchanges"], errors="coerce").notna().any()
    ) else "scores"
    columns = (["pvals_adj"] if valid_p else []) + [effect]
    return frame.sort_values(columns, ascending=([True] if valid_p else []) + [False]), effect


def top_markers(table: pd.DataFrame, *, n_top: int = 10) -> pd.DataFrame:
    """Return the top n_top rows per group, using adjusted p-value then effect.

    Tables without finite adjusted p-values, including COSG, use scores.
    Otherwise logfoldchanges is the effect when available, falling back to scores.
    """
    if table.empty:
        return pd.DataFrame()
    frame, _ = _ranked(table)
    return frame.groupby("group", sort=False, observed=False).head(n_top).copy()


def cluster_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Return n_markers, top_gene, top_effect, median_effect and effect_metric per group.

    The top gene uses the same ordering as top_markers. top_effect is the
    group's maximum effect, not necessarily that gene's effect. Use a row
    from top_markers when reporting a gene together with its effect size.
    Effect statistics use all returned markers in the group.
    """
    if table.empty:
        return pd.DataFrame()
    frame, effect = _ranked(table)
    summary = frame.groupby("group", dropna=False, observed=False).agg(
        n_markers=("names", "count"), top_gene=("names", "first"),
        top_effect=(effect, "max"), median_effect=(effect, "median"),
    ).reset_index()
    summary["effect_metric"] = effect
    return summary


def marker_dotplot_figure(adata, table: pd.DataFrame, *, groupby: str, n_top: int = 5):
    """Return a matplotlib Figure of marker expression in adata.X by group.

    Dot size shows the expressing fraction; color shows mean expression.
    The top n_top markers per group are selected with top_markers.
    """
    selected = top_markers(table, n_top=n_top)
    genes = {str(group): [gene for gene in rows["names"] if gene in adata.var_names]
             for group, rows in selected.groupby("group", observed=True)}
    genes = {group: names for group, names in genes.items() if names}
    if not genes:
        raise ValueError("No marker genes overlap the expression matrix")
    plot = sc.pl.dotplot(adata, genes, groupby=groupby, use_raw=False, show=False, return_fig=True)
    plot.make_figure()
    return plot.fig

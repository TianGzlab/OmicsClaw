"""sc-de's function library: differential expression between groups of cells or pseudobulk samples.

In a step: ``de = load_skill("sc-de")``. The functions compute and return
tables; they read and write no files. ``rank_genes(method="mast")`` and
``pseudobulk_de`` run R through ``Rscript``.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc

from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills._sdk.r_script_runner import RScriptRunner
from skills.singlecell._lib.adata_utils import get_matrix_contract, matrix_looks_count_like
from skills.singlecell._lib.pseudobulk import aggregate_to_pseudobulk, run_deseq2_analysis
from skills.singlecell._lib.r_exchange import write_matrix_exchange

__all__ = [
    "rank_genes",
    "pseudobulk_de",
    "run_info",
    "top_genes",
    "volcano_figure",
]

logger = logging.getLogger(__name__)

CELL_METHODS = ("wilcoxon", "t-test", "logreg", "mast")
_RUN_KEY = "omicsclaw_sc_de_run"


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def _remember(adata, summary: dict) -> None:
    adata.uns[_RUN_KEY] = json.dumps({"summary": summary}, default=_json_default)


def rank_genes(
    adata,
    *,
    groupby: str = "leiden",
    method: str = "wilcoxon",
    group1: str | None = None,
    group2: str | None = None,
    logreg_solver: str = "lbfgs",
) -> pd.DataFrame:
    """Rank genes per group of cells: every group against the rest, or ``group1`` against ``group2``.

    ``wilcoxon``, ``t-test`` and ``logreg`` run scanpy's ``rank_genes_groups`` on
    ``X`` (``use_raw=False``, with the fraction of expressing cells) and also leave
    its result in ``uns['rank_genes_groups']``; ``mast`` runs the MAST hurdle model
    in R. Cells are the units here, so p-values overstate the evidence for a
    difference between conditions; use :func:`pseudobulk_de` for that.

    :param groupby: The ``obs`` column defining the groups. Default ``"leiden"``; when it
        is missing and ``louvain`` exists, ``louvain`` is used and recorded.
    :param method: ``"wilcoxon"`` (default; scanpy's recommended test), ``"t-test"``,
        ``"logreg"`` or ``"mast"``.
    :param group1: Compare only this group ...
    :param group2: ... against this one. Default: each group against the rest.
    :param logreg_solver: The scikit-learn solver for ``logreg``. Default ``"lbfgs"``.
    :returns: One row per gene and group. scanpy methods: ``names``, ``scores``,
        ``logfoldchanges``, ``pvals``, ``pvals_adj``, ``pct_nz_group``,
        ``pct_nz_reference``, ``group``; ``mast``: ``gene``, ``group``, ``pvalue``,
        ``padj`` and effect columns.
    :raises ValueError: an unknown method, or the group column is missing.
    :raises RuntimeError: ``mast`` and R or MAST is missing.
    """
    if method not in CELL_METHODS:
        raise ValueError(f"unknown method {method!r}; choose one of {', '.join(CELL_METHODS)}, or use pseudobulk_de")
    if method == "mast":
        table, summary = _run_de_mast(adata, groupby=groupby, group1=group1, group2=group2)
    else:
        table, summary = _run_de_scanpy(adata, groupby, method, group1, group2, logreg_solver=logreg_solver)
    _remember(adata, summary)
    return table


def pseudobulk_de(
    adata,
    *,
    condition_key: str,
    group1: str,
    group2: str,
    sample_key: str = "sample_id",
    celltype_key: str = "cell_type",
    min_cells: int = 10,
    min_counts: int = 1000,
) -> pd.DataFrame:
    """DESeq2 on pseudobulk counts: one test of ``group1`` against ``group2`` per cell type, run in R.

    Counts are summed per sample and cell type from ``layers['counts']``, ``raw``
    or a count-like ``X``; bins below the thresholds are dropped. Samples, not
    cells, are the units, so this is the test for condition effects.

    :param condition_key: The ``obs`` column holding the condition.
    :param group1: The condition of interest (numerator of the fold change).
    :param group2: The reference condition.
    :param sample_key: The ``obs`` column naming biological replicates. Default ``"sample_id"``.
    :param celltype_key: The ``obs`` column with cell types. Default ``"cell_type"``.
    :param min_cells: Minimum cells per sample and cell type bin. Default 10.
    :param min_counts: Minimum total counts per bin. Default 1000.
    :returns: Columns ``gene``, ``log2FoldChange``, ``pvalue``, ``padj`` (and DESeq2's
        others) plus ``cell_type``.
    :raises ValueError: a missing column, missing groups, or no count-like matrix.
    :raises RuntimeError: R or DESeq2 is missing, or no bin passes the thresholds.
    """
    table, summary = _run_de_deseq2_r(
        adata,
        condition_key=condition_key,
        group1=group1,
        group2=group2,
        sample_key=sample_key,
        celltype_key=celltype_key,
        pseudobulk_min_cells=min_cells,
        pseudobulk_min_counts=min_counts,
    )
    _remember(adata, summary)
    return table


def run_info(adata, *, keep: bool = True) -> dict:
    """What the last :func:`rank_genes` or :func:`pseudobulk_de` call recorded under ``summary``.

    ``summary`` has ``method``, ``groupby`` (the column actually used), ``n_groups``,
    ``n_genes_tested`` and ``expression_source``.

    :param keep: Leave the record in ``adata.uns``; ``False`` removes it.
    :returns: The record, or an empty dict when neither has run on *adata*.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def top_genes(table: pd.DataFrame, *, n_top: int = 10) -> pd.DataFrame:
    """The first *n_top* genes of each group.

    A scanpy table is already ranked within each group. A table with ``padj``
    (MAST) is sorted by ``padj`` then ``pvalue`` first.

    :param table: What :func:`rank_genes` returned.
    :param n_top: Genes per group. Default 10, the CLI's default.
    :returns: The selected rows, in the table's columns.
    """
    if {"padj", "pvalue"} <= set(table.columns):
        table = table.sort_values(["padj", "pvalue"], na_position="last")
    return table.groupby("group", observed=False).head(n_top)


def volcano_figure(table: pd.DataFrame, *, padj_threshold: float = 0.05, log2fc_threshold: float = 1.0,
                   group: str | None = None):
    """A volcano plot of a DE table, significant genes coloured.

    :param table: What :func:`rank_genes` or :func:`pseudobulk_de` returned.
    :param padj_threshold: Adjusted p-value cut. Default 0.05.
    :param log2fc_threshold: Absolute log2 fold-change cut. Default 1.0.
    :param group: Plot only this group (or cell type). Default: all rows.
    :returns: A matplotlib Figure.
    """
    import matplotlib.pyplot as plt

    fc_col = next(c for c in ("logfoldchanges", "log2FoldChange", "log2fc", "avg_log2FC", "coef") if c in table.columns)
    p_col = next(c for c in ("pvals_adj", "padj", "pvalue", "pvals") if c in table.columns)
    data = table
    if group is not None:
        group_col = "group" if "group" in table.columns else "cell_type"
        data = table.loc[table[group_col].astype(str) == str(group)]
    fc = pd.to_numeric(data[fc_col], errors="coerce").to_numpy(dtype=float)
    p = pd.to_numeric(data[p_col], errors="coerce").to_numpy(dtype=float)
    neglog = -np.log10(np.clip(p, 1e-300, 1.0))
    significant = (p < padj_threshold) & (np.abs(fc) >= log2fc_threshold)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(fc[~significant], neglog[~significant], s=4, color="#b0b0b0", linewidths=0)
    ax.scatter(fc[significant], neglog[significant], s=6, color="#c44e52", linewidths=0)
    ax.axhline(-np.log10(padj_threshold), color="#555555", linestyle="--", linewidth=0.8)
    for x in (-log2fc_threshold, log2fc_threshold):
        ax.axvline(x, color="#555555", linestyle="--", linewidth=0.8)
    ax.set_xlabel(fc_col)
    ax.set_ylabel(f"-log10 {p_col}")
    ax.set_title(f"{int(significant.sum())} genes past both cuts" + (f" ({group})" if group is not None else ""))
    fig.tight_layout()
    return fig


def _run_de_scanpy(
    adata,
    groupby="leiden",
    method="wilcoxon",
    group1=None,
    group2=None,
    *,
    logreg_solver: str = "lbfgs",
):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for DE demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")

    effective_method = method
    method_kwargs: dict[str, object] = {"pts": True, "use_raw": False}
    if method == "logreg":
        method_kwargs["solver"] = logreg_solver

    if group1 and group2:
        sc.tl.rank_genes_groups(
            adata,
            groupby=resolved_groupby,
            groups=[group1],
            reference=group2,
            method=effective_method,
            **method_kwargs,
        )
    else:
        sc.tl.rank_genes_groups(
            adata,
            groupby=resolved_groupby,
            method=effective_method,
            **method_kwargs,
        )

    result_df = sc.get.rank_genes_groups_df(adata, group=None)
    n_groups = len(result_df["group"].unique()) if "group" in result_df.columns else 0
    return result_df, {
        "method": method,
        "groupby": resolved_groupby,
        "n_groups": n_groups,
        "n_genes_tested": int(adata.n_vars),
        "expression_source": "adata.X",
    }


def _build_count_like_adata(adata) -> tuple[sc.AnnData, str]:
    if "counts" in adata.layers and matrix_looks_count_like(adata.layers["counts"]):
        prepared = adata.copy()
        prepared.X = adata.layers["counts"].copy()
        return prepared, "layers.counts"

    if adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X):
        prepared = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        prepared.obs_names = adata.obs_names.copy()
        prepared.var_names = adata.raw.var_names.copy()
        return prepared, "adata.raw"

    matrix_contract = get_matrix_contract(adata)
    if matrix_contract.get("X") == "raw_counts" or matrix_looks_count_like(adata.X):
        return adata.copy(), "adata.X"

    raise ValueError(
        "deseq2_r requires raw counts in `layers['counts']`, aligned raw counts in `adata.raw`, or an unnormalized count-like `adata.X` matrix."
    )


def _run_de_deseq2_r(
    adata,
    *,
    condition_key: str,
    group1: str,
    group2: str,
    sample_key: str,
    celltype_key: str,
    pseudobulk_min_cells: int = 10,
    pseudobulk_min_counts: int = 1000,
):
    if not group1 or not group2:
        raise ValueError("R pseudobulk DESeq2 requires both --group1 and --group2")
    if sample_key not in adata.obs.columns:
        raise ValueError(f"sample_key '{sample_key}' not found in adata.obs")
    if celltype_key not in adata.obs.columns:
        raise ValueError(f"celltype_key '{celltype_key}' not found in adata.obs")

    pb_adata, expression_source = _build_count_like_adata(adata)
    pb = aggregate_to_pseudobulk(
        pb_adata,
        sample_key=sample_key,
        celltype_key=celltype_key,
        min_cells=pseudobulk_min_cells,
        min_counts=pseudobulk_min_counts,
        layer=None,
    )
    if pb["counts"].empty:
        raise RuntimeError("Pseudobulk aggregation returned no sample-celltype combinations")

    sample_meta = adata.obs[[sample_key, condition_key]].drop_duplicates().rename(columns={sample_key: "sample"})
    de_results = run_deseq2_analysis(
        pb,
        sample_meta,
        formula="~ condition",
        contrast=["condition", group1, group2],
        celltype_key="celltype",
        use_rpy2=True,
    )
    if not de_results:
        raise RuntimeError("R pseudobulk DESeq2 returned no results")

    frames = []
    for cell_type, df in de_results.items():
        tmp = df.copy()
        tmp["cell_type"] = cell_type
        frames.append(tmp)
    full_df = pd.concat(frames, ignore_index=True)
    n_groups = full_df["cell_type"].nunique() if "cell_type" in full_df.columns else 0
    return full_df, {
        "method": "deseq2_r",
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }


def _run_de_mast(adata, *, groupby: str, group1: str | None, group2: str | None):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for MAST demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export = sc.AnnData(X=adata.X.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = adata.var_names.copy()
    expression_source = "adata.X"
    with tempfile.TemporaryDirectory(prefix="omicsclaw_mast_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_dir = write_matrix_exchange(export, tmpdir / "input", obs_columns=[resolved_groupby])
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        args = [str(input_dir), str(output_dir), resolved_groupby]
        if group1:
            args.append(group1)
        if group2:
            args.append(group2)
        runner.run_script(
            "sc_mast_de.R",
            args=args,
            expected_outputs=["mast_results.csv"],
            output_dir=output_dir,
        )
        full_df = pd.read_csv(output_dir / "mast_results.csv")
    n_groups = full_df["group"].nunique() if "group" in full_df.columns else 0
    return full_df, {
        "method": "mast",
        "groupby": resolved_groupby,
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }

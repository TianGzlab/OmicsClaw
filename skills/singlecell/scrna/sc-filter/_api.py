"""Cell and gene filtering, summaries and a retention figure."""

from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd

from skills.singlecell._lib import qc
from skills.singlecell._lib.adata_utils import (
    canonicalize_singlecell_adata,
    ensure_input_contract,
    infer_qc_species,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
)

__all__ = [
    "filter_cells", "run_info", "filter_summary", "filter_stats_table",
    "retention_table", "filter_state_table", "tissue_presets", "filter_figure",
]

_RUN_KEY = "omicsclaw_sc_filter_run"
_QC_COLUMNS = ("n_genes_by_counts", "total_counts", "pct_counts_mt")


def _prepare(adata):
    species = infer_qc_species(adata)
    original_x_kind = infer_x_matrix_kind(adata)
    had_qc = set(_QC_COLUMNS).issubset(adata.obs.columns)
    if had_qc and original_x_kind == "normalized_expression":
        working = adata.copy()
        ensure_input_contract(
            working,
            standardized=bool(working.uns.get("omicsclaw_input_contract", {}).get("standardized", False)),
        )
        prepared = None
    else:
        working, prepared, _ = canonicalize_singlecell_adata(
            adata, species=species, standardizer_skill="sc-filter",
        )
    working = qc.ensure_qc_metrics(working, species=species, inplace=True)
    preparation = {
        "expression_source": prepared.expression_source if prepared else "existing_object_state",
        "gene_name_source": prepared.gene_name_source if prepared else "existing_var_names",
        "warnings": prepared.warnings if prepared else [],
        "species": species,
    }
    return working, original_x_kind, had_qc, preparation


def filter_cells(
    adata,
    *,
    min_genes: int = 200,
    max_genes: int | None = None,
    min_counts: int | None = None,
    max_counts: int | None = None,
    max_mt_percent: float | None = 20.0,
    min_cells: int = 3,
    tissue: str | None = None,
    remove_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
):
    """Return a filtered copy of an AnnData, with counts and matrix contracts.

    Existing QC columns are reused. Otherwise counts are selected from the
    input's counts layer, raw snapshot or X and missing QC metrics are computed.
    A normalized X with existing QC metrics is preserved. Doublet removal reads
    existing obs columns; it does not run doublet detection.

    :param min_genes: Minimum detected genes per cell. Default 200.
    :param max_genes: Maximum detected genes per cell; None leaves it uncapped.
    :param min_counts: Minimum counts per cell; None disables this threshold.
    :param max_counts: Maximum counts per cell; None disables this threshold.
    :param max_mt_percent: Maximum mitochondrial percentage. Default 20.0;
        None disables the threshold.
    :param min_cells: Minimum retained cells expressing a gene. Default 3.
    :param tissue: Preset from tissue_presets(); overrides min_genes, max_genes
        and max_mt_percent. None uses the supplied thresholds.
    :param remove_doublets: Drop cells marked by predicted_doublet, or by
        doublet_score when the boolean column is absent. Default True.
    :param doublet_score_threshold: Score cutoff for the score-only case. Default 0.25.
    :returns: A new AnnData with retained cells and genes; run_info records
        effective thresholds, the count source and the filtering summary.
    :raises ValueError: Input requiring QC metrics has no count-like matrix.
    """
    working, x_kind, had_qc, preparation = _prepare(adata)
    filtered, summary, params = qc.apply_threshold_filtering(
        working, min_genes=min_genes, max_genes=max_genes,
        min_counts=min_counts, max_counts=max_counts,
        max_mt_percent=max_mt_percent, min_cells=min_cells, tissue=tissue,
        filter_doublets=remove_doublets, doublet_score_threshold=doublet_score_threshold,
    )
    stats = summary["filter_stats"]
    if "outliers_removed" in stats:
        stats["outliers_flagged"] = stats.pop("outliers_removed")
    summary.update(workflow="threshold_filtering", qc_metrics_reused=had_qc,
                   input_preparation=preparation)
    if "counts" in filtered.layers:
        raw = filtered.copy()
        raw.X = filtered.layers["counts"].copy()
        filtered.raw = raw
    input_contract, matrix_contract = propagate_singlecell_contracts(
        working, filtered, producer_skill="sc-filter",
        x_kind=x_kind if x_kind in {"raw_counts", "normalized_expression"} else "raw_counts",
        raw_kind="raw_counts_snapshot" if filtered.raw is not None else None,
    )
    filtered.uns[_RUN_KEY] = json.dumps({
        "summary": summary, "effective_params": params,
        "input_contract": input_contract, "matrix_contract": matrix_contract,
    })
    return filtered


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the filtering record from the returned AnnData.

    :param keep: False removes the record from uns; default True keeps it.
    :returns: summary, effective_params, input_contract and matrix_contract;
        an empty dict when filter_cells has not run. outliers_flagged counts
        existing outlier flags, which do not themselves remove cells.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def filter_summary(adata) -> pd.DataFrame:
    """Return retention counts and effective thresholds as metric/value rows.

    :param adata: The result of filter_cells.
    :returns: A DataFrame matching the CLI's tables/filter_summary.csv.
    """
    info = run_info(adata)
    summary, params = info["summary"], info["effective_params"]
    records = [{"metric": "workflow", "value": "threshold_filtering"}]
    for key in ("n_cells_before", "n_cells_after", "cells_retained_pct",
                "n_genes_before", "n_genes_after", "genes_retained_pct"):
        records.append({"metric": key, "value": summary[key]})
    for key in ("min_genes", "max_genes", "min_counts", "max_counts",
                "max_mt_percent", "min_cells", "tissue"):
        records.append({"metric": key, "value": params[key]})
    records.append({"metric": "qc_metrics_reused", "value": summary["qc_metrics_reused"]})
    return pd.DataFrame(records)


def filter_stats_table(adata) -> pd.DataFrame:
    """Return metric/value rows for threshold removals and existing outlier flags.

    Threshold counts can overlap. outliers_flagged is a count of flags, not
    removals. doublets_removed counts doublets remaining after QC thresholds.
    """
    return pd.DataFrame([
        {"metric": key, "value": value}
        for key, value in run_info(adata)["summary"]["filter_stats"].items()
    ], columns=["metric", "value"])


def retention_table(adata) -> pd.DataFrame:
    """Return Cells and Genes rows with before/after counts from filter_cells."""
    summary = run_info(adata)["summary"]
    return pd.DataFrame([
        {"feature": label, "before": summary[f"n_{key}_before"], "after": summary[f"n_{key}_after"]}
        for label, key in (("Cells", "cells"), ("Genes", "genes"))
    ])


def filter_state_table(before, after) -> pd.DataFrame:
    """Return QC metrics and Retained/Removed labels for every input cell.

    Missing QC columns are calculated on a copy using filter_cells' input
    preparation. The index contains the original cell names.
    """
    prepared, _, _, _ = _prepare(before)
    frame = prepared.obs[[key for key in _QC_COLUMNS if key in prepared.obs]].copy()
    frame["state"] = "Removed"
    frame.loc[frame.index.isin(after.obs_names), "state"] = "Retained"
    return frame


def tissue_presets() -> dict:
    """Return copies of the shared QC presets, including their descriptions.

    Each preset has min_genes, max_genes and max_mt (a percentage). These
    replace the corresponding filter_cells thresholds when tissue is set.
    """
    return {name: deepcopy(qc.get_tissue_qc_thresholds(name))
            for name in ("pbmc", "brain", "tumor", "kidney", "liver", "heart", "default")}


def filter_figure(before, after):
    """Return a matplotlib Figure comparing cell and gene counts before and after filtering."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(7, 3))
    for ax, label, original, retained in (
        (axes[0], "Cells", before.n_obs, after.n_obs),
        (axes[1], "Genes", before.n_vars, after.n_vars),
    ):
        ax.bar(["Before", "After"], [original, retained], color=["#999999", "#4c72b0"])
        ax.set_title(label)
        ax.set_ylabel("count")
    fig.tight_layout()
    return fig

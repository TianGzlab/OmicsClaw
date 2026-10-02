"""sc-qc's function library: per-cell QC metrics and their summaries. No cell is removed.

In a step: ``qc = load_skill("sc-qc")``. The functions compute and return
objects; they read and write no files.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from skills.singlecell._lib import qc as _qc
from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata

__all__ = [
    "calculate_qc",
    "run_info",
    "qc_summary",
    "qc_metrics_table",
    "highest_expressed_genes",
    "barcode_rank_table",
    "qc_correlation_table",
    "qc_figure",
]

_RUN_KEY = "omicsclaw_sc_qc_run"
_METRICS = ("n_genes_by_counts", "total_counts", "pct_counts_mt", "pct_counts_ribo")


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def calculate_qc(adata, *, species: str = "human", calculate_ribo: bool = True):
    """Bring the input into the OmicsClaw scRNA contract and add per-cell QC metrics to ``obs``.

    The count-like matrix becomes ``X`` and ``layers['counts']``, ``raw`` keeps a
    counts snapshot, and gene names are made unique. Then scanpy's
    ``calculate_qc_metrics`` adds ``n_genes_by_counts``, ``total_counts``,
    ``pct_counts_mt`` and ``pct_counts_ribo`` (when the gene prefixes match), plus
    ``log10_total_counts`` and ``log10_n_genes_by_counts``; ``var`` gets ``mt`` and
    ``ribo`` flags. How the input was read is recorded for :func:`run_info`.

    :param species: ``"human"`` (``MT-``, ``RPS``/``RPL`` prefixes) or ``"mouse"``
        (``mt-``, ``Rps``/``Rpl``). Default ``"human"``, the CLI default. Set it to the
        organism of the data: with the wrong one no mitochondrial gene matches and
        ``pct_counts_mt`` is not computed at all.
    :param calculate_ribo: Also compute ``pct_counts_ribo``. Default ``True``, as the CLI does.
    :returns: A new AnnData (the standardized copy), with the metrics in ``obs``.
    :raises ValueError: no count-like matrix can be found in ``X``, ``layers`` or ``raw``.
    """
    processed, prepared, contract = canonicalize_singlecell_adata(
        adata, species=species, standardizer_skill="sc-qc"
    )
    processed.uns["omicsclaw_matrix_contract"] = {
        "X": "raw_counts",
        "raw": "raw_counts_snapshot",
        "layers": {"counts": "raw_counts"},
        "producer_skill": "sc-qc",
    }
    processed = _qc.calculate_qc_metrics(processed, species=species, calculate_ribo=calculate_ribo, inplace=True)
    info = {
        "species": species,
        "calculate_ribo": bool(calculate_ribo),
        "expression_source": prepared.expression_source,
        "gene_name_source": prepared.gene_name_source,
        "warnings": list(prepared.warnings),
        "input_contract": contract,
        "matrix_contract": processed.uns["omicsclaw_matrix_contract"],
        "qc_obs_columns": [
            column
            for column in (*_METRICS, "log10_total_counts", "log10_n_genes_by_counts")
            if column in processed.obs.columns
        ],
    }
    processed.uns[_RUN_KEY] = json.dumps(info, default=_json_default)
    return processed


def run_info(adata, *, keep: bool = True) -> dict:
    """What :func:`calculate_qc` recorded about the input it prepared.

    Keys: ``species``, ``calculate_ribo``, ``expression_source`` (the matrix used
    as counts), ``gene_name_source``, ``warnings``, ``input_contract``,
    ``matrix_contract`` and ``qc_obs_columns``.

    :param keep: Leave the record in ``adata.uns``; ``False`` removes it.
    :returns: The record, or an empty dict when ``calculate_qc`` has not run on *adata*.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def _metrics(adata) -> list[str]:
    return [metric for metric in _METRICS if metric in adata.obs.columns]


def qc_summary(adata) -> pd.DataFrame:
    """One row per QC metric with ``min``, ``max``, ``mean``, ``median``, ``std``, ``q25`` and ``q75``.

    :returns: Columns ``metric``, ``min``, ``max``, ``mean``, ``median``, ``std``, ``q25``,
        ``q75``, for the metrics :func:`calculate_qc` added.
    """
    rows = []
    for metric in _metrics(adata):
        values = adata.obs[metric]
        rows.append({
            "metric": metric,
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "std": float(values.std()),
            "q25": float(values.quantile(0.25)),
            "q75": float(values.quantile(0.75)),
        })
    return pd.DataFrame(rows)


def qc_metrics_table(adata) -> pd.DataFrame:
    """The per-cell QC metrics, one row per cell.

    :returns: Column ``cell_id`` followed by the QC metrics present in ``obs``.
    """
    table = adata.obs.loc[:, _metrics(adata)].copy()
    table.insert(0, "cell_id", adata.obs_names.astype(str))
    return table.reset_index(drop=True)


def highest_expressed_genes(adata, *, n_top: int = 20) -> pd.DataFrame:
    """The genes with the highest mean expression in ``X``.

    A few genes dominating the counts (mitochondrial, ribosomal, MALAT1) point
    to stressed cells or ambient RNA.

    :param n_top: How many genes to return. Default 20, the CLI's table length.
    :returns: Columns ``gene`` and ``mean_expression``, highest first.
    """
    mean_expression = np.asarray(adata.X.mean(axis=0)).ravel()
    table = pd.DataFrame({"gene": adata.var_names.astype(str), "mean_expression": mean_expression})
    return table.sort_values("mean_expression", ascending=False).head(n_top).reset_index(drop=True)


def barcode_rank_table(adata) -> pd.DataFrame:
    """Library sizes ranked from largest to smallest, for a barcode-rank (knee) plot.

    :returns: Columns ``rank``, ``total_counts``, ``log10_rank`` and ``log10_total_counts``.
    :raises KeyError: ``total_counts`` is not in ``obs``; run :func:`calculate_qc` first.
    """
    counts = np.sort(np.asarray(adata.obs["total_counts"], dtype=float))[::-1]
    return pd.DataFrame({
        "rank": np.arange(1, len(counts) + 1),
        "total_counts": counts,
        "log10_rank": np.log10(np.arange(1, len(counts) + 1)),
        "log10_total_counts": np.log10(counts + 1),
    })


def qc_correlation_table(adata, *, metrics: list[str] | None = None) -> pd.DataFrame:
    """Pearson correlations between QC metrics across cells.

    :param metrics: The ``obs`` columns to correlate. Default: the QC metrics present.
    :returns: A square table with a ``metric`` column naming each row.
    """
    columns = list(metrics) if metrics is not None else _metrics(adata)
    corr = adata.obs.loc[:, columns].corr(numeric_only=True)
    corr.index.name = "metric"
    return corr.reset_index()


def qc_figure(adata, *, metrics: list[str] | None = None):
    """Histograms of the QC metrics, one panel per metric, with the median marked.

    :param metrics: The ``obs`` columns to plot. Default: the QC metrics present.
    :returns: A matplotlib Figure.
    """
    import matplotlib.pyplot as plt

    columns = list(metrics) if metrics is not None else _metrics(adata)
    fig, axes = plt.subplots(1, max(len(columns), 1), figsize=(4 * max(len(columns), 1), 3.2), squeeze=False)
    for ax, column in zip(axes[0], columns):
        values = np.asarray(adata.obs[column], dtype=float)
        ax.hist(values, bins=60, color="#4c72b0", alpha=0.85)
        median = float(np.median(values))
        ax.axvline(median, color="#c44e52", linestyle="--", linewidth=1.2, label=f"median {median:.1f}")
        ax.set_title(column)
        ax.set_ylabel("cells")
        ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    return fig

"""Spatial statistics with in-memory results and replayable diagnostics."""
from __future__ import annotations

import inspect
import pandas as pd
from skills.spatial._lib.statistics import ANALYSIS_REGISTRY
from skills.spatial._lib.inference_result import store_info, read_info

__all__ = ["analyze", "run_info", "results_table", "enrichment_figure"]
_RUN_KEY = "omicsclaw_spatial_statistics_run"


def analyze(adata, *, analysis_type: str = "neighborhood_enrichment", random_state: int = 123, **parameters):
    """Run one spatial analysis in place and return the same AnnData.

    Gene analyses read X (log-normalized expression); cluster and network
    analyses read labels, coordinates and spatial_connectivities. Existing
    spatial graphs are reused unless force_graph_rebuild=True.

    :param adata: Spatial AnnData; cluster-aware methods require categorical labels.
    :param analysis_type: CLI default neighborhood_enrichment; also ripley,
        co_occurrence, moran, geary, local_moran, getis_ord, bivariate_moran,
        network_properties or spatial_centrality.
    :param random_state: Permutation/simulation seed, matching CLI default 123.
    :param parameters: Method keyword options from references/parameters.md;
        omitted values retain backend wrapper defaults. Unknown options raise.
    :returns: The same AnnData with JSON-encoded diagnostics and result tables.
    :raises ValueError: Unknown analysis or invalid input.
    :raises TypeError: An option does not belong to the chosen method.
    :raises ImportError: Missing backend; use install_skill_deps with squidpy,
        esda, libpysal or networkx as reported in the error.
    """
    if analysis_type not in ANALYSIS_REGISTRY:
        raise ValueError(f"Unknown analysis_type {analysis_type!r}")
    if "seed" in parameters:
        raise TypeError("Use random_state, not seed, to control permutations")
    func = ANALYSIS_REGISTRY[analysis_type]
    if "n_top_genes" in inspect.signature(func).parameters:
        parameters.setdefault("n_top_genes", 20)
    if "seed" in inspect.signature(func).parameters:
        parameters["seed"] = random_state
    try:
        summary = func(adata, **parameters)
    except ImportError as exc:
        raise ImportError(f"{exc}; use install_skill_deps for spatial-statistics") from exc
    summary["n_cells"] = int(adata.n_obs)
    summary["n_features"] = int(adata.n_vars)
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the analysis diagnostics, including method-specific DataFrames.

    :param adata: AnnData returned by analyze.
    :param keep: True retains the record; False removes it before CLI serialization.
    :returns: Diagnostic dict; encoded tables are restored as DataFrames.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def results_table(adata, *, name: str = "pair_summary_df"):
    """Return a method result table independently of the CLI gallery.

    :param adata: AnnData returned by analyze.
    :param name: Default pair_summary_df for enrichment; results_df for most
        other methods, or zscore_df/count_df/per_cluster_df when present.
    :returns: A DataFrame copy.
    :raises KeyError: The selected analysis has no table with this name.
    """
    table = run_info(adata).get(name)
    if not isinstance(table, pd.DataFrame):
        raise KeyError(f"No result table {name!r}")
    return table.copy()


def enrichment_figure(adata):
    """Plot the neighborhood enrichment z-score matrix.

    :param adata: AnnData after neighborhood_enrichment; expression is not read.
    :returns: A matplotlib Figure without saving it.
    :raises KeyError: No enrichment matrix is available.
    """
    import matplotlib.pyplot as plt
    table = results_table(adata, name="zscore_df")
    fig, ax = plt.subplots()
    artist = ax.imshow(table.to_numpy(), cmap="coolwarm")
    ax.set_xticks(range(len(table.columns)), table.columns, rotation=90)
    ax.set_yticks(range(len(table.index)), table.index)
    fig.colorbar(artist, ax=ax, label="Enrichment z-score")
    fig.tight_layout()
    return fig

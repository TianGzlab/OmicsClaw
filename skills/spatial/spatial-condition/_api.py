"""Compare conditions using biological-sample pseudobulk counts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.spatial._lib.condition import run_condition_comparison
from skills.spatial._lib.inference_result import read_info, store_info

__all__ = ["compare_conditions", "run_info", "results", "volcano_figure"]
_RUN_KEY = "omicsclaw_spatial_condition_run"


def compare_conditions(adata, *, condition_key: str = "condition", sample_key: str = "sample_id",
                       cluster_key: str = "leiden", method: str = "pydeseq2",
                       reference_condition: str | None = None, min_counts_per_gene: int = 10,
                       min_samples_per_condition: int = 2, fdr_threshold: float = .05,
                       log2fc_threshold: float = 1., random_state: int = 0, **parameters):
    """Aggregate counts per sample and cluster, then test conditions in place.

    Both methods use biological-sample pseudobulk, not individual spots.
    PyDESeq2 fitting failures may fall back to Wilcoxon, with warnings and a
    per-contrast fallback record. Missing packages do not trigger fallback.

    :param adata: AnnData with integer counts in layers['counts'], raw, or X,
        in that preference order; each sample belongs to exactly one condition.
    :param condition_key: Condition column, default condition.
    :param sample_key: Biological replicate column, default sample_id.
    :param cluster_key: Cluster column, default leiden; missing leiden is computed.
    :param method: pydeseq2 (default) or pseudobulk wilcoxon.
    :param reference_condition: Reference label; None uses the first sorted condition.
    :param min_counts_per_gene: Minimum total pseudobulk count, default 10.
    :param min_samples_per_condition: Minimum independent replicates, default 2.
    :param fdr_threshold: Adjusted p-value threshold, default 0.05.
    :param log2fc_threshold: Absolute effect threshold for hit summaries, default 1.
    :param random_state: Seed for clustering only if leiden is absent, default 0.
    :param parameters: Backend options retain CLI defaults: pydeseq2_fit_type='parametric',
        pydeseq2_size_factors_fit_type='ratio', pydeseq2_refit_cooks=True,
        pydeseq2_alpha=0.05, pydeseq2_cooks_filter=True,
        pydeseq2_independent_filter=True, pydeseq2_n_cpus=1,
        wilcoxon_alternative='two-sided'.
    :returns: The same AnnData with JSON-encoded tables and diagnostics; results
        returns the DE table and run_info includes skipped contrasts.
    :raises ValueError: Invalid counts, design, cluster column or parameters.
    :raises ImportError: Missing PyDESeq2; use install_skill_deps.
    """
    if condition_key == sample_key:
        raise ValueError("condition_key and sample_key must be different columns")
    if not np.isfinite(log2fc_threshold) or log2fc_threshold < 0:
        raise ValueError("log2fc_threshold must be finite and >= 0")
    if not np.isfinite(fdr_threshold) or not 0 < fdr_threshold <= 1:
        raise ValueError("fdr_threshold must be in (0, 1]")
    if cluster_key not in adata.obs:
        if cluster_key != "leiden":
            raise ValueError(f"Cluster column {cluster_key!r} is absent")
        import scanpy as sc

        if "counts" not in adata.layers and adata.raw is None:
            adata.layers["counts"] = adata.X.copy()
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=min(2000, max(2, adata.n_vars - 1)), flavor="seurat")
        hvg = adata[:, adata.var["highly_variable"]].copy()
        sc.pp.scale(hvg, max_value=10)
        n_comps = max(2, min(50, hvg.n_vars - 1, hvg.n_obs - 1))
        sc.tl.pca(hvg, n_comps=n_comps, random_state=random_state)
        adata.obsm["X_pca"] = hvg.obsm["X_pca"]
        sc.pp.neighbors(adata, n_neighbors=15, n_pcs=min(n_comps, 30), random_state=random_state)
        sc.tl.leiden(adata, resolution=1., flavor="igraph", random_state=random_state)
    summary = run_condition_comparison(
        adata, condition_key=condition_key, sample_key=sample_key,
        cluster_key=cluster_key, method=method, reference_condition=reference_condition,
        min_counts_per_gene=min_counts_per_gene, min_samples_per_condition=min_samples_per_condition,
        fdr_threshold=fdr_threshold, log2fc_threshold=log2fc_threshold, **parameters)
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read comparison diagnostics and result tables.

    :param adata: AnnData returned by compare_conditions.
    :param keep: True retains diagnostics; False removes them for CLI serialization.
    :returns: Summary including global_de, per_cluster_de and skipped contrasts.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def results(adata) -> pd.DataFrame:
    """Return all tested genes across clusters and condition contrasts.

    :param adata: Compared AnnData.
    :returns: DataFrame with gene, log2fc, pvalue_adj, cluster, contrast and sample counts.
        Empty if every contrast was skipped or diagnostics were removed.
    """
    return run_info(adata).get("global_de", pd.DataFrame())


def volcano_figure(adata, *, contrast: str | None = None):
    """Plot log2 fold changes against adjusted p-values.

    :param adata: Compared AnnData.
    :param contrast: Optional exact contrast label; None shows all tested entries.
    :returns: A matplotlib Figure; the caller saves and closes it.
    """
    import matplotlib.pyplot as plt

    table = results(adata)
    if contrast is not None and not table.empty:
        table = table.loc[table["contrast"] == contrast]
    fig, ax = plt.subplots(figsize=(6, 4))
    if not table.empty:
        ax.scatter(table["log2fc"], -np.log10(table["pvalue_adj"].clip(lower=1e-300)), s=8)
    ax.set(xlabel="log2 fold change", ylabel="-log10 adjusted p-value")
    fig.tight_layout()
    return fig

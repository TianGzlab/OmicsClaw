"""Spatial marker discovery and sample-aware differential expression."""
from skills.spatial._lib.inference_result import store_info as save_info, read_info
from skills.spatial._lib.de import run_de, run_pydeseq2

__all__ = ['differential_expression', 'results', 'run_info', 'volcano_figure']
_INFO = '_spatial_de_run_info'


def differential_expression(adata, *, method='wilcoxon', groupby='leiden',
                            group1=None, group2=None, n_top_genes=10,
                            fdr_threshold=0.05, log2fc_threshold=1.0, **parameters):
    """Test groups and return the same AnnData, with results in its diagnostics.

    Scanpy uses raw when present, otherwise log-normalized X. PyDESeq2 uses
    counts, then raw, then X; provide integer counts and biological samples.

    :param adata: Expression and group labels; modified in place.
    :param method: CLI default wilcoxon; t-test or pydeseq2 for other tests.
    :param groupby: CLI default leiden; obs column defining comparisons.
    :param group1: Tested group, or None for each group versus rest.
    :param group2: Reference group; supply together with group1.
    :param n_top_genes: CLI default 10 marker genes per group.
    :param fdr_threshold: CLI default 0.05 adjusted-p-value threshold.
    :param log2fc_threshold: CLI default 1.0 effect-size threshold.
    :param parameters: Method-specific CLI parameters from references/parameters.md.
    :returns: The same AnnData; results returns the full result table.
    :raises ValueError: Groups, method or sample replication are invalid.
    :raises ImportError: PyDESeq2 is unavailable; use install_skill_deps.
    """
    if (group1 is None) != (group2 is None):
        raise ValueError('Supply group1 and group2 together')
    if group1 is not None and str(group1) == str(group2):
        raise ValueError('group1 and group2 must differ')
    if n_top_genes < 1 or not 0 < fdr_threshold <= 1 or log2fc_threshold < 0:
        raise ValueError('Invalid marker count, FDR or fold-change threshold')
    for name in ('min_in_group_fraction', 'max_out_group_fraction'):
        if name in parameters and not 0 <= parameters[name] <= 1:
            raise ValueError(f'{name} must be in [0, 1]')
    for name in ('min_cells_per_sample', 'min_counts_per_gene', 'pydeseq2_n_cpus'):
        if parameters.get(name) is not None and parameters[name] < 1:
            raise ValueError(f'{name} must be positive')
    if parameters.get('min_fold_change', 0) < 0:
        raise ValueError('min_fold_change must be non-negative')
    common = dict(groupby=groupby, group1=group1, group2=group2,
                  n_top_genes=n_top_genes, fdr_threshold=fdr_threshold,
                  log2fc_threshold=log2fc_threshold)
    if method == 'pydeseq2':
        if parameters.get('sample_key', 'sample_id') == groupby:
            raise ValueError('sample_key and groupby must differ')
        if group1 is None:
            raise ValueError('pydeseq2 requires explicit group1 and group2')
        try:
            import pydeseq2
        except ImportError as exc:
            raise ImportError('pydeseq2 is required; use install_skill_deps') from exc
        summary = run_pydeseq2(adata, **common, **parameters)
    else:
        summary = run_de(adata, method=method, **common, **parameters)
    save_info(adata, _INFO, summary)
    return adata


def run_info(adata, *, keep=True):
    """Read diagnostics and the result tables from the most recent run.

    :param adata: AnnData returned by differential_expression.
    :param keep: Default True; False removes diagnostics before CLI serialization.
    :returns: Diagnostic dictionary including full_df and markers_df.
    :raises ValueError: No differential expression run is recorded.
    """
    info = read_info(adata, _INFO, keep=keep)
    if not info:
        raise ValueError('Run differential_expression before requesting its results')
    return info


def results(adata, *, markers_only=False):
    """Return the full or selected marker table without changing expression.

    :param adata: AnnData returned by differential_expression.
    :param markers_only: Default False; True selects the reported top markers.
    :returns: A new DataFrame with method-native effect and significance columns.
    :raises ValueError: No differential expression run is recorded.
    """
    return run_info(adata)['markers_df' if markers_only else 'full_df'].copy()


def volcano_figure(adata, *, group=None):
    """Plot effect size against adjusted significance for one comparison.

    :param adata: AnnData returned by differential_expression.
    :param group: Tested group; None chooses the first reported group.
    :returns: A matplotlib Figure; no files are written.
    :raises ValueError: No results exist for the selected group.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    table = results(adata)
    if group is None and len(table):
        group = table['group'].iloc[0]
    table = table[table['group'].astype(str) == str(group)]
    if table.empty:
        raise ValueError('No results for the requested group')
    x = 'logfoldchanges' if 'logfoldchanges' in table else 'log2fc'
    p = 'pvals_adj' if 'pvals_adj' in table else 'pvalue_adj'
    fig, ax = plt.subplots()
    ax.scatter(table[x], -np.log10(table[p].clip(lower=1e-300)), s=12)
    ax.set(xlabel='Log2 fold change', ylabel='-log10 adjusted p-value', title=str(group))
    return fig

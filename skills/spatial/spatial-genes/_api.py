"""Spatial gene scores on an in-memory AnnData."""
from skills.spatial._lib.inference_result import store_info as save_info, read_info
from skills.spatial._lib.genes import METHOD_DISPATCH

__all__ = ['spatial_genes', 'results', 'run_info', 'ranking_figure']
_INFO = '_spatial_genes_run_info'


def spatial_genes(adata, *, method='morans', n_top_genes=20,
                  fdr_threshold=0.05, random_state=None, **parameters):
    """Compute spatial gene scores and return the same AnnData.

    Moran's I reads X; count-based methods prefer counts, then raw, then X.
    SpatialDE AEH does not expose a seed: results vary between runs.

    :param adata: Expression and spatial coordinates; modified in place.
    :param method: CLI default morans; spatialde, sparkx or flashs also supported.
    :param n_top_genes: CLI default 20 reported significant genes.
    :param fdr_threshold: CLI default 0.05 significance threshold.
    :param random_state: None uses CLI seeds, 0 for Moran's I and 42 for FlashS.
    :param parameters: Method-specific CLI parameters in references/parameters.md.
    :returns: The same AnnData with spatial_genes_results in uns.
    :raises ValueError: Method, thresholds or spatial coordinates are invalid.
    :raises ImportError: A backend is missing; use install_skill_deps.
    """
    if method not in METHOD_DISPATCH:
        raise ValueError(f'Unknown spatial gene method: {method}')
    if n_top_genes < 1 or not 0 < fdr_threshold <= 1:
        raise ValueError('Invalid n_top_genes or fdr_threshold')
    minima = {'n_neighs': 1, 'n_perms': 0, 'min_counts_per_gene': 1,
              'aeh_patterns': 2, 'num_cores': 1, 'n_max_genes': 0,
              'n_rand_features': 1}
    for name, minimum in minima.items():
        value = parameters.get(name)
        if value is not None and value < minimum:
            raise ValueError(f'{name} must be >= {minimum}')
    for name in ('bandwidth', 'aeh_lengthscale'):
        if parameters.get(name) is not None and parameters[name] <= 0:
            raise ValueError(f'{name} must be positive')
    if method in ('morans', 'flashs'):
        parameters['random_state'] = (42 if method == 'flashs' else 0) if random_state is None else random_state
    try:
        table, summary = METHOD_DISPATCH[method](
            adata, n_top_genes=n_top_genes, fdr_threshold=fdr_threshold, **parameters)
    except ImportError as exc:
        package = {'morans': 'squidpy', 'spatialde': 'SpatialDE and NaiveDE',
                   'sparkx': 'R SPARK', 'flashs': 'statsmodels'}[method]
        raise ImportError(f'{package} is required; use install_skill_deps') from exc
    adata.uns['spatial_genes_results'] = table.copy()
    adata.uns['spatial_genes_summary'] = summary.copy()
    save_info(adata, _INFO, summary)
    return adata


def run_info(adata, *, keep=True):
    """Read the most recent spatial-gene diagnostics.

    :param adata: AnnData returned by spatial_genes.
    :param keep: Default True; False removes transient diagnostics for CLI output.
    :returns: Method, thresholds and significant-gene counts.
    :raises ValueError: No run is recorded.
    """
    info = read_info(adata, _INFO, keep=keep)
    if not info:
        raise ValueError('Run spatial_genes before requesting its results')
    return info


def results(adata, *, significant_only=False):
    """Return native spatial-gene scores and significance columns.

    :param adata: AnnData returned by spatial_genes.
    :param significant_only: Default False; True selects the run's FDR threshold.
    :returns: A new DataFrame; score meaning depends on the method.
    :raises ValueError: No run is recorded.
    """
    info = run_info(adata)
    table = adata.uns['spatial_genes_results'].copy()
    if significant_only:
        table = table[table[info['significance_column']] < info['fdr_threshold']]
        if info['method'] == 'morans':
            table = table[table['I'] > 0]
    return table


def ranking_figure(adata, *, n_top=20):
    """Plot the highest-scoring genes without writing files.

    :param adata: AnnData returned by spatial_genes.
    :param n_top: Default 20 genes, matching the CLI report size.
    :returns: A matplotlib Figure.
    :raises ValueError: No run is recorded or n_top is not positive.
    """
    import matplotlib.pyplot as plt

    if n_top < 1:
        raise ValueError('n_top must be positive')
    info = run_info(adata)
    table = results(adata).sort_values(info['score_column'], ascending=False).head(n_top)
    fig, ax = plt.subplots()
    ax.barh(table['gene'].astype(str)[::-1], table[info['score_column']][::-1])
    ax.set_xlabel(info['score_label'])
    return fig

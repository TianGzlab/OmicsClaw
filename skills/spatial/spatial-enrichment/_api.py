"""Spatial group enrichment with explicit gene-set and method diagnostics."""
import warnings

from skills.spatial._lib.inference_result import store_info, read_info
from skills.spatial._lib.enrichment import run_enrichment

__all__ = ['enrich', 'results', 'run_info', 'terms_figure']
_INFO = '_spatial_enrichment_run_info'


def enrich(adata, *, method='enrichr', groupby='leiden', source='omicsclaw_core',
           species='human', gene_sets=None, gene_set=None, gene_set_file=None,
           fdr_threshold=0.05, n_top_terms=20, random_state=123, **parameters):
    """Enrich group markers or score group means and return the same AnnData.

    Marker ranking reads raw when present, otherwise X; ssGSEA reads X and
    scores group means, then copies each group's score to its observations.

    :param adata: Log-normalized expression and group labels; modified in place.
    :param method: CLI default enrichr; gsea or ssgsea also supported.
    :param groupby: CLI default leiden; obs column defining groups.
    :param source: CLI default omicsclaw_core, a small local signature library.
    :param species: CLI default human; mouse changes the built-in symbols.
    :param gene_sets: Explicit mapping of term to gene names; None resolves source.
    :param gene_set: Optional remote library name overriding source.
    :param gene_set_file: Optional local GMT/JSON path; record it with read_input.
    :param fdr_threshold: CLI default 0.05 adjusted significance cutoff.
    :param n_top_terms: CLI default 20 reported terms or attached score columns.
    :param random_state: CLI default 123 for GSEA and ssGSEA backend randomness.
    :param parameters: Method-specific CLI options in references/parameters.md.
    :returns: The same AnnData, with canonical enrichment_results in uns.
    :raises ValueError: Groups, gene sets or numeric thresholds are invalid.
    :raises ImportError: A requested remote library needs gseapy; use install_skill_deps.
    """
    if gene_sets is not None and (gene_set is not None or gene_set_file is not None):
        raise ValueError('Supply gene_sets or a library/file, not both')
    if not 0 < fdr_threshold <= 1 or n_top_terms < 1:
        raise ValueError('Invalid fdr_threshold or n_top_terms')
    if method == 'gsea':
        parameters.setdefault('gsea_seed', random_state)
    elif method == 'ssgsea':
        parameters.setdefault('ssgsea_seed', random_state)
    summary = run_enrichment(
        adata, method=method, groupby=groupby, source=source, species=species,
        gene_sets=gene_sets, gene_set=gene_set, gene_set_file=gene_set_file,
        fdr_threshold=fdr_threshold, n_top_terms=n_top_terms, **parameters)
    reasons = [message for message in summary['warnings'] if 'fell back' in message]
    if reasons:
        table = summary['enrich_df']
        engines = sorted(table['engine'].unique()) if 'engine' in table else []
        fallback = {'enrichr': 'hypergeometric_fallback', 'gsea': 'rank_based_fallback',
                    'ssgsea': 'score_fallback'}[method]
        summary.update(requested_method=method, executed_method=engines or [fallback],
                       fallback_reason='; '.join(reasons))
        warnings.warn(summary['fallback_reason'], RuntimeWarning, stacklevel=2)
    store_info(adata, _INFO, summary)
    return adata


def run_info(adata, *, keep=True):
    """Read enrichment diagnostics, including any executed fallback method.

    :param adata: AnnData returned by enrich.
    :param keep: Default True; False removes transient diagnostics for CLI output.
    :returns: Diagnostic dictionary, including enrich_df and marker_df.
    :raises ValueError: No enrichment run is recorded.
    """
    info = read_info(adata, _INFO, keep=keep)
    if not info:
        raise ValueError('Run enrich before requesting its results')
    return info


def results(adata, *, significant_only=False):
    """Return enrichment results, retaining missing p values for score-only methods.

    :param adata: AnnData returned by enrich.
    :param significant_only: Default False; True selects adjusted p values below FDR.
    :returns: A new DataFrame; ssGSEA scores do not imply significance.
    :raises ValueError: No enrichment run is recorded.
    """
    info = run_info(adata)
    table = info['enrich_df'].copy()
    if significant_only:
        if 'pvalue_adj' not in table:
            return table.iloc[:0].copy()
        table = table[table['pvalue_adj'] <= info['fdr_threshold']]
    return table


def terms_figure(adata, *, n_top=20):
    """Plot available term scores without treating scores as calibrated p values.

    :param adata: AnnData returned by enrich.
    :param n_top: Default 20 rows, matching the CLI report size.
    :returns: A matplotlib Figure; an empty result is labelled explicitly.
    :raises ValueError: No run is recorded or n_top is not positive.
    """
    import matplotlib.pyplot as plt

    if n_top < 1:
        raise ValueError('n_top must be positive')
    table = results(adata).head(n_top)
    fig, ax = plt.subplots()
    if table.empty:
        ax.text(0.5, 0.5, 'No enriched terms', ha='center')
    else:
        column = 'nes' if 'nes' in table and table['nes'].notna().any() else 'score'
        labels = table['group'].astype(str) + ': ' + table['term'].astype(str)
        ax.barh(labels[::-1], table[column][::-1])
        ax.set_xlabel(column)
    return fig

"""Spatial group enrichment with explicit gene-set and method diagnostics."""
import warnings
from pathlib import Path

from skills.spatial._lib.inference_result import store_info, read_info
from skills.spatial._lib.enrichment import (
    run_enrichment, _load_gene_set_file, _resolve_gene_sets, BUILTIN_SOURCES,
)

__all__ = ['read_gene_sets', 'fetch_gene_sets', 'enrich', 'results', 'run_info', 'terms_figure']
_INFO = '_spatial_enrichment_run_info'


class _GeneSets(dict):
    def __init__(self, values, metadata):
        super().__init__(values)
        self.metadata = metadata


def read_gene_sets(path):
    """Read a local GMT or JSON gene-set library without writing files.

    In a step call read_input(path, reader=library.read_gene_sets) to record
    the input file hash and resolve the path relative to the project root.

    :param path: Local GMT or JSON path supplied by read_input or the CLI.
    :returns: Term-to-gene mapping retaining its local source metadata.
    :raises FileNotFoundError: The local file is absent.
    :raises ValueError: The format or JSON structure is invalid.
    """
    values = _load_gene_set_file(path)
    return _GeneSets(values, dict(requested_source=Path(path).name,
        resolved_source=Path(path).name, library_mode='local_file',
        gene_set_file=str(path), warnings=[]))


def fetch_gene_sets(source, *, species='human'):
    """Fetch a remote Enrichr library; this call requires network access.

    Cache the mapping as JSON, then use read_input(path, reader=library.read_gene_sets)
    for repeatable analysis steps. Fetching alone does not record a file hash.

    :param source: Enrichr library name or an alias in references/parameters.md.
    :param species: Default human; mouse is also supported.
    :returns: Term-to-gene mapping retaining requested and resolved library names.
    :raises ValueError: Species or remote source is invalid or unavailable.
    :raises ImportError: gseapy is unavailable; use install_skill_deps.
    """
    if species not in {'human', 'mouse'} or source in BUILTIN_SOURCES:
        raise ValueError('fetch_gene_sets requires a remote source and human or mouse species')
    values, metadata = _resolve_gene_sets(source=source, species=species,
        gene_set=None, gene_set_file=None, var_names=[])
    return _GeneSets(values, metadata)


def enrich(adata, *, method='enrichr', groupby='leiden', source='omicsclaw_core',
           species='human', gene_sets=None, gene_set=None,
           fdr_threshold=0.05, n_top_terms=20, random_state=123, **parameters):
    """Enrich group markers or score group means and return the same AnnData.

    Marker ranking reads raw when present, otherwise X; ssGSEA reads X and
    scores group means, then copies each group's score to its observations.

    :param adata: Log-normalized expression and group labels; modified in place.
    :param method: CLI default enrichr; gsea or ssgsea also supported.
    :param groupby: CLI default leiden; obs column defining groups.
    :param source: CLI default omicsclaw_core; only built-in libraries are resolved here.
    :param species: CLI default human; mouse changes the built-in symbols.
    :param gene_sets: Already-read term-to-gene mapping; None selects the built-in source.
    :param gene_set: Optional built-in library alias overriding source.
    :param fdr_threshold: CLI default 0.05 adjusted significance cutoff.
    :param n_top_terms: CLI default 20 reported terms or attached score columns.
    :param random_state: CLI default 123 for GSEA and ssGSEA backend randomness.
    :param parameters: Method-specific CLI options in references/parameters.md.
    :returns: The same AnnData, with canonical enrichment_results in uns.
    :raises ValueError: Groups, gene sets or numeric thresholds are invalid.
    :raises TypeError: A file path is passed; use read_gene_sets first.
    """
    if 'gene_set_file' in parameters:
        raise TypeError('Use read_gene_sets(path), then pass gene_sets to enrich')
    if gene_sets is not None and gene_set is not None:
        raise ValueError('Supply gene_sets or a library, not both')
    if gene_sets is None and (gene_set or source) not in BUILTIN_SOURCES:
        raise ValueError('Use fetch_gene_sets(source), then pass the mapping as gene_sets')
    if not 0 < fdr_threshold <= 1 or n_top_terms < 1:
        raise ValueError('Invalid fdr_threshold or n_top_terms')
    if method == 'gsea':
        parameters.setdefault('gsea_seed', random_state)
    elif method == 'ssgsea':
        parameters.setdefault('ssgsea_seed', random_state)
    summary = run_enrichment(
        adata, method=method, groupby=groupby, source=source, species=species,
        gene_sets=gene_sets, gene_set=gene_set,
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

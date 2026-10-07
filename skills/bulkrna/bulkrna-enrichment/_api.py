"""Enrichment of supplied differential tests against supplied pathways."""
import numpy as np
from skills.bulkrna._lib.enrichment import core_analysis
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['enrich', 'run_info', 'enrichment_figure']


def enrich(de_results, *, gene_sets, method='ora', padj_cutoff=0.05, lfc_cutoff=1.0, random_state=42):
    """Test pathway enrichment without choosing a reference database.

    :param de_results: DataFrame with gene, log2FoldChange, pvalue and padj.
    :param gene_sets: Nonempty mapping from pathway names to unique gene lists.
    :param method: CLI default ora; gsea runs GSEApy prerank.
    :param padj_cutoff: CLI significance threshold, default 0.05.
    :param lfc_cutoff: Strict absolute fold-change threshold, default 1.0.
    :param random_state: Local permutation seed, legacy default 42.
    :returns: Enrichment DataFrame with execution diagnostics in attrs.
    :raises ValueError: Missing reference, invalid values or unsupported method.
    """
    if method in ('ora_r', 'gsea_r'):
        raise ValueError('The requested R enrichment adapter is not implemented')
    if not isinstance(gene_sets, dict) or not gene_sets:
        raise ValueError('gene_sets must be an explicit nonempty mapping')
    if any(not isinstance(v, (list, tuple)) or not v or len(set(v)) != len(v) for v in gene_sets.values()):
        raise ValueError('gene_sets entries must contain unique, nonempty gene lists')
    required = {'gene', 'log2FoldChange', 'pvalue', 'padj'}
    if required - set(de_results.columns) or de_results.empty:
        raise ValueError('Expected nonempty gene, log2FoldChange, pvalue and padj columns')
    if de_results['gene'].isna().any() or de_results['gene'].duplicated().any():
        raise ValueError('Gene identifiers must be present and unique')
    if not np.isfinite(de_results['log2FoldChange']).all():
        raise ValueError('log2FoldChange must be finite')
    if any(not de_results[c].dropna().between(0, 1).all() for c in ('pvalue', 'padj')):
        raise ValueError('Probabilities must be in [0, 1] or missing')
    if not 0 < padj_cutoff <= 1 or not np.isfinite(lfc_cutoff) or lfc_cutoff < 0:
        raise ValueError('Invalid enrichment thresholds')
    info = core_analysis(de_results.copy(), gene_sets=gene_sets, method=method,
                         padj_cutoff=padj_cutoff, lfc_cutoff=lfc_cutoff, random_state=random_state)
    return attach_info(info['enrichment_df'], info)


def run_info(result, *, keep=True):
    """Read tested terms, pathway universe and requested/executed methods.

    :param result: DataFrame returned by enrich.
    :param keep: Default True; False removes diagnostic attrs.
    :returns: Diagnostic dictionary; empty after removal.
    """
    return read_info(result, keep=keep)


def enrichment_figure(result):
    """Plot pathway adjusted significance without saving it.

    :param result: Enrichment DataFrame with term and padj columns.
    :returns: matplotlib Figure.
    :raises KeyError: Required columns are missing.
    """
    import matplotlib.pyplot as plt
    top = result.sort_values('padj').head(15)
    fig, ax = plt.subplots()
    ax.barh(top['term'], -np.log10(top['padj'].astype(float).clip(lower=1e-300)))
    ax.set(xlabel='-log10 adjusted p', ylabel='Pathway')
    return fig

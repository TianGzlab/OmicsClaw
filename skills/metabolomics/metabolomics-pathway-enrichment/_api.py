"""Metabolite over-representation analysis with explicit reference scope."""
import numpy as np
from skills.metabolomics._lib.pathways import pathway_enrichment, DEMO_METABOLIC_PATHWAYS

__all__ = ['enrich', 'run_info', 'enrichment_figure']


def enrich(data, *, method='ora', pathways=None):
    """Test case-insensitive exact metabolite-name overlap by hypergeometric ORA.

    :param data: Iterable of metabolite names; duplicates count once in each overlap.
    :param method: CLI default ora, the only implemented method.
    :param pathways: Mapping of pathway names to metabolites lists and kegg_id labels; None uses nine demo pathways.
    :returns: A new table; BH FDR covers pathways with at least one hit, matching the CLI.
    :raises ValueError: A requested method is unimplemented or reference is empty.
    """
    if method != 'ora':
        raise ValueError('Only ora is implemented; mummichog and fella require external tools')
    reference = DEMO_METABOLIC_PATHWAYS if pathways is None else pathways
    if not reference or any(not entry.get('metabolites') or 'kegg_id' not in entry for entry in reference.values()):
        raise ValueError('pathways require nonempty metabolites and kegg_id labels')
    values = list(data)
    result = pathway_enrichment(values, method=method, pathways=reference)
    result.attrs['run_info'] = {'method': method, 'n_metabolites': len(values), 'n_pathways_tested': len(reference),
                              'n_significant': int((result['fdr'] < .05).sum()),
                              'reference_scope': 'demo' if pathways is None else 'provided',
                              'fdr_family': 'pathways_with_overlap'}
    return result


def enrichment_figure(data, *, n_top=10):
    """Plot the strongest pathway overlaps by adjusted p value.

    :param data: Results returned by enrich.
    :param n_top: Default 10; maximum number of pathways shown.
    :returns: A matplotlib Figure.
    :raises KeyError: pathway or fdr is absent.
    """
    from matplotlib.figure import Figure
    rows = data.sort_values('fdr').head(n_top).iloc[::-1]
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    ax.barh(rows['pathway'], -np.log10(rows['fdr'].clip(lower=np.finfo(float).tiny)))
    ax.set_xlabel('-log10(FDR)')
    fig.tight_layout()
    return fig


def run_info(data, *, keep=True):
    """Read diagnostics attached to a returned table.

    :param data: DataFrame returned by this library.
    :param keep: Default True; use False in the CLI to remove diagnostics.
    :returns: An independent dictionary describing the run.
    :raises ValueError: The table carries no run_info.
    """
    from skills.metabolomics._lib.library import run_info as read
    return read(data, keep=keep)

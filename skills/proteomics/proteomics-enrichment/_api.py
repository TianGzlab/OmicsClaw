"""Protein-set over-representation against caller-supplied pathways."""
import pandas as pd
from skills.proteomics._lib import enrichment as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['enrich', 'run_info', 'enrichment_figure', 'demo_data', 'demo_pathways']


def enrich(genes: list[str], *, pathway_db: dict | None = None,
           background_size: int | None = None, method: str = 'ora') -> pd.DataFrame:
    """Run one-sided Fisher tests with BH correction against an explicit pathway library.

    :param genes: Protein or gene identifiers in the same identifier space as pathway_db.
    :param pathway_db: Required pathway-to-member mapping; no default biological database is assumed.
    :param background_size: CLI default None uses the input/library union plus at least one background-only member.
    :param method: CLI default ora is the only implemented method.
    :returns: Ranked pathway overlaps, odds ratios and adjusted p values.
    :raises ValueError: The library is absent, the method is invalid, or the background is too small.
    """
    if not pathway_db:
        raise ValueError('An explicit nonempty pathway_db is required; demo_pathways is synthetic example data')
    if method != 'ora':
        raise ValueError('Only ora is supported')
    genes = list(genes)
    if not genes or not all(isinstance(g, str) and g for g in genes):
        raise ValueError('genes must contain nonempty string identifiers')
    union = set(g.upper() for g in genes)
    for members in pathway_db.values():
        if not members or not all(isinstance(g, str) and g for g in members):
            raise ValueError('Every pathway must contain nonempty string identifiers')
        union.update(g.upper() for g in members)
    if background_size is not None and (not isinstance(background_size, int) or background_size < len(union)):
        raise ValueError('background_size must be an integer covering all input and pathway identifiers')
    result = core.enrichment_analysis(genes, background_size=background_size, pathway_db=pathway_db, method=method)
    return attach(result, library_source='caller', background_size=background_size,
                  summary={'n_input_genes':len(genes),'n_pathways_tested':len(pathway_db),
                           'n_significant':int((result['fdr'] < .05).sum()), 'method':method})


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read enrichment diagnostics.

    :param table: Output of enrich.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate dictionary with library provenance and summary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def enrichment_figure(table: pd.DataFrame, *, top_n: int = 10):
    """Plot leading pathways by enrichment ratio.

    :param table: Enrichment results sorted by p value.
    :param top_n: Display ten pathways by default; change for a larger result table.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: pathway or enrichment_ratio is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7,4))
    ax = fig.subplots()
    selected = table.head(top_n).iloc[::-1]
    ax.barh(selected['pathway'], selected['enrichment_ratio'])
    ax.set(xlabel='Enrichment ratio')
    fig.tight_layout()
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate a synthetic significant-protein list.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Eighteen example identifiers with simulated statistics.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)


def demo_pathways() -> dict:
    """Return the eight small illustrative pathway sets used by --demo.

    :returns: A separate mapping, not a production pathway database.
    :raises RuntimeError: No runtime failures are expected.
    """
    return {name:list(members) for name,members in core.DEMO_PATHWAYS.items()}

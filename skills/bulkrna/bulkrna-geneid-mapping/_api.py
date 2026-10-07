"""Gene identifier conversion with explicit local references and network queries."""
import pandas as pd
from skills.bulkrna._lib.geneid import _DEMO_MAPPING, map_gene_ids, _try_mygene_mapping, _strip_version
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['map_ids', 'fetch_mapping', 'mapping_table', 'run_info', 'mapping_figure']


def map_ids(data, *, from_type='ensembl', to_type='symbol', species='human', on_duplicate='sum', mapping=None):
    """Map count-matrix row identifiers without network or file access.

    :param data: Gene-by-sample counts; the row index contains source IDs.
    :param from_type: CLI default ensembl; entrez and symbol are also supported.
    :param to_type: CLI default symbol; target namespace.
    :param species: CLI default human; mouse requires an explicit reference.
    :param on_duplicate: CLI default sum; first or drop resolve target collisions differently.
    :param mapping: Optional source/target DataFrame; None uses ten human demo genes only.
    :returns: A new mapped DataFrame with reference scope, mapping records and summary diagnostics.
    :raises ValueError: Namespaces, duplicate policy or reference data are invalid.
    """
    if from_type not in ('ensembl', 'entrez', 'symbol') or to_type not in ('ensembl', 'entrez', 'symbol'):
        raise ValueError('Namespaces must be ensembl, entrez or symbol')
    if on_duplicate not in ('sum', 'first', 'drop'):
        raise ValueError('on_duplicate must be sum, first or drop')
    if data.empty:
        raise ValueError('Provide a nonempty count matrix')
    if mapping is None:
        if species != 'human':
            raise ValueError('A non-human species requires an explicit mapping reference')
        rows = [dict(ensembl=ensembl, **info) for ensembl, info in _DEMO_MAPPING.items()]
        reference = {row[from_type]: row[to_type] for row in rows}
    else:
        if not {'source', 'target'}.issubset(mapping) or mapping[['source', 'target']].isna().any().any():
            raise ValueError('mapping requires nonmissing source and target columns')
        if mapping.source.astype(str).duplicated().any():
            raise ValueError('mapping source identifiers must be unique')
        reference = dict(zip(mapping.source.astype(str), mapping.target.astype(str)))
    counts = data.copy()
    counts.index = counts.index.astype(str)
    result, info = map_gene_ids(counts, from_type, to_type, species, on_duplicate, reference)
    return attach_info(result, {**info['summary'], 'summary': info['summary'],
                               'mapping_records': info['mapping_df'].to_dict('records'),
                               'reference_scope': 'demo' if mapping is None else 'provided'})


def fetch_mapping(data, *, from_type='ensembl', to_type='symbol', species='human'):
    """Query MyGene explicitly and return a local source/target mapping table.

    :param data: Iterable of identifiers to send to the public MyGene service.
    :param from_type: Default ensembl; source namespace.
    :param to_type: Default symbol; requested target namespace.
    :param species: Default human; MyGene species selector.
    :returns: A DataFrame containing only identifiers for which MyGene returned a match.
    :raises ImportError: Install mygene with install_skill_deps if unavailable.
    :raises Exception: Network or service errors propagate; no demo substitute is returned.
    """
    identifiers = [_strip_version(str(value)) for value in data]
    mapped = _try_mygene_mapping(identifiers, from_type, to_type, species)
    return pd.DataFrame(mapped.items(), columns=['source', 'target'])


def mapping_table(data):
    """Return the original-to-target mapping decisions for every input row.

    :param data: Mapped count matrix returned by map_ids.
    :returns: A new DataFrame with original_id, stripped_id, mapped_id and was_mapped.
    :raises KeyError: The count matrix has no mapping diagnostics.
    """
    return pd.DataFrame(read_info(data)['mapping_records'])


def run_info(data, *, keep=True):
    """Read mapping diagnostics without modifying the count values.

    :param data: Mapped counts returned by map_ids.
    :param keep: Default True; the CLI removes diagnostics with False.
    :returns: An independent diagnostic dictionary.
    :raises TypeError: data is not a DataFrame.
    """
    return read_info(data, keep=keep)


def mapping_figure(data):
    """Plot mapped and unmapped source-row counts.

    :param data: Count matrix returned by map_ids.
    :returns: A matplotlib Figure; no files are written.
    :raises KeyError: Mapping diagnostics are absent.
    """
    from matplotlib.figure import Figure
    info = read_info(data)
    fig = Figure(figsize=(5, 3))
    ax = fig.subplots()
    ax.bar(['Mapped', 'Unmapped'], [info['n_mapped'], info['n_unmapped']])
    ax.set_ylabel('Input genes')
    return fig

"""PPI network analysis with explicit STRING acquisition."""
from io import StringIO
import numpy as np
import pandas as pd
from skills.bulkrna._lib.ppi import _build_adjacency, _compute_centrality, _spring_layout
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['analyze', 'fetch_interactions', 'run_info', 'network_figure', 'hubs_figure']


def _graph(edges, genes, induced=False):
    if not {'gene_a', 'gene_b', 'score'}.issubset(edges):
        raise ValueError('Edges require gene_a, gene_b and score columns')
    if edges[['gene_a', 'gene_b', 'score']].isna().any().any():
        raise ValueError('Edges cannot contain missing endpoints or scores')
    nodes = list(dict.fromkeys(genes if genes is not None else list(edges.gene_a) + list(edges.gene_b)))
    if not nodes:
        raise ValueError('Provide at least one gene')
    selected = edges[edges.gene_a.isin(nodes) & edges.gene_b.isin(nodes)].copy() if induced else edges.copy()
    return nodes, selected, _build_adjacency(selected, nodes)


def analyze(data, *, genes=None, induced=False):
    """Rank query nodes using the CLI's unweighted neighborhood convention.

    :param data: Interaction DataFrame with gene_a, gene_b and score columns; scores do not weight centrality.
    :param genes: Optional gene list including isolates; None uses all edge endpoints.
    :param induced: Default False preserves external neighbors in degree/closeness; True restricts edges to genes.
    :returns: A node-centrality DataFrame with degree, betweenness, closeness and hub_score.
    :raises ValueError: Edge columns or the node list are invalid.
    """
    nodes, selected, adjacency = _graph(data, genes, induced)
    result = _compute_centrality(adjacency)
    connected = sum(bool(adjacency[g]) for g in nodes)
    info = {'n_genes': len(nodes), 'n_edges': len(selected), 'n_connected': connected,
            'n_isolated': len(nodes) - connected, 'mean_degree': round(float(np.mean([len(adjacency[g]) for g in nodes])), 2)}
    return attach_info(result, info)


def fetch_interactions(data, *, species=9606, score_threshold=400):
    """Query STRING explicitly; unavailable or malformed responses raise.

    :param data: Gene identifiers sent to the public STRING service.
    :param species: CLI default 9606 (human); NCBI taxonomy identifier.
    :param score_threshold: CLI default 400; integer confidence cutoff from 0 to 1000.
    :returns: A DataFrame with gene_a, gene_b and scores on STRING's 0 to 1 scale.
    :raises ImportError: Install requests with install_skill_deps if unavailable.
    :raises ValueError: Parameters or response columns are invalid.
    :raises Exception: Network and HTTP failures propagate without demo fallback.
    """
    if not isinstance(score_threshold, int) or not 0 <= score_threshold <= 1000:
        raise ValueError('score_threshold must be an integer in [0, 1000]')
    if not isinstance(species, int) or species <= 0:
        raise ValueError('species must be a positive taxonomy integer')
    try:
        import requests
    except ImportError as exc:
        raise ImportError('Install requests with install_skill_deps for STRING queries') from exc
    response = requests.get('https://string-db.org/api/tsv/network', params={
        'identifiers': '\r'.join(map(str, data)), 'species': species,
        'required_score': score_threshold, 'caller_identity': 'OmicsClaw'}, timeout=30)
    response.raise_for_status()
    if not response.text.strip():
        return pd.DataFrame(columns=['gene_a', 'gene_b', 'score'])
    table = pd.read_csv(StringIO(response.text), sep='\t')
    columns = ['preferredName_A', 'preferredName_B', 'score']
    if not set(columns).issubset(table):
        raise ValueError('STRING response lacks interaction columns')
    result = table[columns].copy()
    result.columns = ['gene_a', 'gene_b', 'score']
    return result[result.score >= score_threshold / 1000.].reset_index(drop=True)


def run_info(data, *, keep=True):
    """Read topology diagnostics attached to the node table.

    :param data: Centrality DataFrame returned by analyze.
    :param keep: Default True; the CLI removes diagnostics with False.
    :returns: An independent summary dictionary.
    :raises TypeError: data is not a DataFrame.
    """
    return read_info(data, keep=keep)


def network_figure(data, *, genes=None, random_state=42):
    """Draw a seeded spring layout without changing numpy's global random state.

    :param data: Edge DataFrame accepted by analyze.
    :param genes: Optional gene list including isolates; None uses edge endpoints.
    :param random_state: CLI default 42; spring-layout initialization seed.
    :returns: A matplotlib Figure.
    :raises ValueError: Edges or node list are invalid.
    """
    from matplotlib.figure import Figure
    nodes, edges, adjacency = _graph(data, genes)
    positions = _spring_layout(adjacency, nodes, random_state=random_state)
    fig = Figure(figsize=(7, 6))
    ax = fig.subplots()
    for row in edges.itertuples(index=False):
        if row.gene_a not in positions or row.gene_b not in positions:
            continue
        a, b = positions[row.gene_a], positions[row.gene_b]
        ax.plot([a[0], b[0]], [a[1], b[1]], color='lightgray', zorder=1)
    for gene in nodes:
        ax.scatter(*positions[gene], zorder=2)
        ax.annotate(gene, positions[gene], fontsize=7)
    ax.axis('off')
    return fig


def hubs_figure(data, *, top_n=20):
    """Plot the highest-ranked hub scores.

    :param data: Centrality table returned by analyze.
    :param top_n: CLI default 20; maximum number of nodes shown.
    :returns: A matplotlib Figure.
    :raises KeyError: gene or hub_score is absent.
    """
    from matplotlib.figure import Figure
    rows = data.head(top_n).iloc[::-1]
    fig = Figure(figsize=(7, 4))
    ax = fig.subplots()
    ax.barh(rows.gene, rows.hub_score)
    ax.set_xlabel('Hub score')
    return fig

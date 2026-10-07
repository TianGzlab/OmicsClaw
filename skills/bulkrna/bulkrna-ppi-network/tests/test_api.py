import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_three_node_chain_has_known_centrality_and_preserves_isolates():
    library = load_skill('bulkrna-ppi-network')
    edges = pd.DataFrame({'gene_a': ['A', 'B'], 'gene_b': ['B', 'C'], 'score': [.9, .8]})
    result = library.analyze(edges, genes=['A', 'B', 'C', 'D'])
    table = result.set_index('gene')
    assert table.loc['B', 'degree'] == 2
    assert table.loc['B', 'betweenness'] == pytest.approx(1 / 3, abs=1e-6)
    assert table.loc['D', 'degree'] == 0
    assert library.run_info(result)['n_isolated'] == 1
    assert library.hubs_figure(result).axes
    assert library.network_figure(edges, genes=['A', 'B', 'C', 'D']).axes


def test_fetch_failure_does_not_return_demo_edges(monkeypatch):
    import requests
    def fail(*args, **kwargs):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests, 'get', fail)
    with pytest.raises(requests.ConnectionError, match='offline'):
        load_skill('bulkrna-ppi-network').fetch_interactions(['TP53', 'MDM2'])


def test_query_neighborhood_default_and_explicit_induced_subgraph():
    edges = pd.DataFrame({'gene_a': ['A', 'A'], 'gene_b': ['B', 'outside'], 'score': [.9, .8]})
    library = load_skill('bulkrna-ppi-network')
    neighborhood = library.analyze(edges, genes=['A', 'B'])
    assert neighborhood.set_index('gene').loc['A', 'degree'] == 2
    result = library.analyze(edges, genes=['A', 'B'], induced=True)
    assert result['degree'].tolist() == [1, 1]

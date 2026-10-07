import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_explicit_pathways_use_supplied_background():
    lib = load_skill('bulkrna-enrichment')
    data = pd.DataFrame({'gene': ['a', 'b', 'c'], 'log2FoldChange': [3., 2., 0.],
                         'pvalue': [.001, .002, .8], 'padj': [.003, .004, .8]})
    original = data.copy(deep=True)
    result = lib.enrich(data, gene_sets={'target': ['a', 'b'], 'background': list('abcdefghij')})
    info = lib.run_info(result)
    assert info['background_genes'] == 10
    assert info['query_genes_in_background'] == 2
    assert result.set_index('term').loc['target', 'pvalue'] == pytest.approx(1 / 45)
    pd.testing.assert_frame_equal(data, original)


def test_real_input_cannot_silently_use_demo_pathways():
    lib = load_skill('bulkrna-enrichment')
    data = pd.DataFrame({'gene': ['TP53'], 'log2FoldChange': [3.], 'pvalue': [.001], 'padj': [.01]})
    with pytest.raises(ValueError, match='gene_sets'):
        lib.enrich(data, gene_sets={})
    with pytest.raises(ValueError, match='not implemented'):
        lib.enrich(data, gene_sets={'p': ['TP53']}, method='ora_r')

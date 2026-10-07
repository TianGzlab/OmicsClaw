"""Bulk differential expression through the public library."""
import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_ttest_retains_effect_direction_and_filtered_gene_count():
    counts = pd.DataFrame({'ctrl_1': [10, 100, 0], 'ctrl_2': [12, 120, 0], 'ctrl_3': [11, 110, 0],
                           'treat_1': [100, 10, 0], 'treat_2': [120, 12, 0], 'treat_3': [110, 11, 0]},
                          index=['up', 'down', 'zero'])
    api = load_skill('bulkrna-de')
    result = api.differential_expression(counts, method='ttest')
    indexed = result.set_index('gene')
    assert indexed.loc['up', 'log2FoldChange'] > 3
    assert indexed.loc['down', 'log2FoldChange'] < -3
    assert api.run_info(result)['n_genes_prefiltered'] == 1
    assert indexed['padj'].between(0, 1).all()


def test_transformed_counts_are_rejected():
    with pytest.raises(ValueError, match='integers'):
        load_skill('bulkrna-de').differential_expression(pd.DataFrame({'ctrl_1': [1.5], 'treat_1': [2.5]}), method='ttest')


@pytest.mark.requires_r
def test_real_deseq2_runs_on_overdispersed_counts_without_fallback():
    rng = np.random.default_rng(17)
    means = rng.lognormal(4, 1, 400)
    counts = rng.negative_binomial(5, 5 / (5 + means[:, None]), size=(400, 12))
    counts[:30, 6:] *= 4
    data = pd.DataFrame(counts, index=[f'g{i}' for i in range(400)],
                        columns=[f'ctrl_{i}' for i in range(6)] + [f'treat_{i}' for i in range(6)])
    api = load_skill('bulkrna-de')
    try:
        result = api.differential_expression(data)
    except ImportError as exc:
        pytest.skip(str(exc))
    info = api.run_info(result)
    assert info['executed_method'] == 'deseq2'
    assert info['fallback_reason'] is None
    assert result['padj'].notna().any()
    assert result.loc[result.gene.isin([f'g{i}' for i in range(30)]), 'log2FoldChange'].median() > 1

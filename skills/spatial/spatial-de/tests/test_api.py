"""Differential expression through the function interface used by steps."""
import numpy as np
import pytest
import scanpy as sc
from anndata import AnnData
from skills._sdk.notebook import load_skill


def expression():
    rng = np.random.default_rng(7)
    counts = rng.poisson(2, (40, 12)).astype(float)
    counts[:20, 0] += 30
    counts[20:, 1] += 30
    data = AnnData(counts)
    data.var_names = ['marker_A', 'marker_B'] + [f'g{i}' for i in range(10)]
    data.obs['leiden'] = ['A'] * 20 + ['B'] * 20
    data.layers['counts'] = counts.copy()
    sc.pp.normalize_total(data)
    sc.pp.log1p(data)
    return data


def test_pairwise_markers_preserve_expression_and_report_direction():
    library = load_skill('spatial-de')
    data = expression()
    before = data.X.copy()
    assert library.differential_expression(data, group1='A', group2='B') is data
    np.testing.assert_array_equal(data.X, before)
    table = library.results(data)
    marker = table.set_index('names').loc['marker_A']
    assert marker['logfoldchanges'] > 2
    assert marker['pvals_adj'] < 0.01
    assert library.run_info(data)['comparison_mode'] == 'pairwise'


@pytest.mark.parametrize('options', [{'group1': 'A'}, {'group1': 'A', 'group2': 'A'},
                                    {'method': 'unknown'}, {'fdr_threshold': 0},
                                    {'method': 'pydeseq2'},
                                    {'method': 'pydeseq2', 'group1': 'A', 'group2': 'B',
                                     'sample_key': 'leiden'},
                                    {'min_in_group_fraction': -1}])
def test_invalid_comparisons_are_rejected(options):
    with pytest.raises(ValueError):
        load_skill('spatial-de').differential_expression(expression(), **options)


def test_diagnostics_are_removable_and_figure_has_real_points():
    import matplotlib.pyplot as plt
    library = load_skill('spatial-de')
    data = expression()
    library.differential_expression(data)
    fig = library.volcano_figure(data, group='A')
    assert len(fig.axes[0].collections[0].get_offsets()) == data.n_vars
    plt.close(fig)
    assert library.run_info(data, keep=False)['method'] == 'wilcoxon'
    with pytest.raises(ValueError):
        library.run_info(data)

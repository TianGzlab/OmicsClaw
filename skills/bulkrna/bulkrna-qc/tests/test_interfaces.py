"""Notebook-facing calculations return data and figures without writing outputs."""
import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


@pytest.mark.parametrize('name', ['qc', 'de', 'deconvolution', 'splicing', 'enrichment', 'cosinor-rhythm'])
def test_calculation_figure_and_diagnostics_are_isolated(name, tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    monkeypatch.chdir(tmp_path)
    api = load_skill('bulkrna-' + name)
    counts = pd.DataFrame({'ctrl_1': [1, 10], 'ctrl_2': [2, 11],
                           'treat_1': [10, 1], 'treat_2': [11, 2]}, index=['a', 'b'])
    state = np.random.get_state()
    if name == 'qc':
        result = api.assess(counts)
        figure = api.library_figure(result)
    elif name == 'de':
        result = api.differential_expression(counts, method='ttest')
        figure = api.volcano_figure(result)
    elif name == 'deconvolution':
        result = api.deconvolve(counts, signature=pd.DataFrame({'A': [1, 0], 'B': [0, 1]}, index=counts.index))
        figure = api.proportions_figure(result)
    elif name == 'splicing':
        result = api.summarize(pd.DataFrame({'gene': ['a'], 'event_type': ['SE'], 'delta_psi': [.3], 'padj': [.01]}))
        figure = api.volcano_figure(result)
    elif name == 'enrichment':
        result = api.enrich(pd.DataFrame({'gene': ['a', 'b'], 'log2FoldChange': [3., 2.],
                                         'pvalue': [.001, .002], 'padj': [.01, .02]}),
                            gene_sets={'target': ['a', 'b'], 'background': list('abcdefghij')})
        figure = api.enrichment_figure(result)
    else:
        result = api.fit(pd.DataFrame({'T00_R1': [10], 'T06_R1': [13], 'T12_R1': [10], 'T18_R1': [7]}, index=['a']))
        figure = api.rhythm_figure(result)
    assert figure.axes
    plt.close(figure)
    after = np.random.get_state()
    assert state[0] == after[0] and np.array_equal(state[1], after[1]) and state[2:] == after[2:]
    info = api.run_info(result)
    assert info
    info['caller_only'] = True
    assert 'caller_only' not in api.run_info(result)
    assert api.run_info(result, keep=False)
    assert api.run_info(result) == {}
    assert not list(tmp_path.iterdir())

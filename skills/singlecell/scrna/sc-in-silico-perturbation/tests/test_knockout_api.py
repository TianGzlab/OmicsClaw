"""Correlation scores have no calibrated significance or causal interpretation."""

import numpy as np
import pytest
from anndata import AnnData

from skills._sdk.notebook import load_skill


def test_correlation_scores_are_exact_and_do_not_fabricate_pvalues():
    api = load_skill('sc-in-silico-perturbation')
    adata = AnnData(np.array([[1, 2, 4], [2, 4, 3], [3, 6, 2], [4, 8, 1]], dtype=float))
    adata.var_names = ['KO', 'positive', 'negative']
    result = api.knockout_correlation(adata, ko_gene='KO', n_top_genes=3)
    assert not {'p_value', 'p.adj', 'z_score', 'FC'} & set(result.columns)
    np.testing.assert_allclose(result.set_index('gene').loc[['KO', 'positive', 'negative'], 'dr_score'], [1, 1/3, 1/3])
    assert api.top_perturbed_genes(result, n_top=1)['gene'].tolist() == ['KO']
    assert 'correlation' in api.run_info(result)['interpretation'].lower()
    assert 'p' not in adata.var
    with pytest.raises(ValueError, match='missing'):
        api.knockout_correlation(adata, ko_gene='missing')


def test_r_backend_uses_csv_arguments_and_seed(monkeypatch):
    from pathlib import Path
    import pandas as pd
    from skills._sdk.r_script_runner import RScriptRunner

    api = load_skill('sc-in-silico-perturbation')
    adata = AnnData(np.arange(12).reshape(4, 3).astype(float))
    adata.var_names = ['KO', 'G2', 'G3']

    def run(self, script, *, args, output_dir, **kwargs):
        assert Path(script).name == 'sc_sctenifoldknk.R'
        matrix = pd.read_csv(args[0], index_col=0)
        assert matrix.shape == (3, 4)
        assert args[2] == 'KO' and args[-1] == '17'
        pd.DataFrame({'gene': ['G2'], 'FC': [2.], 'p.adj': [.01]}).to_csv(args[1], index=False)

    monkeypatch.setattr(RScriptRunner, 'run_script', run)
    result = api.sctenifoldknk(adata, ko_gene='KO', random_state=17)
    assert result['p.adj'].tolist() == [.01]

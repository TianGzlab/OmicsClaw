"""Target-expression averages are not predictions of drug response."""

import numpy as np
import pytest
from anndata import AnnData

from skills._sdk.notebook import load_skill


def test_score_is_mean_expression_and_copies_inputs():
    api = load_skill('sc-drug-response')
    adata = AnnData(np.array([[1., 3.], [3., 5.], [5., 7.]]))
    adata.var_names = ['EGFR', 'BRAF']
    adata.obs['group'] = ['A', 'A', 'B']
    result = api.score_drug_targets(adata, cluster_key='group', drug_targets={'example': ['EGFR', 'BRAF']})
    assert 'Score' not in result and 'mean_target_expression' in result
    assert result.set_index('Cluster')['mean_target_expression'].to_dict() == {'A': 3., 'B': 6.}
    assert api.top_drugs(result, n_top=1)['Drug'].tolist() == ['example']
    assert list(adata.obs.columns) == ['group']
    targets = api.builtin_drug_targets()
    first = next(iter(targets))
    targets[first].clear()
    assert api.builtin_drug_targets()[first]


def test_cadrres_requires_explicit_local_models(tmp_path):
    api = load_skill('sc-drug-response')
    adata = AnnData(np.ones((3, 2)))
    adata.obs['group'] = ['A'] * 3
    with pytest.raises(FileNotFoundError, match='model'):
        api.cadrres(adata, cluster_key='group', model_dir=tmp_path)


def test_cadrres_honors_group_and_keeps_model_directory_read_only(tmp_path, monkeypatch):
    import pandas as pd
    import sys
    import types
    from pathlib import Path

    models = tmp_path / 'models'
    models.mkdir()
    names = ['cadrres-wo-sample-bias_param_dict_all_genes.pickle', 'masked_drugs.csv']
    for name in names:
        (models / name).write_text('backend fixture')
    (tmp_path / 'CaDRReS-Sc').mkdir()
    adata = AnnData(np.ones((4, 2)))
    adata.obs['group'] = ['A', 'A', 'B', 'B']
    adata.obs['louvain'] = ['old'] * 4

    def backend(**kwargs):
        assert kwargs['adata'].obs['louvain'].tolist() == ['A', 'A', 'B', 'B']
        output = Path(kwargs['output'])
        assert not output.is_relative_to(models)
        table = pd.DataFrame([[1.], [2.]], index=['A', 'B'],
                             columns=pd.MultiIndex.from_tuples([('id1', 'example')]))
        table.to_csv(output / 'IC50_prediction.csv')

    module = types.ModuleType('omicverse.single._scdrug')
    module.Drug_Response = backend
    monkeypatch.setitem(sys.modules, 'omicverse.single._scdrug', module)
    result = load_skill('sc-drug-response').cadrres(adata, cluster_key='group', model_dir=models)
    assert result['Score'].tolist() == [1., 2.]
    assert set(path.name for path in models.iterdir()) == set(names)
    assert adata.obs['louvain'].tolist() == ['old'] * 4

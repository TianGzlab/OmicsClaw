import numpy as np
from skills._sdk.notebook import load_skill, load_demo


def test_synthetic_abundance_detects_enriched_type():
    api = load_skill('sc-differential-abundance')
    data = load_demo('multisample_synthetic')
    table = api.test_abundance(data, method='simple')
    enriched = table.set_index('cell_type').loc['Enriched']
    assert enriched['significant'] and enriched['log2fc_group_b_over_a'] > 1
    counts, proportions = api.composition(data, sample_key='sample', celltype_key='cell_type', condition_key='condition')
    assert counts.shape == (8, 3)
    np.testing.assert_allclose(proportions.sum(axis=1), 1)
    assert api.run_info(table)['executed_method'] == 'simple'


def test_milo_fallback_records_import_error_without_mutation(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path
    from scipy import sparse
    path = Path(__file__).parents[1] / '_api.py'
    spec = importlib.util.spec_from_file_location('abundance_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    find_spec = importlib.util.find_spec
    monkeypatch.setitem(sys.modules, 'pertpy', None)
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name, *args, **kwargs:
        None if name == 'pertpy' else find_spec(name, *args, **kwargs))
    data = load_demo('multisample_synthetic')
    data.uns['neighbors'] = {}
    data.obsm['X_umap'] = np.zeros((data.n_obs, 2))
    data.obsp['distances'] = sparse.eye(data.n_obs, format='csr')
    before = data.obs.copy()
    table = module.test_abundance(data, prop=.01)
    info = module.run_info(table)
    assert info['executed_method'] == 'milo_like'
    assert info['fallback_used'] and 'pertpy' in info['fallback_reason']
    assert data.obs.equals(before)

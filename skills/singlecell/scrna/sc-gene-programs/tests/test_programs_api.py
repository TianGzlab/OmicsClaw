import numpy as np
import pandas as pd
import anndata as ad
from skills._sdk.notebook import load_skill


def test_programs_are_reproducible_and_do_not_mutate_input():
    api = load_skill('sc-gene-programs')
    data = ad.AnnData(np.random.default_rng(8).uniform(size=(24, 12)))
    result = api.find_programs(data, method='nmf', n_programs=3)
    repeated = api.find_programs(data, method='nmf', n_programs=3)
    assert 'X_gene_programs' not in data.obsm
    np.testing.assert_allclose(result.obsm['X_gene_programs'], repeated.obsm['X_gene_programs'])
    assert api.program_weights(result).shape == (3, 12)
    assert set(api.top_program_genes(result)['program']) == {'program_1', 'program_2', 'program_3'}
    assert api.run_info(result)['executed_method'] == 'nmf'


def test_missing_cnmf_records_fallback(monkeypatch, caplog):
    import sys
    monkeypatch.setitem(sys.modules, 'cnmf', None)
    api = load_skill('sc-gene-programs')
    result = api.find_programs(ad.AnnData(np.random.default_rng(3).uniform(size=(20, 10))), n_programs=2)
    info = api.run_info(result)
    assert info['requested_method'] == 'cnmf'
    assert info['executed_method'] == 'nmf'
    assert info['fallback_used'] and 'cnmf' in info['fallback_reason']
    assert 'cnmf' in caplog.text.lower() and 'nmf' in caplog.text.lower()

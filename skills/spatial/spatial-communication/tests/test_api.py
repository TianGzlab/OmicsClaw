"""Communication inference through the step-facing function interface."""
import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_demo, load_skill


def pbmc():
    data = load_demo('pbmc3k_processed').raw.to_adata()
    keep = data.obs.groupby('louvain', observed=True).head(30).index
    data = data[keep].copy()
    return data


def test_liana_returns_real_ligand_receptor_scores():
    library = load_skill('spatial-communication')
    data = pbmc()
    assert library.communicate(data, cell_type_key='louvain', n_perms=10) is data
    table = library.interactions(data)
    assert len(table) > 0
    assert table['score'].between(0, 1).all()
    assert set(table['source']).issubset(data.obs['louvain'])
    assert library.run_info(data)['method'] == 'liana'


def test_liana_specificity_rank_is_not_a_p_value(monkeypatch):
    import liana
    def rank_only(data, **kwargs):
        data.uns['liana_res'] = pd.DataFrame({
            'ligand_complex': ['CCL5'], 'receptor_complex': ['CCR5'],
            'source': ['A'], 'target': ['B'], 'magnitude_rank': [0.2],
            'specificity_rank': [0.01]})
    monkeypatch.setattr(liana.mt, 'rank_aggregate', rank_only)
    library = load_skill('spatial-communication')
    data = pbmc()
    library.communicate(data, cell_type_key='louvain')
    assert library.interactions(data)['pvalue'].isna().all()
    assert library.interactions(data, significant_only=True).empty
    assert library.run_info(data)['n_significant'] == 0


@pytest.mark.parametrize('parameters', [{'cell_type_key': 'missing'}, {'method': 'unknown'},
                                      {'expr_prop': 2}, {'min_cells': 0}, {'n_perms': 0}])
def test_invalid_requests_fail_before_inference(parameters):
    with pytest.raises(ValueError):
        load_skill('spatial-communication').communicate(pbmc(), **{'cell_type_key': 'louvain', **parameters})


def test_cellchat_exchanges_matrix_market_and_cleans_temporary_files(monkeypatch):
    import subprocess
    from pathlib import Path
    from scipy.io import mmread
    from anndata import AnnData

    data = AnnData(np.array([[1., 0.], [2., 3.], [0., 1.], [4., 2.]]))
    data.obs_names = ['cell-01', 'cell-02', 'cell-03', 'cell-04']
    data.var_names = ['gene-01', 'gene_02']
    data.obs['labels'] = ['01', '01', 'group_1', 'group_1']
    seen = []

    def rscript(command, **kwargs):
        if '--version' in command:
            return subprocess.CompletedProcess(command, 0, 'Rscript version 4.3', '')
        if '-e' in command:
            return subprocess.CompletedProcess(command, 0, 'CellChat: TRUE\nMatrix: TRUE\n', '')
        inputs, outputs = Path(command[2]), Path(command[3])
        seen.append(inputs)
        np.testing.assert_array_equal(mmread(inputs / 'matrix.mtx').toarray(), data.X.T)
        assert (inputs / 'features.tsv').read_text().splitlines() == ['gene-01', 'gene_02']
        assert (inputs / 'barcodes.tsv').read_text().splitlines() == list(data.obs_names)
        assert command[-1] == '7'
        pd.DataFrame([dict(ligand='gene-01', receptor='gene_02', source='01',
                           target='group_1', score=.5, pvalue=.01)]).to_csv(
                               outputs / 'cellchat_results.csv', index=False)
        return subprocess.CompletedProcess(command, 0, '', '')

    monkeypatch.setattr(subprocess, 'run', rscript)
    library = load_skill('spatial-communication')
    library.communicate(data, method='cellchat_r', cell_type_key='labels', random_state=7)
    assert library.interactions(data)['source'].iloc[0] == '01'
    assert seen and all(not path.exists() for path in seen)

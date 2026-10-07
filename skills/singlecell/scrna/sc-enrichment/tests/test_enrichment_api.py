"""Enrichment functions use explicit gene sets and return reusable tables."""

import json

import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill


def ranking():
    return pd.DataFrame({'group': ['T'] * 20, 'gene': [f'G{i}' for i in range(20)],
                         'scores': np.arange(20, 0, -1), 'logfoldchanges': 1., 'pvals_adj': .001})


def test_default_ora_is_local_and_background_is_explicit(tmp_path):
    api = load_skill('sc-enrichment')
    genes = {'signature': ['G0', 'G1', 'G2', 'G3']}
    result = api.ora(ranking(), genes, background=[f'G{i}' for i in range(40)], max_genes=5)
    assert result.loc[0, 'engine'] == 'hypergeometric_local'
    assert result.loc[0, 'gene_count'] == 4
    assert result.loc[0, 'n_input_genes'] == 5
    assert api.group_summary(result).loc[0, 'n_terms'] == 1
    assert api.top_terms(result, n_top=1).shape[0] == 1
    assert json.loads(json.dumps(api.run_info(result)))['resolved_engine'] == 'python'


def test_marker_gene_sets_and_local_files(tmp_path):
    api = load_skill('sc-enrichment')
    markers = pd.DataFrame({'group': ['B', 'B', 'T'], 'names': ['MS4A1', 'CD79A', 'CD3D'],
                            'pvals_adj': [.1, .001, .002]})
    assert api.marker_gene_sets(markers, groups=['B'], top_n=1) == {'B': ['CD79A']}
    path = tmp_path / 'sets.json'
    path.write_text(json.dumps({'T': ['CD3D', 'CD3E']}))
    assert api.load_gene_sets(path) == {'T': ['CD3D', 'CD3E']}
    assert any('LTB' in genes for genes in api.demo_gene_sets().values())


def test_empty_gene_sets_raise_instead_of_fabricating_pathways():
    api = load_skill('sc-enrichment')
    with pytest.raises(ValueError, match='gene set'):
        api.ora(ranking(), {})
    with pytest.raises(ValueError, match='gene set'):
        api.gsea(ranking(), {})


def test_gsva_passes_explicit_gene_sets_to_the_r_boundary(monkeypatch):
    import anndata as ad
    from pathlib import Path
    from skills._sdk.r_script_runner import RScriptRunner

    adata = ad.AnnData(np.arange(36).reshape(6, 6).astype(float))
    adata.var_names = [f'G{i}' for i in range(6)]
    adata.obs['cell_type'] = ['a'] * 3 + ['b'] * 3

    def run_script(self, script, *, args, output_dir, **kwargs):
        assert Path(script).name == 'sc_gsva_r.R'
        expression = pd.read_csv(args[0], index_col=0)
        np.testing.assert_allclose(expression.loc['a'], adata.X[:3].mean(axis=0))
        assert Path(args[8]).read_text().startswith('signature\tomicsclaw\tG0\tG1\tG2')
        pd.DataFrame({'pathway': ['signature', 'signature'], 'group': ['a', 'b'],
                      'gsva_score': [.2, -.2]}).to_csv(Path(output_dir) / 'gsva_r_scores.csv', index=False)

    monkeypatch.setattr(RScriptRunner, 'run_script', run_script)
    api = load_skill('sc-enrichment')
    result = api.gsva(adata, {'signature': ['G0', 'G1', 'G2']}, groupby='cell_type', min_size=2)
    assert result['group'].tolist() == ['a', 'b']
    assert api.run_info(result)['n_pathways'] == 1

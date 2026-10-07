"""Guide assignment must not confuse target names with control tokens."""

import numpy as np
import pandas as pd
import pytest
from anndata import AnnData

from skills._sdk.notebook import load_skill


def test_synthetic_screen_embeds_downregulation_and_roundtrips_guide_mapping(tmp_path):
    from skills._sdk.notebook._demos import perturbseq_synthetic
    from anndata import read_h5ad

    adata = perturbseq_synthetic()
    adata.write_h5ad(tmp_path / 'screen.h5ad')
    restored = read_h5ad(tmp_path / 'screen.h5ad')
    mapping = restored.uns['guide_mapping']
    assert mapping.shape == (180, 3)
    assert set(mapping.columns) == {'barcode', 'sgRNA', 'target_gene'}
    assert set(mapping['barcode']) == set(restored.obs_names)
    controls = restored.obs['perturbation'].astype(str) == 'NT'
    for target, genes in restored.uns['synthetic_downregulated_gene_sets'].items():
        perturbed = restored.obs['perturbation'].astype(str) == target
        assert restored[perturbed, genes].X.mean() < .2 * restored[controls, genes].X.mean()
        assert restored[perturbed, [target]].X.mean() < .2 * restored[controls, [target]].X.mean()


def test_control_tokens_and_multi_guide_policy():
    api = load_skill('sc-perturb-prep')
    source = pd.DataFrame({'cell': ['a', 'b', 'c', 'd', 'e', 'f', 'f'],
                           'guide': ['NT_sg1', 'WNT3_sg1', 'NTRK1_sg1', 'NT5E_sg1',
                                     'non-target_sg1', 'TP53_sg1', 'TP53_sg2']})
    mapping = api.standardize_mapping(source)
    assigned, dropped = api.collapse_assignments(mapping)
    labels = assigned.set_index('barcode')['perturbation'].to_dict()
    assert labels == {'a': 'NT', 'b': 'WNT3', 'c': 'NTRK1', 'd': 'NT5E', 'e': 'NT'}
    assert dropped['barcode'].tolist() == ['f']
    kept, dropped = api.collapse_assignments(mapping, drop_multi_guide=False)
    assert dropped.empty
    assert kept.set_index('barcode').loc['f', 'n_sgrnas'] == 2
    assert list(source.columns) == ['cell', 'guide']


def test_attach_preserves_input_and_keeps_assigned_gene_features():
    api = load_skill('sc-perturb-prep')
    adata = AnnData(np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=float))
    adata.obs_names = ['a', 'b', 'unassigned']
    adata.var_names = ['WNT3', 'TP53', 'guide_feature']
    adata.var['feature_types'] = ['Gene Expression', 'Gene Expression', 'CRISPR Guide Capture']
    mapping = api.standardize_mapping(pd.DataFrame({'barcode': ['a', 'b'], 'sgRNA': ['NT_sg1', 'WNT3_sg1']}))
    assigned, _ = api.collapse_assignments(mapping)
    result = api.attach_assignments(adata, assigned)
    assert result.shape == (2, 2)
    assert result.obs['perturbation'].tolist() == ['NT', 'WNT3']
    assert api.assignment_summary(result)['n_cells'].sum() == 2
    assert api.perturbation_counts(result)['n_cells'].sum() == 2
    assert adata.shape == (3, 3) and 'sgRNA' not in adata.obs
    with pytest.raises(ValueError, match='barcode'):
        api.attach_assignments(adata, assigned.assign(barcode=['x', 'y']))

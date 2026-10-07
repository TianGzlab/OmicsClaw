"""Mixscape validates labels before touching its optional backend."""

import json
import sys
import types

import numpy as np
import pandas as pd
import pytest
from anndata import AnnData

from skills._sdk.notebook import load_skill


def test_mixscape_seed_reaches_both_backend_stages(monkeypatch):
    calls = []

    class Backend:
        def perturbation_signature(self, adata, *, ref_selection_mode, **kwargs):
            calls.append(('signature', kwargs['random_state']))
            adata.layers['X_pert'] = adata.X.copy()

        def mixscape(self, adata, *, pert_key, **kwargs):
            calls.append(('mixscape', kwargs['random_state']))
            adata.obs['mixscape_class'] = ['NT', 'KO_A KO'] * 3
            adata.obs['mixscape_class_global'] = ['NT', 'KO'] * 3
            adata.obs['mixscape_class_p_ko'] = [0., 1.] * 3

    monkeypatch.setitem(sys.modules, 'pertpy', types.SimpleNamespace(tl=types.SimpleNamespace(Mixscape=Backend)))
    api = load_skill('sc-perturb')
    adata = AnnData(np.random.default_rng(0).random((6, 4)))
    adata.obs['perturbation'] = ['NT', 'KO_A'] * 3
    adata.obsm['X_pca'] = np.ones((6, 2))
    result = api.mixscape(adata, split_by=None, random_state=17)
    assert calls == [('signature', 17), ('mixscape', 17)]
    assert 'mixscape_class' not in adata.obs
    assert api.class_counts(result)['n_cells'].sum() == 6
    assert api.global_class_counts(result).set_index('global_class').loc['KO', 'n_cells'] == 3
    assert json.loads(json.dumps(api.run_info(result)))['random_state'] == 17
    assert isinstance(result.uns['sc_perturb_run_info'], str)


def test_missing_control_and_split_raise_clear_errors():
    api = load_skill('sc-perturb')
    adata = AnnData(np.ones((3, 3)))
    adata.obs['perturbation'] = ['target'] * 3
    with pytest.raises(ValueError, match='control|Control'):
        api.mixscape(adata)
    adata.obs['perturbation'] = ['NT', 'target', 'target']
    with pytest.raises(ValueError, match='replicate'):
        api.mixscape(adata)

"""Batch integration through the function library."""

import sys
import types
import json

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill


@pytest.fixture(autouse=True)
def clear_backend_import_cache():
    from skills._sdk import deps
    deps._try_import.cache_clear()
    yield
    deps._try_import.cache_clear()


def test_small_harmony_reuses_existing_pca_without_building_a_graph(monkeypatch):
    rng = np.random.default_rng(0)
    adata = ad.AnnData(np.log1p(rng.poisson(3, (60, 40))).astype(float))
    adata.obs['batch'] = pd.Categorical(['a'] * 30 + ['b'] * 30)
    adata.var['highly_variable'] = True
    pca = rng.normal(size=(60, 12))
    adata.obsm['X_pca'] = pca.copy()
    calls = []

    def harmony(matrix, obs, batch_key, **kwargs):
        calls.append(kwargs)
        np.testing.assert_array_equal(matrix, pca)
        return types.SimpleNamespace(Z_corr=matrix.T)

    monkeypatch.setitem(sys.modules, 'harmonypy', types.SimpleNamespace(run_harmony=harmony))
    api = load_skill('sc-batch-integration')
    result = api.integrate(adata, n_pcs=50, random_state=13)

    assert result is adata
    np.testing.assert_array_equal(result.obsm['X_harmony'], pca)
    assert calls[0]['random_state'] == 13
    assert 'X_umap' not in result.obsm
    assert 'neighbors' not in result.uns
    assert api.run_info(result)['summary']['embedding_key'] == 'X_harmony'


@pytest.mark.parametrize('method', ['scvi', 'scanvi'])
def test_scvi_seed_is_set_before_backend_setup(monkeypatch, method):
    class SetupReached(Exception):
        pass

    settings = types.SimpleNamespace(seed=None)

    class Model:
        @staticmethod
        def setup_anndata(*args, **kwargs):
            assert settings.seed == 17
            raise SetupReached

    backend = types.SimpleNamespace(settings=settings, model=types.SimpleNamespace(SCVI=Model, SCANVI=Model))
    monkeypatch.setitem(sys.modules, 'scvi', backend)
    adata = ad.AnnData(np.ones((60, 40)))
    adata.layers['counts'] = adata.X.copy()
    adata.var['highly_variable'] = True
    adata.obs['batch'] = ['a'] * 30 + ['b'] * 30
    adata.obs['cell_type'] = ['T'] * 60
    api = load_skill('sc-batch-integration')
    with pytest.raises(SetupReached):
        api.integrate(adata, method=method, random_state=17, use_gpu=False)


def test_scanorama_preserves_cell_order_and_leaves_graph_to_caller(monkeypatch):
    adata = ad.AnnData(np.ones((6, 5)))
    adata.var['highly_variable'] = True
    adata.obs['batch'] = ['b', 'a', 'b', 'a', 'b', 'a']

    def correct(batches, **kwargs):
        assert kwargs['seed'] == 9
        for batch in batches:
            batch.obsm['X_scanorama'] = np.array([[int(x), 1] for x in batch.obs_names])
        return batches[::-1]

    monkeypatch.setitem(sys.modules, 'scanorama', types.SimpleNamespace(correct_scanpy=correct))
    api = load_skill('sc-batch-integration')
    result = api.integrate(adata, method='scanorama', random_state=9)
    np.testing.assert_array_equal(result.obsm['X_scanorama'][:, 0], np.arange(6))
    assert 'neighbors' not in result.uns
    assert 'X_umap' not in result.obsm


def test_missing_backend_names_overlay_install(monkeypatch):
    monkeypatch.setitem(sys.modules, 'harmonypy', None)
    adata = ad.AnnData(np.ones((4, 4)))
    adata.obs['batch'] = ['a', 'a', 'b', 'b']
    with pytest.raises(ImportError, match='install_skill_deps'):
        load_skill('sc-batch-integration').integrate(adata)


def test_r_umap_handoff_stays_outside_run_info(monkeypatch):
    from pathlib import Path
    from skills._sdk.r_script_runner import RScriptRunner

    api = load_skill('sc-batch-integration')
    module = sys.modules[api.integrate.__module__]
    monkeypatch.setattr(module, 'validate_r_environment', lambda **kwargs: None)
    adata = ad.AnnData(np.ones((60, 40)))
    adata.var['highly_variable'] = True
    adata.layers['counts'] = adata.X.copy()
    adata.obs['batch'] = ['a'] * 30 + ['b'] * 30

    def run_script(self, script, *, args, output_dir, **kwargs):
        assert script == 'sc_seurat_integrate.R'
        exported = ad.read_h5ad(args[0])
        np.testing.assert_array_equal(exported.X, adata.layers['counts'])
        folder = Path(output_dir)
        pd.DataFrame(np.ones((60, 12)), index=adata.obs_names).to_csv(folder / 'embedding.csv')
        adata.obs.to_csv(folder / 'obs.csv')
        pd.DataFrame(np.ones((60, 2)), index=adata.obs_names).to_csv(folder / 'umap.csv')

    monkeypatch.setattr(RScriptRunner, 'run_script', run_script)
    result = api.integrate(adata, method='seurat_cca')
    assert 'X_umap' not in result.obsm
    assert 'neighbors' not in result.uns
    assert result.uns['_omicsclaw_legacy_integration_umap'].shape == (60, 2)
    assert len(json.dumps(api.run_info(result))) < 1000
    assert 'legacy_umap' not in api.run_info(result)
    assert api.run_info(result, keep=False)['summary']['method'] == 'seurat_cca'
    assert api.run_info(result) == {}

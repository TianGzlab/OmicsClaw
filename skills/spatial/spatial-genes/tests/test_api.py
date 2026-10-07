"""Spatial autocorrelation through load_skill."""
import numpy as np
import pytest
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill


def test_morans_recovers_spatial_pattern_and_preserves_expression():
    library = load_skill('spatial-genes')
    adata = load_demo('spatial_synthetic')
    adata.layers['counts'] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    before = adata.X.copy()
    assert library.spatial_genes(adata, n_perms=0) is adata
    np.testing.assert_array_equal(adata.X, before)
    table = library.results(adata)
    assert len(table) == adata.n_vars
    assert table['I'].max() > 0.7
    assert library.run_info(adata)['method'] == 'morans'


def test_negative_flashs_bandwidth_is_rejected():
    with pytest.raises(ValueError, match='bandwidth'):
        load_skill('spatial-genes').spatial_genes(
            load_demo('spatial_synthetic'), method='flashs', bandwidth=-1)

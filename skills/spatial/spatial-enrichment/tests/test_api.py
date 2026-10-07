"""Local, explicit gene sets through the public enrichment interface."""
import numpy as np
import scanpy as sc
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_skill


def test_explicit_gene_sets_find_known_marker_group():
    library = load_skill('spatial-enrichment')
    rng = np.random.default_rng(7)
    counts = rng.poisson(2, (60, 40)).astype(float)
    counts[:30, :8] += 30
    counts[30:, 8:16] += 30
    data = AnnData(counts)
    data.var_names = [f'g{i}' for i in range(40)]
    data.obs['leiden'] = ['A'] * 30 + ['B'] * 30
    sc.pp.normalize_total(data)
    sc.pp.log1p(data)
    assert library.enrich(data, gene_sets={'A_markers': [f'g{i}' for i in range(8)]}) is data
    table = library.results(data)
    assert table.loc[table['group'] == 'A', 'pvalue_adj'].min() < 0.001
    assert library.run_info(data)['library_mode'] == 'provided'


@pytest.mark.parametrize('method', ['gsea', 'ssgsea'])
def test_real_gseapy_methods_use_explicit_synthetic_sets(method):
    from skills._sdk.notebook import load_demo
    data = load_demo('spatial_synthetic')
    sc.pp.normalize_total(data)
    sc.pp.log1p(data)
    library = load_skill('spatial-enrichment')
    gene_sets = {f'domain_{i}': [f'Gene_{j:03d}' for j in range(i * 30, (i + 1) * 30)] for i in range(3)}
    library.enrich(data, method=method, groupby='domain_ground_truth', gene_sets=gene_sets)
    table = library.results(data)
    assert len(table) == 9
    assert set(table['engine']) == {f'gseapy.{"prerank" if method == "gsea" else "ssgsea"}'}
    if method == 'ssgsea':
        assert table['pvalue_adj'].isna().all()
        assert library.results(data, significant_only=True).empty


def test_missing_remote_library_does_not_substitute_signatures(monkeypatch):
    import gseapy
    from skills._sdk.notebook import load_demo
    def unavailable(*args, **kwargs):
        raise RuntimeError('offline library service')
    monkeypatch.setattr(gseapy, 'get_library', unavailable)
    with pytest.raises(ValueError, match='Could not resolve remote library'):
        load_skill('spatial-enrichment').enrich(load_demo('spatial_synthetic'),
            groupby='domain_ground_truth', source='requested_remote_library')

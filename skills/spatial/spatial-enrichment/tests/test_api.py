"""Local, explicit gene sets through the public enrichment interface."""
import numpy as np
import scanpy as sc
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_skill


def test_compute_rejects_gene_set_paths_before_reading(tmp_path):
    from skills._sdk.notebook import load_demo
    with pytest.raises(TypeError, match='read_gene_sets'):
        load_skill('spatial-enrichment').enrich(
            load_demo('spatial_synthetic'), groupby='domain_ground_truth',
            gene_set_file=tmp_path / 'not-read.json')


@pytest.mark.parametrize('filename,content', [
    ('sets.json', '{"marker": ["Gene_000", "Gene_001"]}'),
    ('sets.gmt', 'marker\tdescription\tGene_000\tGene_001\n')])
def test_read_gene_sets_is_usable_as_input_reader(tmp_path, filename, content):
    from skills._sdk.notebook import read_input
    path = tmp_path / filename
    path.write_text(content)
    library = load_skill('spatial-enrichment')
    sets = read_input(path, reader=library.read_gene_sets)
    assert sets == {'marker': ['Gene_000', 'Gene_001']}


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
        load_skill('spatial-enrichment').fetch_gene_sets('requested_remote_library')


@pytest.mark.parametrize('selection', [{'source': 'requested_remote_library'},
                                      {'gene_set': 'requested_remote_library'}])
def test_compute_rejects_remote_sources_without_network(monkeypatch, selection):
    import gseapy
    from skills._sdk.notebook import load_demo
    def network_forbidden(*args, **kwargs):
        pytest.fail('Computation attempted network access')
    monkeypatch.setattr(gseapy, 'get_library', network_forbidden)
    with pytest.raises(ValueError, match='fetch_gene_sets'):
        load_skill('spatial-enrichment').enrich(load_demo('spatial_synthetic'),
            groupby='domain_ground_truth', **selection)


def test_explicit_remote_fetch_preserves_source_metadata(monkeypatch):
    import gseapy
    from skills._sdk.notebook import load_demo
    requests = []
    def library_service(name, *, organism):
        requests.append((name, organism))
        return {'first_domain': [f'Gene_{i:03d}' for i in range(30)]}
    monkeypatch.setattr(gseapy, 'get_library', library_service)
    library = load_skill('spatial-enrichment')
    sets = library.fetch_gene_sets('named_library', species='mouse')
    assert requests == [('named_library', 'mouse')]
    data = load_demo('spatial_synthetic')
    sc.pp.normalize_total(data)
    sc.pp.log1p(data)
    library.enrich(data, groupby='domain_ground_truth', gene_sets=sets)
    info = library.run_info(data)
    assert info['resolved_source'] == 'named_library'
    assert info['library_mode'] == 'remote_library'
    assert requests == [('named_library', 'mouse')]


@pytest.mark.cli_subprocess
def test_local_library_remains_compatible_with_cli(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import pandas as pd
    from skills._sdk.notebook import load_demo

    data = load_demo('spatial_synthetic')
    sc.pp.normalize_total(data)
    sc.pp.log1p(data)
    data.write_h5ad(tmp_path / 'input.h5ad')
    sets_path = tmp_path / 'markers.json'
    sets_path.write_text(json.dumps({'first_domain': [f'Gene_{i:03d}' for i in range(30)]}))
    library = load_skill('spatial-enrichment')
    library.enrich(data, groupby='domain_ground_truth', gene_sets=library.read_gene_sets(sets_path))
    info = library.run_info(data)
    assert info['resolved_source'] == 'markers.json'
    assert info['library_mode'] == 'local_file'
    script = Path(__file__).resolve().parents[1] / 'spatial_enrichment.py'
    result = subprocess.run([sys.executable, str(script), '--input', str(tmp_path / 'input.h5ad'),
        '--gene-set-file', str(sets_path), '--groupby', 'domain_ground_truth',
        '--output', str(tmp_path / 'output')], capture_output=True, text=True, timeout=120,
        env={**os.environ, 'NUMBA_DISABLE_JIT': '0', 'OMP_NUM_THREADS': '1',
             'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'NUMBA_NUM_THREADS': '1'})
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    table = pd.read_csv(tmp_path / 'output/tables/enrichment_results.csv')
    assert set(table['source']) == {'markers.json'}
    assert set(table['library_mode']) == {'local_file'}

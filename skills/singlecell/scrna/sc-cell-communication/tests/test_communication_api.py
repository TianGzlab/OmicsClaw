import sys
import types
import anndata as ad
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill


def data():
    return ad.AnnData(np.array([[3., 2.], [1., 4.]]), obs=pd.DataFrame({'cell_type': ['A', 'B']}, index=['a', 'b']), var=pd.DataFrame(index=['TGFB1', 'TGFBR1']))


def test_builtin_is_not_a_significance_test():
    api = load_skill('sc-cell-communication')
    source = data()
    table = api.communicate(source)
    assert len(table) == 4 and table.pvalue.isna().all()
    assert api.run_info(table)['n_significant'] == 0
    assert not source.uns


def test_liana_specificity_is_not_a_pvalue(monkeypatch):
    api = load_skill('sc-cell-communication')
    seeds = []
    def rank_aggregate(adata, **kwargs):
        seeds.append(kwargs['seed'])
        adata.uns['liana_res'] = pd.DataFrame({'ligand_complex': ['TGFB1'], 'receptor_complex': ['TGFBR1'], 'source': ['A'], 'target': ['B'], 'magnitude_rank': [.1], 'specificity_rank': [.001]})
    monkeypatch.setitem(sys.modules, 'liana', types.SimpleNamespace(mt=types.SimpleNamespace(rank_aggregate=rank_aggregate)))
    from skills._sdk import deps
    monkeypatch.setattr(deps, 'is_available', lambda name: True)
    table = api.communicate(data(), method='liana')
    assert table.pvalue.isna().all() and table.specificity_rank.iloc[0] == .001
    assert api.run_info(table)['n_significant'] == 0
    assert seeds == [1337]


def test_cellphonedb_seed_and_temporary_exchange(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1] / '_api.py'
    spec = importlib.util.spec_from_file_location('communication_seed_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = []
    def call(**kwargs):
        seen.append((kwargs['debug_seed'], Path(kwargs['counts_file_path'])))
        assert seen[-1][1].is_file()
        raise KeyError('significant_means')
    package = types.ModuleType('cellphonedb.src.core.methods')
    package.cpdb_statistical_analysis_method = types.SimpleNamespace(call=call)
    monkeypatch.setitem(sys.modules, 'cellphonedb.src.core.methods', package)
    monkeypatch.setattr(module.sc_dep_manager, 'is_available', lambda name: True)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    database = types.SimpleNamespace(download_database=lambda folder, version:
        (Path(folder) / 'cellphonedb.zip').write_bytes(b'test database'))
    monkeypatch.setitem(sys.modules, 'cellphonedb.utils', types.SimpleNamespace(db_utils=database))
    source = data()
    source.X += .2
    module.cellphonedb_lr(source)
    module.cellphonedb_lr(source, random_state=9)
    assert [seed for seed, _ in seen] == [0, 9]
    assert all(not path.exists() for _, path in seen)

import anndata as ad
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill


def test_named_gene_set_library_passes_species(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []

    def get_library(*, name, organism):
        calls.append((name, organism))
        return {"pathway": ["GENE1"]}

    monkeypatch.setitem(sys.modules, "gseapy", SimpleNamespace(get_library=get_library))
    assert load_skill("sc-pathway-scoring").load_gene_sets("kegg", species="mouse") == {"pathway": ["GENE1"]}
    assert calls == [("KEGG_2021_Mouse", "Mouse")]


def test_scores_preserve_cells_and_input():
    api = load_skill('sc-pathway-scoring')
    data = ad.AnnData(np.random.default_rng(2).uniform(size=(20, 12)), var=pd.DataFrame(index=[f'g{i}' for i in range(12)]))
    sets = {'A': ['g0', 'g2', 'g4'], 'missing': ['absent']}
    scores = api.score_gene_sets(data, sets, method='aucell_py', auc_threshold=0.3)
    assert scores.index.equals(data.obs_names)
    assert list(scores) == ['A']
    assert api.run_info(scores)['skipped_gene_sets'] == ['missing']
    result = api.attach_scores(data, scores)
    assert 'enrich__a' not in data.obs and 'enrich__a' in result.obs
    assert api.gene_set_overlap(data, sets).n_matched_genes.tolist() == [3, 0]


def test_score_genes_passes_seed(monkeypatch):
    import scanpy as sc
    api = load_skill('sc-pathway-scoring')
    seen = []
    def score(adata, *, gene_list, score_name, random_state, **kwargs):
        seen.append(random_state)
        adata.obs[score_name] = 1.0
    monkeypatch.setattr(sc.tl, 'score_genes', score)
    data = ad.AnnData(np.random.default_rng(0).uniform(size=(20, 12)), var=pd.DataFrame(index=[f'g{i}' for i in range(12)]))
    api.score_gene_sets(data, {'A': ['g0']}, method='score_genes_py', random_state=11)
    assert seen == [11]


def test_aucell_r_seed_and_temporary_exchange(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1] / '_api.py'
    spec = importlib.util.spec_from_file_location('aucell_seed_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = ad.AnnData(np.ones((3, 2)), var=pd.DataFrame(index=['g0', 'g1']))
    paths = []
    class Runner:
        def __init__(self, **kwargs):
            pass
        def run_script(self, script, *, args, output_dir, **kwargs):
            assert args[-1] == '11'
            assert Path(args[0]).is_file() and Path(args[1]).is_file()
            paths.extend([Path(args[0]), Path(args[1])])
            pd.DataFrame({'Cell': source.obs_names, 'A': [0., .5, 1.]}).to_csv(output_dir / 'aucell_scores.csv', index=False)
    monkeypatch.setattr(module, 'validate_r_environment', lambda **kwargs: None)
    monkeypatch.setattr(module, 'RScriptRunner', Runner)
    scores = module.score_gene_sets(source, {'A': ['g0']}, random_state=11)
    assert scores.A.tolist() == [0., .5, 1.]
    assert all(not path.exists() for path in paths)
    script = (path.parent / 'rscripts/sc_aucell.R').read_text()
    assert 'set.seed(random_state)' in script

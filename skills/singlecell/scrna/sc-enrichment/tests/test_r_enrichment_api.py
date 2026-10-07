"""Real R checks for seed handling and failure without usable gene sets."""

import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill
from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import RScriptError

pytestmark = pytest.mark.slow


def require_r(packages):
    try:
        validate_r_environment(required_r_packages=packages)
    except Exception as exc:
        pytest.skip(f'R packages unavailable: {exc}')


def test_clusterprofiler_gsea_seed_is_repeatable():
    require_r(['clusterProfiler', 'enrichplot'])
    api = load_skill('sc-enrichment')
    rng = np.random.default_rng(7)
    ranking = pd.DataFrame({'gene': [f'G{i}' for i in range(200)], 'group': 'A',
                            'scores': rng.normal(size=200)})
    sets = {'first': [f'G{i}' for i in range(20)], 'second': [f'G{i}' for i in range(30, 70)]}
    left = api.gsea(ranking, sets, engine='r', random_state=23)
    right = api.gsea(ranking, sets, engine='r', random_state=23)
    assert not left.empty
    pd.testing.assert_frame_equal(left, right)
    assert api.run_info(left)['resolved_engine'] == 'r'
    assert '_cli_artifacts' not in api.run_info(left)


def test_gsva_without_annotation_does_not_invent_pathways():
    import anndata as ad

    require_r(['GSVA', 'BiocParallel'])
    api = load_skill('sc-enrichment')
    rng = np.random.default_rng(3)
    adata = ad.AnnData(rng.normal(size=(12, 30)))
    adata.obs['group'] = ['a'] * 4 + ['b'] * 4 + ['c'] * 4
    with pytest.raises(RScriptError, match='No valid gene sets'):
        api.gsva(adata, None, groupby='group', gene_set_db='unavailable_database')


def test_gsea_without_annotation_does_not_invent_pathways():
    require_r(['clusterProfiler', 'DOSE', 'dplyr'])
    api = load_skill('sc-enrichment')
    ranking = pd.DataFrame({'gene': [f'G{i}' for i in range(30)], 'group': 'A',
                            'scores': np.linspace(2, -2, 30)})
    with pytest.raises(RScriptError, match='No enrichment results'):
        api.gsea(ranking, None, engine='gsea_r', gene_set_db='unavailable_database')

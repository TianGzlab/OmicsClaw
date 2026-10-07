import pytest
from skills._sdk.notebook import load_skill


def test_explicit_pathways_use_known_fisher_contingency():
    lib = load_skill('proteomics-enrichment')
    result = lib.enrich(['A','B'], pathway_db={'set':['A','B']}, background_size=4)
    assert result.loc[0,'pvalue'] == pytest.approx(1/6, abs=1e-8)
    assert result.loc[0,'overlap_genes'] == 'A;B'


def test_missing_pathways_and_impossible_background_are_rejected():
    lib = load_skill('proteomics-enrichment')
    with pytest.raises(ValueError, match='pathway_db'):
        lib.enrich(['A'])
    with pytest.raises(ValueError, match='background'):
        lib.enrich(['A','B'], pathway_db={'set':['A','C']}, background_size=2)

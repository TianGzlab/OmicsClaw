import pytest
from skills._sdk.notebook import load_skill


def test_explicit_pathway_reference_has_known_hypergeometric_probability():
    library = load_skill('metabolomics-pathway-enrichment')
    pathways = {'selected': {'kegg_id': '', 'metabolites': ['a', 'b']}, 'other': {'kegg_id': '', 'metabolites': ['c', 'd']}}
    result = library.enrich(['a', 'b'], pathways=pathways)
    assert result.loc[0, 'pathway'] == 'selected'
    assert result.loc[0, 'pvalue'] == pytest.approx(1 / 6)
    assert library.run_info(result)['reference_scope'] == 'provided'
    assert library.enrichment_figure(result).axes


def test_unimplemented_pathway_method_is_rejected():
    with pytest.raises(ValueError, match='ora'):
        load_skill('metabolomics-pathway-enrichment').enrich(['glucose'], method='fella')


def test_no_overlap_retains_result_schema():
    result = load_skill('metabolomics-pathway-enrichment').enrich(['not_in_reference'])
    assert result.empty and 'fdr' in result

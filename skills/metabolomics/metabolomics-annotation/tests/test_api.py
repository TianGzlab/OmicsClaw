import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_annotation_matches_glucose_adduct_without_mutating_input():
    library = load_skill('metabolomics-annotation')
    data = pd.DataFrame({'mz': [181.07066446677, 9999.]})
    result = library.annotate(data)
    assert result['name'].tolist() == ['D-Glucose', 'Unknown']
    assert result.loc[0, 'ppm_error'] == 0.
    assert library.run_info(result)['reference_scope'] == 'demo'
    assert library.mass_error_figure(result).axes


def test_unimplemented_database_is_not_a_different_label_on_demo_results():
    with pytest.raises(ValueError, match='reference'):
        load_skill('metabolomics-annotation').annotate(pd.DataFrame({'mz': [100.]}), database='kegg')


def test_caller_supplied_reference_is_used():
    library = load_skill('metabolomics-annotation')
    reference = pd.DataFrame({'name': ['custom'], 'neutral_mass': [100.], 'database_id': ['X'], 'formula': ['C']})
    result = library.annotate(pd.DataFrame({'mz': [101.00727646677]}), database='custom', reference=reference)
    assert result['name'].tolist() == ['custom']

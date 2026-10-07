import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_imputation_uses_global_positive_minimum_and_preserves_metadata():
    library = load_skill('metabolomics-quantification')
    data = pd.DataFrame({'feature_id': ['a', 'b'], 'mz': [100., 200.], 'sample1': [2., 0.], 'sample2': [4., 8.]})
    result = library.quantify(data, normalize='log')
    assert result['feature_id'].tolist() == ['a', 'b']
    assert result.loc[1, 'sample1'] == 1.0
    assert data.loc[1, 'sample1'] == 0
    assert library.run_info(result)['n_missing_before'] == 1
    assert library.distribution_figure(result).axes


def test_no_sample_columns_fails():
    with pytest.raises(ValueError, match='sample columns'):
        load_skill('metabolomics-quantification').quantify(pd.DataFrame({'feature_id': ['a']}))


@pytest.mark.parametrize('method', ['min', 'median', 'knn'])
def test_completely_missing_samples_are_rejected(method):
    data = pd.DataFrame({'feature_id': ['a', 'b'], 'sample1': [0., float('nan')], 'sample2': [2., 4.]})
    with pytest.raises(ValueError, match='positive'):
        load_skill('metabolomics-quantification').quantify(data, impute=method)

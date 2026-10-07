import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_normalization_preserves_labels_and_does_not_mutate_input():
    library = load_skill('metabolomics-normalization')
    data = pd.DataFrame({'a': [1., 2., 3.], 'b': [2., 4., 6.]}, index=['x', 'y', 'z'])
    before = data.copy()
    result = library.normalize(data)
    pd.testing.assert_frame_equal(result, pd.DataFrame({'a': [1.5, 3., 4.5], 'b': [1.5, 3., 4.5]}, index=data.index))
    pd.testing.assert_frame_equal(data, before)
    assert library.run_info(result)['method'] == 'median'
    assert library.distribution_figure(result).axes


def test_unknown_normalization_fails():
    with pytest.raises(ValueError, match='Unknown method'):
        load_skill('metabolomics-normalization').normalize(pd.DataFrame({'a': [1.]}), method='fake')

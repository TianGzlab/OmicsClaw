import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_de_retains_feature_identity_and_fold_change_direction():
    library = load_skill('metabolomics-de')
    data = pd.DataFrame({'feature_id': ['increase', 'stable'], 'ctrl1': [1., 2.], 'ctrl2': [2., 3.], 'ctrl3': [3., 4.], 'treat1': [2., 2.], 'treat2': [4., 3.], 'treat3': [6., 4.]})
    result = library.differential_expression(data)
    assert result.set_index('feature_id').loc['increase', 'log2fc'] == 1.
    assert library.run_info(result)['n_group_a'] == 3
    figure = library.pca_figure(data)
    assert len(figure.axes[0].collections[0].get_offsets()) == 6
    assert data['feature_id'].tolist() == ['increase', 'stable']


def test_missing_group_is_rejected():
    with pytest.raises(ValueError, match='columns'):
        load_skill('metabolomics-de').differential_expression(pd.DataFrame({'id': ['a'], 'ctrl1': [1.]}))

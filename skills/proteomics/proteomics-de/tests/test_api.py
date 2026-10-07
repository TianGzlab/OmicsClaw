import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


@pytest.mark.parametrize('method', ['ttest', 'welch', 'mann_whitney'])
def test_two_group_fold_change_has_known_direction(method):
    data = pd.DataFrame([[2., 4., 8., 8., 16., 32.]], index=['A'], columns=list('abcdef'))
    result = load_skill('proteomics-de').differential_abundance(data, method=method)
    assert result.loc[0, 'log2fc'] == 2.
    assert 0 <= result.loc[0, 'padj'] <= 1
    assert data.loc['A', 'a'] == 2.


def test_overlapping_groups_are_rejected():
    with pytest.raises(ValueError, match='disjoint'):
        load_skill('proteomics-de').differential_abundance(pd.DataFrame({'a': [1], 'b': [2]}), group1=['a'], group2=['a'])

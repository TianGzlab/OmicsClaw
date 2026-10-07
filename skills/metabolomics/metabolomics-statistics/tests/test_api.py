import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


@pytest.mark.parametrize('method', ['ttest', 'wilcoxon', 'anova', 'kruskal'])
def test_statistics_preserves_contrast_direction(method):
    library = load_skill('metabolomics-statistics')
    data = pd.DataFrame({'a1': [1.], 'a2': [2.], 'a3': [3.], 'b1': [2.], 'b2': [4.], 'b3': [6.]}, index=['metabolite'])
    result = library.test_groups(data, method=method, group1_prefix='a', group2_prefix='b')
    assert result.loc[0, 'feature'] == 'metabolite'
    assert result.loc[0, 'log2fc'] == 1.
    assert 0 <= result.loc[0, 'fdr'] <= 1
    assert library.run_info(result)['method'] == method
    assert library.volcano_figure(result).axes


def test_midpoint_grouping_warns_and_records_actual_columns():
    library = load_skill('metabolomics-statistics')
    data = pd.DataFrame({'a': [1.], 'b': [2.], 'c': [3.], 'd': [4.]})
    with pytest.warns(UserWarning, match='midpoint'):
        result = library.test_groups(data)
    assert library.run_info(result)['group1'] == ['a', 'b']


def test_undefined_kruskal_test_is_not_fabricated_as_pvalue_one():
    data = pd.DataFrame({'a1': [1.], 'a2': [1.], 'b1': [1.], 'b2': [1.]})
    with pytest.raises(ValueError, match='identical'):
        load_skill('metabolomics-statistics').test_groups(data, method='kruskal', group1_prefix='a', group2_prefix='b')

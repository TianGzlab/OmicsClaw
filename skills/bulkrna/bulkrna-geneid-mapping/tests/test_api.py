import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_explicit_mapping_wins_and_duplicate_counts_are_summed():
    library = load_skill('bulkrna-geneid-mapping')
    data = pd.DataFrame({'sample': [2, 3, 7]}, index=['ENSG00000141510.1', 'ENSG00000141510.2', 'unmapped'])
    mapping = pd.DataFrame({'source': ['ENSG00000141510'], 'target': ['CUSTOM']})
    result = library.map_ids(data, mapping=mapping)
    assert result.loc['CUSTOM', 'sample'] == 5
    assert result.loc['unmapped', 'sample'] == 7
    assert library.mapping_table(result)['was_mapped'].tolist() == [True, True, False]
    assert library.run_info(result)['n_mapped'] == 2
    assert data.index[0].endswith('.1')
    assert library.mapping_figure(result).axes


def test_mouse_without_reference_does_not_use_human_demo_mapping():
    with pytest.raises(ValueError, match='reference'):
        load_skill('bulkrna-geneid-mapping').map_ids(pd.DataFrame({'s': [1]}, index=['ENSG00000141510']), species='mouse')

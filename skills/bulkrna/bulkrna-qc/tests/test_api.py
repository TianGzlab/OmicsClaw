"""Count-matrix QC through the notebook interface."""
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_library_sizes_and_cpm_without_changing_counts():
    counts = pd.DataFrame({'ctrl_1': [1, 3, 0], 'treat_1': [2, 6, 0]}, index=['a', 'b', 'c'])
    original = counts.copy(deep=True)
    api = load_skill('bulkrna-qc')
    result = api.assess(counts)
    assert result['total_counts'].tolist() == [4, 8]
    assert result['n_detected_genes'].tolist() == [2, 2]
    assert api.normalized_counts(result).loc['a'].tolist() == [250000, 250000]
    assert api.run_info(result)['n_zero_genes'] == 1
    pd.testing.assert_frame_equal(counts, original)
    assert api.run_info(result, keep=False)['n_samples'] == 2
    assert api.run_info(result) == {}


def test_zero_library_rejected_before_normalization():
    with pytest.raises(ValueError, match='positive library'):
        load_skill('bulkrna-qc').assess(pd.DataFrame({'empty': [0, 0]}))

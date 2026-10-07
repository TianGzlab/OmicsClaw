import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_known_24_hour_sinusoid_and_constant():
    times = np.arange(0, 24, 4)
    data = pd.DataFrame([10 + 3 * np.sin(2 * np.pi * times / 24), np.ones(6) * 5],
                        index=['rhythm', 'constant'], columns=[f'T{t:02d}_R1' for t in times])
    original = data.copy()
    result = load_skill('bulkrna-cosinor-rhythm').fit(data).set_index('gene')
    assert result.loc['rhythm', 'mesor'] == pytest.approx(10)
    assert result.loc['rhythm', 'amplitude'] == pytest.approx(3)
    assert result.loc['rhythm', 'peak_phase_hours'] == pytest.approx(6)
    assert bool(result.loc['rhythm', 'rhythmic'])
    assert not bool(result.loc['constant', 'rhythmic'])
    pd.testing.assert_frame_equal(data, original)


def test_missing_time_columns_are_not_a_successful_fit():
    with pytest.raises(ValueError, match='T.*R'):
        load_skill('bulkrna-cosinor-rhythm').fit(pd.DataFrame({'sample': [2]}, index=['g']))

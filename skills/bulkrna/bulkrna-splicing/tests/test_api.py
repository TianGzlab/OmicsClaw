"""Splicing event thresholds through the public library."""
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_significant_events_use_strict_cutoffs_and_keep_input():
    data = pd.DataFrame({'gene': ['a', 'b', 'c'], 'event_type': ['SE', 'SE', 'RI'],
                         'delta_psi': [.3, -.1, -.4], 'padj': [.01, .01, .05]})
    api = load_skill('bulkrna-splicing')
    result = api.summarize(data)
    assert api.significant_events(result)['gene'].tolist() == ['a']
    assert api.run_info(result)['n_up'] == 1
    pd.testing.assert_frame_equal(result, data)


def test_invalid_probabilities_rejected():
    data = pd.DataFrame({'gene': ['a'], 'event_type': ['SE'], 'delta_psi': [.2], 'padj': [-1.]})
    with pytest.raises(ValueError, match='padj'):
        load_skill('bulkrna-splicing').summarize(data)

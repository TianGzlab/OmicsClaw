"""Known mixtures through NNLS public functions."""
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_known_mixture_and_residual():
    counts = pd.DataFrame({'sample': [3., 1.]}, index=['a', 'b'])
    signature = pd.DataFrame({'A': [1., 0.], 'B': [0., 1.]}, index=['a', 'b'])
    api = load_skill('bulkrna-deconvolution')
    result = api.deconvolve(counts, signature=signature)
    assert result.loc['sample'].tolist() == [.75, .25]
    assert api.run_info(result)['residuals'] == [0.]


def test_reference_with_no_overlap_fails():
    with pytest.raises(ValueError, match='shared genes'):
        load_skill('bulkrna-deconvolution').deconvolve(
            pd.DataFrame({'s': [1.]}, index=['a']), signature=pd.DataFrame({'A': [1.]}, index=['b']))


def test_zero_supported_signal_does_not_invent_a_dominant_cell_type():
    with pytest.raises(ValueError, match='positive.*shared|supported signal'):
        load_skill('bulkrna-deconvolution').deconvolve(
            pd.DataFrame({'sample': [0., 3.]}, index=['a', 'b']),
            signature=pd.DataFrame({'A': [1.]}, index=['a']))

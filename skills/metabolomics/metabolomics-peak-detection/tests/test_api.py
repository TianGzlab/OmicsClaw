import pandas as pd
from skills._sdk.notebook import load_skill


def test_peak_detection_sorts_retention_time_and_reports_known_peak():
    library = load_skill('metabolomics-peak-detection')
    data = pd.DataFrame({'mz': [100., 101., 102., 103., 104.], 'rt': [0., 1., 2., 3., 4.], 'sample1': [0., 1., 8., 1., 0.]})
    result = library.detect_peaks(data.iloc[::-1], prominence=2, distance=1)
    assert result['rt'].tolist() == [2.]
    assert result['intensity'].tolist() == [8.]
    assert library.run_info(result)['n_peaks'] == 1
    assert library.peaks_figure(result).axes


def test_no_peaks_retains_a_readable_table_schema():
    result = load_skill('metabolomics-peak-detection').detect_peaks(pd.DataFrame({'mz': [100., 101., 102.], 'rt': [0., 1., 2.], 'sample1': [1., 1., 1.]}))
    assert result.empty
    assert 'sample' in result

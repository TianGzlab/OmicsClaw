import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_qc_counts_zero_and_nan_as_missing_and_excludes_identifier_columns():
    data = pd.DataFrame({'protein_id':['A','B'], 'sample_a':[2.,0.], 'sample_b':[2.,float('nan')]})
    library = load_skill('proteomics-ms-qc')
    result = library.quality_control(data)
    assert result.loc[0,'missing_rate'] == 50.
    assert result.loc[0,'median_cv'] == 0.
    assert library.run_info(result)['summary']['n_samples'] == 2
    assert 'run_info' not in data.attrs


def test_qc_rejects_tables_without_intensity_columns():
    with pytest.raises(ValueError, match='intensity'):
        load_skill('proteomics-ms-qc').quality_control(pd.DataFrame({'protein':['A']}))

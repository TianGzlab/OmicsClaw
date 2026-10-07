import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_peptide_filter_reports_actual_qvalue_threshold_and_identification_rate():
    data = pd.DataFrame({'protein':['A','A','B'], 'peptide':['AA','BB','CC'], 'qvalue':[.001,.01,.02]})
    lib = load_skill('proteomics-identification')
    result = lib.filter_identifications(data, n_spectra=10)
    assert result['peptide'].tolist() == ['AA','BB']
    info = lib.run_info(result)
    assert info['summary']['id_rate'] == 20.
    assert info['filter_column'] == 'qvalue'
    assert len(data) == 3


def test_missing_qvalues_are_visible_as_unfiltered_not_fdr_controlled():
    lib = load_skill('proteomics-identification')
    with pytest.warns(UserWarning, match='q-value'):
        result = lib.filter_identifications(pd.DataFrame({'peptide':['AA'],'protein':['A']}))
    assert lib.run_info(result)['executed_method'] == 'unfiltered'


def test_reader_normalizes_search_engine_headers(tmp_path):
    path = tmp_path / 'evidence.txt'
    path.write_text('Sequence\tProteins\tScore\tPEP\nAA\tP1\t12\t0.005\n')
    lib = load_skill('proteomics-identification')
    result = lib.filter_identifications(lib.read_table(path))
    assert result['peptide'].tolist() == ['AA']
    assert lib.run_info(result)['filter_column'] == 'pep'

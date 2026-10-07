import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_maxquant_filters_flagged_rows_and_renames_intensities():
    data = pd.DataFrame({'Protein IDs': ['A','B','C'], 'Intensity one': [10,20,30], 'Reverse': ['', '+', ''], 'Potential contaminant': ['', '', '+']})
    result = load_skill('proteomics-data-import').standardize(data)
    assert result['protein_id'].tolist() == ['A']
    assert result['Int_one'].tolist() == [10]
    assert 'Protein IDs' in data and len(data) == 3


@pytest.mark.parametrize(('format','column'), [('fragpipe','Protein'), ('diann','Protein.Group'), ('generic','accession')])
def test_import_formats_preserve_protein_identity(format, column):
    result = load_skill('proteomics-data-import').standardize(pd.DataFrame({column:['A']}), format=format)
    assert result['protein_id'].tolist() == ['A']


def test_reader_loads_a_tab_separated_table(tmp_path):
    path = tmp_path / 'proteins.txt'
    path.write_text('Protein IDs\tIntensity one\nA\t12\n')
    lib = load_skill('proteomics-data-import')
    result = lib.standardize(lib.read_table(path))
    assert result['Int_one'].tolist() == [12]

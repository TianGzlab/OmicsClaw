import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_quantification_sums_and_counts_known_peptides_without_mutation():
    peptides = pd.DataFrame({'protein': ['A', 'A', 'B'], 'peptide': ['AA', 'BB', 'CC'],
                             'intensity': [8., 16., 4.], 'n_theoretical_peptides': [2, 2, 1]})
    original = peptides.copy(deep=True)
    library = load_skill('proteomics-quantification')
    assert library.quantify(peptides)['abundance'].tolist() == [24., 4.]
    assert library.quantify(peptides, method='spectral_count')['abundance'].tolist() == [2, 1]
    assert library.quantify(peptides, method='ibaq')['abundance'].tolist() == [12., 4.]
    pd.testing.assert_frame_equal(peptides, original)


def test_ibaq_refuses_missing_theoretical_counts():
    library = load_skill('proteomics-quantification')
    with pytest.raises(ValueError, match='sequence.*n_theoretical_peptides'):
        library.quantify(pd.DataFrame({'protein': ['A'], 'peptide': ['AA'], 'intensity': [8.]}), method='ibaq')

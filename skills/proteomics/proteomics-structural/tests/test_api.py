import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_crosslink_filter_classification_and_distance_limits():
    data = pd.DataFrame({'protein_a':['A','A','B'],'protein_b':['A','B','C'], 'fdr':[.01,.01,.1], 'distance_angstrom':[15.,25.,10.]})
    lib = load_skill('proteomics-structural')
    result = lib.analyse_crosslinks(data, crosslinker='EDC')
    assert result['link_type'].tolist() == ['intra-protein','inter-protein']
    assert result['constraint_satisfied'].tolist() == [True,False]
    assert lib.run_info(result)['summary']['constraint_satisfaction_rate'] == 50.
    assert len(data) == 3


def test_missing_distances_are_not_reported_as_passed_constraints():
    lib = load_skill('proteomics-structural')
    result = lib.analyse_crosslinks(pd.DataFrame({'protein_a':['A'],'protein_b':['B']}))
    info = lib.run_info(result)
    assert info['distance_checked'] is False
    assert info['summary']['constraint_satisfaction_rate'] is None
    assert info['summary']['n_constraint_satisfied'] is None


def test_missing_protein_identifiers_do_not_become_intra_protein_links():
    with pytest.raises(ValueError, match='protein_a.*protein_b'):
        load_skill('proteomics-structural').analyse_crosslinks(pd.DataFrame({'score':[1]}))


@pytest.mark.parametrize('distances,checked,rate', [([20., float('nan')], 1, 100.),
                                                 ([float('nan'), float('nan')], 0, None)])
def test_partial_missing_distances_are_unchecked_not_failed(distances, checked, rate):
    lib = load_skill('proteomics-structural')
    data = pd.DataFrame({'protein_a': ['A', 'B'], 'protein_b': ['B', 'C'], 'distance_angstrom': distances})
    result = lib.analyse_crosslinks(data)
    assert pd.isna(result.loc[1, 'constraint_satisfied'])
    info = lib.run_info(result)
    assert info['n_distance_checked'] == checked
    assert info['n_distance_unchecked'] == 2 - checked
    assert info['distance_checked'] is bool(checked)
    assert info['summary']['constraint_satisfaction_rate'] == rate

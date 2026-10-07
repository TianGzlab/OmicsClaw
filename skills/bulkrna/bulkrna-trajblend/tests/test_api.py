import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def reference_data():
    genes = [f'g{i}' for i in range(60)]
    a = np.r_[np.full(30,8.),np.full(30,2.)]
    b = np.r_[np.full(30,2.),np.full(30,8.)]
    reference = pd.DataFrame(np.vstack([a]*10+[b]*10),columns=genes,index=[f'c{i}' for i in range(20)])
    bulk = pd.DataFrame([a,b],columns=genes,index=['early','late'])
    labels = pd.Series(['A']*10+['B']*10,index=reference.index)
    time = pd.Series([0.]*10+[1.]*10,index=reference.index)
    return bulk,reference,labels,time


def test_bulk_matches_known_reference_endpoints_and_fractions():
    bulk,reference,labels,time = reference_data()
    lib = load_skill('bulkrna-trajblend')
    result = lib.map_trajectory(bulk,reference=reference,labels=labels,pseudotime=time,k=5)
    assert result['pseudotime'].tolist() == [0.,1.]
    fractions = lib.fractions(result)
    assert fractions.loc['early','A'] == pytest.approx(1.)
    assert fractions.loc['late','B'] == pytest.approx(1.)
    assert 'run_info' not in bulk.attrs


def test_missing_reference_pseudotime_is_not_replaced_with_zeros():
    bulk,reference,labels,time = reference_data()
    with pytest.raises(ValueError,match='pseudotime'):
        load_skill('bulkrna-trajblend').map_trajectory(bulk,reference=reference,labels=labels,pseudotime=time.iloc[:-1])


def test_reference_reader_requires_observed_labels_and_pseudotime(tmp_path):
    path = tmp_path/'reference.csv'
    path.write_text('cell,g1,g2\na,1,2\n')
    with pytest.raises(ValueError,match='cell_type.*pseudotime'):
        load_skill('bulkrna-trajblend').read_reference(path)


def test_seeded_demo_and_placement_leave_global_rng_unchanged():
    lib = load_skill('bulkrna-trajblend')
    before = np.random.get_state()
    bulk,reference,labels,time = lib.demo_data(random_state=42)
    first = lib.map_trajectory(bulk,reference=reference,labels=labels,pseudotime=time,random_state=42)
    second = lib.map_trajectory(bulk,reference=reference,labels=labels,pseudotime=time,random_state=42)
    np.testing.assert_array_equal(first.to_numpy(),second.to_numpy())
    after = np.random.get_state()
    assert np.array_equal(before[1],after[1]) and before[2:] == after[2:]

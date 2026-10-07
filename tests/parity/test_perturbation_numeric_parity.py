"""Retain numeric regression coverage across M7's intentional schema/order changes."""

import subprocess
import sys

import pandas as pd
import pytest

from tests.parity import snapshot

pytestmark = pytest.mark.slow


@pytest.mark.parametrize('skill,case', [
    ('sc-in-silico-perturbation', 'default'), ('sc-in-silico-perturbation', 'top500'),
    ('sc-drug-response', 'default'), ('sc-drug-response', 'two_groups'),
])
@pytest.mark.parametrize('surface', ['api', 'cli'])
def test_corrected_tables_keep_original_numeric_scores(skill, case, surface, tmp_path):
    golden = snapshot.golden_dir(skill, case)
    if not (golden / 'summary.json').is_file():
        pytest.skip('local old-CLI baseline is not recorded')
    output = tmp_path / surface
    if surface == 'cli':
        result = snapshot.run_cli(skill, case, output)
    else:
        result = subprocess.run([sys.executable, '-m', 'tests.parity.api_runs', skill, case, str(output)],
                                cwd=snapshot.REPO, env=snapshot.child_env(), capture_output=True,
                                text=True, timeout=600, start_new_session=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    name = 'diff_regulation.csv' if skill == 'sc-in-silico-perturbation' else 'drug_rankings.csv'
    expected = pd.read_csv(golden / 'tables' / name)
    actual = pd.read_csv(output / 'tables' / name)
    if skill == 'sc-in-silico-perturbation':
        keys, columns = ['gene'], ['dr_score', 'wt_ko_corr']
        assert not {'p_value', 'p.adj', 'z_score', 'FC'} & set(actual.columns)
    else:
        keys, columns = ['Drug', 'Cluster'], ['Score', 'Rank', 'TargetGenes', 'TotalTargets', 'OverlapPct']
        assert 'Score' not in actual
        actual = actual.rename(columns={'mean_target_expression': 'Score'})
    pd.testing.assert_frame_equal(expected.set_index(keys)[columns].sort_index(),
                                  actual.set_index(keys)[columns].sort_index(),
                                  check_exact=False, rtol=1e-12, atol=0.)

"""Partially observed distances remain explicitly unchecked in CLI artifacts."""
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd
import pytest

pytestmark = pytest.mark.cli_subprocess


@pytest.mark.parametrize('observed,rate', [(20., 100.), (float('nan'), None)])
def test_cli_does_not_count_unobserved_distances_as_failed(tmp_path, observed, rate):
    source = tmp_path / 'crosslinks.csv'
    pd.DataFrame({'protein_a': ['A', 'B'], 'protein_b': ['B', 'C'],
                  'distance_angstrom': [observed, float('nan')]}).to_csv(source, index=False)
    script = Path(__file__).resolve().parents[1] / 'struct_proteomics.py'
    output = tmp_path / 'out'
    proc = subprocess.run([sys.executable, str(script), '--input', str(source), '--output', str(output)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((output / 'result.json').read_text(),
                        parse_constant=lambda value: pytest.fail(f'Non-standard JSON number: {value}'))
    assert result['summary']['constraint_satisfaction_rate'] == rate
    assert result['data']['diagnostics']['n_distance_unchecked'] == (1 if rate else 2)
    table = pd.read_csv(output / 'tables/crosslinks.csv')
    assert pd.isna(table.loc[1, 'constraint_satisfied'])

import pandas as pd
import pytest
import json
import subprocess
import sys
from pathlib import Path
from skills._sdk.notebook import load_skill


def test_missing_reference_is_rejected():
    with pytest.raises(ValueError, match='explicit reference'):
        load_skill('metabolomics-annotation').annotate(pd.DataFrame({'mz': [181.07066446677]}))


@pytest.mark.cli_subprocess
def test_real_cli_missing_reference_is_rejected(tmp_path):
    data = tmp_path / 'features.csv'
    data.write_text('mz\n181.07066446677\n')
    script = Path(__file__).parents[1] / 'metabolomics_annotation.py'
    output = tmp_path / 'output'
    completed = subprocess.run([sys.executable, str(script), '--input', str(data), '--output', str(output)], capture_output=True, text=True)
    assert completed.returncode != 0
    assert '--reference-file' in completed.stderr
    assert not (output / 'result.json').exists()


@pytest.mark.cli_subprocess
@pytest.mark.parametrize('demo', [False, True])
def test_cli_uses_explicit_reference_and_records_scope(tmp_path, demo):
    script = Path(__file__).parents[1] / 'metabolomics_annotation.py'
    output = tmp_path / 'output'
    arguments = ['--demo']
    if not demo:
        data = tmp_path / 'features.csv'
        data.write_text('mz\n101.00727646677\n')
        reference = tmp_path / 'reference.csv'
        reference.write_text('name,neutral_mass,database_id,formula\ncustom,100,X,C\n')
        arguments = ['--input', str(data), '--reference-file', str(reference)]
    completed = subprocess.run([sys.executable, str(script), *arguments, '--output', str(output)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    envelope = json.loads((output / 'result.json').read_text())
    assert envelope['data']['run_info']['reference_scope'] == ('demo' if demo else 'provided')
    if not demo:
        table = pd.read_csv(output / 'tables/annotations.csv')
        assert table['name'].tolist() == ['custom']


def test_annotation_matches_glucose_adduct_without_mutating_input():
    library = load_skill('metabolomics-annotation')
    data = pd.DataFrame({'mz': [181.07066446677, 9999.]})
    result = library.annotate(data, reference=library.demo_reference())
    assert result['name'].tolist() == ['D-Glucose', 'Unknown']
    assert result.loc[0, 'ppm_error'] == 0.
    assert library.run_info(result)['reference_scope'] == 'demo'
    assert library.mass_error_figure(result).axes


def test_unimplemented_database_is_not_a_different_label_on_demo_results():
    with pytest.raises(ValueError, match='reference'):
        load_skill('metabolomics-annotation').annotate(pd.DataFrame({'mz': [100.]}), database='kegg')


def test_caller_supplied_reference_is_used():
    library = load_skill('metabolomics-annotation')
    reference = pd.DataFrame({'name': ['custom'], 'neutral_mass': [100.], 'database_id': ['X'], 'formula': ['C']})
    result = library.annotate(pd.DataFrame({'mz': [101.00727646677]}), database='custom', reference=reference)
    assert result['name'].tolist() == ['custom']

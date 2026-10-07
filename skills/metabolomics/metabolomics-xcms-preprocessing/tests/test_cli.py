import subprocess
import sys
from pathlib import Path
import pandas as pd
import pytest

pytestmark = pytest.mark.cli_subprocess
SCRIPT = Path(__file__).parents[1] / 'metabolomics_xcms_preprocessing.py'


def test_real_input_cannot_produce_simulated_peaks(tmp_path):
    source = tmp_path / 'sample.mzML'
    source.write_text('<mzML/>')
    output = tmp_path / 'output'
    result = subprocess.run([sys.executable, str(SCRIPT), '--input', str(source), '--output', str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'simulation' in result.stderr
    assert not (output / 'tables' / 'peak_table.csv').exists()


def test_demo_parameters_control_synthetic_peak_count(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), '--demo', '--ppm', '5', '--output', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(pd.read_csv(tmp_path / 'tables' / 'peak_table.csv')) == 240

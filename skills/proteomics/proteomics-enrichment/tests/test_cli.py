import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.cli_subprocess
SCRIPT = Path(__file__).resolve().parents[1] / 'prot_enrichment.py'


def test_real_input_requires_an_explicit_pathway_database(tmp_path):
    input_path = tmp_path/'proteins.csv'
    input_path.write_text('protein_id\nA\nB\n')
    command = [sys.executable,str(SCRIPT),'--input',str(input_path),'--output',str(tmp_path/'out')]
    result = subprocess.run(command,capture_output=True,text=True)
    assert result.returncode != 0
    assert '--pathways is required' in result.stderr
    assert not (tmp_path/'out/result.json').exists()
    pathways = tmp_path/'pathways.json'
    pathways.write_text('{"example":["A","B"]}')
    result = subprocess.run(command+['--pathways',str(pathways),'--background-size','4'],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path/'out/tables/enrichment_results.csv').exists()

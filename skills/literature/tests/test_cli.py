import json
import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.cli_subprocess
SCRIPT = Path(__file__).parents[1] / 'literature_parse.py'


def test_local_text_cli_preserves_metadata_and_source_artifacts(tmp_path):
    text = 'Human brain Visium data are available as GSE123456.'
    result = subprocess.run([sys.executable, str(SCRIPT), '--input', text, '--input-type', 'text', '--no-download', '--output', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / 'extracted_metadata.json').read_text()) == {
        'geo_accessions': {'gse': ['GSE123456'], 'gsm': [], 'gpl': []},
        'organism': 'homo sapiens', 'tissue': 'brain', 'technology': 'Visium'}
    assert (tmp_path / 'source.txt').read_text() == text
    assert json.loads((tmp_path / 'result.json').read_text())['data']['download_results'] == []

import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.cli_subprocess
SCRIPT = Path(__file__).parents[1] / 'bulkrna_ppi_network.py'


def test_human_demo_edges_cannot_be_labelled_as_mouse(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), '--demo', '--species', '10090', '--output', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'human' in result.stderr

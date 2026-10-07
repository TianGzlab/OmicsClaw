import json
import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.cli_subprocess
SCRIPT = Path(__file__).resolve().parents[1]/'bulkrna_read_alignment.py'


def test_real_alignment_log_does_not_create_synthetic_gene_body_coverage(tmp_path):
    source = tmp_path/'meta_info.json'
    source.write_text('{"num_processed":100,"num_mapped":90}')
    output = tmp_path/'out'
    proc = subprocess.run([sys.executable,str(SCRIPT),'--input',str(source),'--method','salmon','--output',str(output)],capture_output=True,text=True)
    assert proc.returncode == 0,proc.stderr
    assert not (output/'figures/gene_body_coverage.png').exists()
    summary = json.loads((output/'result.json').read_text())['summary']
    assert summary['mapped'] == 90 and 'uniquely_mapped' not in summary

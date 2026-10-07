"""Spatial communication examples run and replay through the public step runner."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skill_example
REPO = Path(__file__).resolve().parents[4]


def test_communication_example_replays(tmp_path):
    skill = 'spatial-communication'
    runner = REPO / 'skills/_sdk/notebook/run.py'
    env = {**os.environ, 'PYTHONHASHSEED': '0', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'NUMBA_NUM_THREADS': '1'}
    env.pop('NUMBA_DISABLE_JIT', None)
    env.pop('OMICSCLAW_SKILL_STUBS', None)

    def command(*args):
        result = subprocess.run([sys.executable, str(runner), *args], cwd=tmp_path,
                                env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]

    command('new', 'expression')
    module = tmp_path / 'analysis/01_expression'
    shutil.copy2(REPO / f'skills/spatial/{skill}/examples/example_step.py', module / '01_analysis.py')
    (module / '02_validate.py').write_text(
        "# %%\nfrom skills._sdk.notebook import read_input\n"
        "data = read_input('results/01_expression/intermediate/processed.h5ad')\n"
        "assert data.n_obs > 100 and data.n_vars > 10000\n"
        "assert 'spatial' in data.obsm and 'ccc_results' in data.uns\n", encoding='utf-8')
    command('run', 'analysis/01_expression')
    tables = sorted((tmp_path / 'results/01_expression/tables').glob('*.csv'))
    assert tables
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tables}
    command('replay', 'analysis/01_expression')
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tables} == before

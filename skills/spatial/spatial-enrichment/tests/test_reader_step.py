"""Gene-set input files appear in the public step provenance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.skill_example, pytest.mark.skill_example_spatial]


def test_local_gene_sets_are_hashed_as_step_inputs(tmp_path):
    runner = Path(__file__).resolve().parents[4] / 'skills/_sdk/notebook/run.py'
    env = {**os.environ, 'NUMBA_DISABLE_JIT': '0', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'NUMBA_NUM_THREADS': '1'}
    def command(*args):
        result = subprocess.run([sys.executable, str(runner), *args], cwd=tmp_path,
            env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]

    command('new', 'genesets')
    source = tmp_path / 'data/sets.gmt'
    source.parent.mkdir(exist_ok=True)
    source.write_text('marker\tdescription\tGene_000\tGene_001\n')
    (tmp_path / 'analysis/01_genesets/01_read.py').write_text(
        "# %%\nfrom skills._sdk.notebook import load_skill, read_input, write_output\n"
        "library = load_skill('spatial-enrichment')\n"
        "sets = read_input('data/sets.gmt', reader=library.read_gene_sets)\n"
        "assert sets == {'marker': ['Gene_000', 'Gene_001']}\n"
        "write_output(sets, 'tables/sets.json')\n")
    command('run', 'analysis/01_genesets')
    manifest = json.loads((tmp_path / 'results/01_genesets/provenance/manifest.json').read_text())
    inputs = [item for step in manifest['steps'] for item in step['inputs']]
    recorded = next(item for item in inputs if item['path'] == 'data/sets.gmt')
    assert recorded['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()

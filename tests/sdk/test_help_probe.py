"""Every skill main script answers ``--help`` (plan 0062 case 24).

Slow; uses the interpreter named by ``OMICSCLAW_TEST_BASE_PYTHON`` (see
``test_sc_scripts_help.py``). Every script :func:`main_scripts` finds must
answer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.sdk._scan import rel
from tests.sdk.test_bootstrap import main_scripts
from tests.sdk.test_sc_scripts_help import base_python, run_help

pytestmark = pytest.mark.slow

def test_every_skill_script_answers_help(tmp_path):
    python = base_python()
    scripts = main_scripts()
    assert len(scripts) == 89

    def probe(script):
        return rel(script), run_help(python, script, tmp_path).returncode

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(pool.map(probe, scripts))
    failed = {name for name, code in results.items() if code != 0}
    assert failed == set()

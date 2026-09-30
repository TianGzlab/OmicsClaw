"""Every skill main script answers ``--help`` (plan 0062 case 24).

Slow; uses the interpreter named by ``OMICSCLAW_TEST_BASE_PYTHON`` (see
``test_sc_scripts_help.py``). The four consensus shells still import the
unimportable ``omicsclaw.runtime.consensus`` and are expected to fail until
plan 0058 replaces them; the set of failures must equal exactly those four.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.sdk._scan import rel
from tests.sdk.test_bootstrap import main_scripts
from tests.sdk.test_sc_scripts_help import base_python, run_help

pytestmark = pytest.mark.slow

EXPECTED_FAILURES = {
    "skills/singlecell/scrna/sc-consensus-clustering/sc_consensus_clustering.py",
    "skills/singlecell/scrna/sc-consensus-integration/sc_consensus_integration.py",
    "skills/singlecell/scrna/sc-consensus-pseudotime/sc_consensus_pseudotime.py",
    "skills/spatial/consensus-domains/consensus_domains.py",
}


def test_all_but_the_consensus_shells_answer_help(tmp_path):
    python = base_python()
    scripts = main_scripts()
    assert len(scripts) == 94

    def probe(script):
        return rel(script), run_help(python, script, tmp_path).returncode

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(pool.map(probe, scripts))
    failed = {name for name, code in results.items() if code != 0}
    assert failed == EXPECTED_FAILURES

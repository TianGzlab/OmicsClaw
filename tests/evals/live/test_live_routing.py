"""Which skill a real model picks for each routing seed.

Runs every seed ``OMICSCLAW_EVAL_LIVE_TRIALS`` times against the
provider of the repository's ``.env`` and records the verdicts for the
session report. Pass rates never fail a test; a seed fails only when
every trial ended in a provider error or a timeout, so a dead key or a
down service shows up. Run by hand, one process, in an environment with
the skills' dependencies (``--help`` runs for real)::

    OMICSCLAW_EVAL_LIVE=1 OMICSCLAW_EVAL_LIVE_TRIALS=3 \\
    OMICSCLAW_EVAL_REPORT_DIR=build/live-eval \\
    /opt/conda/envs/OmicsClaw/bin/python -m pytest -q -p no:randomly -m eval tests/evals/live
"""

from __future__ import annotations

import os

import pytest

from omicsclaw.evals import run_case
from omicsclaw.evals.live import (
    RecordingProvider,
    SeedReport,
    judge,
    live_case,
    load_seeds,
    trial_record,
)
from omicsclaw.evals.runner import skill_index

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(os.environ.get("OMICSCLAW_EVAL_LIVE") != "1", reason="set OMICSCLAW_EVAL_LIVE=1"),
]

TRIAL_TIMEOUT_S = 300.0


@pytest.mark.parametrize("seed", load_seeds(), ids=lambda seed: seed.id)
def test_live_routing(seed, tmp_path, live_setup, live_seeds):
    trials = []
    for trial in range(live_setup.trials):
        root = tmp_path / f"t{trial}"
        made: list[RecordingProvider] = []

        def provider():
            recorder = RecordingProvider(live_setup.provider())
            made.append(recorder)
            return recorder

        case, denials = live_case(
            seed, provider, root / "ws", skill_index(), trial=trial,
            stubs=live_setup.stubs, config=live_setup.app_config,
        )
        result = run_case(case, root, timeout_s=TRIAL_TIMEOUT_S)
        verdict = judge(result, seed, made[0].replies, denials)
        trials.append(trial_record(verdict, result, made[0].usage, denials, live_setup.stubs))
    report = SeedReport(seed, tuple(trials))
    live_seeds.append(report)
    if report.errors == len(trials):
        pytest.fail(
            f"{seed.id}: every trial errored: {[t.verdict.harness_failures for t in trials]}",
            pytrace=False,
        )

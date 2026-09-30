"""``omicsclaw.ensemble.tuning`` — choose K from stability evidence, then tune each method at that K.

Agent-side modules (imported by the agent process; no numerical library):

- :mod:`~omicsclaw.ensemble.tuning.budget` — per-session, per-method run budgets.
- :mod:`~omicsclaw.ensemble.tuning.search` — search dimensions and candidate points.
- :mod:`~omicsclaw.ensemble.tuning.probe` — the probe design: K grid, resolution grid, subsamples.
- :mod:`~omicsclaw.ensemble.tuning.evidence` — stable peaks and the fallback K.
- :mod:`~omicsclaw.ensemble.tuning.calibrate` — reaching a target K by bisection.
- :mod:`~omicsclaw.ensemble.tuning.scoring` — the fixed-K score and its standard error.
- :mod:`~omicsclaw.ensemble.tuning.judge` — skipping stage 2 and choosing trials.
- :mod:`~omicsclaw.ensemble.tuning.prompts` — prompt inputs, templates and output checks.
- :mod:`~omicsclaw.ensemble.tuning.llm` — model calls with retries, recording and replay.
- :mod:`~omicsclaw.ensemble.tuning.ledger` — the event ledger and ``selection.json``.
- :mod:`~omicsclaw.ensemble.tuning.pipeline` — :class:`TuningPipeline`.
- :mod:`~omicsclaw.ensemble.tuning.tools` — ``optimize_params``, ``inspect_trials``, ``select_result``.

Execution-side modules (run as ``python -m`` under the skill interpreter):
:mod:`~omicsclaw.ensemble.tuning.subsample`, :mod:`~omicsclaw.ensemble.tuning.stability`,
:mod:`~omicsclaw.ensemble.tuning.markers` and :mod:`~omicsclaw.ensemble.tuning.inspect`.

This module imports nothing.
"""

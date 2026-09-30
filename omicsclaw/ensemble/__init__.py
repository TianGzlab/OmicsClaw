"""``omicsclaw.ensemble`` — run skill methods side by side and score them alike.

Submodules, each imported on its own:

- :mod:`~omicsclaw.ensemble.space` — the ``tuning.yaml`` search space of a skill.
- :mod:`~omicsclaw.ensemble.resources` — the GPU/memory/CPU pool trials share.
- :mod:`~omicsclaw.ensemble.execution` — where a trial's commands run.
- :mod:`~omicsclaw.ensemble.store` — the ``ensemble_runs/`` directory layout.
- :mod:`~omicsclaw.ensemble.runner` — one trial, and many in parallel.
- :mod:`~omicsclaw.ensemble.metrics` — the internal quality panels.
- :mod:`~omicsclaw.ensemble.evaluation` — ground-truth metrics, kept off the run path.
- :mod:`~omicsclaw.ensemble.tool` — the ``run_skill`` tool.

The names ``tuning`` (parameter search) and ``consensus`` (combining trials)
are reserved for later modules of this package.

This module imports nothing: the scoring half of the package runs under the
skill interpreter, which may be an older Python without the agent's
dependencies, and importing the package there must stay cheap.
"""

RUNS_DIRNAME = "ensemble_runs"
"""Directory under the workspace that holds every ensemble run."""

__all__ = ["RUNS_DIRNAME"]

"""LLM directive generator for autoagent optimization.

Mirrors AutoAgent's ``program.md`` — generates a structured prompt that
tells the LLM meta-agent what it is optimizing, what it can change,
the experiment history, and asks it to suggest the next parameter set.
"""

from __future__ import annotations

from typing import Any

from omicsclaw.autoagent.evaluator import Evaluator
from omicsclaw.autoagent.experiment_ledger import ExperimentLedger
from omicsclaw.autoagent.metrics_registry import MetricDef
from omicsclaw.autoagent.search_space import SearchSpace


def build_directive(
    skill_name: str,
    method: str,
    search_space: SearchSpace,
    metrics: dict[str, MetricDef],
    ledger: ExperimentLedger,
    max_trials: int,
) -> str:
    """Build the meta-agent directive for parameter optimization.

    The directive structure mirrors AutoAgent's ``program.md``:

    1. **Directive** — what you are optimizing and why
    2. **What You Can Modify** — parameters with ranges and tips
    3. **What You Must Not Modify** — fixed params, skill code
    4. **Goal** — maximize composite metric
    5. **Simplicity Criterion** — fewer changes preferred at equal score
    6. **Experiment History** — full trial ledger
    7. **Failure Analysis** — patterns to look for
    8. **Output Format** — structured JSON
    """
    import math

    best = ledger.best_trial()
    if best is not None and math.isfinite(best.composite_score):
        best_score = f"{best.composite_score:.4f}"
    else:
        best_score = "N/A"
    trials_run = len(ledger)

    sections = [
        _section_directive(skill_name, method),
        _section_search_space(search_space),
        _section_metrics(metrics),
        _section_goal(best_score),
        _section_simplicity(),
        _section_history(ledger),
        _section_failure_analysis(),
        _section_output_format(search_space),
        _section_budget(trials_run, max_trials),
    ]
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Directive sections
# ---------------------------------------------------------------------------


def _section_directive(skill_name: str, method: str) -> str:
    return f"""## Directive

You are an autonomous parameter optimization agent for OmicsClaw.

Your job is to improve the analysis quality of the **{skill_name}** skill
(method: **{method}**) by finding better parameter values.  You do NOT
modify code — you suggest parameter values, the system runs the skill,
and you learn from the results.

This is inspired by AutoAgent: you diagnose, suggest, evaluate, decide."""


def _section_search_space(ss: SearchSpace) -> str:
    lines = ["## What You Can Modify", ""]
    lines.append("Tunable parameters (you may change these):")
    lines.append("")
    for p in ss.tunable:
        range_info = ""
        if p.low is not None and p.high is not None:
            range_info = f", range: [{p.low}, {p.high}]"
        elif p.choices is not None:
            range_info = f", choices: {p.choices}"
        tip_info = f"\n    Tip: {p.tip}" if p.tip else ""
        lines.append(
            f"  - **{p.name}** ({p.param_type}): default={p.default}"
            f"{range_info}{tip_info}"
        )

    if ss.fixed:
        lines.append("")
        lines.append("Fixed parameters (do NOT change these):")
        for k, v in ss.fixed.items():
            lines.append(f"  - {k} = {v}")

    return "\n".join(lines)


def _section_metrics(metrics: dict[str, MetricDef]) -> str:
    lines = ["## Evaluation Metrics", ""]
    lines.append("Your suggested parameters will be scored using these metrics:")
    lines.append("")
    for name, m in metrics.items():
        range_info = f", range: [{m.range_min}, {m.range_max}]"
        lines.append(
            f"  - **{name}**: {m.direction} (weight={m.weight}{range_info})"
        )
        if m.description:
            lines.append(f"    {m.description}")
    lines.append("")
    lines.append(
        "The composite score is a weighted sum of **normalized** metric values "
        "(each metric is scaled to 0-1 based on its typical range, then "
        "minimization metrics are flipped so higher is always better)."
    )
    return "\n".join(lines)


def _section_goal(best_score: str) -> str:
    return f"""## Goal

Maximize the composite score.  Current best: **{best_score}**.

Use the composite score as the primary metric.  If two parameter sets
achieve the same score, the simpler one (fewer changes from defaults) wins."""


def _section_simplicity() -> str:
    return """## Simplicity Criterion

All else being equal, simpler is better.

If a change achieves the same score with fewer parameter modifications,
prefer it.  Do not add complexity without measurable improvement."""


def _section_history(ledger: ExperimentLedger) -> str:
    if len(ledger) == 0:
        return "## Experiment History\n\nNo trials yet — this will be the baseline run."
    return f"## Experiment History\n\n{ledger.to_history_text()}"


def _section_failure_analysis() -> str:
    return """## Failure Analysis Guidance

When diagnosing trial results, look for these patterns:

- **Trade-off shifts**: One metric improved but another regressed.
  Identify which parameter change caused the shift.
- **Diminishing returns**: A parameter has been pushed far but gains
  are shrinking — try a different parameter instead.
- **Crash patterns**: Certain parameter ranges cause the skill to fail.
  Avoid those regions.
- **Plateau**: Score hasn't improved for several trials.  Try a larger
  step or a different parameter combination.

Prefer changes that improve overall quality, not just one metric."""


def _section_output_format(ss: SearchSpace) -> str:
    param_example = ", ".join(
        f'"{p.name}": {_example_value(p)}' for p in ss.tunable[:3]
    )
    return f"""## Output Format

Respond with **only** a JSON object (no markdown fences, no explanation outside):

```
{{
  "params": {{{param_example}}},
  "reasoning": "Brief explanation of why you chose these values."
}}
```

Or, if you believe optimization has converged:

```
{{
  "converged": true,
  "reasoning": "Explanation of why further trials are unlikely to help."
}}
```"""


def _section_budget(trials_run: int, max_trials: int) -> str:
    remaining = max(0, max_trials - trials_run)
    return (
        f"## Budget\n\n"
        f"Trials run: {trials_run} / {max_trials}.  "
        f"Remaining: {remaining}.  Use them wisely."
    )


def _example_value(p) -> str:
    """Produce an example value for the output format section."""
    if p.param_type == "float":
        return str(p.default)
    if p.param_type == "int":
        return str(p.default)
    if p.param_type == "bool":
        return "true"
    return f'"{p.default}"'

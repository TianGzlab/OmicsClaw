"""Decisions made without a model: skipping stage 2, and choosing trials.

A trial is *eligible* at K when it ended ok, has exactly K labels and has a
fixed-K score. Choices use the score's standard error as the margin:

- stage 2 is skipped when no stage-1 trial beats the default's score by more
  than the default's standard error;
- a method's answer is the simplest eligible trial within one standard error
  of its best (fewest parameters away from the defaults, then the smallest
  normalised distance, then the earliest), or its default trial when no
  trial is eligible and the default ended ok;
- the pipeline's answer is the method answer with the highest score among
  those at K.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from omicsclaw.ensemble.space import MethodSpec
from omicsclaw.ensemble.tuning.search import deviation

__all__ = [
    "Evaluated",
    "MethodChoice",
    "choose_final",
    "choose_method",
    "eligible",
    "skip_stage2",
]


@dataclass
class Evaluated:
    """One evaluated parameter set of one method, as the judge sees it.

    ``status`` is the trial's status, or ``off_k``/``unreachable_k`` for a
    calibration that did not land on K. ``seq`` orders trials by when they were
    planned.
    """

    method: str
    run_id: str
    trial: str
    seq: int
    params: dict[str, Any]
    status: str
    n_labels: int | None = None
    score: float | None = None
    se: float | None = None
    source: str = ""
    stage: str = ""
    is_default: bool = False
    duplicate_of: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def eligible(item: Evaluated, k: int) -> bool:
    """Whether *item* ended ok with exactly *k* labels and a fixed-K score."""
    return item.status == "ok" and item.n_labels == k and item.score is not None


def skip_stage2(default: Evaluated | None, stage1: Sequence[Evaluated], k: int) -> tuple[bool, dict[str, Any]]:
    """Whether stage 2 is skipped, and the numbers behind the decision.

    Skipped when no eligible stage-1 trial scores above ``default.score +
    default.se``. A default without a score at K (or without a standard error)
    sets no bar: stage 2 then runs whenever some stage-1 trial is eligible.
    """
    scored = [item for item in stage1 if eligible(item, k)]
    best = max(scored, key=lambda item: item.score) if scored else None
    reason: dict[str, Any] = {
        "stage1_best": best.score if best else None,
        "stage1_best_trial": best.trial if best else None,
        "default_score": default.score if default else None,
        "default_se": default.se if default else None,
    }
    if best is None:
        reason["why"] = "no stage-1 trial is eligible"
        return True, reason
    if default is None or not eligible(default, k) or default.se is None:
        reason["why"] = "the default has no score at K"
        return False, reason
    bar = default.score + default.se  # type: ignore[operator]
    reason["bar"] = bar
    if best.score > bar:  # type: ignore[operator]
        reason["why"] = "stage 1 beat the default by more than its standard error"
        return False, reason
    reason["why"] = "no stage-1 trial beat the default by more than its standard error"
    return True, reason


@dataclass
class MethodChoice:
    """One method's answer.

    ``status`` is ``ok``, ``fallback_default`` (no eligible trial; the
    default trial is the answer and may not have K labels) or ``failed``
    (no eligible trial and no default trial that ended ok).
    """

    method: str
    status: str
    chosen: Evaluated | None
    within_se: list[str] = field(default_factory=list)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    best_score: float | None = None
    best_se: float | None = None


def choose_method(
    items: Sequence[Evaluated],
    k: int,
    method_spec: MethodSpec,
    *,
    ignore: Iterable[str] = (),
) -> MethodChoice:
    """The method's answer at *k*; see the module docstring.

    :param ignore: Parameters not counted as deviations (K and the pins).
    """
    ignored = tuple(ignore)
    method = method_spec.name
    pool = [item for item in items if eligible(item, k)]
    if not pool:
        default = next((item for item in items if item.is_default), None)
        if default is None or default.status != "ok":
            return MethodChoice(method=method, status="failed", chosen=None)
        return MethodChoice(method=method, status="fallback_default", chosen=default)
    best = max(pool, key=lambda item: (item.score, -item.seq))
    margin = best.se or 0.0
    band = [item for item in pool if item.score >= best.score - margin]  # type: ignore[operator]
    ranked = []
    for item in band:
        count, distance = deviation(item.params, method_spec, ignore=ignored)
        ranked.append(((count, round(distance, 12), item.seq), item))
    ranked.sort(key=lambda pair: pair[0])
    chosen = ranked[0][1]
    return MethodChoice(
        method=method,
        status="ok",
        chosen=chosen,
        within_se=[item.trial for _, item in ranked],
        ranking=[
            {"trial": item.trial, "deviations": key[0], "distance": key[1], "seq": key[2], "score": item.score}
            for key, item in ranked
        ],
        best_score=best.score,
        best_se=best.se,
    )


def choose_final(choices: Mapping[str, MethodChoice], k: int) -> MethodChoice | None:
    """The method answer with the highest fixed-K score among those at *k*.

    A tie goes to the method listed first. ``None`` when no method has an
    eligible answer.
    """
    at_k = [
        choice for choice in choices.values()
        if choice.status == "ok" and choice.chosen is not None and eligible(choice.chosen, k)
    ]
    if not at_k:
        return None
    return max(at_k, key=lambda choice: (choice.chosen.score, -list(choices).index(choice.method)))  # type: ignore[union-attr]

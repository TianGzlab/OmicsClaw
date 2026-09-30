"""Combine a panel's metric results into one score.

Pure Python. Each metric result carries ``raw``, ``expected`` and ``adjusted``
values; the score is the weighted mean of the adjusted values clipped to
[0, 1], over the scored metrics that neither failed nor were degenerate, with
the weights renormalised over those.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional


@dataclass
class MetricResult:
    """One metric's values, or the reason it has none.

    ``expected`` is the value of a random labelling with the same label sizes;
    ``adjusted`` is 1 for perfect, 0 for chance level and negative below it.
    ``degenerate`` marks a metric whose chance correction is undefined for
    this labelling. ``extra`` holds diagnostics that are reported, never scored.
    """

    raw: Optional[float] = None
    expected: Optional[float] = None
    adjusted: Optional[float] = None
    error: str = ""
    degenerate: bool = False
    extra: Dict[str, object] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return (
            not self.error
            and not self.degenerate
            and self.adjusted is not None
            and math.isfinite(self.adjusted)
        )


def clip01(value: float) -> float:
    """*value* clipped to [0, 1]."""
    return min(1.0, max(0.0, value))


def combine(
    results: Mapping[str, MetricResult],
    weights: Mapping[str, float],
) -> Dict[str, object]:
    """The panel score and the bookkeeping behind it.

    :returns: ``score`` (``None`` when no scored metric is usable), the
        ``weights_used`` after renormalisation, the ``dropped`` scored metrics
        with their reasons, and the per-metric ``clipped`` values.
    """
    usable = {name: weight for name, weight in weights.items() if weight > 0}
    dropped: Dict[str, str] = {}
    clipped: Dict[str, float] = {}
    for name in list(usable):
        result = results.get(name)
        if result is None:
            dropped[name] = "not computed"
        elif result.error:
            dropped[name] = result.error
        elif result.degenerate:
            dropped[name] = "degenerate"
        elif not result.usable:
            dropped[name] = "no adjusted value"
        else:
            clipped[name] = clip01(float(result.adjusted))
            continue
        usable.pop(name)
    total = sum(usable.values())
    if total <= 0:
        return {"score": None, "weights_used": {}, "dropped": dropped, "clipped": clipped}
    weights_used = {name: weight / total for name, weight in usable.items()}
    score = sum(weights_used[name] * clipped[name] for name in weights_used)
    return {
        "score": score,
        "weights_used": weights_used,
        "dropped": dropped,
        "clipped": clipped,
    }


def to_json(results: Mapping[str, MetricResult]) -> Dict[str, Dict[str, object]]:
    """``raw``/``expected``/``adjusted``/``errors``/``degenerate`` as JSON-ready maps."""
    raw: Dict[str, object] = {}
    expected: Dict[str, object] = {}
    adjusted: Dict[str, object] = {}
    errors: Dict[str, str] = {}
    degenerate: List[str] = []
    extra: Dict[str, object] = {}
    for name, result in results.items():
        raw[name] = _finite(result.raw)
        expected[name] = _finite(result.expected)
        adjusted[name] = _finite(result.adjusted)
        if result.error:
            errors[name] = result.error
        if result.degenerate:
            degenerate.append(name)
        if result.extra:
            extra[name] = result.extra
    return {
        "raw": raw,
        "expected": expected,
        "adjusted": adjusted,
        "errors": errors,
        "degenerate_metrics": degenerate,
        "diagnostics": extra,
    }


def _finite(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


__all__ = ["MetricResult", "clip01", "combine", "to_json"]

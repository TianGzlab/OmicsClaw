"""Reaching a target number of labels with a parameter that moves it monotonically.

Each parameter set runs once at an initial value. When the number of labels
misses the target, the next value is the geometric mean of the bracket: the
largest value known to give fewer labels and the smallest known to give more,
among the runs of the same parameter set (and any history the caller passes).
A side with no such run is first tried at the range's end; when the end
itself misses on the same side the target is unreachable. At most
``extra`` runs follow the first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Mapping

__all__ = ["CALIBRATION_RUNS", "Calibration", "calibrate", "initial_value"]

CALIBRATION_RUNS = 4
_DIGITS = 4


@dataclass
class Calibration:
    """How a calibration ended.

    ``status``: ``ok`` (a run hit the target), ``off_k`` (the runs were
    spent), ``unreachable_k`` (an end of the range misses on the same side)
    or ``failed`` (a run failed). ``runs`` lists ``(value, n_labels, payload)``
    for every run made here, in order; ``hit`` is the run that reached the
    target, ``closest`` the run nearest to it.
    """

    status: str
    runs: list[tuple[float, int | None, Any]] = field(default_factory=list)
    hit: tuple[float, int | None, Any] | None = None
    closest: tuple[float, int | None, Any] | None = None


def initial_value(mapping: Mapping[float, int], target: int, *, low: float, high: float) -> float:
    """A first value for *target* from a known ``value -> n_labels`` mapping.

    The median of the values that gave *target*; otherwise the geometric mean
    of the bracket around it (a missing side is the range's end); ``1.0``
    clipped into the range when *mapping* is empty.
    """
    exact = sorted(value for value, n in mapping.items() if n == target)
    if exact:
        return exact[len(exact) // 2]
    if not mapping:
        return min(high, max(low, 1.0))
    below = [value for value, n in mapping.items() if n < target]
    above = [value for value, n in mapping.items() if n > target]
    lo = max(below) if below else low
    hi = min(above) if above else high
    if lo > hi:
        lo, hi = min(lo, hi), max(lo, hi)
    return round(math.sqrt(lo * hi), _DIGITS)


def _bracket(known: Iterable[tuple[float, int]], target: int) -> tuple[float | None, float | None]:
    below = [value for value, n in known if n < target]
    above = [value for value, n in known if n > target]
    return (max(below) if below else None, min(above) if above else None)


async def calibrate(
    target: int,
    run: Callable[[float], Awaitable[tuple[int | None, Any]]],
    *,
    initial: float,
    low: float,
    high: float,
    history: Iterable[tuple[float, int]] = (),
    extra: int = CALIBRATION_RUNS,
) -> Calibration:
    """Run *run* until it returns *target* labels or the runs are spent.

    :param run: Called with a value; returns the number of labels (``None``
        when the run failed) and anything to keep with it.
    :param history: ``(value, n_labels)`` of earlier runs of the same
        parameter set, used for the bracket and not re-run.
    """
    known: list[tuple[float, int]] = list(history)
    tried = {round(value, _DIGITS) for value, _ in known}
    result = Calibration(status="off_k")
    value = round(min(high, max(low, initial)), _DIGITS)
    for attempt in range(extra + 1):
        n_labels, payload = await run(value)
        entry = (value, n_labels, payload)
        result.runs.append(entry)
        tried.add(value)
        if n_labels is None:
            result.status = "failed"
            break
        known.append((value, n_labels))
        if n_labels == target:
            result.status, result.hit = "ok", entry
            break
        if attempt == extra:
            break
        lo, hi = _bracket(known, target)
        if lo is None:
            if round(low, _DIGITS) in tried:
                result.status = "unreachable_k"
                break
            value = round(low, _DIGITS)
        elif hi is None:
            if round(high, _DIGITS) in tried:
                result.status = "unreachable_k"
                break
            value = round(high, _DIGITS)
        else:
            value = round(math.sqrt(lo * hi), _DIGITS)
            if value in tried:
                break
    scored = [entry for entry in result.runs if entry[1] is not None]
    if scored:
        result.closest = min(scored, key=lambda entry: (abs(entry[1] - target), entry[0]))
    return result

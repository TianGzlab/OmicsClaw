"""Reading ``stability.json``: ranks, the stable peaks and the fallback K.

A curve is *defined* at K when its value exists and, for ``f`` and ``c``,
``f(K) >= min_f``. Ranks are taken only among the K where that curve is
defined (1 is the highest value; ties share the mean rank). The *stable
peaks* are the K whose peak frequency on any curve is at least
:data:`STABLE_PEAK`. The *fallback K* is chosen among the K where at least
two curves are defined: the best mean rank, then the larger ``a``, then the
smaller K.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["CURVES", "CurveRow", "Evidence", "STABLE_PEAK", "fallback_k", "load_evidence", "ranks"]

STABLE_PEAK = 0.5
CURVES = ("f", "c", "a")


@dataclass
class CurveRow:
    """One K of the grid, as shown to the model."""

    k: int
    values: dict[str, float | None]
    bands: dict[str, tuple[float | None, float | None]]
    peak_frequency: dict[str, float | None]
    runs: int
    a_members: list[str]
    ranks: dict[str, float | None] = field(default_factory=dict)
    defined: dict[str, bool] = field(default_factory=dict)
    in_stable_peaks: bool = False


@dataclass
class Evidence:
    """The stability evidence over the grid."""

    grid: list[int]
    rows: dict[int, CurveRow]
    stable_peaks: list[int]
    fallback_k: int | None
    min_f: float

    def summary(self) -> dict[str, Any]:
        """The fields the ledger records."""
        return {
            "grid": self.grid,
            "stable_peaks": self.stable_peaks,
            "fallback_k": self.fallback_k,
            "rows": {
                str(k): {
                    "values": row.values, "bands": row.bands, "ranks": row.ranks,
                    "peak_frequency": row.peak_frequency, "runs": row.runs,
                }
                for k, row in self.rows.items()
            },
        }


def _is_defined(row: Mapping[str, Any], curve: str, min_f: float) -> bool:
    value = row.get(curve)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if curve in ("f", "c"):
        f = row.get("f")
        return f is not None and f >= min_f
    return True


def ranks(values: Mapping[int, float]) -> dict[int, float]:
    """Descending ranks of *values* (1 is the largest); ties share the mean rank."""
    ordered = sorted(values.items(), key=lambda item: -item[1])
    result: dict[int, float] = {}
    index = 0
    while index < len(ordered):
        stop = index
        while stop + 1 < len(ordered) and ordered[stop + 1][1] == ordered[index][1]:
            stop += 1
        mean = (index + 1 + stop + 1) / 2
        for position in range(index, stop + 1):
            result[ordered[position][0]] = mean
        index = stop + 1
    return result


def fallback_k(rows: Mapping[int, Mapping[str, Any]], min_f: float) -> int | None:
    """The fallback K of the rows (each a ``stability.json`` row); see the module docstring."""
    per_curve: dict[str, dict[int, float]] = {}
    for curve in CURVES:
        defined = {k: float(row[curve]) for k, row in rows.items() if _is_defined(row, curve, min_f)}
        per_curve[curve] = ranks(defined)
    candidates = []
    for k, row in rows.items():
        mine = [per_curve[curve][k] for curve in CURVES if k in per_curve[curve]]
        if len(mine) < 2:
            continue
        a = row.get("a")
        a_value = float(a) if a is not None and _is_defined(row, "a", min_f) else -math.inf
        candidates.append((sum(mine) / len(mine), -a_value, k))
    if not candidates:
        return None
    return min(candidates)[2]


def load_evidence(document: Mapping[str, Any], *, threshold: float = STABLE_PEAK) -> Evidence:
    """The evidence in a ``stability.json`` document."""
    min_f = float(document.get("min_f", 0.025))
    raw_rows = {int(k): row for k, row in document["per_k"].items()}
    per_curve = {
        curve: ranks({k: float(row[curve]) for k, row in raw_rows.items() if _is_defined(row, curve, min_f)})
        for curve in CURVES
    }
    stable = sorted(
        k for k, row in raw_rows.items()
        if any((row.get("peak_frequency") or {}).get(curve) is not None
               and row["peak_frequency"][curve] >= threshold for curve in CURVES)
    )
    rows: dict[int, CurveRow] = {}
    for k in sorted(raw_rows):
        row = raw_rows[k]
        rows[k] = CurveRow(
            k=k,
            values={curve: row.get(curve) for curve in CURVES},
            bands={curve: (row.get(f"{curve}_lo"), row.get(f"{curve}_hi")) for curve in CURVES},
            peak_frequency=dict(row.get("peak_frequency") or {}),
            runs=int(row.get("runs") or 0),
            a_members=list(row.get("a_members") or []),
            ranks={curve: per_curve[curve].get(k) for curve in CURVES},
            defined={curve: _is_defined(row, curve, min_f) for curve in CURVES},
            in_stable_peaks=k in stable,
        )
    return Evidence(
        grid=[int(k) for k in document.get("grid", sorted(raw_rows))],
        rows=rows,
        stable_peaks=stable,
        fallback_k=fallback_k(raw_rows, min_f),
        min_f=min_f,
    )

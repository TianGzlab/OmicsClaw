"""The fixed-K score: PAS and silhouette normalised by a reference range, then averaged.

For one K the reference set is every ok probe trial with exactly K labels.
Each member ``j`` (corrected PAS, raw silhouette) takes ``lo_j`` and ``hi_j``
over that set, and a trial with K labels scores
``mean_j (x_j - lo_j) / (hi_j - lo_j)``, not clipped. A member whose range is
empty (``hi_j == lo_j``) or whose reference set has fewer than two trials
leaves the mean and is recorded as degenerate; with no member left the K has
no fixed-K score.

The standard error is ``sqrt(sum_j (SE_j / (hi_j - lo_j))**2) / m`` over the
``m`` members used, with ``SE_pas = se_adjusted`` and ``SE_sil = sd / sqrt(m_sil)``
from ``metrics.json``. Scores are comparable only between trials with the same
number of labels on the same reference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

__all__ = [
    "MEMBERS",
    "FixedKScore",
    "KReference",
    "build_references",
    "member_values",
    "score_trial",
]

MEMBERS = ("pas", "silhouette_pca")
"""Scored members, in order."""

MIN_REFERENCE_TRIALS = 2


@dataclass(frozen=True, slots=True)
class KReference:
    """The reference range of every member at one K."""

    k: int
    n_trials: int
    ranges: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    degenerate: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return bool(self.ranges)

    def to_json(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "n_trials": self.n_trials,
            "ranges": {name: {"lo": lo, "hi": hi} for name, (lo, hi) in self.ranges.items()},
            "degenerate": list(self.degenerate),
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> "KReference":
        ranges = {
            name: (float(bounds["lo"]), float(bounds["hi"]))
            for name, bounds in (document.get("ranges") or {}).items()
        }
        return cls(
            k=int(document["k"]),
            n_trials=int(document.get("n_trials", 0)),
            ranges=ranges,
            degenerate=tuple(document.get("degenerate") or ()),
        )


@dataclass(frozen=True, slots=True)
class FixedKScore:
    """A trial's fixed-K score, its standard error and the normalised members."""

    score: float | None
    se: float | None
    components: Mapping[str, float | None]
    members_used: tuple[str, ...]


def member_values(metrics: Mapping[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    """``{member: (value, standard error)}`` read from a ``metrics.json`` document.

    PAS is its corrected value, the silhouette its raw value; a value that
    was not computed is ``None``.
    """
    adjusted = metrics.get("adjusted") or {}
    raw = metrics.get("raw") or {}
    diagnostics = metrics.get("diagnostics") or {}
    pas = _finite(adjusted.get("pas"))
    sil = _finite(raw.get("silhouette_pca"))
    pas_se = _finite((diagnostics.get("pas") or {}).get("se_adjusted"))
    sil_extra = diagnostics.get("silhouette_pca") or {}
    sil_se = _finite(sil_extra.get("se"))
    if sil_se is None and sil_extra.get("sd") is not None and sil_extra.get("sample_size"):
        sil_se = float(sil_extra["sd"]) / math.sqrt(float(sil_extra["sample_size"]))
    return {"pas": (pas, pas_se), "silhouette_pca": (sil, sil_se)}


def build_references(trials: Iterable[Mapping[str, Any]]) -> dict[int, KReference]:
    """References for every K seen among *trials*.

    :param trials: Records with ``n_labels`` and ``metrics`` (a ``metrics.json``
        document); only ok trials should be passed.
    """
    by_k: dict[int, list[Mapping[str, Any]]] = {}
    for trial in trials:
        n_labels = trial.get("n_labels")
        if n_labels is None or trial.get("metrics") is None:
            continue
        by_k.setdefault(int(n_labels), []).append(trial["metrics"])
    references: dict[int, KReference] = {}
    for k, documents in sorted(by_k.items()):
        ranges: dict[str, tuple[float, float]] = {}
        degenerate: list[str] = []
        for member in MEMBERS:
            values = [member_values(doc)[member][0] for doc in documents]
            values = [v for v in values if v is not None]
            if len(values) < MIN_REFERENCE_TRIALS or max(values) == min(values):
                degenerate.append(member)
                continue
            ranges[member] = (min(values), max(values))
        references[k] = KReference(k=k, n_trials=len(documents), ranges=ranges, degenerate=tuple(degenerate))
    return references


def score_trial(metrics: Mapping[str, Any], reference: KReference | None) -> FixedKScore:
    """The fixed-K score of one trial against the reference of its K.

    ``score`` is ``None`` when there is no usable reference or the trial
    lacks every member the reference uses.
    """
    values = member_values(metrics)
    if reference is None or not reference.usable:
        return FixedKScore(score=None, se=None, components={}, members_used=())
    components: dict[str, float | None] = {}
    used: list[str] = []
    variance = 0.0
    se_known = True
    for member, (lo, hi) in reference.ranges.items():
        value, se = values[member]
        if value is None:
            components[member] = None
            continue
        components[member] = (value - lo) / (hi - lo)
        used.append(member)
        if se is None:
            se_known = False
        else:
            variance += (se / (hi - lo)) ** 2
    if not used:
        return FixedKScore(score=None, se=None, components=components, members_used=())
    score = sum(components[m] for m in used) / len(used)  # type: ignore[misc]
    se = math.sqrt(variance) / len(used) if se_known else None
    return FixedKScore(score=score, se=se, components=components, members_used=tuple(used))


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None

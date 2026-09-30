"""Run budgets: how many new trials a session may start, per method.

A reservation is taken before a trial directory is allocated and is never
returned, so a trial that fails still counts. Reservations are atomic across
threads and coroutines.
"""

from __future__ import annotations

import threading
from typing import Mapping

__all__ = [
    "BudgetExceeded",
    "CALIBRATION_RUNS",
    "GROUPS_PER_METHOD",
    "RunBudget",
    "caps",
    "parse_budget",
]

GROUPS_PER_METHOD = 12
"""New parameter sets a method may try at the chosen K."""

CALIBRATION_RUNS = 4
"""Extra runs a calibrate-type method may spend on one parameter set to reach K."""

_TOTAL = "*"


class BudgetExceeded(Exception):
    """A reservation would exceed a cap.

    :ivar method: The method, or ``"*"`` for a session-wide cap.
    :ivar used: Runs already reserved against that cap.
    :ivar cap: The cap.
    """

    def __init__(self, method: str, used: int, cap: int) -> None:
        scope = "this session" if method == _TOTAL else f"method {method!r} in this session"
        super().__init__(f"the run budget of {scope} is used up ({used} of {cap} runs)")
        self.method = method
        self.used = used
        self.cap = cap


def caps(
    kinds: Mapping[str, str],
    *,
    groups: int = GROUPS_PER_METHOD,
    calibration_runs: int = CALIBRATION_RUNS,
) -> dict[str, int]:
    """New-run caps per method from each method's ``k_control`` kind.

    An ``exact`` method gets *groups* runs, a ``calibrate`` method
    ``groups * (1 + calibration_runs)``.

    :raises ValueError: An unknown kind.
    """
    result: dict[str, int] = {}
    for method, kind in kinds.items():
        if kind == "exact":
            result[method] = groups
        elif kind == "calibrate":
            result[method] = groups * (1 + calibration_runs)
        else:
            raise ValueError(f"unknown k_control kind {kind!r} for {method}")
    return result


def parse_budget(text: str) -> dict[str, int] | int | None:
    """Parse ``""`` (no limit), ``"60"`` (session total) or ``"leiden:60,spagcn:12"``.

    :raises ValueError: A malformed entry or a negative number.
    """
    text = (text or "").strip()
    if not text:
        return None
    if ":" not in text:
        value = _count(text)
        return value
    result: dict[str, int] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        method, sep, number = item.partition(":")
        method = method.strip()
        if not sep or not method:
            raise ValueError(f"budget entry {item!r} must be method:count")
        if method in result:
            raise ValueError(f"budget names {method!r} twice")
        result[method] = _count(number)
    return result


def _count(text: str) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError(f"budget count {text!r} is not an integer") from None
    if value < 0:
        raise ValueError(f"budget count {value} is negative")
    return value


class RunBudget:
    """Counts new runs per ``(session, method)`` against caps.

    :param limits: ``None`` for no limit, an ``int`` for a total per session
        over all methods, or a mapping of method to cap (a method not in the
        mapping is unlimited).
    """

    def __init__(self, limits: Mapping[str, int] | int | None = None) -> None:
        self._limits = limits
        self._used: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_text(cls, text: str) -> "RunBudget":
        """A budget from the ``ensemble_run_budget`` setting.

        :raises ValueError: See :func:`parse_budget`.
        """
        return cls(parse_budget(text))

    @property
    def limited(self) -> bool:
        return self._limits is not None

    def cap(self, method: str) -> int | None:
        """The cap that applies to *method*, or ``None``."""
        if self._limits is None:
            return None
        if isinstance(self._limits, int):
            return self._limits
        return self._limits.get(method)

    def used(self, session: str, method: str) -> int:
        """Runs reserved by *session* for *method*."""
        with self._lock:
            return self._used.get((session, method), 0)

    def total(self, session: str) -> int:
        """Runs reserved by *session* over all methods."""
        with self._lock:
            return sum(n for (owner, _), n in self._used.items() if owner == session)

    def reserve(self, session: str, method: str, runs: int = 1) -> None:
        """Take *runs* runs for *method*, or take none.

        :raises BudgetExceeded: The reservation would pass a cap.
        """
        with self._lock:
            if isinstance(self._limits, int):
                total = sum(n for (owner, _), n in self._used.items() if owner == session)
                if total + runs > self._limits:
                    raise BudgetExceeded(_TOTAL, total, self._limits)
            elif self._limits is not None and method in self._limits:
                used = self._used.get((session, method), 0)
                if used + runs > self._limits[method]:
                    raise BudgetExceeded(method, used, self._limits[method])
            key = (session, method)
            self._used[key] = self._used.get(key, 0) + runs

    def snapshot(self, session: str) -> dict[str, int]:
        """Runs reserved by *session*, per method."""
        with self._lock:
            return {method: n for (owner, method), n in self._used.items() if owner == session}

"""Shared parameter range validators for scRNA skills.

These validators are meant to be called early in main() after argparse,
before data loading. They raise ValueError with actionable messages so
users get immediate feedback instead of silent wrong results or cryptic
runtime errors deep inside scanpy/sklearn.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ParamValidator:
    """Collect and run parameter range checks.

    Usage::

        v = ParamValidator("sc-clustering")
        v.positive("n_neighbors", args.n_neighbors, min_val=2)
        v.positive("n_pcs", args.n_pcs, min_val=1)
        v.in_range("resolution", args.resolution, low=0, low_exclusive=True)
        v.fraction("fdr", args.fdr)
        v.non_negative("min_genes", args.min_genes)
        v.check()  # raises if any violations found
    """

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        self._errors: list[str] = []

    # -- Core checks --

    def positive(self, name: str, value, *, min_val: int = 1) -> "ParamValidator":
        """Value must be >= min_val (default 1)."""
        if value is None:
            return self
        if value < min_val:
            self._errors.append(
                f"--{name.replace('_', '-')} must be >= {min_val}, got {value}"
            )
        return self

    def non_negative(self, name: str, value) -> "ParamValidator":
        """Value must be >= 0."""
        if value is None:
            return self
        if value < 0:
            self._errors.append(
                f"--{name.replace('_', '-')} must be >= 0, got {value}"
            )
        return self

    def in_range(
        self,
        name: str,
        value,
        *,
        low: float = 0,
        high: float = 1,
        low_exclusive: bool = False,
        high_exclusive: bool = False,
    ) -> "ParamValidator":
        """Value must be in [low, high] or (low, high) depending on exclusive flags."""
        if value is None:
            return self
        low_ok = value > low if low_exclusive else value >= low
        high_ok = value < high if high_exclusive else value <= high
        if not (low_ok and high_ok):
            lb = "(" if low_exclusive else "["
            rb = ")" if high_exclusive else "]"
            self._errors.append(
                f"--{name.replace('_', '-')} must be in {lb}{low}, {high}{rb}, got {value}"
            )
        return self

    def fraction(self, name: str, value) -> "ParamValidator":
        """Value must be in (0, 1]."""
        return self.in_range(name, value, low=0, high=1, low_exclusive=True)

    def percentage(self, name: str, value) -> "ParamValidator":
        """Value must be in [0, 100]."""
        return self.in_range(name, value, low=0, high=100)

    def less_than(self, name: str, value, *, upper: int, upper_name: str = "") -> "ParamValidator":
        """Value must be < upper."""
        if value is None or upper is None:
            return self
        if value >= upper:
            label = upper_name or str(upper)
            self._errors.append(
                f"--{name.replace('_', '-')} must be < {label}, got {value}"
            )
        return self

    def min_max_consistent(self, min_name: str, min_val, max_name: str, max_val) -> "ParamValidator":
        """min_val must be <= max_val when both are provided."""
        if min_val is None or max_val is None:
            return self
        if min_val > max_val:
            self._errors.append(
                f"--{min_name.replace('_', '-')} ({min_val}) must be <= "
                f"--{max_name.replace('_', '-')} ({max_val})"
            )
        return self

    # -- Execute --

    def check(self) -> None:
        """Raise ValueError if any violations were collected."""
        if not self._errors:
            return
        header = f"{self.skill_name} parameter validation failed:"
        body = "\n".join(f"  - {e}" for e in self._errors)
        raise ValueError(f"{header}\n{body}")

    @property
    def has_errors(self) -> bool:
        return len(self._errors) > 0

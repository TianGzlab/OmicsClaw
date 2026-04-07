"""Shared autoagent runtime errors."""

from __future__ import annotations


class OptimizationCancelled(RuntimeError):
    """Raised when an optimization run is cancelled by the caller."""


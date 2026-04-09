"""Shared autoagent runtime errors."""

from __future__ import annotations


class OptimizationCancelled(RuntimeError):
    """Raised when an optimization run is cancelled by the caller."""


class MetricConfigError(RuntimeError):
    """Raised when metric evaluation fails due to configuration mismatch.

    This typically means all declared metrics are missing from the trial
    output — none of the registered metric names were found in the raw
    results dict.  The LLM should not receive a fake score of 0.0 when
    this happens; instead the trial should be recorded as a crash.
    """


"""Tests for omicsclaw.autoagent.errors — custom exception types."""

from __future__ import annotations

from omicsclaw.autoagent.errors import MetricConfigError, OptimizationCancelled


class TestExceptions:
    """Ensure custom exceptions can be instantiated and caught."""

    def test_optimization_cancelled(self):
        exc = OptimizationCancelled("user cancelled")
        assert str(exc) == "user cancelled"
        assert isinstance(exc, RuntimeError)

    def test_metric_config_error(self):
        exc = MetricConfigError("no metrics found")
        assert str(exc) == "no metrics found"
        assert isinstance(exc, RuntimeError)

    def test_optimization_cancelled_catchable_as_runtime_error(self):
        try:
            raise OptimizationCancelled("stop")
        except RuntimeError as e:
            assert "stop" in str(e)

    def test_metric_config_error_catchable_as_runtime_error(self):
        try:
            raise MetricConfigError("bad config")
        except RuntimeError as e:
            assert "bad config" in str(e)

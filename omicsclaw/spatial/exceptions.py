"""Custom exception hierarchy for SpatialClaw spatial analysis."""


class SpatialClawError(Exception):
    """Base exception for all SpatialClaw errors."""


class DataError(SpatialClawError):
    """Input data is missing, corrupt, or in an unexpected format."""


class ParameterError(SpatialClawError):
    """Invalid or conflicting analysis parameters."""


class ProcessingError(SpatialClawError):
    """An analysis step failed during execution."""


class DependencyError(SpatialClawError):
    """A required optional dependency is not installed."""


class PreprocessingRequiredError(SpatialClawError):
    """Data has not been preprocessed; run spatial-preprocess first."""

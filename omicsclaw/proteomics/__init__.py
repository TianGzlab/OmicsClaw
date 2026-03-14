"""Proteomics analysis utilities for OmicsClaw."""

from .exceptions import DataError, PreprocessingRequiredError
from .dependency_manager import require, check_available, DEPENDENCY_REGISTRY

__all__ = [
    "DataError",
    "PreprocessingRequiredError",
    "require",
    "check_available",
    "DEPENDENCY_REGISTRY",
]

"""Custom exceptions for single-cell analysis."""


class PreprocessingRequiredError(Exception):
    """Raised when preprocessing (PCA/neighbors) is required but missing."""
    pass


class DataError(Exception):
    """Raised when input data is invalid or missing required fields."""
    pass

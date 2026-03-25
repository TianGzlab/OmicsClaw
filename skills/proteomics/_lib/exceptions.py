"""Custom exceptions for proteomics analysis."""


class DataError(Exception):
    """Raised when proteomics data is invalid or malformed."""
    pass


class PreprocessingRequiredError(Exception):
    """Raised when preprocessing is required but missing."""
    pass

"""Custom exceptions for genomics analysis."""


class DataError(Exception):
    """Raised when genomics data is invalid or malformed."""
    pass


class PreprocessingRequiredError(Exception):
    """Raised when preprocessing is required but missing."""
    pass

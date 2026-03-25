"""Custom exceptions for metabolomics analysis."""


class DataError(Exception):
    """Raised when metabolomics data is invalid or malformed."""
    pass


class PreprocessingRequiredError(Exception):
    """Raised when preprocessing is required but missing."""
    pass

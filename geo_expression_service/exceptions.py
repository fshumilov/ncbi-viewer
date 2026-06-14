class GeoExpressionError(Exception):
    """Base error for domain and service failures."""


class InvalidGseFormatError(GeoExpressionError):
    """Raised when a GSE identifier does not match GSE\\d+ after normalization."""


class InvalidGeneCountError(GeoExpressionError):
    """Raised when the unique gene count is outside the allowed 2–5 range."""


class GeoDownloadError(GeoExpressionError):
    """Raised when NCBI GEO data cannot be downloaded."""


class MappingError(GeoExpressionError):
    """Raised when probe-to-gene mapping fails irrecoverably."""

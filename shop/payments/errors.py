class FonepayError(Exception):
    """Base class for all FonePay gateway errors."""


class FonepayConfigurationError(FonepayError):
    """Raised when required FonePay configuration is missing or invalid."""


class FonepayUpstreamError(FonepayError):
    """Raised when FonePay returns an unexpected response or a transport error occurs."""

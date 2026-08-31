class EsewaError(Exception):
    """Base class for all eSewa gateway errors."""


class EsewaConfigurationError(EsewaError):
    """Raised when required eSewa configuration is missing or invalid."""


class EsewaUpstreamError(EsewaError):
    """Raised when eSewa returns an unexpected response or a transport error occurs."""

class TrackingError(Exception):
    """Base tracking exception."""


class CourierNotSupportedError(TrackingError):
    """Raised when a courier has no active adapter."""


class InvalidTrackingNumberError(TrackingError):
    """Raised when the input number fails validation."""


class UpstreamTrackingError(TrackingError):
    """Raised when the courier endpoint fails or changes unexpectedly."""

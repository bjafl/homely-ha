"""Homely API exceptions."""

import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .models import ErrorResponse


class HomelyError(HomeAssistantError):
    """Base exception for Homely API errors."""


class HomelyNetworkError(HomelyError, aiohttp.ClientError):
    """Exception for network-related errors."""


class HomelyWebSocketError(HomelyNetworkError):
    """Exception for WebSocket-related errors."""


class HomelyValidationError(HomelyError):
    """Exception for data validation errors."""

    def __init__(self, message: str, invalid_data: dict[str, str]) -> None:
        """Initialize with message and copy of invalid data."""
        super().__init__(message)
        self.invalid_data = invalid_data


class HomelyRequestError(HomelyError):
    """Exception for API request errors."""

    def __init__(self, message: str, error: ErrorResponse | None = None) -> None:
        """Initialize with message and optional received ErrorResponse."""
        super().__init__(message)
        self.error = error


class HomelyAuthError(HomelyError):
    """Base authentication error."""


class HomelyConfigAuthError(ConfigEntryAuthFailed, HomelyAuthError):
    """Authentication error during config entry setup."""


class HomelyStateUpdateError(HomelyError):
    """Error updating state from WebSocket event."""


class HomelyStateUdateLocationMismatchError(HomelyStateUpdateError):
    """Location ID in update does not match location ID of this home state."""


class HomelyStateUpdateMissingTargetError(HomelyStateUpdateError):
    """Can't find target state to apply update."""


class HomelyStateUpdateOutOfOrderError(HomelyStateUpdateError):
    """Update is out of order (older than current state)."""


class HomelyValueError(HomelyError, ValueError):
    """Invalid value provided."""


class HomelyAuthExpiredError(HomelyAuthError):
    """Authentication token expired - triggers reauth flow."""


class HomelyAuthInvalidError(HomelyAuthError):
    """Invalid credentials - may need manual intervention."""


class HomelyAuthRequestError(HomelyAuthInvalidError, HomelyRequestError):
    """Exception for login errors."""

    def __init__(self, message: str, error: ErrorResponse | None = None):
        """Initialize with message and optional received ErrorResponse."""
        super().__init__(message, error)


class HomelyServiceUnavailableError(HomelyNetworkError):
    """Service temporarily unavailable - will retry setup."""


class NoActiveSessionError(HomelyError, RuntimeError):
    """No active session found."""

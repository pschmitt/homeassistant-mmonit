"""Exceptions for the M/Monit integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class MMonitError(HomeAssistantError):
    """Base M/Monit error."""


class MMonitApiError(MMonitError):
    """Raised when the M/Monit API request fails."""


class MMonitAuthenticationError(MMonitApiError):
    """Raised when the M/Monit credentials are rejected."""


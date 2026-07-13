"""Exception types raised by the Levanto SDK.

Every error inherits from :class:`LevantoError` and carries the HTTP
``status`` code and the server-supplied ``detail`` string (when available),
so callers can branch on either the type or the fields.
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "LevantoError",
    "AuthError",
    "ValidationError",
    "ServiceUnavailableError",
    "LevantoAPIError",
]


class LevantoError(Exception):
    """Base class for every error raised by this library."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class AuthError(LevantoError):
    """Authentication or billing failure (HTTP 401 / 402).

    Raised for a missing or invalid API key, or when the account balance is
    too low to serve the request.
    """


class ValidationError(LevantoError):
    """The request was rejected as malformed (HTTP 400 / 422)."""


class ServiceUnavailableError(LevantoError):
    """The Sage model is loading or otherwise unavailable (HTTP 503)."""


class LevantoAPIError(LevantoError):
    """Any other non-2xx response that is not covered by a more specific type."""

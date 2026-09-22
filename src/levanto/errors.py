"""Errors raised by the SDK.

Every error is a :class:`LevantoError` carrying the HTTP ``status`` (``None``
for network failures) and the server's ``detail`` message when there is one.
"""

from __future__ import annotations

__all__ = [
    "LevantoError",
    "AuthError",
    "AllowanceExhaustedError",
    "ValidationError",
    "ServiceUnavailableError",
    "LevantoAPIError",
]


class LevantoError(Exception):
    """Base class for every SDK error. Also raised for network failures and timeouts."""

    def __init__(self, message: str, *, status: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class AuthError(LevantoError):
    """HTTP 401: the API key is missing or invalid."""


class AllowanceExhaustedError(AuthError):
    """HTTP 402: the key is valid, but this period's decision allowance is used up."""


class ValidationError(LevantoError):
    """HTTP 400/422: the request was rejected (schema, limits, or an unsupported combination)."""


class ServiceUnavailableError(LevantoError):
    """HTTP 503 after retries: Sage is loading or temporarily unavailable."""


class LevantoAPIError(LevantoError):
    """Any other non-2xx response."""

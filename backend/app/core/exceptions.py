"""Domain exceptions and their HTTP representation.

Services raise domain errors; a single exception handler in ``app.main`` maps
them to consistent JSON envelopes, so endpoints never need try/except blocks and
error shapes cannot drift between modules.
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = int(status_code or self.status_code)
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        payload = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class ValidationError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "One or more fields are invalid."


class AuthError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "authentication_error"
    message = "Authentication is required."


class InvalidCredentialsError(AuthError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class PermissionDeniedError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "permission_denied"
    message = "You do not have access to this resource."


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"
    message = "The requested resource does not exist."


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "conflict"
    message = "The resource already exists."


class RateLimitError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many attempts. Please try again later."


class UpstreamUnavailableError(AppError):
    """A third-party dependency (weather, Places, ML service) is unavailable."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "upstream_unavailable"
    message = "A required external service is currently unavailable."


class NotConfiguredError(AppError):
    """The feature is implemented but its API key is missing."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "not_configured"
    message = "This feature is not configured on the server."

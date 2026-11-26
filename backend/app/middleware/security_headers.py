"""Security headers and request-ID middleware.

The API serves JSON and file downloads to a native app, so the CSP is strict and
irrelevant to the app itself, but it protects the generated Swagger UI and any
browser that happens to hit the service.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": settings.frame_options,
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(self), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        # Modern browsers honour Content-Security-Policy frame-ancestors over
        # X-Frame-Options, so the two are kept consistent. With DENY there is
        # nothing to add: an absent frame-ancestors cannot contradict the header.
        if settings.frame_options != "DENY" or settings.frame_ancestor_list:
            sources = []
            if settings.frame_options == "SAMEORIGIN":
                sources.append("'self'")
            sources.extend(settings.frame_ancestor_list)
            if sources:
                response.headers.setdefault(
                    "Content-Security-Policy",
                    f"frame-ancestors {' '.join(sources)};",
                )
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id so a user-visible error can be traced in the logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

"""Structured logging configuration.

JSON-ish key=value logging keeps the container logs greppable without pulling in
an extra dependency, and redacts anything that looks like a credential.
"""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

SECRET_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*['\"]?([^\s,'\"]+)",
    re.IGNORECASE,
)


class SecretRedactingFilter(logging.Filter):
    """Replace secret-looking values in log records before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - stdlib API
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=***REDACTED***", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"


def configure_logging() -> None:
    """Configure root logging once, for both the API and the workers."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Third-party noise: httpx logs every request at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

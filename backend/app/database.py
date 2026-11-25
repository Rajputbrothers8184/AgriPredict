"""Database engine, session management and ORM initialisation."""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import REPO_ROOT, settings
from app.models import Base

logger = logging.getLogger(__name__)


def _resolve_sqlite_path(url: str) -> str:
    """Make a relative SQLite path absolute against the repository root.

    Without this, the database file's location depends on the shell's current
    directory, which produces the classic "my data disappeared" bug when the
    server is started from a different folder.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    raw = url[len(prefix) :]
    if raw in {":memory:", ""} or raw.startswith("file:"):
        return url
    path = Path(raw)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{path}"


def build_engine(database_url: str | None = None, echo: bool | None = None) -> Engine:
    """Create an engine tuned for the target backend."""
    url = database_url or settings.database_url
    echo = settings.db_echo if echo is None else echo

    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        url = _resolve_sqlite_path(url)
        # check_same_thread=False is required because FastAPI may touch the
        # session from a different thread than the one that opened it.
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            # Enforce the FK actions declared in the schema; SQLite defaults off.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine: Engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Create all tables if they do not exist.

    Development and test convenience only: production schema changes go through
    Alembic (``backend/alembic``) so that upgrades are reviewable.
    """
    eng = target_engine or engine
    if eng.dialect.name == "sqlite":
        _ = URL  # imported for type clarity in some deployments
    Base.metadata.create_all(bind=eng)
    logger.info("database schema ensured on %s", eng.url.render_as_string(hide_password=True))

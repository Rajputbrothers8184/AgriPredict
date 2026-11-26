"""Reference-data seeding.

The SQL seed files under ``database/seed`` are the single source of truth for
commodities and markets. Rather than duplicating those lists in Python (which
would drift immediately), this module parses the ``INSERT ... VALUES`` statements
and applies them through the ORM, so the API can bootstrap a fresh SQLite
database without requiring psql.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, settings
from app.database import SessionLocal
from app.models import Commodity, Market

logger = logging.getLogger(__name__)

SEED_DIR = REPO_ROOT / "database" / "seed"

TRUE_VALUES = {"true", "t", "1"}
FALSE_VALUES = {"false", "f", "0"}


def _split_rows(values_block: str) -> list[str]:
    """Split ``(..), (..), (..)`` into the raw text of each row.

    A character scanner is required rather than a regex: seed values legitimately
    contain parentheses and commas inside quoted strings (for example
    ``'Gram (Chickpea)'``), which a naive pattern would split incorrectly.
    """
    rows: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    for char in values_block:
        if char == "'":
            in_string = not in_string
            if depth > 0:
                current.append(char)
            continue
        if not in_string:
            if char == "(":
                depth += 1
                if depth == 1:
                    current = []
                    continue
            elif char == ")":
                depth -= 1
                if depth == 0:
                    rows.append("".join(current))
                    current = []
                    continue
        if depth > 0:
            current.append(char)
    return [row for row in (r.strip() for r in rows) if row]


def _split_fields(row: str) -> list[str]:
    """Split one row's fields on top-level commas, respecting quoted commas."""
    fields: list[str] = []
    current: list[str] = []
    in_string = False
    for char in row:
        if char == "'":
            in_string = not in_string
            current.append(char)
        elif char == "," and not in_string:
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        fields.append("".join(current).strip())
    return fields


def _literal(raw: str):
    """Convert a raw SQL literal from a seed file into a Python value."""
    value = raw.strip()
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    lowered = value.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    if lowered == "null":
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _load_insert(sql: str) -> tuple[str, list[str], list[list]]:
    """Extract ``(table, columns, rows)`` from the first INSERT statement."""
    insert_match = re.search(
        r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES(.*?)ON\s+CONFLICT",
        sql,
        flags=re.S | re.I,
    )
    if insert_match is None:
        raise ValueError("no INSERT ... ON CONFLICT statement found")
    table = insert_match.group(1)
    columns = [c.strip() for c in insert_match.group(2).split(",")]
    rows = [[_literal(v) for v in _split_fields(raw)] for raw in _split_rows(insert_match.group(3))]
    for index, row in enumerate(rows, start=1):
        if len(row) != len(columns):
            raise ValueError(
                f"seed row {index} of {table} has {len(row)} values for "
                f"{len(columns)} columns: {row}"
            )
    return table, columns, rows


def seed_reference_data(session: Session | None = None) -> dict[str, int]:
    """Insert/update commodities and markets; returns counts processed."""
    owns_session = session is None
    session = session or SessionLocal()
    counts = {"commodities": 0, "markets": 0}

    try:
        for filename, model, key in (
            ("001_commodities.sql", Commodity, "slug"),
            ("002_markets.sql", Market, "slug"),
        ):
            path = SEED_DIR / filename
            if not path.is_file():
                logger.warning("seed file missing: %s", path)
                continue
            table, columns, rows = _load_insert(path.read_text(encoding="utf-8"))
            for row in rows:
                data = dict(zip(columns, row))
                slug = data.get(key)
                if not slug:
                    continue
                existing = session.scalar(select(model).where(getattr(model, key) == slug))
                if existing is None:
                    session.add(model(**data))
                else:
                    for field, value in data.items():
                        setattr(existing, field, value)
                counts[table] = counts.get(table, 0) + 1
        session.commit()
        logger.info(
            "reference data ready (commodities=%s, markets=%s)",
            counts.get("commodities", 0),
            counts.get("markets", 0),
        )
    finally:
        if owns_session:
            session.close()

    return counts


def seed_demo_user_data() -> None:
    """Optionally load demo farm/cycle data for a fresh demo environment.

    Only runs when ``SEED_DEMO_DATA=true``. It never creates price history: no
    prices are invented, because fabricated market data is exactly what this
    project refuses to ship.
    """
    if not settings.seed_demo_data:
        return
    logger.info("SEED_DEMO_DATA is true but demo farm data is created through the API")


if __name__ == "__main__":  # pragma: no cover - developer utility
    logging.basicConfig(level=logging.INFO)
    print(seed_reference_data())

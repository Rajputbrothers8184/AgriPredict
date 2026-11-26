"""Parity between the canonical SQL schema and the backend ORM models.

There are two definitions of the data model on purpose:

* ``database/schema/001_schema.sql`` — authoritative for PostgreSQL deployments
  and reviewable by a database administrator.
* ``backend/app/models.py`` — what the application actually creates and queries.

Two definitions can drift, so this test fails the build when they do. It is a
structural comparison (tables, columns, nullability, uniqueness, foreign-key
targets and delete actions), not a textual one, so cosmetic differences such as
column order or ``INTEGER`` vs ``IDENTITY`` are allowed.

Run it from the repository root:

    python -m pytest database/tests -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = REPO_ROOT / "database" / "schema" / "001_schema.sql"

# The backend package is importable without installing it.
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.models import Base  # noqa: E402  (import after sys.path setup)

NON_COLUMN_PREFIXES = (
    "CONSTRAINT",
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE",
    "CHECK",
    "EXCLUDE",
)
TYPE_ALIASES = {
    "INTEGER": "INTEGER",
    "VARCHAR": "STRING",
    "NUMERIC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "DATE": "DATE",
    "TIMESTAMPTZ": "DATETIME",
    "TIMESTAMP": "DATETIME",
    "BOOLEAN": "BOOLEAN",
    "TEXT": "TEXT",
}


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"COMMENT ON[^;]*;", "", sql, flags=re.S)


def _split_top_level(body: str) -> list[str]:
    parts, buf, depth, in_string = [], [], 0, False
    for char in body:
        if char == "'":
            in_string = not in_string
        if not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(char)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def parse_sql_schema() -> dict[str, dict[str, dict]]:
    """Return ``{table: {column: {type, nullable, unique, fk, fk_column, on_delete}}}``.

    Primary keys are reported as non-nullable: PostgreSQL's ``PRIMARY KEY``
    implies ``NOT NULL`` even though the DDL does not spell it out.
    """
    sql = _strip_comments(SCHEMA_FILE.read_text(encoding="utf-8"))
    tables: dict[str, dict[str, dict]] = {}

    for match in re.finditer(
        r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\n\);", sql, flags=re.S | re.I
    ):
        table = match.group(1).lower()
        body = match.group(2)
        columns: dict[str, dict] = {}
        for definition in _split_top_level(body):
            flat = " ".join(definition.split())
            if not flat or flat.upper().startswith(NON_COLUMN_PREFIXES):
                continue
            column_match = re.match(r"(\w+)\s+([A-Za-z]+(?:\([^)]*\))?)", flat)
            if not column_match:
                continue
            name = column_match.group(1).lower()
            base_type = column_match.group(2).split("(")[0].upper()
            is_primary = "PRIMARY KEY" in flat.upper()
            implicit_table = re.search(
                rf"FOREIGN\s+KEY\s*\(\s*{re.escape(name)}\s*\)"
                rf"\s*REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)",
                body,
                re.I,
            )
            fk_match = re.search(r"REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)", flat, re.I)
            on_delete_match = re.search(r"ON\s+DELETE\s+(CASCADE|SET NULL|RESTRICT)", flat, re.I)
            if fk_match is None and implicit_table is not None:
                fk_match = implicit_table
                on_delete_match = re.search(
                    rf"FOREIGN\s+KEY\s*\(\s*{re.escape(name)}\s*\)[^,]*"
                    r"ON\s+DELETE\s+(CASCADE|SET NULL|RESTRICT)",
                    body,
                    re.I,
                )
            columns[name] = {
                "type": TYPE_ALIASES.get(base_type, base_type),
                "nullable": ("NOT NULL" not in flat.upper()) and not is_primary,
                "unique": "UNIQUE" in flat.upper(),
                "fk": fk_match.group(1).lower() if fk_match else None,
                "fk_column": fk_match.group(2).lower() if fk_match else None,
                "on_delete": (
                    on_delete_match.group(1).upper().replace(" ", "_")
                    if on_delete_match
                    else ("NO_ACTION" if fk_match else None)
                ),
                "check": "CHECK" in flat.upper(),
            }
        tables[table] = columns
    return tables


def parse_orm_schema() -> dict[str, dict[str, dict]]:
    """Same structure, read from the SQLAlchemy mapper configuration."""
    result: dict[str, dict[str, dict]] = {}
    for table_name, table in Base.metadata.tables.items():
        columns: dict[str, dict] = {}
        for column in table.columns:
            fk = None
            on_delete = None
            if column.foreign_keys:
                foreign = next(iter(column.foreign_keys))
                fk = foreign.column.table.name.lower()
                on_delete = (foreign.ondelete or "NO_ACTION").upper().replace(" ", "_")
            columns[column.name.lower()] = {
                "type": column.type.__class__.__name__.upper(),
                "nullable": bool(column.nullable),
                # PK columns omit `unique=True`; the SQL side declares UNIQUE only
                # where it is a real business rule, so compare those directly.
                "unique": bool(column.unique),
                "fk": fk,
                "fk_column": (
                    next(iter(column.foreign_keys)).column.name.lower()
                    if column.foreign_keys
                    else None
                ),
                "on_delete": on_delete,
                "check": None,  # CheckConstraints live on the table, compared below
            }
        result[table_name] = columns
    return result


@pytest.fixture(scope="module")
def sql_schema() -> dict[str, dict[str, dict]]:
    assert SCHEMA_FILE.is_file(), f"canonical schema missing: {SCHEMA_FILE}"
    return parse_sql_schema()


@pytest.fixture(scope="module")
def orm_schema() -> dict[str, dict[str, dict]]:
    return parse_orm_schema()


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_same_tables(sql_schema, orm_schema):
    missing_in_orm = set(sql_schema) - set(orm_schema)
    missing_in_sql = set(orm_schema) - set(sql_schema)
    assert not missing_in_orm, f"tables in SQL but not in the ORM: {sorted(missing_in_orm)}"
    assert not missing_in_sql, f"tables in the ORM but not in SQL: {sorted(missing_in_sql)}"


def test_same_columns_per_table(sql_schema, orm_schema):
    problems = []
    for table, sql_columns in sql_schema.items():
        orm_columns = orm_schema.get(table, {})
        only_sql = set(sql_columns) - set(orm_columns)
        only_orm = set(orm_columns) - set(sql_columns)
        if only_sql:
            problems.append(f"{table}: missing in ORM {sorted(only_sql)}")
        if only_orm:
            problems.append(f"{table}: missing in SQL {sorted(only_orm)}")
    assert not problems, "column drift:\n" + "\n".join(problems)


def test_nullability_matches(sql_schema, orm_schema):
    problems = []
    for table, sql_columns in sql_schema.items():
        for column, meta in sql_columns.items():
            orm_meta = orm_schema.get(table, {}).get(column)
            if orm_meta is None:
                continue
            # A primary key is never nullable in either definition.
            if meta["nullable"] != orm_meta["nullable"]:
                problems.append(
                    f"{table}.{column}: SQL nullable={meta['nullable']} "
                    f"ORM nullable={orm_meta['nullable']}"
                )
    assert not problems, "nullability drift:\n" + "\n".join(problems)


def test_column_types_match(sql_schema, orm_schema):
    problems = []
    for table, sql_columns in sql_schema.items():
        for column, meta in sql_columns.items():
            orm_meta = orm_schema.get(table, {}).get(column)
            if orm_meta is None:
                continue
            if meta["type"] != orm_meta["type"]:
                problems.append(
                    f"{table}.{column}: SQL {meta['type']} vs ORM {orm_meta['type']}"
                )
    assert not problems, "type drift:\n" + "\n".join(problems)


def test_foreign_keys_match(sql_schema, orm_schema):
    problems = []
    for table, sql_columns in sql_schema.items():
        for column, meta in sql_columns.items():
            orm_meta = orm_schema.get(table, {}).get(column)
            if orm_meta is None:
                continue
            if meta["fk"] != orm_meta["fk"]:
                problems.append(
                    f"{table}.{column}: SQL FK -> {meta['fk']} vs ORM FK -> {orm_meta['fk']}"
                )
    assert not problems, "foreign-key drift:\n" + "\n".join(problems)


def test_foreign_key_delete_actions_match(sql_schema, orm_schema):
    problems = []
    for table, sql_columns in sql_schema.items():
        for column, meta in sql_columns.items():
            if meta["fk"] is None:
                continue
            orm_meta = orm_schema.get(table, {}).get(column)
            if orm_meta is None:
                continue
            if meta["on_delete"] != orm_meta["on_delete"]:
                problems.append(
                    f"{table}.{column}: SQL ON DELETE {meta['on_delete']} vs "
                    f"ORM ON DELETE {orm_meta['on_delete']}"
                )
    assert not problems, "delete-action drift:\n" + "\n".join(problems)


def test_orm_declares_check_constraints_for_every_sql_check():
    """Checks are table-level, so compare counts per table."""
    sql_text = _strip_comments(SCHEMA_FILE.read_text(encoding="utf-8"))
    sql_checks: dict[str, int] = {}
    for match in re.finditer(r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\n\);", sql_text, flags=re.S | re.I):
        table = match.group(1).lower()
        sql_checks[table] = len(re.findall(r"\bCHECK\s*\(", match.group(2), re.I))

    problems = []
    for table_name, table in Base.metadata.tables.items():
        orm_checks = [
            constraint
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        ]
        if len(orm_checks) != sql_checks.get(table_name, 0):
            problems.append(
                f"{table_name}: SQL has {sql_checks.get(table_name, 0)} CHECKs, "
                f"ORM has {len(orm_checks)}"
            )
    assert not problems, "check-constraint drift:\n" + "\n".join(problems)

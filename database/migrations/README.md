# Migrations

**Owner:** Member 4 (Database Engineer)

The canonical schema is [`../schema/001_schema.sql`](../schema/001_schema.sql).
It is recorded as migration version `001_schema.sql` on first application, so
there is exactly one source of truth and no copy of the DDL to drift.

## How it works

Each migration runs **once**, in lexical order, inside a transaction, and is
recorded in `schema_migrations(version, applied_at)`.

```bash
cd database/migrations
export DATABASE_URL=postgresql://user:pass@localhost:5432/agripredict

./apply.sh --status     # what is applied, what is pending
./apply.sh --dry-run    # preview
./apply.sh              # apply
```

## Adding a migration

1. Create `NNN_short_description.sql` with the next free number
   (e.g. `002_add_forecast_interval_width.sql`).
2. Write **forward-only, additive** SQL. Never rewrite a migration that has been
   applied to a shared database.
3. Wrap destructive operations behind an explicit guard and document the
   rollback procedure in a comment at the top of the file.
4. Update `../schema/README.md` and, if the shape of a table changes, the ERD.
5. Apply it locally, run `pytest database/tests`, and commit both the migration
   and the doc change in one commit: `feat(database): ...`.

## Writing rules

- `ADD COLUMN` should be nullable or carry a `DEFAULT`, so an old backend keeps
  working during a rolling deploy.
- Backfill in a separate statement from the `ADD COLUMN`.
- Dropping a column/table requires a deprecation step in the previous release.
- Always create the index `CONCURRENTLY` on large tables (outside a transaction;
  mark the migration and run it manually if needed).
- Include `COMMENT ON` statements so the intent survives in the database.

## Verification after applying

```bash
psql -d agripredict -c "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
cd ../.. && python -m pytest database/tests -q
```

## Why not Alembic for PostgreSQL?

The backend uses Alembic for the **SQLite/ORM** path so that a fresh clone needs
no database server. For the PostgreSQL deployment we keep plain, reviewable SQL:
it is auditable by the database owner, independent of the Python code, and can be
applied by someone who does not have the application installed. The two are kept
in sync by `database/tests/test_schema_parity.py`.

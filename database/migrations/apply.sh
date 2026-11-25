#!/usr/bin/env bash
# ===========================================================================
# AgriPredict — migration runner (PostgreSQL)
#
#   ./apply.sh                apply every pending migration
#   ./apply.sh --status       show applied / pending versions
#   ./apply.sh --dry-run      print what would be applied
#
# Environment:
#   PGHOST / PGPORT / PGUSER / PGDATABASE / PGPASSWORD  (standard libpq vars)
#   DATABASE_URL  may be used instead, e.g.
#     DATABASE_URL=postgresql://user:pass@host:5432/agripredict ./apply.sh
#
# Design note: the canonical schema lives in ../schema/001_schema.sql and is
# recorded as migration version 001. Later deltas are added here as
# NNN_<description>.sql and run in lexical order, exactly once, inside a
# transaction, and recorded in schema_migrations.
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../schema/001_schema.sql"
MIGRATIONS_DIR="$SCRIPT_DIR"

if [[ -n "${DATABASE_URL:-}" ]]; then
  PSQL=(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q)
else
  PSQL=(psql -v ON_ERROR_STOP=1 -q)
fi

MODE="apply"
case "${1:-}" in
  --status)  MODE="status" ;;
  --dry-run) MODE="dry" ;;
  "" ) ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

command -v psql >/dev/null || { echo "psql not found on PATH" >&2; exit 1; }
[[ -f "$SCHEMA_FILE" ]] || { echo "missing $SCHEMA_FILE" >&2; exit 1; }

"${PSQL[@]}" -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    VARCHAR(120) PRIMARY KEY,
    applied_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);"

applied="$("${PSQL[@]}" -At -c "SELECT version FROM schema_migrations ORDER BY version;")"

# Build the ordered list: 001 = canonical schema, then any NNN_*.sql deltas.
declare -a VERSIONS=("001_schema.sql")
declare -a FILES=("$SCHEMA_FILE")
while IFS= read -r f; do
  base="$(basename "$f")"
  case "$base" in
    001_*) continue ;;   # reserved for the canonical schema
  esac
  VERSIONS+=("$base")
  FILES+=("$f")
done < <(find "$MIGRATIONS_DIR" -maxdepth 1 -name '[0-9][0-9][0-9]_*.sql' | sort)

pending=0
for i in "${!VERSIONS[@]}"; do
  v="${VERSIONS[$i]}"
  f="${FILES[$i]}"
  if grep -qx "$v" <<<"$applied"; then
    [[ "$MODE" == "status" ]] && echo "applied  $v"
    continue
  fi
  pending=$((pending + 1))
  case "$MODE" in
    status) echo "PENDING  $v ($f)" ;;
    dry)    echo "would apply  $v ($f)" ;;
    apply)
      echo "applying $v ..."
      # One transaction per migration: a failure leaves the DB untouched.
      # The canonical schema file already contains BEGIN/COMMIT, so it runs
      # standalone; deltas are wrapped here.
      if [[ "$v" == "001_schema.sql" ]]; then
        "${PSQL[@]}" -f "$f"
      else
        { echo "BEGIN;"; cat "$f"; echo "COMMIT;"; } | "${PSQL[@]}" -f -
      fi
      "${PSQL[@]}" -c "INSERT INTO schema_migrations (version) VALUES ('$v');"
      ;;
  esac
done

if [[ "$MODE" == "status" ]]; then
  echo "---"
  echo "$pending pending migration(s)"
elif [[ "$MODE" == "apply" ]]; then
  echo "done: $pending migration(s) applied"
fi

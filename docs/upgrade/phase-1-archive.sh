#!/usr/bin/env bash
#
# Phase 1 — Archive retired-module data to CSV before Odoo registry cleanup.
# Safe to run multiple times. Read-only against the database.
#
# Targets the local docker postgres container (myservicenrs-db-1, db=odoo).
# Adjust DB_CONTAINER / DB_NAME / DB_USER if your environment differs.
#
# Output: docs/upgrade/archive/<table>.csv for every retired-module table.

set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-myservicenrs-db-1}"
DB_NAME="${DB_NAME:-odoo}"
DB_USER="${DB_USER:-odoo}"
ARCHIVE_DIR="${ARCHIVE_DIR:-docs/upgrade/archive}"

mkdir -p "$ARCHIVE_DIR"

# Tables owned by the modules we're fully retiring.
# Some may not exist if the modules were never installed in this DB — that's fine.
RETIRED_TABLES=(
    # myservice_osint
    osint_feed_entry
    osint_source_config
    # myservice_ai_patterns
    ai_pattern_alert
    ai_daily_brief
    ai_brief_download_log
    # myservice_security (partial — these models are dropped)
    security_watchlist
    security_watchlist_alias
    security_state_threat
    # nrs_watchlist
    nrs_watchlist_subject
)

# M2M relation tables that join kept models to dropped models.
# These also need archiving so the relationships are not silently lost.
RELATION_TABLES=(
    security_incident_watchlist_rel   # security.incident <-> security.watchlist
)

echo "==> Archive directory: $ARCHIVE_DIR"
echo "==> Database: $DB_USER@$DB_CONTAINER:$DB_NAME"
echo ""

archive_table() {
    local table="$1"
    local out="$ARCHIVE_DIR/${table}.csv"

    # Check table existence first; missing tables are not an error here.
    local exists
    exists=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='$table'" \
        2>/dev/null || true)

    if [ "$exists" != "1" ]; then
        printf "  %-45s SKIP (table not present)\n" "$table"
        return 0
    fi

    local rows
    rows=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT count(*) FROM \"$table\"")

    if [ "$rows" = "0" ]; then
        printf "  %-45s EMPTY (0 rows) — writing header-only CSV\n" "$table"
    else
        printf "  %-45s %s rows\n" "$table" "$rows"
    fi

    # \copy runs client-side so the file lands on the docker host's psql output stream.
    # We pipe through `docker exec` then capture into the host filesystem.
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "\\copy (SELECT * FROM \"$table\") TO STDOUT WITH (FORMAT CSV, HEADER true)" \
        > "$out"
}

echo "==> Archiving fully-retired module tables..."
for t in "${RETIRED_TABLES[@]}"; do
    archive_table "$t"
done

echo ""
echo "==> Archiving M2M relation tables..."
for t in "${RELATION_TABLES[@]}"; do
    archive_table "$t"
done

echo ""
echo "==> Done. Archive contents:"
ls -lh "$ARCHIVE_DIR"
echo ""
echo "Next step: see docs/upgrade/phase-1-cleanup-options.md for two cleanup paths"
echo "  (nuke-and-reseed vs in-place SQL surgery)."

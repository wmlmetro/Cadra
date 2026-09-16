#!/usr/bin/env bash
# Fingerprint the tables an audit report reads, so "this report writes
# nothing" is a measurement rather than a claim.
#
# Handoff 16 acceptance: "Neither report writes anything — prove it by
# fingerprinting before and after."
#
# A row count alone is not enough: an in-place UPDATE leaves the count
# identical. So each line carries the count, the newest write_date, and an
# md5 over the whole table's ordered content — which moves if any byte of any
# row does. `write_date` is included on its own because a recompute that
# writes an unchanged value still bumps it, and that is exactly the silent
# defect handoff 09 found in the daily sweeps.
#
# WHY THE MEASUREMENT IS NOW CHECKED INSTEAD OF JUST TAKEN — handoff 26 §B
# ------------------------------------------------------------------------
# The first cut ran each table as one pipeline:
#
#     $COMPOSE exec -T db psql ... 2>/dev/null | tr -d '\r' || echo "$t (absent)"
#
# and that falsified the proof this script exists to make. `2>/dev/null`
# discarded the only thing that says WHY nothing came back, and the `|| echo`
# caught the whole pipeline — so a misspelled <db>, a stopped `db` container,
# an authentication failure and a genuinely absent table all printed the same
# line, and the script still exited 0. Two runs that fail in the same way
# produce byte-identical fingerprints, so "the report wrote nothing" was being
# proved by measuring nothing at all.
#
# So, now:
#   * every psql call's exit status is checked on its own, never through a
#     pipeline, and its stderr is quoted back rather than thrown away;
#   * a failure names the database, the table and the SQL it tried, and
#     ABORTS — a fingerprint that could not be taken is never printed, because
#     a partial fingerprint compares clean against another partial one;
#   * "this table does not exist" is measured DELIBERATELY, by asking the
#     catalogue before querying, so a legitimate zero stays distinguishable
#     from a failure;
#   * only fingerprint lines go to stdout. Context and errors go to stderr, so
#     two runs are still comparable with a byte-for-byte diff.
#
# Usage:  scripts/audit_report_fingerprint.sh <db>
#         scripts/audit_report_fingerprint.sh nrs19 > before.txt
#         ... run the report ...
#         scripts/audit_report_fingerprint.sh nrs19 > after.txt
#         diff before.txt after.txt     # empty = the report wrote nothing
set -euo pipefail
DB="${1:?usage: audit_report_fingerprint.sh <db>}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.19.yml"

TABLES=(nrs_asset nrs_asset_custody nrs_asset_tag_label mail_tracking_value
        mail_message nrs_asset_transfer)

# psql's stderr lands here so a failure can be shown instead of guessed at.
ERRFILE="$(mktemp "${TMPDIR:-/tmp}/cadra-fingerprint.XXXXXX")"
trap 'rm -f "$ERRFILE"' EXIT

# One query. Result on stdout, diagnosis in $ERRFILE, psql's own exit status
# returned unchanged. No pipe: a pipeline's status is the LAST command's, and
# that is how the previous version lost the failure.
psql_q() {
  $COMPOSE exec -T db psql -U odoo -d "$DB" -v ON_ERROR_STOP=1 -tAc "$1" 2>"$ERRFILE"
}

# Refuse to emit a fingerprint we could not actually take, and say what was
# being attempted when it broke. $1 = what failed, $2 = the SQL.
die() {
  {
    echo "FATAL: $1"
    echo "  database : $DB"
    echo "  command  : $COMPOSE exec -T db psql -U odoo -d $DB -tAc <sql>"
    echo "  sql      : $2"
    echo "  psql said:"
    sed 's/^/    /' "$ERRFILE"
    echo
    echo "NO FINGERPRINT PRINTED. A measurement that failed must not be"
    echo "compared against one that succeeded, and two failures must not be"
    echo "allowed to match each other — that is how a broken run 'proves'"
    echo "a report wrote nothing."
  } >&2
  exit 1
}

# ─── preflight ───────────────────────────────────────────────────────────
# Asked first so that a dead container or a wrong database name is reported
# once, in those words, rather than six times as six identical table errors
# that the reader has to diagnose backwards.
PREFLIGHT_SQL="SELECT current_database();"
if ! CONNECTED="$(psql_q "$PREFLIGHT_SQL")"; then
  die "cannot query database '$DB' through the compose 'db' service" "$PREFLIGHT_SQL"
fi
CONNECTED="$(printf '%s' "$CONNECTED" | tr -d '\r')"
echo "# connected to: $CONNECTED" >&2

# ─── which of these tables actually exist ────────────────────────────────
# Asked of the catalogue, once, so that "absent" is something this script
# MEASURED rather than something it inferred from a query that failed.
IN_LIST="$(printf "'%s'," "${TABLES[@]}")"
IN_LIST="${IN_LIST%,}"
CATALOGUE_SQL="SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m')
    AND c.relname IN ($IN_LIST) ORDER BY 1;"
if ! PRESENT="$(psql_q "$CATALOGUE_SQL")"; then
  die "could not read the table catalogue of '$DB'" "$CATALOGUE_SQL"
fi
PRESENT="$(printf '%s' "$PRESENT" | tr -d '\r')"

# ─── the fingerprint ─────────────────────────────────────────────────────
# Accumulated and printed only once every table has answered, so an abort
# halfway through leaves no half-fingerprint on stdout to be diffed.
OUT=""
for t in "${TABLES[@]}"; do
  if ! printf '%s\n' "$PRESENT" | grep -qxF "$t"; then
    # A deliberate, catalogued zero — not a query that fell over. Stated in
    # these words so the two cases can never again print the same line.
    OUT="${OUT}${t} ABSENT (no such table in ${DB})"$'\n'
    continue
  fi

  SQL="SELECT '$t rows=' || count(*)
        || ' max_write=' || coalesce(max(write_date)::text, '-')
        || ' md5=' || coalesce(md5(string_agg(t::text, '|' ORDER BY t.id)), '-')
      FROM $t t;"
  if ! LINE="$(psql_q "$SQL")"; then
    die "fingerprint query failed for table '$t'" "$SQL"
  fi
  LINE="$(printf '%s' "$LINE" | tr -d '\r')"
  # An aggregate over an existing table returns exactly one row even when the
  # table is empty (count=0, the coalesces supply '-'). Nothing at all means
  # the query did not do what this script thinks it does, which is a failed
  # measurement and not a zero.
  if [ -z "$LINE" ]; then
    die "empty result from an aggregate over existing table '$t'" "$SQL"
  fi
  OUT="${OUT}${LINE}"$'\n'
done

printf '%s' "$OUT"

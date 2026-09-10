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
# Usage:  scripts/audit_report_fingerprint.sh <db>
set -euo pipefail
DB="${1:?usage: audit_report_fingerprint.sh <db>}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.19.yml"

for t in nrs_asset nrs_asset_custody nrs_asset_tag_label mail_tracking_value \
         mail_message nrs_asset_transfer; do
  $COMPOSE exec -T db psql -U odoo -d "$DB" -tAc "
    SELECT '$t rows=' || count(*)
        || ' max_write=' || coalesce(max(write_date)::text, '-')
        || ' md5=' || coalesce(md5(string_agg(t::text, '|' ORDER BY t.id)), '-')
      FROM $t t;" 2>/dev/null | tr -d '\r' \
    || echo "$t (absent)"
done

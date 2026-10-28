#!/usr/bin/env bash
# Where is a capture? One command, read-only (handoff 69 §5 C1).
#
#   scripts/audit_trace.sh <tenant>                       every capture received in the window
#   scripts/audit_trace.sh <tenant> --capture <uuid>      one capture, by the phone's capture_id
#   scripts/audit_trace.sh <tenant> --code <code>         one capture, by its printed code (or old tag)
#   scripts/audit_trace.sh <tenant> --device <DEV-…>      what one device sent
#   scripts/audit_trace.sh <tenant> --campaign <id>       one campaign
#     [--since <YYYY-MM-DD>]   received on or after that UTC day (default: 14 days ago;
#                              ignored for --capture/--code unless given)
#     [--logs]                 add the Odoo log's POST /api/v1/audit/captures lines
#     [--local]                this machine's compose stack instead of the cluster
#
# The phone says *submitted*, the reviewer cannot find it. It is either on the
# server and hidden by the review page (H1–H4), or it never got there (H5–H7);
# `docs/runbooks/where-is-a-capture.md` says what each one means and what to
# do. This prints the evidence for the cases the web app cannot answer:
#
#   - every matching `nrs_audit_capture` with `reviewers_named` (ACTIVE users
#     on the campaign's reviewer list) and `rank_in_review_list` (its place,
#     by id, among its campaign's captures in the same state — the review
#     page's order), and `hidden_by`: which of H1–H4 hides a waiting one;
#   - per campaign: captured / waiting / accepted / returned, the reviewer
#     ids, and whose review-page dropdown OPENS on it (the newest open
#     campaign naming them — `AuditReview.tsx`);
#   - the devices, the refused syncs kept since handoff 69
#     (`nrs_audit_capture_refusal`), and phone photos uploaded on no capture —
#     Part A's lead for a capture the phone photographed and never sent;
#   - `--capture`/`--code` with no row here: the same search on every other
#     database (H6, another tenant), and where it was found.
#
# What it never does:
#   - write. Every query is fed on STDIN inside `BEGIN READ ONLY; … ROLLBACK;`
#     (`psql -c` with several statements prints only the last result —
#     measured), with a statement timeout, and every value from the command
#     line reaches SQL as a psql variable (`:'name'`), never spliced in;
#   - print a name, an email, an IP address or a secret. Users, rooms and
#     campaigns are ids; the log's client address is replaced by `<addr>`.
#     A kept refusal's `message` is the sentence the phone was sent, cut at
#     120 characters; it quotes values the phone sent (a scanned label, a
#     date) and campaign, room and device names, and the one sentence that
#     names a PERSON (a device bound to somebody else) is printed with
#     `<person>` in the name's place.
#     psql runs inside `db-0` as `odoo` over the local socket, so no password
#     is read at all;
#   - touch `nrs19` — handoff 69 §2: it is a replica of a real NRS staff
#     extract and is not touched, read-only included. Refused by name, and
#     skipped by the cross-tenant search;
#   - use the current kube context. The owner's is usually another cluster
#     (Vendra's), so the context is named on every call — `CADRA_KUBE_CONTEXT`,
#     default below — and it must hold, in `cadra-dev`, the pod `db-0` and the
#     deployment `odoo-19`, or nothing runs. The current context is not
#     changed.
#
# Timestamps are UTC as stored (Lagos is UTC+1).
set -euo pipefail

CONTEXT="${CADRA_KUBE_CONTEXT:-do-ams3-cadra-1779758691124}"
NS=cadra-dev

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
compose=(docker compose -f docker-compose.yml -f docker-compose.19.yml)

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

# ── arguments ───────────────────────────────────────────────────────────
tenant="${1:-}"
case "$tenant" in ""|-h|--help|-*) usage ;; esac
shift
cap="" code="" device="" campaign="" since="" logs=0 local=0 by=""
need() { [ -n "${2:-}" ] || { echo "$1 needs a value" >&2; usage; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    --capture)  need "$1" "${2:-}"; cap="$2"; by="${by}c"; shift 2 ;;
    --code)     need "$1" "${2:-}"; code="$2"; by="${by}k"; shift 2 ;;
    --device)   need "$1" "${2:-}"; device="$2"; by="${by}d"; shift 2 ;;
    --campaign) need "$1" "${2:-}"; campaign="$2"; by="${by}m"; shift 2 ;;
    --since)    need "$1" "${2:-}"; since="$2"; shift 2 ;;
    --logs)     logs=1; shift ;;
    --local)    local=1; shift ;;
    -h|--help)  usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done
[ ${#by} -le 1 ] || { echo "give one of --capture, --code, --device, --campaign" >&2; usage; }

# A database name is spliced into a command line (psql -d), so it is held to
# what a tenant name can be: a subdomain.
[[ "$tenant" =~ ^[a-z0-9_]+$ ]] || { echo "Refused: '$tenant' is not a tenant name." >&2; exit 2; }
if [ "$tenant" = nrs19 ]; then
  echo "Refused: 'nrs19' — a replica of a real NRS staff extract; handoff 69 says it is not touched, read-only included." >&2
  exit 1
fi

# The phone's capture_id as the server stores it: lower-case, no braces.
cap=$(printf '%s' "$cap" | tr -d '{}[:space:]' | tr '[:upper:]' '[:lower:]')
if [ -n "$cap" ] && ! [[ "$cap" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
  echo "note: '$cap' is not a UUID; it is matched as sent (a refusal keeps a malformed id as sent)." >&2
fi
code=$(printf '%s' "$code" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
# The same text as an old FIRS tag, as the server compares one (`norm_tag`:
# upper-case, `\` → `/`, no whitespace) — `--code` finds either.
tag=$(printf '%s' "$code" | tr '\\' '/' | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')
device=$(printf '%s' "$device" | tr -d '[:space:]')
if [ -n "$campaign" ] && ! [[ "$campaign" =~ ^[0-9]+$ ]]; then
  echo "--campaign takes the campaign's id (a number), not '$campaign'" >&2; exit 2
fi
since_given=1
if [ -z "$since" ]; then
  since_given=0
  since=$(python3 -c 'import datetime; print(datetime.date.today() - datetime.timedelta(days=14))')
fi
[[ "$since" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "--since takes YYYY-MM-DD, not '$since'" >&2; exit 2; }
# A capture asked for by its id or code is looked for whenever it arrived.
row_since="$since"
if [ $since_given = 0 ] && { [ -n "$cap" ] || [ -n "$code" ]; }; then row_since=1970-01-01; fi

# ── where the database is ───────────────────────────────────────────────
K=(kubectl --context "$CONTEXT" -n "$NS")
if [ $local = 1 ]; then
  if [ -n "${DOCKER_HOST:-}" ] && [[ "$DOCKER_HOST" != unix://* ]]; then
    echo "Refused: DOCKER_HOST is '$DOCKER_HOST'; --local reads this machine's stack only." >&2; exit 1
  fi
  "${compose[@]}" ps --status running --services 2>/dev/null | grep -qx db \
    || { echo "Refused: no running 'db' service in this repository's compose stack." >&2; exit 1; }
  where="local compose stack"
else
  kubectl config get-contexts -o name 2>/dev/null | grep -qx "$CONTEXT" \
    || { echo "Refused: kube context '$CONTEXT' is not configured here (set CADRA_KUBE_CONTEXT)." >&2; exit 1; }
  # That this is the Cadra cluster is proved by what is in it, not by its name.
  "${K[@]}" get pod/db-0 deploy/odoo-19 -o name >/dev/null 2>&1 \
    || { echo "Refused: context '$CONTEXT' has no pod db-0 and deployment odoo-19 in '$NS' — not the Cadra cluster." >&2; exit 1; }
  where="cluster $CONTEXT, namespace $NS"
fi

# psql on <db>, the script on stdin. Every value is a psql variable, quoted
# by psql itself (`:'cap'`), so nothing from the command line is SQL.
psql_ro() {
  local db="$1"
  local args=(psql -U odoo -d "$db" -X -q -v ON_ERROR_STOP=1 -P pager=off -P null=
              -v "cap=$cap" -v "code=$code" -v "device=$device" -v "campaign=$campaign"
              -v "tag=$tag" -v "since=$since" -v "row_since=$row_since")
  if [ $local = 1 ]; then
    "${compose[@]}" exec -T db "${args[@]}"
  else
    "${K[@]}" exec -i db-0 -- "${args[@]}"
  fi
}
# Unaligned, for a script to read.
psql_ro_tA() {
  local db="$1"
  local args=(psql -U odoo -d "$db" -X -q -tA -v ON_ERROR_STOP=1 -v "cap=$cap" -v "code=$code" -v "tag=$tag")
  if [ $local = 1 ]; then
    "${compose[@]}" exec -T db "${args[@]}"
  else
    "${K[@]}" exec -i db-0 -- "${args[@]}"
  fi
}

exists=$(printf "BEGIN READ ONLY;\nSELECT count(*) FROM pg_database WHERE datname = '%s';\nROLLBACK;\n" "$tenant" | psql_ro_tA postgres)
[ "$exists" = 1 ] || { echo "Refused: there is no database '$tenant' on the $where." >&2; exit 1; }

echo "audit_trace — tenant '$tenant' on the $where — $(date -u '+%Y-%m-%d %H:%M UTC')"
case "$by" in
  c) echo "asked: capture_id $cap (any date unless --since)" ;;
  k) echo "asked: code '$code' (any date unless --since)" ;;
  d) echo "asked: device $device, received since $since" ;;
  m) echo "asked: campaign $campaign, received since $since" ;;
  *) echo "asked: every capture received since $since" ;;
esac
echo "(ids only: users, rooms, campaigns and devices by id; times UTC)"

# The old tag confirmed on a capture is a stored column since handoff 69
# (`legacy_tag_key`); a tenant before it is matched on the code alone.
has_tag=$(printf "BEGIN READ ONLY;\nSELECT count(*) FROM information_schema.columns WHERE table_name = 'nrs_audit_capture' AND column_name = 'legacy_tag_key';\nROLLBACK;\n" | psql_ro_tA "$tenant")
if [ "$has_tag" = 1 ]; then
  code_match="(upper(btrim(x.code)) = upper(:'code') OR x.legacy_tag_key = :'tag')"
else
  code_match="upper(btrim(x.code)) = upper(:'code')"
fi
# The captures this run is about: one WHERE, used by every query below.
MATCH="(:'cap' = '' OR lower(btrim(x.capture_uuid)) = :'cap')
   AND (:'code' = '' OR $code_match)
   AND (:'device' = '' OR upper(d.device_code) = upper(:'device'))
   AND (:'campaign' = '' OR x.campaign_id = NULLIF(:'campaign', '')::int)
   AND x.received_at >= :'row_since'::date"
# Without a filter the campaign table lists every campaign, empty ones too.
if [ -z "$by" ]; then all_campaigns=true; else all_campaigns=false; fi
# Phone photos on no capture: only when the question is not one capture.
if [ "$by" = c ] || [ "$by" = k ]; then photos=false; else photos=true; fi

psql_ro "$tenant" <<SQL
BEGIN READ ONLY;
SET LOCAL statement_timeout = '120s';
SELECT to_regclass('public.nrs_audit_capture') IS NOT NULL AS has_capture,
       to_regclass('public.nrs_audit_capture_refusal') IS NOT NULL AS has_refusal,
       to_regclass('public.nrs_audit_capture_photo_rel') IS NOT NULL AS has_photo,
       to_regclass('public.nrs_ai_suggestion') IS NOT NULL
         AND EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name = 'nrs_ai_suggestion' AND column_name = 'audit_photo_id') AS has_ai
\gset
\if :has_capture
\echo
\echo '== captures on this tenant (the denominator)'
SELECT count(*) AS all_time,
       count(*) FILTER (WHERE received_at >= :'since'::date) AS received_since,
       to_char(min(received_at), 'YYYY-MM-DD HH24:MI') AS first_received,
       to_char(max(received_at), 'YYYY-MM-DD HH24:MI') AS last_received
  FROM nrs_audit_capture;

\echo '== the captures asked for (A1)'
\echo '   hidden_by, for a waiting capture: H1 no active reviewer named · H2 campaign closed ·'
\echo '   H3 past the first 100 in its list (the review page before handoff 69 showed one page) ·'
\echo '   H4 open with reviewers, but no reviewer''s dropdown opens on it (they must pick it)'
WITH rev AS (
       SELECT r.campaign_id, count(*) FILTER (WHERE u.active) AS n
         FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id = r.user_id
        GROUP BY 1),
     dflt AS (   -- the review page's default: the newest open campaign naming the reviewer
       SELECT r.user_id, max(r.campaign_id) AS campaign_id
         FROM nrs_audit_campaign_reviewer_rel r
         JOIN res_users u ON u.id = r.user_id AND u.active
         JOIN nrs_audit_campaign c ON c.id = r.campaign_id AND c.state = 'open'
        GROUP BY 1),
     ranked AS (
       SELECT x.*, row_number() OVER (PARTITION BY x.campaign_id, x.state ORDER BY x.id) AS rank_in_review_list
         FROM nrs_audit_capture x)
SELECT x.id, x.capture_uuid, x.code, x.campaign_id AS camp, c.state AS camp_state,
       x.location_id AS loc, x.state, x.outcome, x.duplicate_of_id AS dup_of,
       x.operator_id AS op, x.device_id AS dev, d.device_code,
       to_char(x.captured_at, 'YYYY-MM-DD HH24:MI') AS captured_at,
       to_char(x.received_at, 'YYYY-MM-DD HH24:MI') AS received_at,
       coalesce(rev.n, 0) AS reviewers_named, x.rank_in_review_list,
       CASE WHEN x.state = 'pending_review' THEN concat_ws(' ',
         CASE WHEN coalesce(rev.n, 0) = 0 THEN 'H1' END,
         CASE WHEN c.state <> 'open' THEN 'H2' END,
         CASE WHEN x.rank_in_review_list > 100 THEN 'H3' END,
         CASE WHEN c.state = 'open' AND coalesce(rev.n, 0) > 0
                   AND NOT EXISTS (SELECT 1 FROM dflt WHERE dflt.campaign_id = x.campaign_id) THEN 'H4' END)
       END AS hidden_by
  FROM ranked x
  JOIN nrs_audit_campaign c ON c.id = x.campaign_id
  LEFT JOIN rev ON rev.campaign_id = x.campaign_id
  LEFT JOIN nrs_audit_device d ON d.id = x.device_id
 WHERE $MATCH
 ORDER BY x.id;

\echo '== per campaign'
WITH hit AS (
       SELECT DISTINCT x.campaign_id FROM nrs_audit_capture x
         LEFT JOIN nrs_audit_device d ON d.id = x.device_id WHERE $MATCH),
     dflt AS (
       SELECT r.user_id, max(r.campaign_id) AS campaign_id
         FROM nrs_audit_campaign_reviewer_rel r
         JOIN res_users u ON u.id = r.user_id AND u.active
         JOIN nrs_audit_campaign c ON c.id = r.campaign_id AND c.state = 'open'
        GROUP BY 1)
SELECT c.id AS campaign, c.state,
       to_char(c.create_date, 'YYYY-MM-DD') AS created, c.created_by_id AS created_by,
       (SELECT count(*) FROM nrs_audit_capture x WHERE x.campaign_id = c.id) AS captured,
       (SELECT count(*) FROM nrs_audit_capture x WHERE x.campaign_id = c.id AND x.state = 'pending_review') AS pending_review,
       (SELECT count(*) FROM nrs_audit_capture x WHERE x.campaign_id = c.id AND x.state = 'accepted') AS accepted,
       (SELECT count(*) FROM nrs_audit_capture x WHERE x.campaign_id = c.id AND x.state = 'returned') AS returned,
       (SELECT count(*) FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id = r.user_id
         WHERE r.campaign_id = c.id AND u.active) AS reviewers_named,
       (SELECT string_agg(r.user_id::text || CASE WHEN u.active THEN '' ELSE '(archived)' END, ',' ORDER BY r.user_id)
          FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id = r.user_id
         WHERE r.campaign_id = c.id) AS reviewer_ids,
       (SELECT string_agg(user_id::text, ',' ORDER BY user_id) FROM dflt WHERE dflt.campaign_id = c.id) AS dropdown_opens_here_for,
       (SELECT string_agg(r.user_id::text, ',' ORDER BY r.user_id)
          FROM nrs_audit_campaign_capturer_rel r WHERE r.campaign_id = c.id) AS capturer_ids
  FROM nrs_audit_campaign c
 WHERE ($all_campaigns OR c.id IN (SELECT campaign_id FROM hit))
   AND (:'campaign' = '' OR c.id = NULLIF(:'campaign', '')::int)
 ORDER BY c.id;

\echo '== devices'
SELECT d.id, d.device_code, d.active, d.user_id AS bound_to,
       to_char(d.registered_at, 'YYYY-MM-DD HH24:MI') AS registered,
       (SELECT count(*) FROM nrs_audit_capture x WHERE x.device_id = d.id) AS captures_all_time,
       to_char((SELECT max(x.received_at) FROM nrs_audit_capture x WHERE x.device_id = d.id),
               'YYYY-MM-DD HH24:MI') AS last_capture
  FROM nrs_audit_device d
 WHERE (:'device' = '' OR upper(d.device_code) = upper(:'device'))
   AND ($all_campaigns OR :'device' <> ''
        OR d.id IN (SELECT x.device_id FROM nrs_audit_capture x
                      LEFT JOIN nrs_audit_device d ON d.id = x.device_id WHERE $MATCH))
 ORDER BY d.id;
\else
\echo
\echo 'this tenant has no nrs_audit_capture table: myservice_asset_register is older than handoff 66 here, so no capture was ever stored on it.'
\endif

\echo
\if :has_refusal
\echo '== refused syncs kept (nrs_audit_capture_refusal; kept 90 days; a 401 and a scope 403 are not kept — use --logs)'
SELECT count(*) AS kept_all, count(*) FILTER (WHERE refused_at >= :'since'::date) AS refused_since
  FROM nrs_audit_capture_refusal;
SELECT f.id, to_char(f.refused_at, 'YYYY-MM-DD HH24:MI:SS') AS refused_at, f.capture_uuid,
       f.user_id, f.device_code, f.device_id, f.campaign_id, f.location_id, f.code,
       f.http_status, f.error_code, f.reason,
       -- the server's own sentence; the one refusal on this route that names
       -- a person (Device X is bound to NAME, not to you) has the name taken out
       left(regexp_replace(f.message, 'is bound to .*, not to you', 'is bound to <person>, not to you'), 120) AS message,
       f.request_id
  FROM nrs_audit_capture_refusal f
 WHERE f.refused_at >= :'row_since'::date
   AND (:'cap' = '' OR lower(btrim(f.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(f.code)) = upper(:'code'))
   AND (:'device' = '' OR upper(f.device_code) = upper(:'device'))
   AND (:'campaign' = '' OR f.campaign_id = NULLIF(:'campaign', '')::int)
 ORDER BY f.id DESC
 LIMIT 200;
\else
\echo 'this tenant has no nrs_audit_capture_refusal table (myservice_asset_register older than 19.0.1.37.0, handoff 69):'
\echo 'a refusal there left nothing but the Odoo log line — run again with --logs.'
\endif

\if $photos
\if :has_photo
\echo
\echo '== photos uploaded since the window opened and on NO capture (a capture photographed and never sent, or sent and refused)'
SELECT p.source, count(*) AS uploaded_since,
       count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM nrs_audit_capture_photo_rel r WHERE r.photo_id = p.id)) AS on_no_capture
  FROM nrs_audit_photo p
 WHERE p.uploaded_at >= :'since'::date
   AND (:'device' = '' OR p.uploaded_by_id IN (SELECT user_id FROM nrs_audit_device WHERE upper(device_code) = upper(:'device')))
 GROUP BY 1 ORDER BY 1;
\if :has_ai
SELECT p.id AS photo, p.source, p.uploaded_by_id AS by,
       to_char(p.uploaded_at, 'YYYY-MM-DD HH24:MI') AS uploaded,
       (SELECT count(*) FROM nrs_ai_suggestion s WHERE s.audit_photo_id = p.id) AS ai_calls
  FROM nrs_audit_photo p
 WHERE p.uploaded_at >= :'since'::date
   AND NOT EXISTS (SELECT 1 FROM nrs_audit_capture_photo_rel r WHERE r.photo_id = p.id)
   AND (:'device' = '' OR p.uploaded_by_id IN (SELECT user_id FROM nrs_audit_device WHERE upper(device_code) = upper(:'device')))
 ORDER BY p.id;
\else
SELECT p.id AS photo, p.source, p.uploaded_by_id AS by,
       to_char(p.uploaded_at, 'YYYY-MM-DD HH24:MI') AS uploaded
  FROM nrs_audit_photo p
 WHERE p.uploaded_at >= :'since'::date
   AND NOT EXISTS (SELECT 1 FROM nrs_audit_capture_photo_rel r WHERE r.photo_id = p.id)
   AND (:'device' = '' OR p.uploaded_by_id IN (SELECT user_id FROM nrs_audit_device WHERE upper(device_code) = upper(:'device')))
 ORDER BY p.id;
\endif
\echo '== one photo on several captures (each capture should carry its own photo — handoff 69 Part A: staging photo 8 on four)'
SELECT r.photo_id AS photo, count(*) AS captures,
       string_agg(r.capture_id::text, ',' ORDER BY r.capture_id) AS capture_ids,
       count(DISTINCT x.location_id) AS rooms
  FROM nrs_audit_capture_photo_rel r JOIN nrs_audit_capture x ON x.id = r.capture_id
  LEFT JOIN nrs_audit_device d ON d.id = x.device_id
 WHERE $MATCH
 GROUP BY r.photo_id HAVING count(*) > 1
 ORDER BY r.photo_id;
\endif
\endif
ROLLBACK;
SQL

# The cross-tenant search (H6): how many captures match here, and on another
# database what matches there — a capture, or a kept refusal.
# A missing table is an error when the statement is PARSED, whatever a CASE
# around it says, so each part is behind psql's own `\if`.
sql_count_here() {
  cat <<'SQL'
BEGIN READ ONLY;
SELECT to_regclass('public.nrs_audit_capture') IS NOT NULL AS has_capture,
       EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'nrs_audit_capture'
                AND column_name = 'legacy_tag_key') AS has_tag \gset
\if :has_capture
\if :has_tag
SELECT count(*) FROM nrs_audit_capture x
 WHERE (:'cap' = '' OR lower(btrim(x.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(x.code)) = upper(:'code') OR x.legacy_tag_key = :'tag');
\else
SELECT count(*) FROM nrs_audit_capture x
 WHERE (:'cap' = '' OR lower(btrim(x.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(x.code)) = upper(:'code'));
\endif
\else
SELECT 0;
\endif
ROLLBACK;
SQL
}
# Prints `no capture table`, or one line per capture found and per refusal
# kept, or nothing.
sql_found_where() {
  cat <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout = '60s';
SELECT to_regclass('public.nrs_audit_capture') IS NOT NULL AS has_capture,
       to_regclass('public.nrs_audit_capture_refusal') IS NOT NULL AS has_refusal,
       EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'nrs_audit_capture'
                AND column_name = 'legacy_tag_key') AS has_tag \gset
\if :has_capture
\if :has_tag
SELECT 'capture id ' || x.id || ' (campaign ' || x.campaign_id || ', ' || x.state
       || ', received ' || to_char(x.received_at, 'YYYY-MM-DD HH24:MI') || ')'
  FROM nrs_audit_capture x
 WHERE (:'cap' = '' OR lower(btrim(x.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(x.code)) = upper(:'code') OR x.legacy_tag_key = :'tag')
 ORDER BY x.id;
\else
SELECT 'capture id ' || x.id || ' (campaign ' || x.campaign_id || ', ' || x.state
       || ', received ' || to_char(x.received_at, 'YYYY-MM-DD HH24:MI') || ')'
  FROM nrs_audit_capture x
 WHERE (:'cap' = '' OR lower(btrim(x.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(x.code)) = upper(:'code'))
 ORDER BY x.id;
\endif
\else
SELECT 'no capture table';
\endif
\if :has_refusal
SELECT 'refused ' || count(*) || 'x, last ' || to_char(max(f.refused_at), 'YYYY-MM-DD HH24:MI')
  FROM nrs_audit_capture_refusal f
 WHERE (:'cap' = '' OR lower(btrim(f.capture_uuid)) = :'cap')
   AND (:'code' = '' OR upper(btrim(f.code)) = upper(:'code'))
HAVING count(*) > 0;
\endif
ROLLBACK;
SQL
}

# ── H6: not here — is it on another tenant? ─────────────────────────────
if [ "$by" = c ] || [ "$by" = k ]; then
  q_here=$(sql_count_here | psql_ro_tA "$tenant")
  if [ "$q_here" = 0 ]; then
    echo
    echo "== not stored on '$tenant' — looking on every other database (H6)"
    dbs=$(printf "BEGIN READ ONLY;\nSELECT datname FROM pg_database WHERE NOT datistemplate AND datallowconn AND datname NOT IN ('postgres', 'nrs19', '%s') ORDER BY 1;\nROLLBACK;\n" "$tenant" | psql_ro_tA postgres)
    found=0
    for db in $dbs; do
      [[ "$db" =~ ^[a-z0-9_]+$ ]] || continue
      line=$(sql_found_where | psql_ro_tA "$db" 2>/dev/null || echo unreadable)
      line=$(printf '%s' "$line" | paste -sd ';' - | sed 's/;/; /g')
      case "$line" in
        "")               echo "  $db: not there" ;;
        "no capture table"|unreadable) echo "  $db: $line" ;;
        *)                echo "  $db: FOUND — $line"; found=1 ;;
      esac
    done
    here=$(sql_found_where | psql_ro_tA "$tenant" | grep '^refused ' || true)
    if [ -n "$here" ]; then
      echo "  but '$tenant' REFUSED it: $here — the refused syncs above say why (H5)."
      echo "  The phone must show that sentence and keep the capture to fix and send again."
    elif [ $found = 0 ]; then
      echo "  found on no database, and no refusal kept for it here. Not stored anywhere: refused"
      echo "  (by a 401/403 at the door, which is never kept, or before handoff 69 kept refusals) (H5),"
      echo "  or still on the phone (H7) — run with --logs for the POSTs that reached the server."
    else
      echo "  the phone sent it to another tenant (H6): its base URL is not '$tenant'."
    fi
  fi
fi

# ── --logs: what reached the server ─────────────────────────────────────
if [ $logs = 1 ]; then
  hours=$(python3 -c "import datetime,math; d=datetime.datetime.strptime('$since','%Y-%m-%d'); print(max(1, math.ceil((datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)-d).total_seconds()/3600)))")
  echo
  echo "== the Odoo log: POST /api/v1/audit/captures for '$tenant' since $since (${hours}h), client address removed"
  # One werkzeug line per request: `… INFO <db> werkzeug: <addr> - - [date] "POST /path HTTP/1.1" <status> - …`
  pick() {
    grep -E " INFO $tenant werkzeug: .*\"POST /api/v1/audit/captures(\?[^ ]*)? HTTP" \
      | sed -E 's/werkzeug: [^[]* - - \[/werkzeug: <addr> - - [/' || true
  }
  if [ $local = 1 ]; then
    cid=$("${compose[@]}" ps -q odoo)
    # Docker keeps a container's log across a restart; a recreate (`up -d
    # --force-recreate`, a new image) starts it empty.
    echo "  odoo container created $(docker inspect -f '{{.Created}}' "$cid"); nothing before that is in its log."
    lines=$("${compose[@]}" logs --no-log-prefix --since "${since}T00:00:00Z" odoo 2>&1 | pick)
  else
    sel=$("${K[@]}" get deploy/odoo-19 -o go-template='{{range $k, $v := .spec.selector.matchLabels}}{{$k}}={{$v}},{{end}}')
    sel="${sel%,}"
    pods=$("${K[@]}" get pods -l "$sel" -o go-template='{{range .items}}{{.metadata.name}} {{(index .status.containerStatuses 0).state.running.startedAt}} restarts={{(index .status.containerStatuses 0).restartCount}}{{"\n"}}{{end}}')
    lines=""
    while read -r pod started restarts; do
      [ -n "$pod" ] || continue
      # A pod's log begins when its container started; a rollout or a
      # restart loses what came before (`kubectl logs --previous` holds one
      # restart back).
      echo "  pod $pod started $started ($restarts); nothing before that is in its log."
      lines="$lines$("${K[@]}" logs "$pod" --since="${hours}h" 2>&1 | pick)
"
    done <<< "$pods"
  fi
  lines=$(printf '%s\n' "$lines" | sed '/^$/d')
  if [ -z "$lines" ]; then
    echo "  0 POSTs in the window."
  else
    total=$(printf '%s\n' "$lines" | wc -l | tr -d ' ')
    if [ "$total" -gt 40 ]; then echo "  the last 40 of $total:"; fi
    printf '%s\n' "$lines" | tail -40 | sed 's/^/  /'
    echo "  by status, all $total:"
    printf '%s\n' "$lines" | sed -E 's/.*HTTP\/[0-9.]+" ([0-9]{3}) .*/\1/' | sort | uniq -c | sed 's/^/  /'
  fi
fi

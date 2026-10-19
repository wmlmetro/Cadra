#!/usr/bin/env bash
# A fresh test tenant in a minute (handoff 63b).
#
#   scripts/fresh_test_tenant.sh <tenant>                     restore from the template
#   scripts/fresh_test_tenant.sh <tenant> --rebuild-template  rebuild it first, then restore
#
# `test19` grows every week — 23,024 assets and 332 MB on 2026-10-19, 20,680
# of them in one class — and every suite run on it gets slower. CI runs the
# same suites on a database it built that morning, in a seventh of the time.
# This gives the bench that database: a TEMPLATE built the way CI builds its
# one (bootstrap's module list installed, `scripts/bootstrap.py` with the core
# seed and `CADRA_DATABASE_CLASS=test`, the demo personas), kept as a Postgres
# template nobody can connect to, and copied with `CREATE DATABASE … TEMPLATE`
# whenever a clean tenant is wanted.
#
# What it refuses, before it touches anything:
#   - a tenant not on ALLOWED below — `nrs19` is a replica of a real NRS staff
#     extract, `jaizbankplc`/`nrs`/`lasg`/`gtb` replicas of client registers;
#   - an existing database not marked `cadra.database_class = test` — it is
#     DROPPED and recreated, so the database has to say it is a test one;
#   - a Docker daemon that is not this machine's (`DOCKER_HOST` set to
#     anything but a unix socket): the cluster is never a target.
#
# The template carries the same credentials and persona passwords as every
# tenant restored from it, so `docs/api/.creds.<template>` and
# `.personas.<template>` are copied to the tenant's names on each restore.
#
# Only one `--stop-after-init` registry load at a time on this host
# (`docs/ENVIRONMENT-FACTS.md`): a rebuild runs two, one after the other,
# beside the live server. A restore runs none.
set -euo pipefail

ALLOWED=(test19f test19)
TEMPLATE=cadra_test_template

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
compose=(docker compose -f docker-compose.yml -f docker-compose.19.yml)

tenant="${1:-}"
rebuild=0
case "${2:-}" in
  "") ;;
  --rebuild-template) rebuild=1 ;;
  *) echo "usage: $0 <tenant> [--rebuild-template]" >&2; exit 2 ;;
esac

# ── the refusals, before a connection is opened ─────────────────────────
if [ -z "$tenant" ]; then
  echo "usage: $0 <tenant> [--rebuild-template]   (allowed: ${ALLOWED[*]})" >&2
  exit 2
fi
allowed=0
for t in "${ALLOWED[@]}"; do [ "$t" = "$tenant" ] && allowed=1; done
if [ "$allowed" != 1 ]; then
  case "$tenant" in
    nrs19)  why="it is a replica of a real NRS staff extract" ;;
    jaizbankplc|nrs|lasg|gtb) why="it is a replica of a client's register, marked client" ;;
    cadra19|gtb19) why="it is a demo tenant, not a disposable one" ;;
    staging) why="it is a cluster tenant" ;;
    *) why="it is not on this script's allow-list" ;;
  esac
  echo "Refused: '$tenant' — $why. This script recreates only: ${ALLOWED[*]}." >&2
  exit 1
fi
if [ -n "${DOCKER_HOST:-}" ] && [[ "$DOCKER_HOST" != unix://* ]]; then
  echo "Refused: DOCKER_HOST is '$DOCKER_HOST'. This script recreates a tenant on this machine's stack only." >&2
  exit 1
fi

psql() { "${compose[@]}" exec -T db psql -U odoo -d postgres -v ON_ERROR_STOP=1 -tA "$@"; }
psql_db() { local d="$1"; shift; "${compose[@]}" exec -T db psql -U odoo -d "$d" -v ON_ERROR_STOP=1 -tA "$@"; }
exists() { [ "$(psql -c "SELECT count(*) FROM pg_database WHERE datname = '$1'")" = 1 ]; }
kick() {
  psql -c "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
           WHERE datname = '$1' AND pid <> pg_backend_pid()" >/dev/null
}
# The filestore is not in Postgres: `CREATE DATABASE … TEMPLATE` copies the
# rows and none of the files they name. Without the copy, the first asset
# bundle request answers 500 and the login page goes blank
# (`docs/ENVIRONMENT-FACTS.md`, handoff 45).
FILESTORE=/var/lib/odoo/.local/share/Odoo/filestore
odoo_sh() { "${compose[@]}" exec -T odoo sh -c "$1"; }
now() { python3 -c 'import time; print(time.time())'; }
since() { python3 -c "import sys; print('%.1f' % (float(sys.argv[2]) - float(sys.argv[1])))" "$1" "$(now)"; }

if exists "$tenant"; then
  class=$(psql_db "$tenant" -c "SELECT value FROM ir_config_parameter WHERE key = 'cadra.database_class'" 2>/dev/null || true)
  if [ "$class" != test ]; then
    echo "Refused: '$tenant' exists and is marked '${class:-(unmarked)}', not 'test'. It would be dropped." >&2
    exit 1
  fi
fi

# ── the template ────────────────────────────────────────────────────────
build_template() {
  local t0 modules out creds
  t0=$(now)
  echo "▶ building template '$TEMPLATE' (about 4 minutes)"
  if exists "$TEMPLATE"; then
    psql -c "ALTER DATABASE $TEMPLATE WITH IS_TEMPLATE false ALLOW_CONNECTIONS true" >/dev/null
    kick "$TEMPLATE"
    psql -c "DROP DATABASE $TEMPLATE" >/dev/null
  fi
  odoo_sh "rm -rf '$FILESTORE/$TEMPLATE'"
  modules=$(grep -E '^CADRA_BOOTSTRAP_MODULES=' .env.example | cut -d= -f2-)
  echo "  install: $modules"
  # Odoo creates the empty database itself (`odoo/cli/server.py`), with
  # its own encoding and collation, the way CI's is created.
  "${compose[@]}" exec -T odoo odoo -c /etc/odoo/odoo.conf -d "$TEMPLATE" \
    -i "$modules" --stop-after-init --workers=0 \
    --http-port=8099 --gevent-port=8098 --log-level=warn 2>&1 | tail -5
  [ "$(psql_db "$TEMPLATE" -c "SELECT count(*) FROM ir_module_module WHERE name = 'myservice_api' AND state = 'installed'")" = 1 ] \
    || { echo "FATAL: myservice_api is not installed on '$TEMPLATE'" >&2; exit 1; }

  echo "  bootstrap.py (core seed, class test)"
  out=$(mktemp); chmod 600 "$out"
  # `exec(open(...))`, as bootstrap.sh does: piped line by line, the
  # interactive console ends a block at the first blank line inside it.
  "${compose[@]}" exec -T -e CADRA_DATABASE_CLASS=test -e CADRA_SEED_PROFILE=core \
    -e CADRA_PROFILE=dev odoo bash -c \
    "odoo shell -c /etc/odoo/odoo.conf -d $TEMPLATE --no-http --http-port=8099 --gevent-port=8098 --log-level=warn <<< \"exec(open('/mnt/extra-addons/scripts/bootstrap.py').read())\"" \
    > "$out" 2>&1 || { tail -30 "$out" >&2; rm -f "$out"; exit 1; }
  creds=$(sed -n '/CADRA_BOOTSTRAP_BEGIN/,/CADRA_BOOTSTRAP_END/p' "$out" \
    | grep -E '^(JWT_SECRET|CLIENT_ID|CLIENT_SECRET|TAGGING_CLIENT_ID|TAGGING_CLIENT_SECRET|VENDRA_CLIENT_ID|VENDRA_CLIENT_SECRET)=' || true)
  if [ -z "$creds" ] || printf '%s\n' "$creds" | grep -q '=<'; then
    echo "FATAL: bootstrap.py printed no complete credentials block for a fresh database:" >&2
    tail -30 "$out" >&2; rm -f "$out"; exit 1
  fi
  grep -E '^\[bootstrap:' "$out" | tail -8 || true
  rm -f "$out"
  (umask 077; printf '%s\n' "$creds" > "docs/api/.creds.$TEMPLATE")

  echo "  demo personas"
  rm -f "docs/api/.personas.$TEMPLATE"
  scripts/demo_personas.sh "$TEMPLATE" seed | grep -E '^(passwords|created|personas)' || true
  [ -s "docs/api/.personas.$TEMPLATE" ] \
    || { echo "FATAL: no persona passwords written for '$TEMPLATE'" >&2; exit 1; }

  echo "  the fixtures test19 carries and CI's database does not"
  "${compose[@]}" exec -T odoo bash -c \
    "odoo shell -c /etc/odoo/odoo.conf -d $TEMPLATE --no-http --http-port=8099 --gevent-port=8098 --log-level=warn <<< \"exec(open('/mnt/extra-addons/scripts/seed_test_template_fixtures.py').read())\"" \
    2>&1 | grep -E '^\[template-fixtures\]|refused|Error' || true
  [ "$(psql_db "$TEMPLATE" -c "SELECT count(*) FROM res_users WHERE login = 'h41_tagger'")" = 1 ] \
    || { echo "FATAL: the template fixtures were not seeded on '$TEMPLATE'" >&2; exit 1; }

  [ "$(psql_db "$TEMPLATE" -c "SELECT value FROM ir_config_parameter WHERE key = 'cadra.database_class'")" = test ] \
    || { echo "FATAL: '$TEMPLATE' is not marked test after bootstrap" >&2; exit 1; }

  # A template nobody can connect to: Odoo's database list skips it
  # (`not datistemplate and datallowconn`), so the scheduler never opens a
  # cursor on it, and `CREATE DATABASE … TEMPLATE` never finds it busy.
  kick "$TEMPLATE"
  psql -c "ALTER DATABASE $TEMPLATE WITH IS_TEMPLATE true ALLOW_CONNECTIONS false" >/dev/null
  echo "  template built in $(since "$t0") s"
}

if [ "$rebuild" = 1 ] || ! exists "$TEMPLATE"; then
  build_template
fi
for f in creds personas; do
  [ -s "docs/api/.$f.$TEMPLATE" ] || {
    echo "FATAL: docs/api/.$f.$TEMPLATE is missing — the template's secrets are unreadable. Run with --rebuild-template." >&2
    exit 1; }
done

# ── the restore ─────────────────────────────────────────────────────────
t0=$(now)
echo "▶ restoring '$tenant' from '$TEMPLATE'"
if exists "$tenant"; then
  psql -c "ALTER DATABASE $tenant WITH ALLOW_CONNECTIONS false" >/dev/null
  kick "$tenant"
  psql -c "DROP DATABASE $tenant" >/dev/null
fi
psql -c "CREATE DATABASE $tenant TEMPLATE $TEMPLATE OWNER odoo" >/dev/null
odoo_sh "rm -rf '$FILESTORE/$tenant' && if [ -d '$FILESTORE/$TEMPLATE' ]; then cp -a '$FILESTORE/$TEMPLATE' '$FILESTORE/$tenant'; fi"
# The live server may hold a registry for a database of this name from
# before the drop. Moving the signalling sequences makes every worker
# reload it on its next request instead of serving the old one's caches.
psql_db "$tenant" -c "SELECT count(setval(c.relname::regclass, nextval(c.relname::regclass) + 1000))
                      FROM pg_class c WHERE c.relkind = 'S' AND c.relname LIKE 'base\_%\_signaling%'" >/dev/null
for f in creds personas; do
  (umask 077; cp "docs/api/.$f.$TEMPLATE" "docs/api/.$f.$tenant")
done
echo "  restored in $(since "$t0") s"

curl -s -o /dev/null -w "  http://$tenant.localhost:8069/web/login → %{http_code}\n" \
  "http://$tenant.localhost:8069/web/login" || true
echo "  run: CADRA_API_BASE=http://$tenant.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q"

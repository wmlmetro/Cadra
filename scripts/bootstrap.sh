#!/usr/bin/env bash
#
# Cadra deployment bootstrap.
#
# Brings a fresh stack from zero → fully operational + API client ready.
# Idempotent — safe to re-run on a populated stack (steps that are already
# done become no-ops).
#
# Usage:
#   scripts/bootstrap.sh                 # dev profile (uses docker-compose.dev.yml)
#   CADRA_PROFILE=prod scripts/bootstrap.sh
#
# What it does:
#   1. Validates prerequisites (docker, .env)
#   2. Brings up the stack (`docker compose up -d`)
#   3. Waits for Postgres ready (healthcheck)
#   4. Detects whether the DB already has Odoo modules installed:
#        - 0 modules → fresh DB → run odoo with -i MODULES
#        - N modules → existing → skip install, run -u to pick up code changes
#   5. Runs scripts/bootstrap.py inside an odoo shell:
#        - sets JWT secret + admin groups + API client + seeds
#   6. Captures the printed credentials, writes them to docs/api/.creds.<db>
#   7. Restarts the live odoo container so it picks up the new state
#   8. Prints a usage summary

set -euo pipefail

# ─── pre-flight ──────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CADRA_PROFILE="${CADRA_PROFILE:-dev}"
COMPOSE_FILES=(-f docker-compose.yml)
case "$CADRA_PROFILE" in
    dev)   COMPOSE_FILES+=(-f docker-compose.dev.yml) ;;
    dev19) COMPOSE_FILES+=(-f docker-compose.19.yml) ;;   # Odoo 19 rebuild stack
    prod)  COMPOSE_FILES+=(-f docker-compose.prod.yml) ;;
    *)     echo "FATAL: CADRA_PROFILE must be 'dev', 'dev19' or 'prod', got '$CADRA_PROFILE'" >&2; exit 1 ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    echo "FATAL: docker not found in PATH" >&2
    exit 1
fi

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "==> No .env found. Copying .env.example → .env (defaults are dev-safe)."
        cp .env.example .env
    else
        echo "FATAL: neither .env nor .env.example exists" >&2
        exit 1
    fi
fi

# Source .env for our own use (docker-compose reads it independently).
set -a
# shellcheck disable=SC1091
. ./.env
set +a

ODOO_DB="${POSTGRES_DB:-odoo}"
ODOO_USER_DB="${POSTGRES_USER:-odoo}"

# Strip web_responsive from the install list if its source isn't vendored
# (we ship it under dist/ — see dist/web_responsive/). Defensive only.
MODULES="${CADRA_BOOTSTRAP_MODULES:-myservice_api,myservice_asset_register,myservice_barcode_station,myservice_dashboard,myservice_fleet_maintenance,myservice_fm_dashboard,myservice_identity,myservice_nrs_base,myservice_request_fields,myservice_security,myservice_staff_bus,myservice_theme_v5,myservice_website_theme,myservice_workflow,web_responsive}"

echo "═══════════════════════════════════════════════════════════════════"
echo "  Cadra bootstrap — profile: $CADRA_PROFILE"
echo "  Compose files: ${COMPOSE_FILES[*]}"
echo "  Database: $ODOO_DB"
echo "═══════════════════════════════════════════════════════════════════"

# ─── step 1: build image + start postgres only ───────────────────────

echo ""
echo "▶ Building odoo image (cached on subsequent runs)..."
docker compose "${COMPOSE_FILES[@]}" build odoo >/dev/null

echo ""
echo "▶ Starting postgres first (odoo + proxy come up after install)..."
docker compose "${COMPOSE_FILES[@]}" up -d db

# ─── step 2: wait for postgres ────────────────────────────────────────

echo ""
echo "▶ Waiting for postgres healthcheck..."
for i in $(seq 1 60); do
    if docker compose "${COMPOSE_FILES[@]}" exec -T db pg_isready -U "$ODOO_USER_DB" -d "$ODOO_DB" >/dev/null 2>&1; then
        echo "  postgres ready after ${i}s"
        break
    fi
    sleep 1
done

if ! docker compose "${COMPOSE_FILES[@]}" exec -T db pg_isready -U "$ODOO_USER_DB" -d "$ODOO_DB" >/dev/null 2>&1; then
    echo "FATAL: postgres did not become ready" >&2
    exit 1
fi

# ─── step 3: detect DB state ─────────────────────────────────────────

echo ""
echo "▶ Detecting Odoo DB state..."

# A fresh postgres has the `odoo` DB but no ir_module_module table.
# An initialised Odoo DB has it. Use that as the discriminator.
installed_count=$(docker compose "${COMPOSE_FILES[@]}" exec -T db \
    psql -U "$ODOO_USER_DB" -d "$ODOO_DB" -tAc \
    "SELECT count(*) FROM ir_module_module WHERE state='installed'" 2>/dev/null \
    || echo "0")
installed_count=$(echo "$installed_count" | tr -d ' \n')

# ─── step 4: install or update modules ───────────────────────────────

if [ "$installed_count" = "0" ]; then
    echo "  fresh DB — installing $MODULES"
    docker compose "${COMPOSE_FILES[@]}" run --rm -T odoo \
        odoo -c /etc/odoo/odoo.conf -d "$ODOO_DB" \
        -i "$MODULES" --stop-after-init --no-http 2>&1 \
        | tail -8
else
    echo "  existing DB with $installed_count installed modules — skipping init"
fi

# Now bring up odoo + proxy (they were held back so install could own the DB)
echo ""
echo "▶ Starting odoo + proxy..."
docker compose "${COMPOSE_FILES[@]}" up -d
sleep 5

# ─── step 5: run bootstrap.py via odoo shell ─────────────────────────

echo ""
echo "▶ Running scripts/bootstrap.py inside odoo shell..."

# Run in a one-off odoo container so we don't fight the live one for the
# DB lock. The repo is bind-mounted at /mnt/extra-addons so the script is
# reachable via /mnt/extra-addons/scripts/bootstrap.py.
docker compose "${COMPOSE_FILES[@]}" stop odoo >/dev/null
BOOT_OUTPUT=$(docker compose "${COMPOSE_FILES[@]}" run --rm -T odoo bash -c \
    "odoo shell -c /etc/odoo/odoo.conf -d $ODOO_DB --no-http <<< \"exec(open('/mnt/extra-addons/scripts/bootstrap.py').read())\"" 2>&1)
docker compose "${COMPOSE_FILES[@]}" up -d odoo >/dev/null

# Print the bootstrap [bootstrap:...] lines for visibility
echo "$BOOT_OUTPUT" | grep -E "^\[bootstrap:" || true

# ─── step 6: capture credentials ─────────────────────────────────────

mkdir -p docs/api

# Extract the sentinel-wrapped credentials block
CREDS=$(echo "$BOOT_OUTPUT" | sed -n '/CADRA_BOOTSTRAP_BEGIN/,/CADRA_BOOTSTRAP_END/p' \
    | grep -E '^(JWT_SECRET|CLIENT_ID|CLIENT_SECRET|TAGGING_CLIENT_ID|TAGGING_CLIENT_SECRET|VENDRA_CLIENT_ID|VENDRA_CLIENT_SECRET)=')

# Per-tenant. Secrets belong to a database, not to a checkout: one Odoo process
# serves every tenant, but each holds its own API clients and its own
# jwt_secret. A single shared docs/api/.creds meant bootstrapping ANY tenant
# silently invalidated the file for whichever tenant the test suite was aimed
# at — which is exactly how handoff 03 lost an afternoon.
# ODOO_DB is POSTGRES_DB from .env — this script takes no database argument,
# so bootstrapping another tenant means changing .env first.
CREDS_FILE="docs/api/.creds.${ODOO_DB}"

# bootstrap.py cannot re-read a hashed secret, so when it preserves one it
# prints "<UNCHANGED — ...>" in its place. That placeholder used to be written
# straight to disk, destroying a working creds file and producing a 401 that
# looks like a code fault. Merge instead: a placeholder keeps whatever the
# file already held for that key, and only real values overwrite.
merge_creds() {
    local target="$1" tmp line key val old
    tmp="$(mktemp)"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        key="${line%%=*}"
        val="${line#*=}"
        case "$val" in
            "<"*)
                old=""
                # `|| true`: no previous line for this key is the normal
                # first-run case, and grep's exit 1 would abort under `set -e`.
                [ -f "$target" ] && old="$(grep -E "^${key}=" "$target" | head -1 || true)"
                if [ -n "$old" ]; then
                    printf '%s\n' "$old" >> "$tmp"
                    echo "  ${key}: preserved (existing value kept)"
                else
                    printf '# %s not captured — existing secret preserved and unreadable.\n' "$key" >> "$tmp"
                    printf '# Rotate it from Settings → API Clients, or re-run with the matching CADRA_*_SECRET set.\n' >> "$tmp"
                    echo "  ${key}: NOT captured — no previous value on file" >&2
                fi
                ;;
            *)
                printf '%s\n' "$line" >> "$tmp"
                ;;
        esac
    done
    mv "$tmp" "$target"
    chmod 600 "$target"
}

if [ -z "$CREDS" ]; then
    echo ""
    echo "WARNING: bootstrap.py didn't print a credentials block." >&2
    echo "Full output for debugging:" >&2
    echo "$BOOT_OUTPUT" | tail -30 >&2
else
    echo ""
    echo "▶ Credentials → ${CREDS_FILE} (gitignored)"
    printf '%s\n' "$CREDS" | merge_creds "$CREDS_FILE"
    echo "  The test suite resolves this file from CADRA_API_BASE's hostname:"
    echo "    CADRA_API_BASE=http://${ODOO_DB}.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q"
fi

# ─── step 7: wait for odoo to be healthy again ───────────────────────

echo ""
echo "▶ Waiting for odoo to be ready (post-bootstrap restart)..."
for i in $(seq 1 60); do
    if docker compose "${COMPOSE_FILES[@]}" exec -T odoo python3 -c 'import urllib.request,sys; urllib.request.urlopen("http://localhost:8069/web/login", timeout=3)' >/dev/null 2>&1; then
        echo "  odoo ready after ${i}s"
        break
    fi
    sleep 2
done

# ─── step 8: summary ─────────────────────────────────────────────────

cat <<EOF

═══════════════════════════════════════════════════════════════════
  Bootstrap complete ✓
═══════════════════════════════════════════════════════════════════

  Web UI:      $([ "$CADRA_PROFILE" = "prod" ] && echo "https://${CADRA_DOMAIN:-<set CADRA_DOMAIN>}" || echo "http://localhost:8069")
  API docs:    $([ "$CADRA_PROFILE" = "prod" ] && echo "https://${CADRA_DOMAIN:-<set CADRA_DOMAIN>}/api/v1/docs" || echo "http://localhost:8069/api/v1/docs")
  OpenAPI:     $([ "$CADRA_PROFILE" = "prod" ] && echo "https://${CADRA_DOMAIN:-<set CADRA_DOMAIN>}/api/v1/openapi.json" || echo "http://localhost:8069/api/v1/openapi.json")

  Admin login: admin / ${ODOO_MASTER_PASSWORD:-admin}
  API client:  see ${CREDS_FILE:-docs/api/.creds.${ODOO_DB}}

  Run the test suite (the hostname picks the tenant, and the tenant picks
  the credentials file):
    CADRA_API_BASE=http://${ODOO_DB}.localhost:8069 \
      tests/.venv/bin/python -m pytest tests/ -q

═══════════════════════════════════════════════════════════════════
EOF

#!/usr/bin/env bash
#
# seed_dev.sh — Docker-aware seed loader for the local NRS dev environment.
#
# Replaces load_all.sh (which targets a /opt/odoo VPS install). Runs the core
# seed scripts via `docker compose run --rm odoo odoo shell` against the local
# docker-compose stack. The repo root is bind-mounted at /mnt/extra-addons in
# the container so seed scripts are reachable inside the runtime.
#
# Usage:
#   ./seed_dev.sh                # run all default seeds (core)
#   ./seed_dev.sh fleet          # also run myservice_master_seed (slow — fleet + branding)
#   SKIP_OFFICES=1 ./seed_dev.sh # skip the 415-office loader (faster iteration)
#
# Each seed runs in its own one-off container so a failure in one doesn't
# leave the runtime in a half-loaded state. The live odoo container is
# stopped during the run to avoid two odoos contending for the same DB.

# Pipefail on, but not -e: we want to continue past individual seed failures
# (some seeds commit successful data then crash on cleanup; we shouldn't
# abort the chain when that happens).
set -uo pipefail

# BOTH files, always. The overlay alone resolves no image for `db` and
# mounts no repo at /mnt/extra-addons, so every seed path below would be
# missing inside the container. This said `-f docker-compose.dev.yml`
# for as long as it has existed and was broken the same way.
COMPOSE_FILES=(-f docker-compose.yml -f "${COMPOSE_FILE:-docker-compose.19.yml}")
DB_NAME="${DB_NAME:-odoo}"

# Default seed sequence — same as load_all.sh but with self-contained
# load_offices.py (the OFFICES_CSV env var in load_all.sh was vestigial).
SEEDS_CORE=(
    "ITSM Structure          /mnt/extra-addons/itsm_structure.py"
    "Location Skeleton       /mnt/extra-addons/load_locations.py"
)

if [ "${SKIP_OFFICES:-0}" != "1" ]; then
    SEEDS_CORE+=("FIRS Offices (415)      /mnt/extra-addons/load_offices.py")
fi

# Extended seeds — opt-in via positional args
SEEDS_FLEET=(
    "Master Seed (ITSM+Fleet) /mnt/extra-addons/myservice_master_seed.py"
)

# ─── helpers ─────────────────────────────────────────────────────────

SEED_FAILURES=()

run_seed() {
    local label="$1"
    local path="$2"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  ▶  ${label}"
    echo "     ${path}"
    echo "════════════════════════════════════════════════════════════"
    # `odoo shell` reads Python from stdin; we pipe the seed file in.
    # The script must be path-resolvable INSIDE the container.
    # We don't propagate the exit code — some seeds commit then crash on
    # cleanup; row-count check at the end is the real verification.
    if ! docker compose "${COMPOSE_FILES[@]}" run --rm -T odoo bash -c \
        "odoo shell -c /etc/odoo/odoo.conf -d ${DB_NAME} --no-http <<< \"exec(open('${path}').read())\""; then
        SEED_FAILURES+=("${label}")
        echo "  ⚠  ${label} returned non-zero — continuing (check row counts at end)"
    fi
}

# ─── main ────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════"
echo "  NRS myservice — Dev Seed Loader"
echo "  Database: ${DB_NAME}  Compose: ${COMPOSE_FILES[*]}"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "==> Stopping live odoo container so seed runs don't contend for DB lock"
docker compose "${COMPOSE_FILES[@]}" stop odoo

# Build the run set based on positional args
declare -a RUN_SET
for s in "${SEEDS_CORE[@]}"; do RUN_SET+=("$s"); done

for arg in "$@"; do
    case "$arg" in
        fleet)
            for s in "${SEEDS_FLEET[@]}"; do RUN_SET+=("$s"); done
            ;;
        *)
            echo "WARN: unknown arg '$arg' — ignoring"
            ;;
    esac
done

# Execute
for entry in "${RUN_SET[@]}"; do
    label=$(echo "$entry" | awk '{print $1" "$2" "$3" "$4}' | sed 's/  *$//')
    path=$(echo "$entry" | awk '{print $NF}')
    run_seed "$label" "$path"
done

echo ""
echo "==> Restarting live odoo container"
docker compose "${COMPOSE_FILES[@]}" up -d odoo

echo ""
if [ ${#SEED_FAILURES[@]} -gt 0 ]; then
    echo "==> Seeds with non-zero exit (may still have committed data — see row counts):"
    for f in "${SEED_FAILURES[@]}"; do
        echo "    ⚠ $f"
    done
fi

echo ""
echo "==> Row counts on key models:"
docker exec myservicenrs-db-1 psql -U odoo -d "${DB_NAME}" -c "
SELECT 'request.stage'         AS model, count(*) FROM request_stage UNION ALL
SELECT 'request.type',                    count(*) FROM request_type UNION ALL
SELECT 'request.category',                count(*) FROM request_category UNION ALL
SELECT 'generic.service.group',           count(*) FROM generic_service_group UNION ALL
SELECT 'generic.service',                 count(*) FROM generic_service UNION ALL
SELECT 'generic.location',                count(*) FROM generic_location UNION ALL
SELECT 'fleet.vehicle',                   count(*) FROM fleet_vehicle UNION ALL
SELECT 'nrs.asset',                       count(*) FROM nrs_asset;"

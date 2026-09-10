#!/usr/bin/env bash
# Entrypoint for the cadra-nrs-import Job. Reproduces NRS master data on the
# target 19 DB from source (see Dockerfile.nrs-import). Idempotent — re-running
# updates rather than duplicating (load()/external-id matching).
#
# Env (non-credential defaults in the Dockerfile; DB_USER/DB_PASSWORD from the
# cadra-db Secret, ODOO_ADMIN_PW from cadra-odoo/ODOO_ADMIN_PASSWORD):
#   ODOO_URL SOURCE_DB TARGET_DB DB_HOST DB_USER DB_PASSWORD ODOO_ADMIN_PW PACK
# ODOO_ADMIN_PW has NO default — see the refusal below.
set -euo pipefail

# The admin XML-RPC password has no default and never will have one.
#
# `ODOO_ADMIN_PW=admin` used to be an ENV line in Dockerfile.nrs-import, so
# the credential this script authenticates with shipped inside a published
# image layer — pulled by every host that runs the Job, printed by
# `docker history`, readable by anyone with registry access. That is worse
# than a literal in a source file, which at least stays where it was written.
#
# Unset now REFUSES, and the refusal names the variable, the Secret it comes
# from and the manifest that wires the two together. `set -u` alone would
# abort with "unbound variable" and a line number, which tells an operator
# that something is missing but not what or where.
if [ -z "${ODOO_ADMIN_PW:-}" ]; then
  echo "REFUSED: ODOO_ADMIN_PW is not set." >&2
  echo "  It is the Odoo *admin user* password used for XML-RPC against" >&2
  echo "  ${ODOO_URL:-the target server}, not the master password." >&2
  echo "  In the cluster it comes from the cadra-odoo Secret, key" >&2
  echo "  ODOO_ADMIN_PASSWORD, wired up by k8s/dev/71-nrs-import-job.yaml." >&2
  echo "  Create it with:" >&2
  echo "    kubectl -n cadra-dev patch secret cadra-odoo --type merge \\" >&2
  echo "      -p '{\"stringData\":{\"ODOO_ADMIN_PASSWORD\":\"<password>\"}}'" >&2
  echo "  Running locally: export ODOO_ADMIN_PW before invoking this script." >&2
  exit 78   # EX_CONFIG — configuration error, not a runtime failure
fi

echo "═══ NRS import: source=${SOURCE_DB} → target=${TARGET_DB} via ${ODOO_URL} ═══"

# 1) Export the real NRS location tree from the live 15 DB (stable external id
#    nrs_loc_<N>, hierarchy via parent_id/id, coords), parent-first for load().
echo "── [1/3] exporting ${SOURCE_DB} location tree ──"
PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${SOURCE_DB}" -tAc "
COPY (
  SELECT 'nrs_loc_'||id AS \"id\", name,
         CASE WHEN parent_id IS NOT NULL THEN 'nrs_loc_'||parent_id ELSE '' END AS \"parent_id/id\",
         COALESCE(location_type,'') AS \"location_type\",
         COALESCE(zone_code,'') AS \"zone_code\",
         COALESCE(longitude::text,'') AS \"longitude\",
         COALESCE(latitude::text,'') AS \"latitude\",
         (CASE WHEN active THEN '1' ELSE '0' END) AS \"active\"
  FROM generic_location ORDER BY parent_path
) TO STDOUT WITH CSV HEADER" > /tmp/nrs_locations_export.csv
echo "   exported $(( $(wc -l < /tmp/nrs_locations_export.csv) - 1 )) locations"

# 2) Reference bridge: import locations + asset categories + rebuild the
#    __export__.generic_location_<N>_<hash> external ids the asset CSVs use.
echo "── [2/3] location + category bridge on ${TARGET_DB} ──"
python3 /opt/cadra/scripts/migrate_nrs_locations.py \
  --url "${ODOO_URL}" --db "${TARGET_DB}" --user admin --password "${ODOO_ADMIN_PW}" \
  --locations-csv /tmp/nrs_locations_export.csv --asset-pack "${PACK}"

# 3) Employees + assets (departments → jobs → employees → ICT → fleet).
echo "── [3/3] employees + assets on ${TARGET_DB} ──"
python3 /opt/cadra/scripts/seed_nrs_assets.py \
  --url "${ODOO_URL}" --db "${TARGET_DB}" --user admin --password "${ODOO_ADMIN_PW}" \
  --ensure-fields --seed-dir "${PACK}"

echo "═══ NRS import complete ═══"

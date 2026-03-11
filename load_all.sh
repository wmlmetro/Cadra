#!/bin/bash
# ============================================================
# load_all.sh — NRS myservice Data Loader
# ============================================================
set -e

ODOO_DB="${ODOO_DB:-myservice}"
ODOO_PATH="${ODOO_PATH:-/opt/odoo}"
ODOO_CONF="${ODOO_CONF:-/etc/odoo/odoo.conf}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ODOO_BIN="${ODOO_PATH}/venv/bin/python ${ODOO_PATH}/odoo/odoo-bin"

echo ""; echo "  NRS myservice — Data Loader"
echo "  Database : ${ODOO_DB}  Repo: ${REPO_DIR}"; echo ""

run_py() {
    echo "  ▶  $1..."
    ${ODOO_BIN} shell --config="${ODOO_CONF}" --database="${ODOO_DB}" --no-http << EOF
${3:-}
exec(open('${2}').read())
EOF
    echo "  ✅  $1 done."; echo ""
}

[ "${SKIP_STRUCT:-0}" != "1" ] && run_py "ITSM Structure" "${REPO_DIR}/data/itsm_structure.py"
[ "${SKIP_LOCS:-0}"   != "1" ] && run_py "Location Skeleton" "${REPO_DIR}/data/load_locations.py"

if [ -n "${OFFICES_CSV:-}" ] && [ -f "${OFFICES_CSV}" ]; then
    run_py "Office Sites" "${REPO_DIR}/data/load_offices.py" "OFFICES_CSV='${OFFICES_CSV}'"
else
    echo "  ℹ️  Set OFFICES_CSV=/path/to/file.csv to load office sites."
fi

echo "  All done."; echo ""

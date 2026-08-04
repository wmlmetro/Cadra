#!/usr/bin/env bash
# Fetch the CRND 19.0 foundation for the Odoo 19 rebuild.
#
# The rebuild's foundation splits into three tiers by licence/availability:
#
#   1. FREE  — the public generic-addons monorepo (LGPL-3 base utilities).
#              Fetched automatically by this script.
#   2. LGPL  — generic_service / generic_resource / generic_location /
#              generic_team. LGPL-3, but the 19.0 source lives in gated CRND
#              repos. We are entitled to the source; either clone with a CRND
#              account, OR port our existing 15.0 copies (dist/<mod>) forward.
#   3. PAID  — generic_request (OPL-1, proprietary). Requires a valid CRND 19.0
#              licence. This is the ONE hard commercial dependency.
#
# crnd_wsd / crnd_service_desk are intentionally DROPPED in the rebuild.
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=crnd-19
echo "==> Fetching FREE generic-addons 19.0 base utilities into $DEST/ ..."
tmp="$(mktemp -d)"
git clone --depth 1 --branch 19.0 --single-branch \
    https://gitlab.crnd.pro/crnd-opensource/generic-addons.git "$tmp/generic-addons"
mkdir -p "$DEST"
# Copy just the modules (drop the repo's own .git so they vendor into ours).
for m in "$tmp"/generic-addons/*/; do
    name="$(basename "$m")"
    [ -f "$m/__manifest__.py" ] || continue
    rm -rf "${DEST:?}/$name"
    cp -R "$m" "$DEST/$name"
done
rm -rf "$tmp"

echo "==> FREE foundation vendored:"
ls -1 "$DEST" | sed 's/^/    /'

cat <<'NOTE'

==> STILL REQUIRED (not fetched — gated / paid):
    LGPL (get from CRND account OR port dist/<mod> 15.0 -> 19.0):
        generic_service  generic_resource  generic_location  generic_team
    PAID (needs a CRND 19.0 OPL-1 licence):
        generic_request

    Drop the licensed/ported copies into crnd-19/ alongside the free base,
    then: docker compose -f docker-compose.yml -f docker-compose.19.yml up -d
NOTE

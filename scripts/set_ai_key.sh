#!/usr/bin/env bash
#
# Place the provider key for *Identify from photo* on ONE local tenant
# (handoff 64 §1). The OWNER runs this; the key is the owner's.
#
#   scripts/set_ai_key.sh <db>            # prompts; nothing is echoed
#   scripts/set_ai_key.sh <db> --clear    # removes the key from the tenant
#
# The key is read from the terminal with echo off (or from stdin when piped,
# e.g. from a password manager), passed to the container on stdin, and
# written to `myservice_api.ai_api_key`. It never appears on a command line,
# in shell history, in a log or in the repo. Placing a key switches nothing
# on: an administrator turns `cadra.ai.identify` on in Settings → Identify
# from photo, and only once NRS has accepted in writing that photos go to
# the provider (R7 / R11).
#
# On the cluster the same parameter is mirrored by bootstrap from the
# `CADRA_AI_API_KEY` key of the `cadra-odoo` secret (one-way: empty leaves
# the stored key alone) — see docs/DEPLOYMENT.md.
set -euo pipefail

DB="${1:-}"
MODE="${2:-}"
if [[ -z "$DB" ]]; then
  echo "usage: scripts/set_ai_key.sh <db> [--clear]" >&2
  exit 2
fi
# A database name, and nothing a shell could read as anything else.
if [[ ! "$DB" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]]; then
  echo "Not a database name: $DB" >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.19.yml)

if [[ "$MODE" == "--clear" ]]; then
  KEY=""
else
  if [[ -t 0 ]]; then
    read -r -s -p "Provider key for $DB (input hidden): " KEY
    echo
  else
    read -r KEY
  fi
  KEY="${KEY//[[:space:]]/}"
  if [[ -z "$KEY" ]]; then
    echo "No key given; nothing was written." >&2
    exit 1
  fi
fi

# The key travels on stdin (first line), never as an argument; the database
# name as a positional argument, never spliced into the script.
printf '%s\n' "$KEY" | "${COMPOSE[@]}" exec -T -e PYTHONWARNINGS=ignore odoo sh -c '
read -r KEY
export CADRA_AI_KEY_IN="$KEY"
odoo shell -c /etc/odoo/odoo.conf -d "$1" --no-http --log-level=error <<PY
import os
key = os.environ.pop("CADRA_AI_KEY_IN", "")
icp = env["ir.config_parameter"].sudo()
if key:
    icp.set_param("myservice_api.ai_api_key", key)
    print("AI provider key placed on " + env.cr.dbname + " (" + str(len(key)) + " characters).")
else:
    icp.set_param("myservice_api.ai_api_key", "")
    print("AI provider key removed from " + env.cr.dbname + ".")
env.cr.commit()
PY
' sh "$DB"

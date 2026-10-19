#!/usr/bin/env bash
#
# Set the provider key for *Identify from photo* on THIS machine's server
# (handoff 65 §0a.1). The OWNER runs this; the key is the owner's.
#
#   scripts/set_ai_key.sh            # prompts; nothing is echoed
#   scripts/set_ai_key.sh --clear    # empties the key
#
# The key lives in the SERVER'S ENVIRONMENT, never in a database: this
# writes one line, `CADRA_AI_API_KEY=<key>`, into the repository's `.env`
# (replacing an existing line in place, or appending one), which compose
# hands to the Odoo container. Until handoff 65 it took a database name and
# wrote an `ir_config_parameter` row — readable by any back-office system
# administrator and carried by every backup; migration 19.0.3.36.0 deleted
# that row on every tenant. ONE key serves every tenant on the server; each
# tenant's own switch (`cadra.ai.identify`, Settings → Identify from photo,
# off by default) decides whether it is used, and only once NRS has accepted
# in writing that photos go to the provider (R7 / R11).
#
# The key is read from the terminal with echo off (or from stdin when piped,
# e.g. from a password manager). It never appears on a command line, in
# shell history, in a log or in this script's output — only its length is
# said. `.env` is untracked (handoff 04); never commit it.
#
# On the cluster the server reads the same variable from the `cadra-odoo`
# secret, into which deploy-dev syncs the GitHub repository secret
# `CADRA_AI_API_KEY` — set it there, not on the cluster (docs/DEPLOYMENT.md).
set -euo pipefail

MODE=""
for arg in "$@"; do
  case "$arg" in
    --clear) MODE="--clear" ;;
    -h|--help)
      sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      # Handoff 64's form was `set_ai_key.sh <db>`. The key is per SERVER
      # now, so a database name means nothing here — say so rather than
      # silently placing a key the caller thinks is for one tenant.
      echo "The key is set per server, not per tenant: '$arg' is ignored." >&2
      echo "Every tenant on this server will use it; each tenant's own switch" >&2
      echo "(Settings → Identify from photo) decides whether it asks." >&2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [[ "$MODE" == "--clear" ]]; then
  KEY=""
else
  if [[ -t 0 ]]; then
    read -r -s -p "Provider key for this server (input hidden): " KEY
    echo
  else
    read -r KEY || true
  fi
  KEY="${KEY//[[:space:]]/}"
  if [[ -z "$KEY" ]]; then
    echo "No key given; nothing was written." >&2
    exit 1
  fi
  # One line of `KEY=value` in a file compose parses: nothing that could end
  # the line or be read as anything else.
  if [[ ! "$KEY" =~ ^[A-Za-z0-9_.:+/=-]+$ ]]; then
    echo "That key has characters a provider key does not; nothing was written." >&2
    exit 1
  fi
fi

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
# Rewrite through a temporary file in the same directory, the key passed on
# the environment of awk (not its argv, which `ps` shows), then move it over
# `.env` — one line replaced in place, or one appended.
TMP="$(mktemp "$REPO_ROOT/.env.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP"
CADRA_AI_KEY_IN="$KEY" awk '
  BEGIN { key = ENVIRON["CADRA_AI_KEY_IN"]; done = 0 }
  /^[[:space:]]*(export[[:space:]]+)?CADRA_AI_API_KEY[[:space:]]*=/ {
    if (!done) { print "CADRA_AI_API_KEY=" key; done = 1 }
    next
  }
  { print }
  END { if (!done) print "CADRA_AI_API_KEY=" key }
' "$ENV_FILE" > "$TMP"
mv "$TMP" "$ENV_FILE"
trap - EXIT
unset KEY

if [[ "$MODE" == "--clear" ]]; then
  echo "CADRA_AI_API_KEY emptied in .env."
else
  echo "CADRA_AI_API_KEY written to .env ($(grep -E '^CADRA_AI_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\n' | wc -c | tr -d ' ') characters)."
fi
cat <<'MSG'
It takes effect when the Odoo container is recreated:

  export ODOO_DBFILTER='^%d$'
  docker compose -f docker-compose.yml -f docker-compose.19.yml up -d --force-recreate odoo

Then Settings → Identify from photo says whether the server holds a key.
Setting it switches nothing on; each tenant's switch does.
MSG

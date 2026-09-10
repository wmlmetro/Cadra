#!/usr/bin/env bash
#
# Start-up for the `prod` compose profile — the profile a CLIENT is deployed
# with. Run by docker-compose.prod.yml's `command:`.
#
# This lives in a file rather than inline in the compose YAML for one reason:
# **a shell block inside a YAML block scalar cannot be executed by a test.**
# The inline version refused a correct configuration and printed nothing,
# because `set -e` kills the script on `check … && flag=1` when the check
# passes, and that survived a careful read-through. It is the riskiest code in
# the deployment — it runs at container start on somebody's server, and a bug
# here is a client whose Cadra does not come up. tests/test_prod_entrypoint.py
# runs this file directly, with a table of values and a stubbed `odoo`.
#
# Three jobs, in order:
#   1. Refuse a credential that still holds a value this repository ships.
#   2. Build a writable config: the mounted template plus the three settings
#      that must come from the environment rather than from a committed file.
#   3. exec odoo.

set -euo pipefail

CONF_TEMPLATE="${CADRA_CONF_TEMPLATE:-/etc/odoo/odoo.conf.template}"
CONF="${CADRA_CONF:-/tmp/odoo.conf}"

# ── 1. Refuse a DEFAULT-VALUED credential ───────────────────────────────
#
# The `:?` markers in docker-compose.prod.yml already refuse a MISSING
# credential. They cannot see the other half: `.env.example` ships
# `ODOO_MASTER_PASSWORD=admin` and `POSTGRES_PASSWORD=odoo`, and the
# documented prod route is `cp .env.example .env` followed by editing it.
# Until this existed, the only thing between a client server and those two
# values was docs/DEPLOYMENT.md telling the operator to run `openssl rand` —
# advice, which means the security position rested on somebody having read it.
# That is precisely the promise a rule exists to replace.
#
# Refusing at START rather than warning is deliberate. A warning on a
# container that comes up healthy is a line in a log nobody reads, and by the
# time anybody looks the deployment is live on the internet with a published
# master password.
#
# cadra-refusable-defaults: admin odoo postgres password passwd secret changeme change-me CHANGEME test cadra example
CADRA_REFUSE=0

cadra_check() {
    # $1 is the name to print, $2 the value. An EMPTY value is not this
    # guard's business — the `:?` markers and bootstrap handle those — so it
    # passes here. The list above is the same list as the `case` below;
    # tests/test_deployment_profile.py asserts they agree, so neither can be
    # widened alone.
    case "${2:-}" in
        admin|odoo|postgres|password|passwd|secret|changeme|change-me|CHANGEME|test|cadra|example)
            echo "FATAL: $1 is still set to '$2', which is a default this repository ships." >&2
            echo "       Generate a real one and put it in .env, e.g." >&2
            echo "         $1=\$(openssl rand -base64 32)" >&2
            echo "       Refusing to start. See docs/DEPLOYMENT.md." >&2
            CADRA_REFUSE=1
            ;;
    esac
}

# Every credential is checked before any is reported, so an operator with two
# to fix learns about both on the first attempt rather than one per bring-up.
#
# PASSWORD is what the base compose calls POSTGRES_PASSWORD inside this
# container — it is the name the Odoo image entrypoint reads, and the name
# this script has to append to the config below.
cadra_check POSTGRES_PASSWORD "${PASSWORD:-}"
cadra_check ODOO_MASTER_PASSWORD "${ODOO_MASTER_PASSWORD:-}"
# CADRA_JWT_SECRET is allowed to be EMPTY — bootstrap generates one and stores
# it per database in ir.config_parameter, which is the documented flow. What
# it may not be is one of the placeholders above.
cadra_check CADRA_JWT_SECRET "${CADRA_JWT_SECRET:-}"

[ "$CADRA_REFUSE" = "0" ] || exit 1

# ── 2. Build the runtime config ─────────────────────────────────────────
#
# **`db_user` and `db_password` are appended here, and that is not optional.**
#
# The Odoo image's /entrypoint.sh injects HOST/USER/PASSWORD as `--db_user` /
# `--db_password` — but ONLY on its `--`, `odoo` and `-*` branches. A compose
# `command:` replaces CMD, not ENTRYPOINT, so the entrypoint runs with `$1`
# set to whatever the command starts with, falls through to `*) exec "$@"`,
# and appends nothing. `config/odoo.prod.conf` deliberately does not commit a
# database password, so without these two lines Odoo connects as the container
# user with no password and Postgres — which `postgres:13` initialises with
# md5 host auth whenever POSTGRES_PASSWORD is set — refuses it with
# `fe_sendauth: no password supplied`.
#
# This repository already knew: k8s/dev/10-configmap-odoo-19.yaml says in as
# many words that "the pods override the image entrypoint, so its
# HOST/USER/PASSWORD injection does not run", and
# k8s/dev/41-odoo-19-deployment.yaml appends both. The compose prod profile
# did the same conf-copy dance and appended only `admin_passwd`, so it has
# never been able to reach its own database. Nothing caught it because nothing
# has ever started it — CI runs `docker compose config`, which parses YAML.
#
# No Odoo major has an `--admin-passwd` CLI flag (checked against
# `odoo server --help` on 19.0), which is why admin_passwd goes in the file
# rather than on the command line.
cp "$CONF_TEMPLATE" "$CONF"
{
    printf '\nadmin_passwd = %s\n' "$ODOO_MASTER_PASSWORD"
    printf 'db_user = %s\n' "${USER:-odoo}"
    printf 'db_password = %s\n' "${PASSWORD:-}"
} >> "$CONF"

# ── 3. Hand over ────────────────────────────────────────────────────────
exec odoo -c "$CONF" \
    --workers="${ODOO_WORKERS:-4}" \
    --max-cron-threads="${ODOO_MAX_CRON_THREADS:-2}"

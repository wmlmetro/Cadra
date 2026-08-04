"""
Cadra bootstrap — one-shot environment setup for a fresh deployment.

Runs INSIDE an `odoo shell` session (see scripts/bootstrap.sh for the
host-side orchestrator). Idempotent: re-running on a fully-bootstrapped
stack is a no-op except for credential output.

Steps:
  1. JWT secret — set ir.config_parameter `myservice_api.jwt_secret`
     from CADRA_JWT_SECRET env var, or generate one if blank.
  2. Admin user groups — add base.user_admin to:
       - myservice_asset_register.group_asset_manager
       - myservice_security.group_security_admin
     (so API calls from the smoke-test client can read every model)
  3. API smoke-test client — create or rotate the test_client record
     (client_id from CADRA_TEST_CLIENT_ID, secret from CADRA_TEST_CLIENT_SECRET
     or generated). Scopes cover every read+write across all 4 resources
     plus integrations.
  4. Seeds — based on CADRA_SEED_PROFILE env var:
       core            = ITSM structure + Nigeria locations + 415 FIRS offices
       fleet           = above + master fleet seed (1,617 vehicles — slow)
       full            = ITSM + locations + offices v3 + master seed + NRS HQ
                         assets (1,272) + HQ location metadata + fleet taxonomy
                         + fleet→location matcher (~12-15 min total)
       full-no-master  = full minus master_seed (use when master already ran;
                         saves ~7 min of idempotent rework)
       full+geo        = full + OSM geocoding (~30 min — exceeds the 20 min
                         bootstrap Job cap; bump the wait timeout first)
       (empty)         = no seeds
     All seeds are idempotent via the get_or_create helpers in the seed
     scripts themselves.

Outputs:
  Prints a marked-up block of credentials at the end (between
  CADRA_BOOTSTRAP_BEGIN and CADRA_BOOTSTRAP_END sentinels) so the host
  orchestrator can capture them for writing to docs/api/.creds.
"""
import logging
import os
import secrets
import sys

_logger = logging.getLogger(__name__)

# The Odoo shell injects `env`, `cr`, `uid`, `openerp` into locals before
# exec'ing this file. We rely on `env` only.
# pylint: disable=undefined-variable


# ─── helpers ────────────────────────────────────────────────────────

def _say(msg, level="INFO"):
    """Stdout banner that the host-side orchestrator can grep."""
    print(f"[bootstrap:{level:>5}] {msg}", flush=True)


def _has_meaningful_secret(value):
    """Reject empty + known placeholders + too-short secrets."""
    if not value or len(value) < 16:
        return False
    placeholders = {"CHANGE_ME__MYservice_API_JWT_SECRET", "CHANGE_ME", "changeme"}
    return value not in placeholders


# ─── step 1: JWT secret ─────────────────────────────────────────────

def ensure_jwt_secret():
    """Set the JWT signing secret in ir.config_parameter.

    Source precedence:
      1. CADRA_JWT_SECRET env var (if meaningful)
      2. Existing ir.config_parameter value (if meaningful)
      3. Generate a new one (48 url-safe chars)

    Returns the secret that's now set, so the host orchestrator can
    write it back to .env.runtime for future runs.
    """
    param = env["ir.config_parameter"].sudo()
    current = param.get_param("myservice_api.jwt_secret", "")
    from_env = os.environ.get("CADRA_JWT_SECRET", "").strip()

    if _has_meaningful_secret(from_env):
        if current != from_env:
            param.set_param("myservice_api.jwt_secret", from_env)
            _say("JWT secret set from CADRA_JWT_SECRET env var")
        else:
            _say("JWT secret already matches CADRA_JWT_SECRET (no change)")
        return from_env

    if _has_meaningful_secret(current):
        _say("JWT secret already set in ir.config_parameter (preserving)")
        return current

    new_secret = secrets.token_urlsafe(48)
    param.set_param("myservice_api.jwt_secret", new_secret)
    _say("JWT secret generated and stored")
    return new_secret


# ─── step 2: admin groups ───────────────────────────────────────────

REQUIRED_ADMIN_GROUPS = [
    "myservice_asset_register.group_asset_manager",
    "myservice_security.group_security_admin",
]


def ensure_admin_groups():
    """Add base.user_admin to the operational groups our API needs."""
    admin = env.ref("base.user_admin")
    added = 0
    skipped_missing = []
    for xmlid in REQUIRED_ADMIN_GROUPS:
        try:
            group = env.ref(xmlid)
        except ValueError:
            skipped_missing.append(xmlid)
            continue
        if admin.id in group.users.ids:
            _say(f"admin already in {group.name!r}")
        else:
            group.users = [(4, admin.id)]
            added += 1
            _say(f"added admin to {group.name!r}")
    if skipped_missing:
        _say(f"groups not installed (skipped): {skipped_missing}", level="WARN")
    return added


# ─── step 3: API smoke-test client ──────────────────────────────────

ALL_SCOPES = (
    "dashboards:read "
    "assets:read assets:write "
    "locations:read locations:write "
    "requests:read requests:write "
    "integrations:write "
    "identity:read"
)


def ensure_test_client():
    """Create or rotate the smoke-test API client.

    Returns (client_id, raw_secret).
    """
    Client = env["myservice.api.client"].sudo()
    client_id = os.environ.get("CADRA_TEST_CLIENT_ID", "").strip() or "test_client"
    requested_secret = os.environ.get("CADRA_TEST_CLIENT_SECRET", "").strip()

    rec = Client.search([("client_id", "=", client_id)], limit=1)
    if not rec:
        admin = env.ref("base.user_admin")
        rec = Client.create({
            "name": "Smoke Test",
            "client_id": client_id,
            "user_id": admin.id,
            "scopes": ALL_SCOPES,
            "token_ttl_seconds": 3600,
        })
        _say(f"created API client {client_id!r}")
    else:
        # Always re-sync scopes so we never drift behind the canonical set.
        if rec.scopes != ALL_SCOPES:
            rec.scopes = ALL_SCOPES
            _say(f"updated scopes on existing client {client_id!r}")

    # Rotate the secret if:
    #   - the env var supplied a specific value and it doesn't match
    #   - no secret has ever been set on this client
    # Otherwise preserve the existing secret (idempotent).
    raw = None
    if requested_secret:
        if not rec.check_client_secret(requested_secret):
            rec.set_client_secret(requested_secret)
            _say(f"client_secret set from CADRA_TEST_CLIENT_SECRET env var")
        raw = requested_secret
    elif not rec.client_secret_hash:
        raw = rec.rotate_secret()
        _say(f"client_secret generated for {client_id!r}")
    else:
        raw = "<UNCHANGED — existing secret preserved>"

    return client_id, raw


# ─── step 3.5: outgoing mail server ────────────────────────────────

SMTP_ENCRYPTION_CHOICES = {"none", "starttls", "ssl"}


def ensure_mail_server():
    """Create or update the default outgoing mail server (ir.mail_server).

    Driven by env vars (all optional — if SMTP_HOST is blank the whole
    step is a no-op):
      SMTP_HOST         — e.g. smtp.zoho.com
      SMTP_PORT         — int, default 587
      SMTP_USER         — auth username (full email address for Zoho/Gmail)
      SMTP_PASS         — auth password / app password
      SMTP_ENCRYPTION   — one of {none, starttls, ssl}, default starttls
      SMTP_FROM_FILTER  — optional From-address filter (Odoo "from_filter")
      EMAIL_FROM        — system-wide default sender, written to
                          ir.config_parameter `mail.default.from`
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        _say("SMTP_HOST not set — skipping mail-server setup")
        return

    Mail = env["ir.mail_server"].sudo()
    encryption = os.environ.get("SMTP_ENCRYPTION", "starttls").strip().lower()
    if encryption not in SMTP_ENCRYPTION_CHOICES:
        _say(f"invalid SMTP_ENCRYPTION={encryption!r} — falling back to starttls", level="WARN")
        encryption = "starttls"

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        _say("invalid SMTP_PORT — falling back to 587", level="WARN")
        port = 587

    vals = {
        "name": "Cadra Default SMTP",
        "smtp_host": host,
        "smtp_port": port,
        "smtp_user": os.environ.get("SMTP_USER", "").strip() or False,
        "smtp_pass": os.environ.get("SMTP_PASS", "") or False,
        "smtp_encryption": encryption,
        "sequence": 10,
    }
    from_filter = os.environ.get("SMTP_FROM_FILTER", "").strip()
    if from_filter:
        vals["from_filter"] = from_filter

    rec = Mail.search([("name", "=", vals["name"])], limit=1)
    if rec:
        rec.write(vals)
        _say(f"updated ir.mail_server {rec.name!r} → {host}:{port} ({encryption})")
    else:
        Mail.create(vals)
        _say(f"created ir.mail_server {vals['name']!r} → {host}:{port} ({encryption})")

    # Default From address for system-generated mail.
    default_from = os.environ.get("EMAIL_FROM", "").strip()
    if default_from:
        env["ir.config_parameter"].sudo().set_param("mail.default.from", default_from)
        _say(f"set ir.config_parameter mail.default.from = {default_from}")


# ─── step 3.6: email relay (HTTPS bridge for DO SMTP-blocked clusters) ───

def ensure_email_relay():
    """Persist email-relay config so myservice_email_relay's override picks it up.

    Env vars:
      CADRA_EMAIL_RELAY_URL    — full POST URL of the relay
      CADRA_EMAIL_RELAY_SECRET — shared secret the relay validates

    Both must be set for the relay to take effect; otherwise the override
    in myservice_email_relay falls through to native SMTP. Setting an empty
    string explicitly clears any previously-stored values (useful when
    rotating off the relay).
    """
    ICP = env["ir.config_parameter"].sudo()
    url = os.environ.get("CADRA_EMAIL_RELAY_URL", "").strip()
    secret = os.environ.get("CADRA_EMAIL_RELAY_SECRET", "").strip()

    if url:
        ICP.set_param("cadra.email_relay_url", url)
        _say(f"set ir.config_parameter cadra.email_relay_url = {url}")
    if secret:
        ICP.set_param("cadra.email_relay_secret", secret)
        _say("set ir.config_parameter cadra.email_relay_secret = ***")

    if not url and not secret:
        _say("CADRA_EMAIL_RELAY_* not set — relay disabled, native SMTP will be used")


# ─── step 4: seeds ─────────────────────────────────────────────────

SEED_PROFILES = {
    "core": [
        ("ITSM Structure",     "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",  "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices (415)", "/mnt/extra-addons/load_offices.py"),
    ],
    "fleet": [
        ("ITSM Structure",        "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",     "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices (415)",    "/mnt/extra-addons/load_offices.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
    ],
    # Full seed = everything validated against a fresh dev DB on 2026-06-01.
    # Order matters: HQ assets depend on locations, fleet matcher depends on
    # both vehicles + offices. Uses load_offices_v3 (4-level hierarchy) over
    # the legacy v1. Geocoding (~30 min OSM run) stays opt-in via the
    # `full+geo` profile so a normal deploy isn't blocked on rate-limited
    # external calls.
    "full": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # Same as `full` but skips myservice_master_seed.py. Use this when the
    # master seed has already landed and you only need to fill in the four
    # follow-on seeds — saves ~7 min of idempotent rework on the master seed.
    "full-no-master": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    "full+geo": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Geocode Locations (OSM)",  "/mnt/extra-addons/geocode_locations.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # full-no-master + geocoding. Use on a populated DB that needs lat/lng
    # backfilled for the dashboard map without re-running the 7-min master seed.
    "full-no-master+geo": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Geocode Locations (OSM)",  "/mnt/extra-addons/geocode_locations.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # Guaranty Trust Bank demo tenant. Generic ITSM structure + GTB company
    # branding + 122 GTB branches (41 real from OpenStreetMap with live coords,
    # 81 demo-fill across the remaining states) + light bank-facilities demo
    # requests. Branches load BEFORE the company seed so its demo requests can
    # attach to real branch locations. No FIRS/NRS data.
    "gtb": [
        ("ITSM Structure",              "/mnt/extra-addons/itsm_structure.py"),
        ("GTB Branches (122)",          "/mnt/extra-addons/scripts/load_gtb_locations.py"),
        ("GTB Company + Demo Requests", "/mnt/extra-addons/scripts/gtb_seed.py"),
        ("GTB Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/gtb_data_seed.py"),
    ],
    # Jaiz Bank Plc demo tenant. Generic ITSM structure + 39 real client-supplied
    # branches + company + demo requests + full demo depth (staff/assets/fleet).
    "jaiz": [
        ("ITSM Structure",               "/mnt/extra-addons/itsm_structure.py"),
        ("Jaiz Branches (39)",           "/mnt/extra-addons/scripts/load_jaiz_locations.py"),
        ("Jaiz Company + Demo Requests",  "/mnt/extra-addons/scripts/jaiz_seed.py"),
        ("Jaiz Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/jaiz_data_seed.py"),
    ],
    # Lagos State Ministry of Health demo tenant. Generic ITSM structure + 90
    # real public health facilities (60 PHCs + 30 General hospitals) + company +
    # demo requests + full demo depth (staff w/ 30 real Medical Directors,
    # healthcare-themed assets, ambulance fleet).
    "lasg": [
        ("ITSM Structure",               "/mnt/extra-addons/itsm_structure.py"),
        ("LASG Facilities (90)",         "/mnt/extra-addons/scripts/load_lasg_locations.py"),
        ("LASG Company + Demo Requests", "/mnt/extra-addons/scripts/lasg_seed.py"),
        ("LASG Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/lasg_data_seed.py"),
    ],
}


def _resolve_seed_path(path):
    """Resolve a seed-profile path against both dev and k8s layouts.

    In dev (docker-compose), the whole repo is bind-mounted at
    /mnt/extra-addons, so scripts/ files live at /mnt/extra-addons/scripts/.
    In k8s (Dockerfile.odoo.k8s), scripts/ is copied to /opt/cadra/scripts/
    instead. Profile entries are written using the dev layout; this swap
    lets the same profile work in both environments.
    """
    if os.path.exists(path):
        return path
    alt = path.replace("/mnt/extra-addons/scripts/", "/opt/cadra/scripts/")
    if alt != path and os.path.exists(alt):
        return alt
    return None


def run_seeds():
    """Idempotent re-run of the data seed scripts.

    Each seed uses get_or_create-style logic so running on a populated DB
    is a no-op for existing rows + creates anything new. Failures in one
    seed are logged but don't abort the next.
    """
    profile = (os.environ.get("CADRA_SEED_PROFILE", "core") or "").strip()
    if not profile:
        _say("seed profile is empty — skipping all seeds")
        return
    if profile not in SEED_PROFILES:
        _say(f"unknown seed profile {profile!r}; valid: {list(SEED_PROFILES)}",
             level="WARN")
        return

    _say(f"running seed profile: {profile}")
    for label, path in SEED_PROFILES[profile]:
        resolved = _resolve_seed_path(path)
        if not resolved:
            _say(f"  skip {label} — file not present at {path}", level="WARN")
            continue
        _say(f"  → {label} ({resolved})")
        try:
            # Inject our own env into the seed's globals (the seed expects
            # `env` to be available, same as Odoo shell does for us).
            seed_globals = {"env": env}
            exec(compile(open(resolved).read(), resolved, "exec"), seed_globals)
            env.cr.commit()
            _say(f"    ✓ {label}")
        except Exception as e:
            _say(f"    ✗ {label} failed: {e}", level="ERROR")


# ─── main ──────────────────────────────────────────────────────────

def main():
    _say("Cadra bootstrap starting")
    try:
        jwt_secret = ensure_jwt_secret()
        ensure_admin_groups()
        client_id, raw_secret = ensure_test_client()
        ensure_mail_server()
        ensure_email_relay()
        env.cr.commit()
        run_seeds()
        env.cr.commit()
    except Exception:
        env.cr.rollback()
        _logger.exception("bootstrap failed")
        raise

    _say("Cadra bootstrap complete")
    # Output sentinel-wrapped credentials for the host orchestrator to capture.
    # Sentinel format is deliberately simple — grep-friendly.
    print("CADRA_BOOTSTRAP_BEGIN", flush=True)
    print(f"JWT_SECRET={jwt_secret}", flush=True)
    print(f"CLIENT_ID={client_id}", flush=True)
    print(f"CLIENT_SECRET={raw_secret}", flush=True)
    print("CADRA_BOOTSTRAP_END", flush=True)


main()

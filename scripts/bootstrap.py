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
       core   = ITSM structure + Nigeria location skeleton + 415 FIRS offices
       fleet  = above + master fleet seed (1,617 vehicles — slow)
       (empty) = no seeds
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
    "integrations:write"
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
}


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
        if not os.path.exists(path):
            _say(f"  skip {label} — file not present at {path}", level="WARN")
            continue
        _say(f"  → {label} ({path})")
        try:
            # Inject our own env into the seed's globals (the seed expects
            # `env` to be available, same as Odoo shell does for us).
            seed_globals = {"env": env}
            exec(compile(open(path).read(), path, "exec"), seed_globals)
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

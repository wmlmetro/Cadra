#!/usr/bin/env python3
"""Walk a receipt unit through Cadra's gates on a LOCAL TEST tenant.

Handoff 62 §2. Vendra's Builder cannot fire Cadra's gates: its permission
layer refused `odoo shell` as credential exploration, and it was right to
stop. This is the one supported tool instead. It walks a unit forward as the
demo personas, over HTTP, one gate at a time — the same calls, the same
seven people and the same walker as the test suites (`tests/gates.py`, so
there is one answer to "how do you walk a unit") — and prints each state.

    tests/.venv/bin/python scripts/walk_units.py --tenant test19 \\
        --asset 95682 --to registered
    tests/.venv/bin/python scripts/walk_units.py --tenant test19 \\
        --asset 95683 --reject "Not the model on the order."
    tests/.venv/bin/python scripts/walk_units.py --tenant test19 \\
        --asset 95687 --query "Which invoice covers this unit?"

`--to` takes a state a unit rests in: vfm_pending, vfm_verified,
vfm_approved, tag_issued, tagged, reg_ready (a record_only unit),
reg_submitted, registered. `--query` and `--reject` walk a `captured` unit
to IAD first, then ask or reject in the words given.

What it refuses, before it reads a file or opens a connection:

- a tenant not on the allow-list of the bench's test tenants — `staging`,
  every cluster tenant and every client's register by name;
- a host that is not `localhost` or `<tenant>.localhost`.

It never touches the cluster. Passwords come from the owner's local personas
file (`docs/api/.personas.<tenant>`, seeded by `scripts/demo_personas.sh`)
and are never printed: a persona is named by its role.
"""
import argparse
import pathlib
import sys
from urllib.parse import urlsplit

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The local test tenants a unit may be walked on. `test19` is the one
#: marked `cadra.database_class = test` with personas seeded; a tenant joins
#: this list by a ruling in a commit, never by a flag.
ALLOWED_TENANTS = ("test19",)

#: Named in the refusal, because they are the ones somebody will try.
_NOT_A_BENCH = {
    "staging": "the cluster's demonstration tenant",
    "nrs19": "a replica of NRS's real staff register",
    "cadra19": "ruled a client tenant (2026-09-16)",
    "jaizbankplc": "a replica of a live client's register",
    "nrs": "a client replica", "lasg": "a client replica",
    "gtb": "a client replica", "gtb19": "not yet marked a test tenant",
}

#: The persona whose token reads the unit between gates. The storekeeper is
#: an Asset User, and every Asset User holds `candidates:read`.
READER = "storekeeper"


def refusal(tenant, origin):
    """The sentence refusing this target, or None. Pure: no file, no
    network — so a refusal is said before anything is touched."""
    if tenant not in ALLOWED_TENANTS:
        why = _NOT_A_BENCH.get(tenant, "not on the bench's allow-list")
        return (f"Refused: {tenant!r} is not a local test tenant ({why}). "
                f"This script walks units only on {', '.join(ALLOWED_TENANTS)}"
                " and never contacts the cluster.")
    parts = urlsplit(origin)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return f"Refused: {origin!r} is not an http(s) origin."
    if host not in ("localhost", f"{tenant}.localhost"):
        if host.endswith(".localhost"):
            return (f"Refused: {origin!r} is another tenant's host; "
                    f"--tenant {tenant} is served at {tenant}.localhost.")
        return (f"Refused: {origin!r} is not this machine. This script "
                "walks units only on the local bench (localhost or "
                "<tenant>.localhost) and never touches the cluster.")
    return None


class PersonaClient:
    """The suites' `client` shape (`.base`, `.get`, `.post`, `.patch`),
    acting as one persona — `tests/gates.py` reads the unit through it."""

    def __init__(self, base, key, gates):
        self.base = base
        self._key = key
        self._gates = gates

    def _call(self, method, path, **kw):
        import requests
        url = path if path.startswith("http") else self.base + path
        headers = {"Authorization":
                   f"Bearer {self._gates._token(self, self._key)}",
                   "Accept": "application/json"}
        return requests.request(method, url, headers=headers, timeout=60,
                                **kw)

    def get(self, path, **kw):
        return self._call("GET", path, **kw)

    def post(self, path, **kw):
        return self._call("POST", path, **kw)

    def patch(self, path, **kw):
        return self._call("PATCH", path, **kw)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Walk a receipt unit through Cadra's gates on a local "
                    "test tenant, as the demo personas.")
    p.add_argument("--tenant", required=True,
                   help="the database, e.g. test19")
    p.add_argument("--asset", required=True, type=int, help="the asset id")
    act = p.add_mutually_exclusive_group(required=True)
    act.add_argument("--to", help="the state to walk the unit to")
    act.add_argument("--reject", metavar="REASON",
                     help="Internal Audit rejects the unit, in these words")
    act.add_argument("--query", metavar="QUESTION",
                     help="Internal Audit queries the unit, in these words")
    p.add_argument("--origin",
                   help="default http://<tenant>.localhost:8069")
    args = p.parse_args(argv)
    origin = (args.origin or f"http://{args.tenant}.localhost:8069").rstrip("/")

    refused = refusal(args.tenant, origin)
    if refused:
        print(refused, file=sys.stderr)
        return 2
    for words, flag in ((args.reject, "--reject"), (args.query, "--query")):
        if words is not None and not words.strip():
            print(f"Refused: {flag} needs the words — say why.",
                  file=sys.stderr)
            return 2

    sys.path.insert(0, str(REPO_ROOT / "tests"))
    import gates  # noqa: E402 — the suites' walker, after the refusals

    client = PersonaClient(origin, READER, gates)
    try:
        r = client.get(f"/api/v1/assets/{args.asset}")
        if r.status_code != 200:
            print(f"asset {args.asset} on {args.tenant}: HTTP "
                  f"{r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        asset = r.json()["data"]
        print(f"{args.tenant} asset {asset['id']} {asset.get('asset_code')} "
              f"({asset.get('identification_mode') or 'serial'}): "
              f"{asset.get('register_state')}")

        def step(frm, action, key, after):
            print(f"  {frm} -> {after.get('register_state')}   "
                  f"[{action}, as {key}]")

        if args.reject is not None:
            asset = gates.reject(client, asset, args.reject.strip(), step)
        elif args.query is not None:
            asset = gates.query(client, asset, args.query.strip(), step)
        else:
            asset = gates.walk_to(client, asset, args.to, step)
    except AssertionError as e:   # GateWalkError, and the walker's checks
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    waiting = (asset.get("gates") or {}).get("waiting_on")
    print(f"now: {asset.get('register_state')}"
          + (f", waiting on {waiting}" if waiting else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

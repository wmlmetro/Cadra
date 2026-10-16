"""`scripts/walk_units.py` — handoff 62 §2.

The one supported way to walk a unit from outside the suites. What is held
here: it refuses `staging`, every client replica and any non-local host
BEFORE it reads a file or opens a connection; on the bench it walks a unit
as the personas, through the suites' own walker; and it never prints a
password. Run as a subprocess, so the suite's own `gates` module is not
shared with it. No skip in either switch state: with the gates off the
walk is refused in words, and that is asserted instead.
"""
import pathlib
import subprocess
import sys
from urllib.parse import urlsplit

import pytest

from .gates import receive, receipt_gated

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "walk_units.py"
sys.path.insert(0, str(REPO / "scripts"))
import walk_units  # noqa: E402


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("tenant", ["staging", "nrs19", "jaizbankplc",
                                    "cadra19", "anything"])
def test_a_tenant_off_the_bench_is_refused_by_name(tenant):
    said = walk_units.refusal(tenant, f"http://{tenant}.localhost:8069")
    assert said and said.startswith(f"Refused: {tenant!r} is not a local "
                                    "test tenant"), said


@pytest.mark.parametrize("origin", [
    "https://staging.cadra.ng", "http://10.0.0.5:8069",
    "http://test19.cadra.ng", "http://nrs19.localhost:8069",
    "ftp://test19.localhost"])
def test_a_host_off_this_machine_is_refused(origin):
    said = walk_units.refusal("test19", origin)
    assert said and said.startswith("Refused:"), said


def test_the_bench_is_accepted():
    assert walk_units.refusal("test19", "http://test19.localhost:8069") is None


def test_a_bare_localhost_is_refused():
    """It names no tenant (verification pass, 62)."""
    said = walk_units.refusal("test19", "http://localhost:8069")
    assert said and "names no tenant" in said, said


def test_a_refusal_touches_nothing():
    """`staging` is refused with exit 2 before the personas file is read or
    the walker imported — the cluster's own personas file
    (`.personas.cluster.staging`) is never opened."""
    out = _run("--tenant", "staging", "--asset", "1", "--to", "registered")
    assert out.returncode == 2
    assert "the cluster's demonstration tenant" in out.stderr
    assert out.stdout == ""


def test_it_walks_as_the_personas_and_prints_no_password(client, api_base):
    tenant = urlsplit(api_base).hostname.split(".")[0]
    unit = receive(client, name="walk_units probe")
    out = _run("--tenant", tenant, "--origin", api_base,
               "--asset", str(unit["id"]), "--to", "vfm_verified")
    personas = REPO / "docs" / "api" / f".personas.{tenant}"
    if tenant not in walk_units.ALLOWED_TENANTS:
        assert out.returncode == 2 and "Refused:" in out.stderr, out.stderr
        return
    passwords = [line.split()[2] for line in personas.read_text().splitlines()
                 if not line.startswith("#") and len(line.split()) == 3]
    assert passwords, "the personas file has no passwords to check against"
    for secret in passwords:
        assert secret not in out.stdout + out.stderr
    if receipt_gated(client):
        assert out.returncode == 0, out.stderr
        assert "captured -> vfm_pending   [submit, as storekeeper]" \
            in out.stdout
        assert "vfm_pending -> vfm_verified   [verify, as iad_officer]" \
            in out.stdout
        state = client.get(f"/api/v1/assets/{unit['id']}").json()["data"]
        assert state["register_state"] == "vfm_verified"
    else:
        # Gates off: the unit was born registered, and a walk only goes
        # forward — said, not attempted.
        assert out.returncode == 1, out.stdout + out.stderr
        assert "already at 'registered', past 'vfm_verified'" in out.stderr

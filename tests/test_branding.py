"""Tenant branding settings.

One static SPA bundle serves every tenant and fetches GET /api/v1/brand per
host at startup, so these values change what a customer sees without a rebuild
or a deploy. Writes are admin-scoped for that reason.

Every test restores what it changed — branding is visible to every user on the
tenant, not just the one running the suite.
"""
import pytest

from .conftest import assert_envelope_ok


@pytest.fixture(scope="module")
def original(client):
    return assert_envelope_ok(client.get("/api/v1/settings/branding"))["data"]


def test_get_branding_shape(client, capture):
    r = client.get("/api/v1/settings/branding")
    capture("settings/branding_get", r)
    d = assert_envelope_ok(r)["data"]
    for key in ("name", "short_name", "primary", "primary_dark", "logo"):
        assert key in d, f"missing `{key}`"
    assert d["name"], "a tenant always has a name"


def test_colour_change_round_trips_to_the_public_endpoint(
        client, admin_scope, original, capture):
    """The public /api/v1/brand is what the SPA actually reads, so a settings
    write that does not reach it would be invisible to users."""
    try:
        r = client.patch("/api/v1/settings/branding",
                         json={"primary": "#7b1fa2", "short_name": "ZZTEST"})
        capture("settings/branding_patch", r)
        d = assert_envelope_ok(r)["data"]
        # Normalised to upper case on the way in.
        assert d["primary"] == "#7B1FA2"
        assert d["short_name"] == "ZZTEST"

        # /api/v1/brand is deliberately NOT the standard envelope: it is
        # public, cached and hand-built, returning a bare {"data": ...} with no
        # `meta`. Parse it directly rather than through assert_envelope_ok.
        pub = client.get("/api/v1/brand")
        assert pub.status_code == 200
        public = pub.json()["data"]
        assert public["primary"] == "#7B1FA2"
        assert public["short_name"] == "ZZTEST"
    finally:
        client.patch("/api/v1/settings/branding", json={
            "primary": original["primary"],
            "short_name": original["short_name"],
        })


def test_renaming_the_tenant_round_trips(client, admin_scope, original):
    try:
        d = assert_envelope_ok(client.patch(
            "/api/v1/settings/branding",
            json={"name": "ZZ Test Tenant"}))["data"]
        assert d["name"] == "ZZ Test Tenant"
    finally:
        client.patch("/api/v1/settings/branding", json={"name": original["name"]})


@pytest.mark.parametrize("colour", ["blue", "#12345", "#GGGGGG", "004080"])
def test_colours_must_be_six_digit_hex(client, admin_scope, colour):
    r = client.patch("/api/v1/settings/branding", json={"primary": colour})
    assert r.status_code == 400, f"{colour!r} should be rejected"


def test_logo_must_be_an_image_data_uri(client, admin_scope, capture):
    """A logo is injected into the page, so anything that is not an image is a
    script-injection vector rather than a bad-looking mark."""
    r = client.patch("/api/v1/settings/branding",
                     json={"logo": "javascript:alert(1)"})
    capture("settings/branding_bad_logo", r)
    assert r.status_code == 400
    assert "allowed" in r.json()["error"]["details"]


def test_oversized_logo_is_rejected(client, admin_scope):
    """It rides in every page load, so the cap is a performance guard."""
    huge = "data:image/png;base64," + ("A" * 300_000)
    r = client.patch("/api/v1/settings/branding", json={"logo": huge})
    assert r.status_code == 400
    assert r.json()["error"]["details"]["max_chars"] > 0


def test_blank_name_is_rejected(client, admin_scope):
    r = client.patch("/api/v1/settings/branding", json={"name": "   "})
    assert r.status_code == 400


def test_unknown_fields_are_rejected(client, admin_scope):
    r = client.patch("/api/v1/settings/branding", json={"favourite_colour": "red"})
    assert r.status_code == 400
    assert "writable" in r.json()["error"]["details"]

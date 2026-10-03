"""The sender address, on the screen where the brand is set. Handoff 45 H.6.

Invitations and password resets are sent FROM the company record's email
(`res.users._action_reset_password` in `myservice_api/models/invitation.py`
reads `company_id.email_formatted`). Until now that address could only be set
in the back office, so whoever stood a tenant up never met it. It is now
`sender_email` on `GET`/`PATCH /api/v1/settings/branding`, stored on the
company record — the field the letter reads — not as a parameter beside it.

Every test restores what it changed: the address is what every letter on the
tenant is sent from, not something only this suite sees.
"""
import pytest

from .conftest import assert_envelope_err, assert_envelope_ok

PATH = "/api/v1/settings/branding"
PROBE = "pytest-sender@example.org"


def _read(client):
    return assert_envelope_ok(client.get(PATH))["data"]


@pytest.fixture(scope="module")
def original_sender(client):
    """The address before this module ran, put back after it, and checked."""
    before = _read(client)["sender_email"]
    yield before
    r = client.patch(PATH, json={"sender_email": before})
    assert r.status_code == 200, f"could not restore the sender address: {r.text[:300]}"
    assert _read(client)["sender_email"] == before


def test_get_publishes_the_sender_address(client):
    d = _read(client)
    assert "sender_email" in d, "GET /settings/branding has no `sender_email`"
    assert isinstance(d["sender_email"], str), (
        "`sender_email` is a string, \"\" when the company has none — "
        f"got {d['sender_email']!r}")


def test_a_valid_address_is_stored_and_read_back(client, admin_scope, original_sender):
    assert original_sender != PROBE
    r = client.patch(PATH, json={"sender_email": PROBE})
    assert assert_envelope_ok(r)["data"]["sender_email"] == PROBE
    assert _read(client)["sender_email"] == PROBE, "the PATCH answered but the GET disagrees"


def test_surrounding_spaces_are_not_part_of_the_address(client, admin_scope, original_sender):
    r = client.patch(PATH, json={"sender_email": f"  {PROBE}  "})
    assert assert_envelope_ok(r)["data"]["sender_email"] == PROBE


@pytest.mark.parametrize("bad", [
    "not-an-address",
    "Assets Team <assets@example.org>",   # one bare address, no display name
    "a@example.org, b@example.org",       # one address, not a list
    "assets @example.org",
    "assets@localhost",
    "x" * 250 + "@example.org",           # longer than any server accepts
    42,
])
def test_an_address_that_is_not_one_is_refused_in_words(client, admin_scope, original_sender, bad):
    client.patch(PATH, json={"sender_email": PROBE})
    r = client.patch(PATH, json={"sender_email": bad})
    body = assert_envelope_err(r, 400)
    message = body["error"]["message"]
    assert "sender_email" in message and "email address" in message, message
    assert _read(client)["sender_email"] == PROBE, f"{bad!r} was refused and still written"


def test_a_refused_address_writes_nothing_sent_beside_it(client, admin_scope, original_sender):
    """Every refusal before any write — the rule `test_branding.py` holds for
    the name, held for the new key too. The probe colour is one nobody would
    choose, so "unchanged" cannot be satisfied by coincidence."""
    before = _read(client)
    probe_colour = "#0A1B2D"
    assert before["primary"].upper() != probe_colour
    try:
        r = client.patch(PATH, json={"primary": probe_colour,
                                     "sender_email": "not-an-address"})
        assert r.status_code == 400
        after = _read(client)
        assert after["primary"] == before["primary"], (
            "a 400 for the sender address still wrote the colour sent beside it")
        assert after["sender_email"] == before["sender_email"]
    finally:
        client.patch(PATH, json={"primary": before["primary"]})


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_the_address_can_be_cleared(client, admin_scope, original_sender, empty):
    client.patch(PATH, json={"sender_email": PROBE})
    r = client.patch(PATH, json={"sender_email": empty})
    assert assert_envelope_ok(r)["data"]["sender_email"] == ""
    assert _read(client)["sender_email"] == ""


def test_the_screen_saving_every_key_unchanged_is_accepted(client, admin_scope, original_sender):
    """The Branding screen PATCHes back every key it was given. With the new
    key in the GET, that whole object must still be accepted as it stands."""
    client.patch(PATH, json={"sender_email": PROBE})
    current = _read(client)
    r = client.patch(PATH, json=current)
    assert assert_envelope_ok(r)["data"] == current


def test_the_refusal_of_an_unknown_key_names_the_new_one_as_writable(client, admin_scope):
    r = client.patch(PATH, json={"sender": PROBE})
    body = assert_envelope_err(r, 400)
    assert "sender_email" in body["error"]["details"]["writable"]

"""4 barcode endpoints + /tags/lookup — and, since handoff 38, the serial.

THE SERIAL LOOKUP
-----------------
NRS said, on 30 September, that scanning is one of the two things they care
most about; we had told them in the room that scanning a laptop's serial
number shows its details immediately. It did not: `lookup_tag` searched tag
number and asset code only, so the serial of a TAGGED asset found nothing —
while the published parameter description on both `/api/v1` routes promised
*"Tag, asset code, or serial number"*. The tests below are that promise,
asserted:

  * precedence is tag number, then asset code, then serial number, each an
    exact match, so a scanned tag never loses to a serial that reads the
    same — proved by making one that does;
  * the serial is matched after the query is stripped and without regard to
    case, so a scanner's trailing space still finds it;
  * `matched_by` says which field matched, every time;
  * a serial on more than one asset is a 404 that SAYS so, never a silent
    first pick.

What this suite CANNOT express is the serial of an asset with no tag at all:
`POST /api/v1/assets` always mints one (`nrs.asset.create`), and neither
`tag_source` nor `asset_tag` is in `_WRITABLE_FIELDS`. That case is a named
skip below rather than a test that passes on the wrong branch. The nearest
reachable case — an asset whose only tag is awaiting replacement, which has
no ACTIVE tag — is covered in `tests/test_tag_replacement.py`.
"""
import uuid

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok


def test_kpis(client, capture):
    r = client.get("/api/v1/barcode/kpis")
    capture("barcode/kpis", r)
    assert_envelope_ok(r)


# The FM domain values are published API surface — `/barcode/lookup` answers
# with the human label, and this is the mapping it must resolve them through
# (nrs.asset.category.domain). Hard-coded rather than read back from the API
# so that a lookup echoing the raw key cannot agree with itself.
DOMAIN_LABELS = {
    "building":  "Building Services",
    "plant":     "Plant & Machinery",
    "plumbing":  "Plumbing & Drainage",
    "fleet":     "Fleet",
    "security":  "Security & Safety",
    "it":        "IT & Communications",
    "furniture": "Furniture & Fittings",
    "other":     "Other",
}


def _asset_with_an_fm_domain(client):
    """Create an asset whose category carries an FM domain.

    The bug below only fired when `asset.domain` was truthy — the old code
    guarded the `dict()` call with `if asset.domain else ''`. An asset in a
    domainless category therefore exercised none of it, so the test has to
    pick its category deliberately and then say out loud that it got one.
    """
    body = assert_envelope_ok(client.get("/api/v1/asset-categories",
                                         params={"limit": 200}))
    category = next((c for c in body["data"] if c.get("domain")), None)
    assert category is not None, (
        "no asset category on this tenant carries an FM domain, so the "
        "lookup path this test exists to cover cannot be reached. Seed one "
        "rather than letting the test pass on the branch that never broke."
    )

    asset = gates.new_registered_asset(
        client, name=f"pytest-barcode-{uuid.uuid4().hex[:8]}",
        category_id=category["id"])
    assert asset["domain"], (
        f"asset was created in category {category['id']} "
        f"({category['name']}, domain {category['domain']!r}) but came back "
        "with an empty `domain` — without it this test exercises the branch "
        "that always worked and proves nothing"
    )
    return asset


def test_lookup_empty_query(client, capture):
    """No query is a negative answer, not a server fault.

    This used to be xfailed against the `dict(<callable>)` TypeError described
    in test_lookup_with_query — wrongly: `lookup_tag` returns
    `{'found': False, ...}` before it touches any Selection field, so the
    empty-query path never reached that bug and never produced a 500. What it
    actually does, and must keep doing, is come back through
    `_delegate_failure` as an enveloped 404: a scanner pointed at nothing has
    not found a fault worth retrying.
    """
    r = client.get("/api/v1/barcode/lookup")
    capture("barcode/lookup_empty", r)
    body = assert_envelope_err(r, 404, "not_found")
    assert body["error"]["details"]["query"] == "", (
        "the error must echo the query it could not resolve"
    )


def test_lookup_with_query(client, capture):
    """Look up an asset by its tag — and get the domain LABEL back.

    This was xfailed on a real 500: `lookup_tag` did
    `dict(asset._fields['domain'].selection)`, and `nrs.asset.domain` is
    `related='category_id.domain'`, so Odoo had filled `.selection` with a
    callable and `dict()` over it raised TypeError. Every asset the lookup
    actually found in a category with an FM domain — which is most of the
    register — answered 500. It is fixed by resolving the label through
    `fields_get`, which does not care how the field was declared.

    The label, not the key, is the assertion that matters: returning `"it"`
    where `"IT & Communications"` belongs would be a green 200 and a barcode
    station showing raw enum keys to a field team.
    """
    asset = _asset_with_an_fm_domain(client)

    r = client.get("/api/v1/barcode/lookup", params={"query": asset["tag"]})
    capture("barcode/lookup_query", r)
    data = assert_envelope_ok(r)["data"]

    assert data["found"] is True, f"lookup did not find {asset['tag']!r}: {data}"
    for key in ("tag_id", "tag_number", "tag_state", "tag_date",
                "asset_id", "asset_name", "asset_code", "category", "domain",
                "location", "custodian", "condition", "state",
                "last_service_date", "next_service_date", "sap_asset_number",
                "import_source",
                # handoff 38 — additive
                "matched_by", "tagged", "serial_number"):
        assert key in data, f"`{key}` missing from the lookup payload"

    assert data["asset_id"] == asset["id"]
    assert data["tag_number"] == asset["tag"]
    assert data["domain"] == DOMAIN_LABELS[asset["domain"]], (
        f"lookup returned domain {data['domain']!r} for the raw value "
        f"{asset['domain']!r}; the station renders this straight to a field "
        f"team, so it must be {DOMAIN_LABELS[asset['domain']]!r}"
    )
    # `condition` and `state` go through the same resolver. They are literal
    # Selections and never broke, but an empty string here would mean the
    # helper had started swallowing failures instead of raising them.
    assert data["condition"] and data["state"]


def test_recent_tags(client, capture):
    r = client.get("/api/v1/barcode/recent-tags", params={"limit": 5})
    capture("barcode/recent_tags", r)
    assert_envelope_ok(r)


def test_print_url(client, test_asset, capture):
    """Generate a tag print URL, from the LABEL id — not the asset id.

    This test used to pass `test_asset["id"]`, an asset id, into a parameter
    the endpoint documents as an `nrs.asset.tag.label` id. It went green only
    when some unrelated label happened to carry that same number: run this
    file on its own and it answered `404 Tag not found`. That is the id-space
    collision in miniature, and it is why `data.tagging.label_id` now exists
    — a caller with an asset payload had nothing else to reach for.

    The URL comes back carrying the ASSET id, because the four label reports
    are registered on `nrs.asset`. So the id going in and the id coming out
    are deliberately different, and neither may be substituted for the other.
    """
    label_id = test_asset["tagging"]["label_id"]
    assert label_id, (
        "the test asset carries no tag label, so this test would be checking "
        "nothing — nrs.asset.create is supposed to mint one"
    )
    r = client.get("/api/v1/barcode/print-url", params={
        "tag_id": label_id,
        "size": "medium",
    })
    capture("barcode/print_url", r)
    body = assert_envelope_ok(r)
    assert body["data"]["url"].endswith("/%d" % test_asset["id"])


def test_tags_lookup(client, test_asset, capture):
    """GET /api/v1/tags/lookup — public-style tag lookup, JWT-protected."""
    r = client.get("/api/v1/tags/lookup", params={"query": test_asset["tag"]})
    capture("barcode/tags_lookup", r)
    assert_envelope_ok(r)


# ─── the serial lookup (handoff 38) ──────────────────────────────────

def _serial():
    """A serial nobody else has. Upper-case with a hyphen, which is the shape
    of a real one and keeps the case-insensitivity test meaningful."""
    return "PYT-" + uuid.uuid4().hex[:10].upper()


def _asset_with_serial(client, label, serial, **extra):
    """A tagged asset of this test's own carrying `serial`. Every asset the
    API creates is tagged — see the module docstring. With the receipt
    gates on (handoff 58) it is walked onto the register by
    `tests/gates.py`, the label affixed on the way."""
    asset = gates.new_registered_asset(
        client, name=f"pytest-barcode-{label}-{uuid.uuid4().hex[:8]}",
        category_id=1, serial_number=serial, **extra)
    assert asset["serial_number"] == serial, (
        "the serial sent was not the serial saved — nothing below means "
        "anything if the fixture does not carry what it claims")
    assert asset["tag"] and asset["tagging"]["label_id"], (
        "nrs.asset.create is supposed to mint a tag; without one the "
        "precedence tests below have nothing to beat")
    return asset


def _lookup(client, query):
    return client.get("/api/v1/barcode/lookup", params={"query": query})


def test_lookup_by_tag_says_it_matched_the_tag(client, capture):
    """`matched_by` is the key the screen reads to say *found by …*."""
    serial = _serial()
    asset = _asset_with_serial(client, "by-tag", serial)
    r = _lookup(client, asset["tag"])
    capture("barcode/lookup_by_tag", r)
    data = assert_envelope_ok(r)["data"]
    assert data["asset_id"] == asset["id"]
    assert data["matched_by"] == "tag_number"
    assert data["tagged"] is True
    assert data["tag_id"] == asset["tagging"]["label_id"]
    assert data["serial_number"] == serial


def test_lookup_by_asset_code_says_so(client, capture):
    serial = _serial()
    asset = _asset_with_serial(client, "by-code", serial)
    r = _lookup(client, asset["asset_code"])
    capture("barcode/lookup_by_asset_code", r)
    data = assert_envelope_ok(r)["data"]
    assert data["asset_id"] == asset["id"]
    # Handoff 58: a label issued through the receipt gates is numbered WITH
    # the asset code, so the code is also the tag number, and the tag is
    # tried first. The code still finds the asset; it says it matched the
    # tag, because it did.
    assert data["matched_by"] == (
        "tag_number" if asset["tag"] == asset["asset_code"] else "asset_code")
    assert data["tagged"] is True
    assert data["tag_number"] == asset["tag"]


def test_lookup_by_the_serial_of_a_tagged_asset(client, capture):
    """THE case from the meeting: an auditor scans the serial of a laptop
    that is already tagged. Before handoff 38 this was a 404."""
    serial = _serial()
    asset = _asset_with_serial(client, "by-serial", serial)
    r = _lookup(client, serial)
    capture("barcode/lookup_by_serial", r)
    data = assert_envelope_ok(r)["data"]
    assert data["found"] is True
    assert data["asset_id"] == asset["id"]
    assert data["matched_by"] == "serial_number"
    assert data["serial_number"] == serial
    # Found by serial, the payload still carries the ACTIVE tag — the
    # station can print or replace it from here.
    assert data["tagged"] is True
    assert data["tag_id"] == asset["tagging"]["label_id"]
    assert data["tag_number"] == asset["tag"]
    assert data["tag_state"] == "active"


@pytest.mark.parametrize("spelling", [
    "{serial} ",          # the trailing space a scanner sends
    " {serial}",
    "{serial}\n",         # a scanner configured to send Enter
    "{serial}",
])
def test_a_scanner_s_whitespace_still_finds_the_serial(client, spelling):
    """The query is stripped. Stored serials carry no padding (measured 0 of
    11,704 with a serial across the eight local tenants, report 38), so stripping the QUERY is
    the whole rule; internal whitespace stays significant."""
    serial = _serial()
    asset = _asset_with_serial(client, "whitespace", serial)
    data = assert_envelope_ok(
        _lookup(client, spelling.format(serial=serial)))["data"]
    assert data["asset_id"] == asset["id"]
    assert data["matched_by"] == "serial_number"


def test_the_serial_match_ignores_case(client):
    serial = _serial()
    asset = _asset_with_serial(client, "case", serial)
    data = assert_envelope_ok(_lookup(client, serial.lower()))["data"]
    assert data["asset_id"] == asset["id"]
    assert data["matched_by"] == "serial_number"


def test_the_serial_match_is_exact_not_partial(client):
    """A prefix of a serial is not that serial. The untagged picker searches
    serials with `ilike`; the scan box must not, or scanning `PROBOOK` would
    find whichever of 94 laptops sorts first."""
    serial = _serial()
    _asset_with_serial(client, "exact", serial)
    r = _lookup(client, serial[:-3])
    body = assert_envelope_err(r, 404, "not_found")
    assert body["error"]["details"]["query"] == serial[:-3]


def test_a_tag_number_beats_a_serial_that_reads_the_same(client, capture):
    """Precedence, proved by building the collision.

    Measured across the eight local tenants on 2026-10-01 there were no such
    collisions (report 38), so this is a rule about determinism rather than
    about data — which is exactly why it has to be proved by making one: a
    rule nobody can observe is a rule nobody notices breaking.
    """
    first = _asset_with_serial(client, "precedence-tagged", _serial())
    # A second asset whose SERIAL is the first asset's TAG NUMBER.
    decoy = _asset_with_serial(client, "precedence-decoy", first["tag"])
    assert decoy["serial_number"] == first["tag"]

    r = _lookup(client, first["tag"])
    capture("barcode/lookup_tag_beats_serial", r)
    data = assert_envelope_ok(r)["data"]
    assert data["asset_id"] == first["id"], (
        "a scanned TAG resolved to the asset whose serial happens to read "
        "the same — the tag must win, every time")
    assert data["matched_by"] == "tag_number"


def test_an_asset_code_beats_a_serial_that_reads_the_same(client):
    first = _asset_with_serial(client, "code-precedence", _serial())
    decoy = _asset_with_serial(client, "code-decoy", first["asset_code"])
    assert decoy["serial_number"] == first["asset_code"]
    data = assert_envelope_ok(_lookup(client, first["asset_code"]))["data"]
    assert data["asset_id"] == first["id"]
    # Gated, the code IS the tag number (handoff 58), which wins before the
    # code is even tried — the serial loses either way.
    assert data["matched_by"] == (
        "tag_number" if first["tag"] == first["asset_code"] else "asset_code")


def test_a_serial_on_two_assets_is_a_miss_that_says_so(client, capture):
    """Never a silent first pick.

    `nrs19` has 1,291 serial values on more than one asset — model names
    typed where a serial should go (`PROBOOK` on 94). Resolving one of those
    to whichever row sorts first would show an auditor the WRONG asset with
    a green tick on it, which is worse than showing nothing.
    """
    serial = _serial()
    a = _asset_with_serial(client, "ambiguous-a", serial)
    if gates.receipt_gated(client):
        # A gated receipt refuses a serial already in Cadra (Section 12,
        # handoff 58), so the duplicate this test needs cannot be RECEIVED
        # — it is the legacy kind (`nrs19`'s 1,291), and is written here the
        # one way a register asset's serial still changes: a PATCH.
        b = _asset_with_serial(client, "ambiguous-b", _serial())
        b = assert_envelope_ok(client.patch(
            f"/api/v1/assets/{b['id']}",
            json={"serial_number": serial}))["data"]
        assert b["serial_number"] == serial
    else:
        b = _asset_with_serial(client, "ambiguous-b", serial)
    assert a["id"] != b["id"]

    r = _lookup(client, serial)
    capture("barcode/lookup_ambiguous_serial", r)
    body = assert_envelope_err(r, 404, "not_found")
    details = body["error"]["details"]
    assert details["query"] == serial
    assert details["ambiguous"] is True
    assert details["matched_by"] == "serial_number"
    assert details["matches"] == 2, details
    assert "on 2 assets" in body["error"]["message"], (
        "the message must say how many, so a person at the scanner knows "
        "to scan the tag instead")

    # The same serial through the public-style twin: the same answer.
    twin = assert_envelope_err(
        client.get("/api/v1/tags/lookup", params={"query": serial}),
        404, "not_found")["error"]["details"]
    assert twin["ambiguous"] is True
    assert twin["matches"] == 2


def test_a_serial_nobody_has_is_a_plain_miss(client):
    """Not ambiguous, not found: the two misses are told apart by the
    PRESENCE of `ambiguous`, so a screen can branch on it."""
    body = assert_envelope_err(_lookup(client, _serial()), 404, "not_found")
    details = body["error"]["details"]
    assert "ambiguous" not in details
    assert "matches" not in details


def test_lookup_by_the_serial_of_an_untagged_asset(client):
    """NOT EXPRESSIBLE over the API, and said rather than faked.

    An asset with no tag at all is the second of the four lookups the
    handoff asks for. `POST /api/v1/assets` cannot create one:
    `nrs.asset.create` mints a tag unless `tag_source` is not `auto` or
    `asset_tag` is given, and neither key is in `_WRITABLE_FIELDS` (both are
    deliberately absent — tags are minted by Cadra, never typed). There is
    no route that scraps a tag without minting another: a replacement
    approved through `POST /tags/<id>/approve-replacement` mints the next
    number in the same act.

    The reachable neighbour — an asset whose only tag is PENDING, which has
    no active tag and answers `tagged: false` with the pending tag's block —
    is asserted in `tests/test_tag_replacement.py`. This one needs a row
    created outside the API, and the browser pass in report 38 does that.
    """
    pytest.skip(
        "the API cannot create an asset without a tag: `tag_source` and "
        "`asset_tag` are not in `_WRITABLE_FIELDS` and every "
        "`POST /api/v1/assets` mints one. The untagged-serial lookup is "
        "proved by the browser pass against a row created in Odoo.")


def test_tags_lookup_by_serial_through_the_public_style_twin(client, capture):
    """`/tags/lookup` resolves the same way and says what it matched. It
    publishes no ids — it never has — so the asset is identified by code."""
    serial = _serial()
    asset = _asset_with_serial(client, "twin", serial)
    r = client.get("/api/v1/tags/lookup", params={"query": serial + " "})
    capture("barcode/tags_lookup_by_serial", r)
    data = assert_envelope_ok(r)["data"]
    assert data["found"] is True
    assert data["matched_by"] == "serial_number"
    assert data["asset_code"] == asset["asset_code"]
    assert data["serial_number"] == serial
    assert data["tagged"] is True
    assert data["tag_number"] == asset["tag"]
    assert "tag_id" not in data and "asset_id" not in data, (
        "the public-style twin has never published an id; if it starts to, "
        "say so in the changelog rather than letting this test go quiet")

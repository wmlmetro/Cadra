"""4 barcode endpoints + /tags/lookup."""
import uuid

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

    r = client.post("/api/v1/assets", json={
        "name": f"pytest-barcode-{uuid.uuid4().hex[:8]}",
        "category_id": category["id"],
    })
    asset = assert_envelope_ok(r, expected_status=201)["data"]
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
                "import_source"):
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

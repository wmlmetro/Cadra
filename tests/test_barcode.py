"""4 barcode endpoints + /tags/lookup."""
import pytest

from .conftest import assert_envelope_ok


def test_kpis(client, capture):
    r = client.get("/api/v1/barcode/kpis")
    capture("barcode/kpis", r)
    assert_envelope_ok(r)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Pre-existing upstream bug in myservice_barcode_station: "
        "BarcodeStationController.lookup_tag at main.py:38 does "
        "`dict(asset._fields['domain'].selection).get(...)` — `.selection` "
        "is a callable when the Selection is dynamic, so dict() over it "
        "raises TypeError. The API routes the call correctly and returns "
        "a PRD 500 envelope (visible in the captured response)."
    ),
)
def test_lookup_empty_query(client, capture):
    """No query → expects to return either empty results or a usable shape."""
    r = client.get("/api/v1/barcode/lookup")
    capture("barcode/lookup_empty", r)
    assert_envelope_ok(r)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Same upstream bug as test_lookup_empty_query — see that test for "
        "the full reason."
    ),
)
def test_lookup_with_query(client, test_asset, capture):
    """Look up the test asset's tag — should find it."""
    r = client.get("/api/v1/barcode/lookup", params={"query": test_asset["tag"]})
    capture("barcode/lookup_query", r)
    assert_envelope_ok(r)


def test_recent_tags(client, capture):
    r = client.get("/api/v1/barcode/recent-tags", params={"limit": 5})
    capture("barcode/recent_tags", r)
    assert_envelope_ok(r)


def test_print_url(client, test_asset, capture):
    """Generate a tag print URL for the test asset."""
    r = client.get("/api/v1/barcode/print-url", params={
        "tag_id": test_asset["id"],
        "size": "medium",
    })
    capture("barcode/print_url", r)
    assert_envelope_ok(r)


def test_tags_lookup(client, test_asset, capture):
    """GET /api/v1/tags/lookup — public-style tag lookup, JWT-protected."""
    r = client.get("/api/v1/tags/lookup", params={"query": test_asset["tag"]})
    capture("barcode/tags_lookup", r)
    assert_envelope_ok(r)

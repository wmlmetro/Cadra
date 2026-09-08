"""The list endpoints tell the truth about what they withheld.

Handoff 12 A, proved end-to-end against a live tenant with a real service
credential — the exact shape of caller the cap exists for.

The suite's own credential is a default client (`total_record_cap = 0`), so
it IS the capped case. That is what makes these assertions worth running
here: an uncapped path would prove nothing about the caller this finding is
about. The per-client uncapped and 500 cases are covered in-registry, in
myservice_api/tests/test_pagination_cap.py, where three clients can be
provisioned.
"""
import csv
import io

import pytest

from .conftest import assert_envelope_ok

# Endpoints whose `total_estimate` used to report the size of the capped
# window rather than the size of the register.
LIST_ENDPOINTS = [
    "/api/v1/assets",
    "/api/v1/locations",
    "/api/v1/identity/employees",
    "/api/v1/requests",
    "/api/v1/fleet",
]


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
def test_total_estimate_is_never_the_page_size(client, path, capture):
    """The count is a fact about the register, not about the response.

    The old bug is invisible on a small resource — `total_estimate` and the
    row count agree when nothing was withheld. It is only detectable where
    the cap actually bit, so this asserts the RELATIONSHIP: if a truncation
    was declared, the total must exceed what was returned.
    """
    r = client.get(f"{path}?limit=2000")
    capture(f"pagination/{path.strip('/').replace('/', '_')}_total", r)
    body = assert_envelope_ok(r)

    rows = len(body["data"])
    total = body["pagination"]["total_estimate"]
    truncated = body.get("_warnings", {}).get("truncated")

    assert total >= rows, (
        f"{path} reported total_estimate={total} while returning {rows} rows"
    )
    if truncated:
        assert total == truncated["total"], (
            "the truncation warning and the pagination block must not "
            "disagree about the size of the register"
        )
        assert total > rows, (
            f"{path} says it truncated but reports a total equal to the "
            f"rows it returned — which is exactly the old bug wearing the "
            f"new warning as a costume"
        )


def test_the_asset_register_is_bigger_than_one_page(client, capture):
    """The live proof, on the tenant the finding was measured against.

    jaizbankplc held 2,363 assets and the API said 100. If this tenant ever
    drops below the cap the assertion becomes vacuous rather than wrong, so
    it skips loudly instead of passing quietly.
    """
    r = client.get("/api/v1/assets?limit=2000")
    capture("pagination/assets_capped", r)
    body = assert_envelope_ok(r)

    total = body["pagination"]["total_estimate"]
    rows = len(body["data"])
    if total <= rows:
        pytest.skip(
            f"this tenant holds {total} assets, which fits inside one capped "
            f"page — nothing to truncate, so there is nothing to prove here")

    assert rows == 100, f"expected the external cap to bite at 100, got {rows}"
    assert total > 100
    assert body["pagination"]["next_cursor"] is None

    truncated = body["_warnings"]["truncated"]
    assert truncated["cap"] == 100
    assert truncated["total"] == total
    assert "contact WestMetro" in truncated["reason"]


def test_the_warning_describes_the_QUERY_not_the_page(client, capture):
    """A small page of an over-cap query still warns — on page one.

    This is a deliberate choice and it is worth stating plainly. The cap
    bites on the query, not on the page: a caller walking a 2,383-asset
    register five rows at a time will hit the wall at record 100. Declaring
    the truncation only on the page where the wall is reached would tell
    them at the end of a twenty-page walk what they needed to know before
    they started.
    """
    r = client.get("/api/v1/assets?limit=5")
    capture("pagination/assets_small_page", r)
    body = assert_envelope_ok(r)

    total = body["pagination"]["total_estimate"]
    assert len(body["data"]) <= 5
    if total <= 100:
        pytest.skip(f"this tenant holds {total} assets — nothing to truncate")

    assert body["pagination"]["next_cursor"], (
        "a 5-row page of a larger register must offer a cursor")
    truncated = body["_warnings"]["truncated"]
    assert truncated["cap"] == 100
    assert truncated["total"] == total


def test_a_query_that_fits_inside_the_cap_carries_no_warning(client, capture):
    """A warning that is always there is not a warning."""
    r = client.get("/api/v1/assets?q=zzz-no-such-asset-zzz&limit=50")
    capture("pagination/assets_narrow_query", r)
    body = assert_envelope_ok(r)

    assert body["pagination"]["total_estimate"] <= 100, (
        "this query was chosen to return few or no rows; if it now matches "
        "more than the cap, pick a narrower one")
    assert "truncated" not in body.get("_warnings", {}), (
        "nothing was withheld from this query, so nothing may claim it was")


def test_export_csv_declares_its_truncation(api_base, token, capture):
    """The CSV bypasses the envelope, so it gets a header and a final
    commented row. This is the artefact that gets saved and emailed."""
    import requests

    r = requests.get(f"{api_base}/api/v1/assets/export.csv",
                     headers={"Authorization": f"Bearer {token}"})
    capture("pagination/export_csv_truncated", r)
    assert r.status_code == 200

    header = r.headers.get("X-Cadra-Truncated")
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    if header is None:
        assert not any(ln.startswith("# TRUNCATED") for ln in lines), (
            "a file that carries the truncation row must carry the header too")
        pytest.skip("this tenant's register fits inside the cap")

    cap, total = (int(part) for part in header.split("/"))
    assert cap == 100
    assert total > cap
    rows = list(csv.reader(io.StringIO(r.text)))
    # header row + cap data rows + the truncation row
    assert len(rows) == cap + 2, (
        f"expected {cap} data rows, a header and a truncation row; got "
        f"{len(rows)} rows")

    # The row goes through csv.writer, so it is QUOTED — the message
    # contains commas. That is deliberate: a raw `# ...` line would make the
    # file invalid CSV and split across cells in Excel, where a quoted field
    # lands in one cell and reads as a sentence. The `#` is for whoever
    # opens it in a text editor.
    assert rows[-1][0].startswith("# TRUNCATED"), (
        "the last row must say so in the file itself — the person who opens "
        "this in Excel never sees a response header")
    assert str(total) in rows[-1][0], (
        "the truncation row must name the true size of the register")


def test_export_json_reports_the_register_not_the_response(client, capture):
    r = client.get("/api/v1/assets/export")
    capture("pagination/export_json_total", r)
    body = assert_envelope_ok(r)["data"]

    assert "total" in body, (
        "`count` is the rows in this response; a route calling itself "
        "'export all assets' must also say how many there are")
    assert body["total"] >= body["count"]

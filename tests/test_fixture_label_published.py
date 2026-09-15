"""The derived fixture label is visible to a reader of the API.

Handoff 26 §A. `is_test_fixture` is stamped onto the record from the acting
credential (`myservice_api/models/test_fixture.py`), which is worth nothing
to anybody reading the register through the API unless the API says so.

This suite authenticates with a credential flagged `is_test_credential` —
`tests/conftest.py::database_accepts_test_writes` refuses to run otherwise —
so every record it creates must come back labelled. That makes the positive
case free and honest: these are real fixtures, created the way every other
fixture in this suite is created, asserting on themselves.

The NEGATIVE case is not here and cannot be: this suite has no unflagged
credential and is forbidden from minting one. It is proved in-registry
instead, at `myservice_api/tests/test_fixture_label_is_derived.py::
test_a_record_created_under_a_real_credential_does_not`, with `with_user()`.
A label that reads TRUE for everything says nothing about anything, so that
half is the half that matters — it is just not this suite's to prove.
"""


def test_a_created_asset_comes_back_labelled(client, test_asset):
    assert "is_test_fixture" in test_asset, (
        "`is_test_fixture` is absent from the asset envelope. It is stamped "
        "on the record but not published, so nothing reading this API can "
        "tell a fixture from register data.")
    assert test_asset["is_test_fixture"] is True, (
        "this suite authenticates with a credential flagged "
        "`is_test_credential`, so an asset it creates must be labelled. Got "
        "%r — the derivation is not reaching `nrs.asset.create`."
        % test_asset["is_test_fixture"])


def test_the_label_survives_a_re_read(client, test_asset):
    """Stamped, not computed per response.

    A value the serializer works out at read time would be a join, and a
    join stops answering the moment the credential is archived or re-homed.
    Re-reading through a different route is the cheapest proof that the
    answer is stored on the row.
    """
    r = client.get("/api/v1/assets/%s" % test_asset["id"])
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["is_test_fixture"] is True


def test_a_created_location_comes_back_labelled(client, test_location):
    assert test_location.get("is_test_fixture") is True, (
        "a location created by this suite is not labelled. Locations are the "
        "PUBLIC exposure: `/api/myservice/form-data` returns every active "
        "one, and report 24 measured 354 of 420 dropdown entries as fixtures.")


def test_a_created_request_comes_back_labelled(client, test_request):
    """`request.request` is the measured hole.

    Its name is a sequence, so before this field a test-created request was
    indistinguishable from a real one by any rule any script could apply —
    460 of them on `jaizbankplc`, unidentifiable permanently.
    """
    assert test_request.get("is_test_fixture") is True, (
        "a service request created by this suite is not labelled — the "
        "unidentifiable population is still growing")


def test_the_label_cannot_be_set_by_the_caller(client, test_location):
    """Sending it is rejected as an unknown field, not honoured.

    `is_test_fixture` is in no `_WRITABLE_FIELDS`, so it lands in
    `_warnings.rejected_fields` — the published behaviour for a field the
    API will not accept. Asserted rather than assumed: a label a caller can
    send is a label that says whatever the caller wants, and
    `tests/test_source_guards.py` guards the allow-list from the other side.
    """
    import time
    r = client.post("/api/v1/locations", json={
        "name": "pytest-loc-label-probe-%d" % int(time.time()),
        "is_test_fixture": False,
    })
    assert r.status_code == 201, r.text[:300]
    body = r.json()["data"]
    assert body["is_test_fixture"] is True, (
        "a payload claiming `is_test_fixture: False` was honoured — the "
        "label is declarable over the API")
    rejected = (body.get("_warnings") or {}).get("rejected_fields") or []
    assert "is_test_fixture" in rejected, (
        "`is_test_fixture` was dropped without being reported in "
        "`_warnings.rejected_fields`. Silently dropping a field an "
        "integration sent is the defect rule 3 names, even on a 201. Got: %r"
        % rejected)

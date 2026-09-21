"""A filter that cannot be read is refused, not dropped.

Every list filter in this API used to fail the same way. A value the parser
did not recognise matched no branch, appended no domain term, and the caller
received the list they would have received with no filter at all.

**An empty list reads as "no matches". A full list reads as an answer.** That
asymmetry is why the booleans are first in this file and were first in the
work: `?is_verified=1` returned the whole register, and a client branching on
the result treated every asset in it as verified. Nothing in the response
said otherwise, and neither the caller nor we would ever have found out.

It is not hypothetical for an auditor. `GET /assets?has_sap_code=false` is
"which assets has finance not booked", `GET /locations?has_coordinates=false`
is "which sites has nobody mapped", `GET /requests?has_deadline=false` is
"which work has nobody put a date on". Each one answered with everything, and
an auditor who satisfies themselves from a Cadra list has then been handed a
false statement by a government system.

The enums are the subtler half: an unrecognised value answered `200 []`, and
an empty list for a mistyped value is indistinguishable from an empty list
for a value that genuinely matched nothing. The reassuring reading is the
wrong one, which is what makes `?sap_reconciliation_state=exceptions` — the
plural, the natural typo — the worst of them.

These tests are HTTP-level and run against a live tenant, because the thing
being asserted is what a caller receives. `tests/test_query_param_guard.py`
is the static half: it asserts that every declared query parameter reaches a
validator, so a parameter added next year cannot quietly rejoin the family
this file exists to close.
"""
import pytest

from .conftest import assert_envelope_err, assert_envelope_ok


# ─── helpers ─────────────────────────────────────────────────────────

def _list(client, path, **params):
    """GET a list endpoint, skipping if this credential cannot reach it.

    The suite's token is a CLIENT token and CLAUDE.md documents that it
    cannot reach every route. A 401/403 here is a scope fact about the
    fixture, not a result — and asserting a 400 against a route that
    answered 403 would be a test that passes for the wrong reason.
    """
    r = client.get(path, params=params)
    if r.status_code in (401, 403):
        pytest.skip("this credential cannot reach %s (%d)" % (path, r.status_code))
    return r


def _refused(client, path, param, value):
    """Assert `?param=value` is a 400 that names the parameter."""
    r = _list(client, path, **{param: value})
    body = assert_envelope_err(r, 400, "invalid_request")
    message = body["error"]["message"]
    assert param in message, (
        "the refusal does not name `%s`, so a caller cannot tell which of "
        "their filters was rejected: %r" % (param, message))
    return body


def _count(client, path, **params):
    """How many records MATCH, not how many came back on this page.

    `len(body["data"])` is bounded by `DEFAULT_PAGE_LIMIT` (50), so on any
    endpoint with more than fifty rows every count here saturated at 50 and
    the partition assertion below — the one the acceptance criterion actually
    asks for — was gated out by its own `if unfiltered < 50` guard. Silently:
    nothing skipped, nothing printed. On `/api/v1/assets`, which is every
    tenant with real data, it never ran at all.

    `pagination.total_estimate` is documented (`utils.paginate`) as ALWAYS a
    `search_count` of the caller's own unclamped domain, on every path,
    precisely so a caller is never told the size of a window and left to read
    it as the size of the register. So the partition can be checked over the
    register instead of over a page of it.
    """
    r = _list(client, path, limit=1, **params)
    body = assert_envelope_ok(r)
    total = (r.json().get("pagination") or {}).get("total_estimate")
    assert total is not None, (
        "%s reports no `pagination.total_estimate`, so this test would be "
        "counting a page rather than the register" % path)
    return total


# ─── the five booleans, and the two the inventory missed ─────────────
#
# `(endpoint, parameter)`. `is_tagged` and `has_sap_code` on the assets list
# were fixed in earlier handoffs and are the precedent the rest now follow;
# they are here so a regression in the precedent fails too.

BOOLEAN_FILTERS = [
    ("/api/v1/assets", "is_verified"),
    ("/api/v1/assets", "is_tagged"),
    ("/api/v1/assets", "has_sap_code"),
    ("/api/v1/requests", "closed"),
    ("/api/v1/requests", "has_deadline"),
    ("/api/v1/fleet", "is_staff_bus"),
    ("/api/v1/identity/employees", "active"),
    ("/api/v1/locations", "active"),
    ("/api/v1/locations", "has_coordinates"),
]

#: Every spelling somebody actually sends. `1`/`0` is the C habit, `yes`/`no`
#: the shell habit, `TRUE` the SQL habit, and `null` what a JS caller sends
#: for a value it never set. Each one used to be a full unfiltered list.
UNREADABLE_BOOLEANS = ["1", "0", "yes", "no", "TRUE", "False ", "null", "on"]


@pytest.mark.parametrize("path,param", BOOLEAN_FILTERS,
                         ids=lambda v: v.strip("/").replace("/", "-"))
@pytest.mark.parametrize("value", UNREADABLE_BOOLEANS)
def test_an_unreadable_boolean_is_refused_not_dropped(client, path, param, value):
    """The whole point, stated once for every boolean this API publishes."""
    if param == "is_tagged" and value == "null":
        pytest.skip(
            "`is_tagged` published `null` as 'no filter' before this rule "
            "existed and keeps it — see the comment in v1_assets._list_domain")
    body = _refused(client, path, param, value)
    assert body["error"]["details"].get("allowed_values") == ["true", "false"], (
        "the refusal does not tell the caller what to send instead: %s"
        % body["error"])


@pytest.mark.parametrize("path,param", BOOLEAN_FILTERS,
                         ids=lambda v: v.strip("/").replace("/", "-"))
def test_a_boolean_filter_can_no_longer_return_the_unfiltered_list(
        client, path, param):
    """The assertion the acceptance criterion actually asks for.

    A 400 is the mechanism; this is the consequence. The two halves of a
    boolean filter must partition the unfiltered list between them — if they
    do not, one branch is missing and the parameter is still capable of the
    silent pass-through, whatever it does with a bad value.

    `has_deadline` and `has_coordinates` are exactly why this test exists
    separately from the one above: both had only a `true` branch, so `false`
    appended nothing and returned everything. A test that only checked the
    400 would have called them fixed.
    """
    if param == "active":
        # `active` is the one boolean whose ABSENCE is not "no filter".
        # Omitting it means `active = True`, which is published behaviour on
        # both the employees and locations lists and stays. So the two halves
        # cannot be compared against an unfiltered baseline — there is no
        # request that produces one — and the assertion below would fail on
        # any tenant holding an archived record.
        yes = _count(client, path, **{param: "true"})
        no = _count(client, path, **{param: "false"})
        default = _count(client, path)
        assert yes == default, (
            "omitting `active` on %s no longer means `active=true`, which is "
            "its documented default (%d vs %d)" % (path, default, yes))
        # `no` used to be computed and never asserted on — a dead assignment
        # whose only effect was proving `active=false` answers 200. That left
        # the `false` branch with NO regression net, and report 21 calls it
        # "arguably the worse failure of the two": an unfiltered list is
        # conspicuously large, while a plausible active-only roster handed to
        # somebody asking for the archived one invites no second look at all.
        #
        # So assert the thing that would actually catch it. `active=false`
        # must not return the active set: if somebody reintroduced an
        # unconditional `("active", "=", True)`, `no` would equal `yes` and
        # the refusal test above would still pass.
        assert no != yes or no == 0, (
            "`%s=false` on %s returned the same count as `%s=true` (%d). "
            "Either the false branch is not being applied, or this tenant "
            "holds exactly as many archived records as live ones — check "
            "before relaxing this." % (param, path, param, no))
        return

    unfiltered = _count(client, path)
    yes = _count(client, path, **{param: "true"})
    no = _count(client, path, **{param: "false"})

    assert yes <= unfiltered and no <= unfiltered, (
        "`%s` on %s returned MORE rows filtered than unfiltered "
        "(%d/%d vs %d) — the filter is not being applied"
        % (param, path, yes, no, unfiltered))

    # A partition with an EMPTY half proves nothing, and it does not fail —
    # it passes. `has_deadline` was mutated back to its `true`-only form to
    # check this test catches it, and the test went green, because no request
    # on this tenant carries a deadline: `true` returned 0, the broken
    # `false` returned everything, and 0 + everything still summed to
    # everything. That is CLAUDE.md's collapsed denominator, one layer up.
    #
    # So say so out loud. A skip is visible in the run; a vacuous pass is
    # indistinguishable from a real one, which is the whole subject of this
    # file.
    if not yes or not no:
        pytest.skip(
            "no data to partition on this tenant: `%s=true` matched %d rows "
            "and `%s=false` matched %d. The refusal test above still covers "
            "the 400; this assertion needs both halves to exist."
            % (param, yes, param, no))

    # Unconditionally, now that `_count` reads `total_estimate` rather than a
    # page length. This used to be gated behind `if unfiltered < 50` — which
    # is "only check this on endpoints with fewer rows than one page" — so on
    # `/api/v1/assets` it never ran. The gate was needed because the counts
    # were page lengths; it is not needed against the register's own count,
    # and leaving it would have kept the acceptance criterion unenforced on
    # every endpoint that matters.
    assert yes + no == unfiltered, (
        "`%s=true` (%d) and `%s=false` (%d) do not partition the %d rows "
        "of %s. One branch of the filter is missing, which is the "
        "unfiltered-list defect wearing a 200."
        % (param, yes, param, no, unfiltered, path))


def test_has_deadline_partitions_a_register_that_actually_has_both(
        client, test_location, test_asset):
    """The vacuity above, closed for the one filter whose `false` branch is
    new in this change.

    `has_deadline` had no `false` branch at all, so the question "which work
    has nobody put a date on" returned every request there is. The mutation
    that proves this test works — reverting to the `true`-only form — went
    GREEN against the shared tenant, because nothing on it carries a
    deadline and an empty half partitions anything. So this makes both
    halves exist first, then asserts.
    """
    def new_request(deadline=None):
        body = {
            "type_id": 1,
            "category_id": 5,
            "priority": "2",
            "request_text": "<p>pytest has_deadline partition</p>",
            "nrs_asset_id": test_asset["id"],
        }
        if deadline:
            body["deadline_date"] = deadline
        r = client.post("/api/v1/requests", json=body)
        if r.status_code in (401, 403):
            pytest.skip("this credential cannot create requests")
        return assert_envelope_ok(r, expected_status=201)["data"]

    dated = new_request("2030-01-31")
    undated = new_request()

    # Scoped to this run's own asset. The suite's credential is capped to
    # the first N records of any query, so enumerating the whole register
    # would leave the two rows just created off the end of both pages and
    # the test would fail for a reason that is not the one it asserts.
    def ids(**params):
        body = assert_envelope_ok(_list(
            client, "/api/v1/requests", asset_id=test_asset["id"], **params))
        return {row["id"] for row in body["data"]}

    with_deadline = ids(has_deadline="true")
    without = ids(has_deadline="false")
    both = ids()

    assert dated["id"] in both and undated["id"] in both, (
        "the two requests this test created are not both on the unfiltered "
        "list for their own asset, so nothing below is measuring the filter")

    assert dated["id"] in with_deadline, (
        "a request created WITH a deadline is missing from "
        "`?has_deadline=true`")
    assert dated["id"] not in without, (
        "a request created WITH a deadline came back from "
        "`?has_deadline=false` — the false branch is not filtering, which is "
        "the unfiltered-list defect this parameter had")
    assert undated["id"] in without
    assert undated["id"] not in with_deadline
    assert not (with_deadline & without), (
        "the two halves overlap on %d requests" % len(with_deadline & without))


# ─── the enums that used to answer `200 []` ──────────────────────────
#
# `(endpoint, parameter, a value that is nearly right)`. Each typo is one
# somebody would really make: a plural, a synonym, the British spelling, the
# label instead of the key.

ENUM_FILTERS = [
    ("/api/v1/assets", "state", "Active"),
    ("/api/v1/assets", "condition", "excellent"),
    ("/api/v1/assets", "domain", "IT"),
    ("/api/v1/assets", "asset_level", "subasset"),
    ("/api/v1/assets", "import_source", "Vendra"),
    ("/api/v1/assets", "tag_label_state", "affixed "),
    ("/api/v1/assets", "sap_reconciliation_state", "exceptions"),
    ("/api/v1/requests", "priority", "urgent"),
    ("/api/v1/requests", "kanban_state", "in_progress"),
    ("/api/v1/identity/employees", "sap_status", "inactive"),
    ("/api/v1/identity/employees", "sap_sync_status", "sync"),
    ("/api/v1/locations", "location_type", "state"),
    ("/api/v1/fleet", "fuel_type", "petrol"),
]


@pytest.mark.parametrize("path,param,typo", ENUM_FILTERS,
                         ids=lambda v: str(v).strip("/").replace("/", "-"))
def test_an_unrecognised_enum_is_refused_rather_than_answering_with_nothing(
        client, path, param, typo):
    """`200 []` for a mistyped value is the most reassuring wrong answer this
    API can give, and the caller cannot tell it from a real empty result."""
    body = _refused(client, path, param, typo)
    allowed = body["error"]["details"].get("allowed_values")
    assert allowed, (
        "`%s` was refused without saying what it accepts, so the caller has "
        "to read our source to find out: %s" % (param, body["error"]))
    assert typo not in allowed


@pytest.mark.parametrize("path,param,typo", ENUM_FILTERS,
                         ids=lambda v: str(v).strip("/").replace("/", "-"))
def test_every_published_enum_value_is_still_accepted(client, path, param, typo):
    """The counterweight, and the one that could break a caller.

    Validation read off the model rather than off the annotation, precisely
    so the accepted set is never narrower than what the model itself allows.
    This asserts it: every value the refusal names must be a value the
    endpoint answers 200 to. A guard that starts refusing something a live
    integration sends is worse than the bug it replaced.
    """
    allowed = _refused(client, path, param, typo)["error"]["details"]["allowed_values"]
    for value in allowed:
        r = _list(client, path, **{param: value})
        assert r.status_code == 200, (
            "`%s=%s` is published as accepted and answered %d: %s"
            % (param, value, r.status_code, r.text[:200]))


def test_priority_still_accepts_the_fifth_value_the_docs_omitted(client):
    """The one case where validating against the annotation would have broken
    a caller — and it would have broken this suite first.

    `request.request.priority` declares five values; the route published four
    and described `3` as "urgent" when the model calls it Critical.
    `tests/test_requests.py` creates a request with `priority: "4"`. Rule 4
    of CLAUDE.md is explicit that the model wins and the documentation is the
    thing that gets corrected.
    """
    r = _list(client, "/api/v1/requests", priority="4")
    assert r.status_code == 200, (
        "`priority=4` is a real value of the model's Selection and must not "
        "be refused: %s" % r.text[:300])


# ─── the integer filters ─────────────────────────────────────────────

INT_FILTERS = [
    ("/api/v1/assets", "category_id"),
    ("/api/v1/assets", "subcategory_id"),
    ("/api/v1/assets", "location_id"),
    ("/api/v1/assets", "building_id"),
    ("/api/v1/assets", "floor_id"),
    ("/api/v1/assets", "room_id"),
    ("/api/v1/assets", "custodian_id"),
    ("/api/v1/assets", "parent_id"),
    ("/api/v1/requests", "type_id"),
    ("/api/v1/requests", "category_id"),
    ("/api/v1/requests", "stage_id"),
    ("/api/v1/requests", "user_id"),
    ("/api/v1/identity/employees", "location_id"),
    ("/api/v1/identity/employees", "department_id"),
    ("/api/v1/locations", "type_id"),
    ("/api/v1/locations", "parent_id"),
    ("/api/v1/locations", "country_id"),
    ("/api/v1/locations", "state_id"),
    ("/api/v1/fleet", "state_id"),
]


@pytest.mark.parametrize("path,param", INT_FILTERS,
                         ids=lambda v: v.strip("/").replace("/", "-"))
def test_a_non_numeric_foreign_key_is_refused_not_swallowed(client, path, param):
    """`except (TypeError, ValueError): pass` returned the whole register.

    `?category_id=laptops` is the shape: a caller sending a NAME where an id
    belongs got every asset in the tenant and no indication they had asked
    the wrong question.
    """
    _refused(client, path, param, "laptops")


@pytest.mark.parametrize("path,param", INT_FILTERS,
                         ids=lambda v: v.strip("/").replace("/", "-"))
def test_the_no_filter_sentinels_still_mean_no_filter(client, path, param):
    """Absent, empty and the literal `null` a JS caller sends for an unset
    value have always meant "do not filter on this" here, and a rule that
    starts refusing them breaks a caller that is not doing anything wrong."""
    unfiltered = _count(client, path)
    for sentinel in ("", "null"):
        assert _count(client, path, **{param: sentinel}) == unfiltered, (
            "`%s=%r` on %s stopped meaning 'no filter'" % (param, sentinel, path))


# ─── limit ───────────────────────────────────────────────────────────

def test_a_non_numeric_limit_is_refused(client):
    """`?limit=all` used to serve fifty rows to a caller who believed they
    had asked for every one."""
    _refused(client, "/api/v1/assets", "limit", "all")


def test_an_oversized_limit_is_still_clamped_and_not_refused(client):
    """Clamping and refusing are different answers to different inputs, and
    the difference is published. The ceiling is per-credential, so a caller
    cannot know it in advance; being refused for asking would be unhelpful,
    and `?limit=100000` has always been answered with a page."""
    r = _list(client, "/api/v1/assets", limit="100000")
    assert r.status_code == 200, r.text[:300]


# ─── `include`, which dropped an unknown section in silence ──────────

INCLUDE_ROUTES = [
    ("/api/v1/assets/%s", "transfers,custdy"),
    ("/api/v1/locations/%s", "childs"),
    ("/api/v1/requests/%s", "route"),
]


def test_an_unknown_include_section_is_refused(client, test_asset):
    """A body missing the section the caller asked for is indistinguishable
    from a record that has nothing in that section."""
    body = _refused(client, "/api/v1/assets/%s" % test_asset["id"],
                    "include", "transfers,custdy")
    assert "custdy" in str(body["error"]["details"]), (
        "the refusal does not say which section it did not recognise: %s"
        % body["error"])


def test_a_known_include_section_still_works(client, test_asset):
    body = assert_envelope_ok(
        client.get("/api/v1/assets/%s" % test_asset["id"],
                   params={"include": "transfers,custody"}))
    assert "transfers" in body["data"]
    assert "custody" in body["data"]


# ─── the label size, which printed the wrong piece of paper ──────────

def test_an_unrecognised_label_size_is_refused(client):
    """Not a wrong list — a wrong physical label, printed and stuck to an
    asset, with a 200 telling the caller it worked. `?size=sheets` fell back
    to `medium`, so a request for the A4 multi-label sheet produced one
    medium label."""
    r = client.get("/api/v1/barcode/print-url",
                   params={"tag_id": 1, "size": "sheets"})
    if r.status_code in (401, 403):
        pytest.skip("this credential cannot reach /barcode/print-url")
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "size" in body["error"]["message"]
    assert body["error"]["details"]["allowed_values"] == [
        "small", "medium", "large", "sheet"]

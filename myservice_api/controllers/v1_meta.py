"""`GET /api/v1/meta/enums` — the model's own Selection sets, published.

WHY THIS ROUTE EXISTS
---------------------
Because every client was maintaining its own copy of sets this server owns,
and every copy had drifted.

The Cadra SPA held five of them. `priority` was shifted one whole step, so a
form showing "Normal" wrote `"2"` — which the model calls **High** — and every
request created without touching the dropdown was filed a level above what the
user saw. `location_type` offered two values the model does not have and
omitted one it does. `asset_level` was missing `group`. `fuel_type` collapsed
nine values onto three labels, rendering `electric` as CNG. The FM `domain`
was a free-text box whose placeholder advertised a value that was not in the
set and not even the right shape.

None of those said a word. A select populated from a stale list looks exactly
like a select populated from a fresh one.

Until now the ONLY way a client could learn a field's accepted values was to
send a wrong one and read `allowed_values` off the 400 (handoff 21). That is a
refusal doing documentation's job: fine for telling a user what they typed
wrong, useless for populating a dropdown before they type anything. The
OpenAPI document carries enums too, but they are hand-written literals in the
route annotations rather than reads of the model — copies with the same
failure mode, in a second place. `/api/v1/home/quick-submit` published four of
`priority`'s five values for exactly that reason.

So: one route, derived from the registry at request time, with no list written
out anywhere in it.

WHAT IT IS NOT
--------------
Not a schema endpoint and not a reflection API. It publishes a FIXED,
hand-chosen set of fields — the ones a user interface has to render a control
for. A caller cannot ask it about an arbitrary model.field, and that is
deliberate: this answers with `sudo()` on the registry, and a route that
enumerates any field a caller names is a map of the schema handed to anyone
holding a token. The cost of the restriction is a one-line edit here when a
new dropdown is added, which is a place a reviewer will see it.
"""

from odoo import http
from odoo.http import request

from odoo.addons.myservice_nrs_base.database_class import TEST, database_class

from .utils import selection_values
from .v1 import cadra_route


# The published sets: public name → (model, field, fallback values).
#
# The FALLBACK is what `selection_values` answers with if it cannot read the
# registry, and it is never "skip it" or "empty". A metadata route that
# answers `[]` on a bad day hands every client an empty dropdown and no
# indication anything is wrong, which is the same silent degradation this
# route was built to remove — one level up.
#
# The fallbacks below are the model's values as of handoff 22, verified
# against the live registry on `jaizbankplc`. `tests/test_frontend_enums.py`
# parses the model source and fails when any of them drifts, so they cannot
# rot the way the front end's copies did.
_PUBLISHED_ENUMS = (
    # name,           model,               field,            fallback
    ("priority",      "request.request",   "priority",
     ("0", "1", "2", "3", "4")),
    ("location_type", "generic.location",  "location_type",
     ("building", "floor", "wing", "room", "zone")),
    ("asset_level",   "nrs.asset",         "asset_level",
     ("group", "asset", "sub_asset", "component")),
    # `nrs.asset.domain` is a related field onto `nrs.asset.category.domain`;
    # a related Selection carries the parent's list, so reading it here gives
    # the category's eight values.
    ("domain",        "nrs.asset",         "domain",
     ("building", "plant", "plumbing", "fleet", "security", "it",
      "furniture", "other")),
    ("condition",     "nrs.asset",         "condition",
     ("new", "good", "fair", "poor", "decommissioned")),
    # Published as `asset_state`, not `state`: `state` is the single most
    # reused field name in the schema (`nrs.asset.tag.label`, `nrs.asset.
    # transfer` and `nrs.asset.import` all have one), and a client keying a
    # cache on the bare name would collide the first time a second one is
    # published here.
    ("asset_state",   "nrs.asset",         "state",
     ("active", "in_repair", "disposed", "transferred", "missing")),
    # Handoff 34. Non-stored and computed against a Lagos day, but a
    # Selection like the rest: the register's warranty filter offers these.
    ("warranty_status", "nrs.asset",       "warranty_status",
     ("under_warranty", "expired", "none")),
    ("fuel_type",     "fleet.vehicle",     "fuel_type",
     ("diesel", "gasoline", "full_hybrid", "plug_in_hybrid_diesel",
      "plug_in_hybrid_gasoline", "cng", "lpg", "hydrogen", "electric")),
)


def _labelled(model_name, field_name, values):
    """`[{value, label}]` — the model's own labels, in the model's own order.

    `selection_values` is the authority on WHICH values are published: it is
    the same helper every filter on this API validates against, so this route
    cannot offer a value a filter would then refuse. It returns keys only, so
    the labels are looked up separately off the same field — and any value it
    returned that has no label falls back to its own key rather than being
    dropped. A value present in the filter's accepted set but absent from a
    dropdown is the drift this route exists to end, so it is never silently
    omitted here.
    """
    labels = {}
    try:
        field = request.env[model_name]._fields[field_name]
        selection = field.selection
        if callable(selection):
            selection = selection(request.env[model_name])
        labels = dict(selection or ())
    except Exception:
        # catch-all: unknown — broad on purpose, and the reason is the same
        # one `selection_values` gives. The VALUES are what a client needs to
        # be correct; a missing label degrades a dropdown's cosmetics, and
        # failing the whole request over it would take the values with it.
        labels = {}
    return [{"value": v, "label": labels.get(v, v)} for v in values]


class MyserviceApiV1Meta(http.Controller):

    @cadra_route(
        "/api/v1/meta/enums", method="GET",
        summary="Accepted values for every Selection field the API publishes",
        scopes=(),
        response_schema={
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string",
                                  "description": "The key the API stores and accepts"},
                        "label": {"type": "string",
                                  "description": "The model's own human label"},
                    },
                },
            },
            "description": (
                "Keyed by field name. Order is the model's order and is "
                "significant for `priority`, whose keys are numeric strings "
                "that read like a scale."
            ),
        },
    )
    def meta_enums(self, **kwargs):
        """Every Selection set this API accepts, read off the model.

        Populate dropdowns from this rather than from a list in your own
        source. A value the model gains appears here the same day, with no
        release on your side, and a value it never had cannot appear at all.

        **`priority` is the one worth reading carefully.** Its keys are the
        strings `"0"`–`"4"` and they are NOT positions: `"2"` is High, and
        the model's own default is `"1"`. A blank form must start on the
        default VALUE, not on the middle of the list.

        Any valid bearer token may call this. There is nothing tenant-specific
        or record-derived in the answer — it is the shape of the API, which
        `/api/v1/openapi.json` already publishes unauthenticated — so scoping
        it further would only stop a client from rendering a correct form.
        """
        return {
            name: _labelled(model, field,
                            selection_values(model, field, fallback))
            for name, model, field, fallback in _PUBLISHED_ENUMS
        }

    @cadra_route(
        "/api/v1/meta/database", method="GET",
        summary="Which database this token is talking to, and whether it may be written to by a test",
        scopes=(),
        response_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "The database name this request was routed to.",
                },
                "database_class": {
                    "type": ["string", "null"],
                    "enum": ["test", "client", "production", None],
                    "description": (
                        "What a person has recorded this database as. `null` "
                        "means nobody has classified it, which a test run "
                        "must treat exactly as it treats `production`."
                    ),
                },
                "accepts_test_writes": {
                    "type": "boolean",
                    "description": (
                        "True only when `database_class` is `test`. Derived "
                        "here so a client cannot get the policy wrong by "
                        "re-deriving it."
                    ),
                },
                "credential_is_test": {
                    "type": "boolean",
                    "description": (
                        "Whether the credential making this call is flagged "
                        "`is_test_credential`. Records written under it "
                        "self-label — `nrs.asset.custody.source = 'test'`."
                    ),
                },
            },
        },
    )
    def meta_database(self, **kwargs):
        """Which database am I about to write to, and is that allowed?

        A test suite's most important question, and until handoff 25 there was
        no way to ask it. The HTTP suite read `CADRA_API_BASE` and wrote
        wherever it pointed; report 24 §B measured the result as 3,584
        `pytest-*` assets in a register derived from a live client's data,
        six fabricated approved disposals among them.

        **The answer comes from the database, not from the request.** The
        class is a system parameter someone set deliberately on THIS database
        (`cadra.database_class`), so it survives a restore into a
        reassuringly-named host and it cannot be talked out of by an
        environment variable, a hostname or a branch. Absent is not "probably
        fine" — `accepts_test_writes` is false for it, exactly as for
        `production`.

        `credential_is_test` is the second half of the same question. A test
        that mints a credential without the flag writes records that cannot
        be identified as fixtures afterwards, which is precisely how six
        approved disposals in `jaizbankplc` ended up unidentifiable while 330
        custody rows self-labelled correctly.

        Any valid bearer token may call this, with no scope. It says nothing
        about records and nothing an integration could not learn by reading
        the host it just connected to — and a guard a caller cannot reach
        without a privilege it may not have is a guard that gets skipped.
        """
        env = request.env
        found = database_class(env)

        # The CALLING credential, by its `sub` claim — not "the first client
        # sitting on this user". `_mint_access` sets `sub = client.client_id`
        # (v1.py:595), so the token names the credential exactly, and
        # `api_client.write()`'s own docstring says clients deliberately
        # pointed at a shared user are supported. Searching by `user_id` and
        # taking `limit=1` therefore answers about whichever client sorts
        # first by name — so a user carrying an unflagged `A probe` and a
        # flagged `Z test probe` would report `credential_is_test: true` while
        # the suite authenticated as the unflagged one, and every record the
        # run wrote would be unlabelled. That is the `Handoff23 Approver`
        # failure with extra steps.
        claims = getattr(request, "jwt_claims", {}) or {}
        sub = claims.get("sub")
        client = env["myservice.api.client"].sudo().with_context(
            active_test=False,
        ).search([("client_id", "=", sub)], limit=1) if sub else None
        return {
            "database": env.cr.dbname,
            "database_class": found,
            "accepts_test_writes": found == TEST,
            # A session token (a human login) carries no client_id, so
            # `sub` names a login and matches nothing here. False is the
            # correct answer: a person is not a test credential.
            "credential_is_test": bool(client and client.is_test_credential),
        }

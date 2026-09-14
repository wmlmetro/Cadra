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

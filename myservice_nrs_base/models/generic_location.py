"""Where a location's coordinates came from.

`generic.location.latitude` / `longitude` are defined in the vendored
`crnd-19/generic_location` tree and are a bare pair of floats. Nothing beside
them says how they got there, and **two coordinates that mean entirely
different things are written into the same two columns**: one is the geocoding
service's answer for that building, the other is the state capital plus up to
±0.05° of random noise — roughly a 5 km smear over the wrong town — written by
`geocode_locations.py` / `regeocode_runner.py` when the service replied that it
had never heard of the place.

On a map the two are indistinguishable. Both put a pin somewhere plausible in
the right state, and the approximate one is *more* convincing than a blank,
because a blank at least announces itself. A reader who cannot tell them apart
will reconcile a physical verification, an asset count or a facilities visit
against a coordinate that was never a measurement of anything — and will
conclude the register is wrong when it is the pin that is invented.

So the coordinate now travels with a statement of its own provenance:

* one of the geocoding strategies (`full_address`, `name_city_state`,
  `city_state`, `name_state`, `name_only`) — the service was asked that
  question and answered with a place. The strategy is kept rather than a flat
  "geocoded", because they are not equally strong: `full_address` located the
  street, `name_only` located *something* called that somewhere in Nigeria, and
  an auditor deciding how far to trust a pin needs to know which.
* `state_capital_approx` — the service answered and had **no such place**, so a
  jittered state capital was written instead. This is an admission, not a
  result.
* unset (`False`) — the coordinate predates this field or was typed in by hand.
  Unknown provenance, and it stays unknown: see the migration note below.

This is `nrs.asset.custody.source = 'tracking_backfill'` and
`nrs.asset.disposal_date_reconstructed` applied a third time. A reconstructed
or approximated value written into the same column as a recorded one is
indistinguishable from it, and the fix is always the same — the value says on
its face what it is.

**Nothing backfills the existing rows, and there is deliberately no migration
script.** Every location that already carries coordinates has them from an
unknown mixture of real geocodes and old jittered fallbacks, and no evidence in
the database says which is which. The obvious heuristic — "within 0.05° of a
state capital, therefore approximate" — is exactly wrong: a genuine geocode of
a location *in* the capital city lands inside the same radius, so the rule
would stamp real geocodes as approximations and, for any capital the old
`STATE_FALLBACK` table had slightly off, miss the approximations it was written
for. Marking a row as anything other than "unknown" would fabricate the precise
evidence this field exists to carry. `False` on an old row is the honest answer.

**One script, and only one, ever replaces it: `regeocode_runner.py`.** That one
re-walks EVERY location and overwrites each row with a coordinate and the
provenance it was obtained with, so a full run is how the estate acquires a
known provenance. `geocode_locations.py` visits only rows that have no
coordinates at all, and a row of unknown provenance has coordinates by
definition — it is the coordinates that are unexplained — so that script never
revisits one. Re-stamping an existing pin is a `regeocode_runner.py` job.

The scripts stamp this field by name and abort loudly if it is missing, and
`tests/test_geocode_source.py` is the shape guard on the name and the values.
"""
from odoo import models, fields


# ── The strategies a geocoding run can answer with ────────────────────────
#
# These names are the strategy labels the two `odoo shell` geocoders already
# use in their own tallies (`regeocode_runner.py`'s `stats` dict), so the run's
# printed summary and the database say the same words. `name_state` is
# `geocode_locations.py`'s "<name>, <state>, Nigeria" query, which that script
# tries before falling back to name-only.
#
# Ordered strongest first: how precisely the question was posed is how much the
# answer is worth.
GEOCODE_SOURCE_STRATEGIES = (
    'full_address',
    'name_city_state',
    'city_state',
    'name_state',
    'name_only',
)

# The one value that does NOT mean "the service found this place". It means the
# service was reachable, answered, and had no such place — and a state capital
# plus noise was written so the map would not be empty.
#
# A run that could not REACH the service writes no coordinate at all and stamps
# nothing, so there is no value here for it: the absence of a row change is the
# record. An unreachable geocoder has no information about where anything is,
# and inventing a pin from that is the defect handoff 17 D exists to remove.
GEOCODE_SOURCE_APPROXIMATE = 'state_capital_approx'

GEOCODE_SOURCE_SELECTION = [
    ('full_address', 'Geocoded — full address'),
    ('name_city_state', 'Geocoded — name, city and state'),
    ('city_state', 'Geocoded — city and state'),
    ('name_state', 'Geocoded — name and state'),
    ('name_only', 'Geocoded — name only'),
    (GEOCODE_SOURCE_APPROXIMATE, 'Approximate — state capital, not the site'),
]


class GenericLocation(models.Model):
    _inherit = 'generic.location'

    geocode_source = fields.Selection(
        selection=GEOCODE_SOURCE_SELECTION,
        string='Coordinate Source',
        index=True,
        help=(
            "How this location's latitude and longitude were obtained.\n\n"
            "A 'Geocoded' value means the geocoding service was asked the "
            "named question and answered with a place; the question matters, "
            "because 'full address' located the street and 'name only' located "
            "something of that name somewhere in Nigeria.\n\n"
            "'Approximate — state capital' means the service had NO record of "
            "this place, so the state capital plus a small random offset was "
            "written to keep the map populated. It is not a measurement of "
            "where this location is and must not be reconciled against as one "
            "— it can be tens of kilometres out.\n\n"
            "Empty means the coordinates predate this field or were entered by "
            "hand: provenance unknown. It is not backfilled, because nothing "
            "in the database records which of the two the old runs wrote."
        ),
    )

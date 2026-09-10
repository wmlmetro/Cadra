"""`generic.location.geocode_source` exists, is stored, and keeps its values.

This is a shape guard, and the shape is load-bearing for code that no test
harness reaches. `geocode_locations.py` and `regeocode_runner.py` are `odoo
shell` scripts run by hand against a live tenant, and they write this field
**by name**, with **literal** selection values. A rename or a re-spelling here
would not break them loudly — it would make every future run write a
coordinate carrying no statement of where it came from, which is the exact
state handoff 17 D exists to end.

Both scripts do refuse to start if the field or the approximation value is
missing on the database they are pointed at, so the failure is loud at the
point of use too. This test is the other half: it fails in CI, before a run
that would have been refused ever gets scheduled.

The values are asserted as an exact set rather than a subset. A silently ADDED
value is as much a problem as a removed one: the scripts are the only writers,
so a value they never write can only ever be wrong or empty, and a reader who
finds it in the data has been told something untrue about the coordinate.

Run with:
    odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_nrs_base \\
         --test-enable --stop-after-init --http-port=8099 --gevent-port=8098
"""
from odoo.tests import TransactionCase, tagged

from odoo.addons.myservice_nrs_base.models.generic_location import (
    GEOCODE_SOURCE_APPROXIMATE,
    GEOCODE_SOURCE_SELECTION,
    GEOCODE_SOURCE_STRATEGIES,
)

# The literal values the two shell geocoders write. Spelled out here rather
# than imported, deliberately: importing the constants would make this test
# agree with the model by construction and prove nothing. These strings are a
# copy of what is typed into the scripts.
_STRATEGIES_THE_SCRIPTS_WRITE = {
    'full_address',
    'name_city_state',
    'city_state',
    'name_state',
    'name_only',
}
_APPROXIMATION_THE_SCRIPTS_WRITE = 'state_capital_approx'


@tagged("post_install", "-at_install")
class TestGeocodeSource(TransactionCase):

    def test_the_field_exists_and_is_stored(self):
        """A coordinate must be able to carry its provenance in the database.

        Stored matters: an unstored or computed field cannot be written by a
        script, cannot be filtered on, and cannot be read back by an auditor
        asking which pins on the map are real.
        """
        fields = self.env['generic.location']._fields
        self.assertIn(
            'geocode_source', fields,
            "generic.location has no `geocode_source` — the geocoders write "
            "this field by name and would stamp nothing")

        field = fields['geocode_source']
        self.assertEqual(field.type, 'selection')
        self.assertTrue(
            field.store,
            "`geocode_source` is not stored — the geocoders write it and an "
            "auditor reads it back; neither works on an unstored field")
        self.assertFalse(
            field.required,
            "`geocode_source` must stay optional: empty is the honest value "
            "for a coordinate of unknown provenance, and existing rows are "
            "deliberately not backfilled")

    def test_the_selection_values_are_the_ones_the_scripts_write(self):
        """The exact value set, matched against what the scripts type in."""
        # `fields_get`, not `dict(field.selection)`: handoff 05 landed the
        # ruling that `.selection` is not always a list (it is a callable on a
        # related Selection, and `dict()` of it raises TypeError). `fields_get`
        # answers the same question for every shape of Selection field.
        selection = dict(
            self.env['generic.location']
            .fields_get(['geocode_source'])['geocode_source']['selection'])

        expected = _STRATEGIES_THE_SCRIPTS_WRITE | {
            _APPROXIMATION_THE_SCRIPTS_WRITE}
        self.assertEqual(
            set(selection), expected,
            "`geocode_source` values have drifted from what "
            "geocode_locations.py and regeocode_runner.py write")

        # Every value carries a human label; an auditor reads these, not the
        # keys, and the approximation must announce itself in its own label.
        for value, label in selection.items():
            self.assertTrue(label, f"`{value}` has no label")
        self.assertIn(
            'Approximate',
            selection[_APPROXIMATION_THE_SCRIPTS_WRITE],
            "the state-capital value's label does not say it is an "
            "approximation — the label is what a reader actually sees")

    def test_the_module_constants_match_the_field(self):
        """The constants the model publishes are the field's own values.

        The scripts and any future caller are meant to read
        `GEOCODE_SOURCE_APPROXIMATE` rather than retype the string; a constant
        that has drifted from the Selection is worse than no constant.
        """
        self.assertEqual(
            [value for value, _label in GEOCODE_SOURCE_SELECTION],
            list(GEOCODE_SOURCE_STRATEGIES) + [GEOCODE_SOURCE_APPROXIMATE],
            "GEOCODE_SOURCE_SELECTION is not the strategies plus the "
            "approximation")
        self.assertNotIn(
            GEOCODE_SOURCE_APPROXIMATE, GEOCODE_SOURCE_STRATEGIES,
            "the approximation is listed as a geocoding strategy — the whole "
            "point is that it is not one")

    def test_a_location_records_where_its_coordinates_came_from(self):
        """Write both kinds and read them back apart.

        Two locations, identical coordinates to a rounding, one geocoded and
        one approximated. On a map they are the same pin; in the database they
        must not be the same record.
        """
        Location = self.env['generic.location']
        real = Location.create({
            'name': 'H17D real geocode',
            'latitude': 9.05785,
            'longitude': 7.49508,
            'geocode_source': 'full_address',
        })
        approx = Location.create({
            'name': 'H17D approximation',
            'latitude': 9.05780,
            'longitude': 7.49500,
            'geocode_source': GEOCODE_SOURCE_APPROXIMATE,
        })
        unknown = Location.create({'name': 'H17D unknown provenance',
                                   'latitude': 9.05781,
                                   'longitude': 7.49501})

        self.assertEqual(real.geocode_source, 'full_address')
        self.assertEqual(approx.geocode_source, GEOCODE_SOURCE_APPROXIMATE)
        self.assertFalse(
            unknown.geocode_source,
            "a coordinate written with no source must read back as unknown, "
            "not as anything that implies it was geocoded")

        found = Location.search([
            ('id', 'in', (real + approx + unknown).ids),
            ('geocode_source', '=', GEOCODE_SOURCE_APPROXIMATE),
        ])
        self.assertEqual(
            found, approx,
            "the approximations are not separable by search — an auditor "
            "cannot ask which pins are invented")

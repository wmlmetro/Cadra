"""The print funnel — and the id space the callers have to agree on.

`nrs.asset.tag.label.label_state` moves `issued → printed` from exactly one
place: `ir.actions.report._render_qweb_pdf`. That is deliberate (handoff 03) —
the label wizard, the barcode station's raw `/report/pdf/` URL and Odoo's own
Print-menu binding all bypass every Python action method, so stamping the
action methods under-records printing badly.

The hook then declined to stamp whenever `res_ids` could be tag-label ids,
because tag ids and asset ids collide and it could not tell them apart. Every
asset mints a label on creation, so the two sequences advance together: on
`nrs19`, measured 2026-09-08, **11,928 of 11,932 asset ids are also valid label
ids** — 99.97%. The guard written for a rare edge case fired on the normal one,
both real callers were declined, and the register held 11,879 labels at
`issued` and exactly one at `printed`.

The ids cannot be disambiguated by value, and they are the only thing that
reaches the renderer: `web/.../reports/utils.js` turns a report action into
`/report/pdf/<report_name>/<active_ids>` and posts it with the *user* context,
so anything the action put in its own context is dropped at the browser. So the
rule is the framework's: **res_ids are ids of the report's declared model**,
which for all four tag labels is `nrs.asset`. The two callers that passed tag
ids were not merely ambiguous — they rendered whichever unrelated asset shared
the number.

Every test below therefore checks two things at once: that the print was
stamped, and that the thing rendered was the right asset. A stamp on the wrong
record is worse than no stamp.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MEDIUM = 'myservice_asset_register.report_asset_tag_label'
SHEET = 'myservice_asset_register.report_asset_tag_label_sheet'


class PrintFunnelCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env['nrs.asset']
        self.Report = self.env['ir.actions.report']
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'H10 Print Category', 'code': 'H10PRINT'})

    def _asset(self, name='H10 Printable Asset'):
        """An asset with an auto-generated, unprinted label."""
        asset = self.Asset.create({'name': name, 'category_id': self.category.id})
        self.assertTrue(asset.active_tag_id,
                        'creating an asset generates its tag label')
        self.assertEqual(asset.active_tag_id.label_state, 'issued')
        return asset

    def _active_ids(self, action):
        """The ids a report action will actually be rendered with.

        `report_action` does not always return the report: on a company with no
        `external_report_layout_id` — which is every tenant here — an admin gets
        the layout configurator wizard instead, carrying the real report action
        nested in its context. Unwrap it, because what these tests are about is
        which ID SPACE the caller handed over, and that survives the wrapper.
        """
        context = action.get('context') or {}
        if 'report_action' in context:
            action = context['report_action']
            context = action.get('context') or {}
        self.assertIn('active_ids', context,
                      'the report action carries the ids it will render')
        return list(context['active_ids']), action['report_name']

    def _render(self, report_name, res_ids):
        """Render exactly the way `/report/pdf/<name>/<ids>` does.

        `web/controllers/report.py` calls `_render_qweb_pdf(reportname, docids)`
        and nothing else, so this is the barcode station's path with the HTTP
        hop removed. Under `--test-enable` Odoo's own `_pre_render_qweb_pdf`
        falls back to HTML rather than shelling out to wkhtmltopdf — the hook
        under test wraps the outer call either way, and the HTML body is what
        lets these tests assert WHICH record was rendered.
        """
        content, _kind = self.Report._render_qweb_pdf(report_name, res_ids)
        return content.decode('utf-8', 'replace') if isinstance(content, bytes) else content


@tagged('post_install', '-at_install')
class TestEveryRealCallerStamps(PrintFunnelCase):
    """Acceptance criterion 1. The test this replaces asserted `printed_at is
    None` twice — both assertions negative — and nothing in the repository
    requested `/report/pdf/` at all.
    """

    def test_the_barcode_stations_raw_url_stamps_the_label(self):
        """`/report/pdf/<report>/<asset_id>`. No Python of ours runs on the way
        in, which is why the stamp has to live at the render layer.
        """
        asset = self._asset()
        label = asset.active_tag_id

        body = self._render(MEDIUM, [asset.id])

        self.assertIn(label.name, body,
                      'the rendered label carries this asset\'s tag number')
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'printed')
        self.assertTrue(label.printed_date, 'printed_at was recorded')
        self.assertEqual(label.printed_by, self.env.user,
                         'and who issued the print instruction')

    def test_odoos_own_print_menu_stamps_the_label(self):
        """The four reports carry `binding_model_id` on `nrs.asset`, so they
        appear in Odoo's Print menu with the list's `active_ids`.
        """
        asset = self._asset()
        label = asset.active_tag_id

        action = asset.action_print_asset_tag()
        res_ids, report_name = self._active_ids(action)
        self.assertEqual(res_ids, [asset.id],
                         'the report is handed ASSET ids')

        self._render(report_name, res_ids)
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'printed')
        self.assertTrue(label.printed_date)

    def test_the_batch_action_stamps_every_label_in_the_selection(self):
        assets = self._asset('H10 Batch A') | self._asset('H10 Batch B')
        labels = assets.mapped('active_tag_id')

        action = assets.action_batch_print_tags()
        res_ids, report_name = self._active_ids(action)
        self.assertEqual(sorted(res_ids), sorted(assets.ids))

        body = self._render(report_name, res_ids)
        for label in labels:
            self.assertIn(label.name, body)
        labels.invalidate_recordset()
        self.assertEqual(set(labels.mapped('label_state')), {'printed'})

    def test_the_label_wizard_hands_over_assets_and_stamps(self):
        """The wizard used to pass a `nrs.asset.tag.label` recordset into a
        report declared on `nrs.asset`, so it rendered whichever asset shared
        the number and the hook could not stamp. It now passes the assets.
        """
        asset = self._asset('H10 Wizard Asset')
        label = asset.active_tag_id
        wizard = self.env['nrs.asset.label.wizard'].create({
            'label_size': 'medium',
            'asset_ids': [(6, 0, asset.ids)],
        })

        action = wizard.action_print()
        res_ids, report_name = self._active_ids(action)
        self.assertEqual(res_ids, [asset.id],
                         'ASSET ids, not the label ids it used to send')

        body = self._render(report_name, res_ids)
        self.assertIn(label.name, body)
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'printed')
        self.assertTrue(label.printed_date)

    def test_the_wizards_copies_survive_the_translation(self):
        """`copies` duplicates the recordset. Translating labels to assets with
        `mapped('asset_id')` would collapse the repeats back to one each and
        silently print one label where three were asked for.
        """
        asset = self._asset('H10 Copies Asset')
        wizard = self.env['nrs.asset.label.wizard'].create({
            'label_size': 'medium',
            'copies': 3,
            'asset_ids': [(6, 0, asset.ids)],
        })
        res_ids, _report = self._active_ids(wizard.action_print())
        self.assertEqual(res_ids, [asset.id] * 3)

    def test_the_tag_forms_print_button_hands_over_its_asset(self):
        """`action_print_tag` sits on `nrs.asset.tag.label` and used to pass
        `self` — tag ids — into an asset report.
        """
        asset = self._asset('H10 Tag Form Asset')
        label = asset.active_tag_id

        res_ids, report_name = self._active_ids(label.action_print_tag())
        self.assertEqual(res_ids, [asset.id])

        body = self._render(report_name, res_ids)
        self.assertIn(label.name, body)
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'printed')


@tagged('post_install', '-at_install')
class TestTheAmbiguousCallIsRefused(PrintFunnelCase):
    """Acceptance criterion 2. The two id spaces collide by construction, so a
    caller has to say which it means — and the only way to say it is to pass a
    recordset of the report's own model. Anything else is refused at the
    boundary rather than guessed at three layers down.
    """

    def test_a_label_recordset_into_a_tag_report_raises_naming_both_models(self):
        asset = self._asset('H10 Ambiguous Asset')
        report = self.env.ref('myservice_asset_register.action_report_asset_tag')

        with self.assertRaises(UserError) as caught:
            report.report_action(asset.active_tag_id)

        message = str(caught.exception)
        self.assertIn('nrs.asset.tag.label', message,
                      'the message names what was passed')
        self.assertIn('nrs.asset', message,
                      'and what the report actually renders')
        self.assertIn('collide', message,
                      'and why it cannot be resolved further down')

    def test_the_refusal_is_loud_rather_than_a_silent_wrong_render(self):
        """The point of raising: before this, the call succeeded and produced a
        PDF of a different machine's label.
        """
        asset = self._asset('H10 Silent Asset')
        report = self.env.ref('myservice_asset_register.action_report_asset_tag')
        self.assertTrue(report.report_action(asset),
                        'an asset recordset is the contract and still works')

    def test_a_non_tag_report_is_not_policed(self):
        """The rule is about the four tag labels, whose id space collides with
        their own callers'. It is not a general restriction on reports.
        """
        report = self.env.ref('base.report_ir_model_overview',
                              raise_if_not_found=False)
        if not report:
            self.skipTest('base.report_ir_model_overview not installed')
        self.assertNotIn(report.report_name,
                         self.env['ir.actions.report']._TAG_LABEL_REPORTS)


@tagged('post_install', '-at_install')
class TestTheStampIsHonest(PrintFunnelCase):

    def test_a_reprint_does_not_walk_an_affixed_label_backwards(self):
        asset = self._asset('H10 Affixed Asset')
        label = asset.active_tag_id
        label._mark_affixed(label.name, affixed_by_name='Tag Unit')
        self.assertEqual(label.label_state, 'affixed')

        self._render(MEDIUM, [asset.id])

        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'affixed',
                         'reprinting a label already on an asset does not make '
                         'the asset less tagged')

    def test_res_ids_that_are_no_assets_stamp_nothing_and_do_not_raise(self):
        """Bookkeeping never fails a print. A missing id is an under-record,
        which is the safe direction.

        The hook is called directly: rendering a non-existent id raises inside
        Odoo's own template evaluation, before this code is reached, so going
        through `_render` would test core's MissingError and not ours.
        """
        missing = self.Asset.search([], order='id desc', limit=1).id + 10_000
        report = self.env.ref('myservice_asset_register.action_report_asset_tag')
        self.Report._mark_printed_for([missing], report)   # must not raise

    def test_a_failing_stamp_does_not_abort_the_transaction(self):
        """The `try` around the stamp is only honest inside a savepoint.

        Swallowing a DATABASE error without one leaves the transaction aborted,
        so the next query anywhere in the request fails with "current
        transaction is aborted" — the print still breaks, just further away and
        complaining about something else.
        """
        asset = self._asset('H10 Savepoint Asset')

        def exploding(self_, report_ref, res_ids):
            # A real SQL error, not a Python one: only a DB error poisons the
            # cursor, so `raise ValueError` here would prove nothing.
            self_.env.cr.execute("SELECT 1 FROM a_table_that_does_not_exist")

        with patch.object(type(self.Report), '_stamp_printed_tags', exploding):
            self._render(MEDIUM, [asset.id])

        # The transaction is still usable, which is the whole claim.
        self.assertTrue(self.Asset.search([('id', '=', asset.id)]),
                        'the cursor survived the failed stamp')

    def test_a_report_that_is_not_a_tag_label_stamps_nothing(self):
        asset = self._asset('H10 Untouched Asset')
        label = asset.active_tag_id
        other = self.env.ref('base.report_ir_model_overview',
                             raise_if_not_found=False)
        if not other:
            self.skipTest('base.report_ir_model_overview not installed')
        self.Report._stamp_printed_tags(other.report_name, [asset.id])
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'issued')


@tagged('post_install', '-at_install', 'pdf')
class TestItReallyRendersAPdf(PrintFunnelCase):
    """`--test-enable` makes Odoo's own `_pre_render_qweb_pdf` fall back to HTML
    rather than shelling out to wkhtmltopdf, so every test above proves the
    funnel without ever producing a PDF. This one forces the real thing, so the
    claim "a label printed through each real caller records printed_at" is
    backed by an actual PDF at least once.
    """

    def test_forcing_the_real_renderer_produces_a_pdf_and_stamps(self):
        asset = self._asset('H10 Real PDF Asset')
        label = asset.active_tag_id

        content, kind = self.Report.with_context(
            force_report_rendering=True)._render_qweb_pdf(MEDIUM, [asset.id])

        self.assertEqual(kind, 'pdf')
        self.assertTrue(content.startswith(b'%PDF'),
                        'wkhtmltopdf produced a real PDF')
        label.invalidate_recordset()
        self.assertEqual(label.label_state, 'printed')
        self.assertTrue(label.printed_date)


@tagged('post_install', '-at_install')
class TestTheFourReportsAgreeOnTheirModel(PrintFunnelCase):
    """The A4 sheet was declared twice — `data/asset_tag_report.xml` on
    `nrs.asset` and `views/asset_tag_views.xml` on `nrs.asset.tag.label` — and
    the views file loads later, so the second won on all eight tenants. The
    sheet template renders `asset_tag_label_body`, which reads `o.asset_tag`,
    `o.asset_code`, `o.floor_room` and `o.get_barcode_base64`; none of those is
    on a tag label, so the A4 sheet had never rendered anything anywhere.

    A `<function>` in the data file already rewrote `model` on every upgrade
    and was overwritten again minutes later by the duplicate. That is why this
    lives in a test and not in another force-update.
    """

    _ACTIONS = (
        'myservice_asset_register.action_report_asset_tag',
        'myservice_asset_register.action_report_asset_tag_small',
        'myservice_asset_register.action_report_asset_tag_large',
        'myservice_asset_register.action_report_asset_tag_sheet',
    )

    def test_every_tag_label_report_renders_nrs_asset(self):
        for xmlid in self._ACTIONS:
            action = self.env.ref(xmlid)
            self.assertEqual(
                action.model, 'nrs.asset',
                '%s renders %s; the label templates read fields that only '
                'exist on nrs.asset' % (xmlid, action.model))

    def test_no_tag_label_report_is_bound_to_the_tag_label_list(self):
        """A binding IS an id space: Odoo hands the report the selected
        records' ids with no translation anywhere.
        """
        for xmlid in self._ACTIONS:
            action = self.env.ref(xmlid)
            if action.binding_model_id:
                self.assertEqual(
                    action.binding_model_id.model, 'nrs.asset',
                    '%s is bound to %s, so its Print menu would hand it %s '
                    'ids' % (xmlid, action.binding_model_id.model,
                             action.binding_model_id.model))

    def test_printing_a_selection_of_labels_translates_and_stamps(self):
        """`action_print_labels` replaces the binding the duplicate declaration
        was reaching for.
        """
        assets = self._asset('H10 Sheet A') | self._asset('H10 Sheet B')
        labels = assets.mapped('active_tag_id')

        res_ids, report_name = self._active_ids(labels.action_print_labels())
        self.assertEqual(sorted(res_ids), sorted(assets.ids))
        self.assertEqual(report_name, SHEET)

        body = self._render(report_name, res_ids)
        for label in labels:
            self.assertIn(label.name, body)
        labels.invalidate_recordset()
        self.assertEqual(set(labels.mapped('label_state')), {'printed'})

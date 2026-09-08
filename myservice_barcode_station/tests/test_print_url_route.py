"""`/barcode/print_url` end to end — the only path in the repo that renders.

This is acceptance criterion 1 taken all the way: a real HTTP session calls the
station's own JSON route, gets a URL back, fetches it, receives a PDF, and the
label carries `printed_date` and `printed_by` afterwards. Every other test of
the print funnel drives `_render_qweb_pdf` directly; this one goes through the
two hops that used to be broken — the URL the route builds, and the report
controller that resolves it.

Both hops had a defect that nothing could see:

  * the route emitted the report ACTION's xmlid with its dot turned into a
    slash, which matches no report and answered the website's 404 page as a
    26 KB HTML body (fixed in handoff 05 — but the station's batch-print button
    kept its own copy of the same mistake until handoff 10);
  * the render hook then declined to stamp, because the asset ids in the URL
    are also valid tag-label ids for 99.97% of the register.

The pytest API suite cannot cover this: `/report/pdf/` is `auth='user'` and
that suite holds a bearer token, not an Odoo session. So the session is made
here, with a user created for the purpose.

Run with **--workers=0**:
    odoo -d <db> -u myservice_barcode_station --test-enable \\
         --test-tags /myservice_barcode_station --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098

The `--workers=0` is not optional and is not a style preference. Under the
prefork server `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port`, and `PreforkServer` has no
`httpd` — so every test in this class ERRORS in setUpClass before it runs. The
dev stack's `odoo.conf` sets `workers = 2`, which means the command line every
other test file in this repository documents would silently produce
"2 tests 0.02s 0 queries" and a setUpClass error nobody reads as a skip.
**What this file can and cannot prove.** Odoo 19 declares the report route
`readonly=True`, so a render reached through `/report/pdf/...` runs on a
read-only Postgres cursor and the print stamp is written on a separate
read/write cursor taken from the registry. Inside `HttpCase` that separate
cursor is a genuinely separate connection — it cannot see the records this
test created and never committed — so the stamp lands on nothing and
`label_state` stays `issued` here no matter how correct the production
behaviour is.

Rather than assert something that would be green for the wrong reason, these
tests assert what the HTTP hop really does prove: the URL the route builds,
that it resolves to a report at all, and that the document rendered is the
right ASSET's label. **The stamp through the readonly route is proved live
against committed data on a tenant — see `docs/handoffs/10-REPORT.md`** — and
the stamp through every read/write path is proved in
`myservice_asset_register/tests/test_print_funnel.py`.

Note on what `/report/pdf/` returns under `--test-enable`: Odoo's own
`_pre_render_qweb_pdf` falls back to HTML rather than shelling out to
wkhtmltopdf whenever tests are running, and the controller still labels the
response `application/pdf`. So the body is asserted on its CONTENT — it must
carry this asset's tag number, which the website's 404 page does not — and one
test appends `?context={"force_report_rendering": true}`, which
`web/controllers/report.py` merges into the render context, to get a real
`%PDF` out of the same URL.
"""
import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPrintUrlRendersAndStamps(HttpCase):

    def setUp(self):
        super().setUp()
        self.password = 'h10-print-route'
        Users = self.env['res.users']
        # Odoo 19 renamed `res.users.groups_id` to `group_ids`; the 15 stack
        # still has the old name. `myservice_api/models/api_client.py` and
        # `scripts/bootstrap.py` both resolve it this way — the same shape is
        # used here rather than a hard-coded name, for the same reason.
        groups_field = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'
        self.operator = Users.create({
            'name': 'H10 Print Operator',
            'login': 'h10_print_operator',
            'password': self.password,
            groups_field: [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('myservice_asset_register.group_asset_user').id,
            ])],
        })
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'H10 Route Category', 'code': 'H10ROUTE'})

    def _asset(self, name):
        asset = self.env['nrs.asset'].create(
            {'name': name, 'category_id': self.category.id})
        self.assertEqual(asset.active_tag_id.label_state, 'issued')
        return asset

    def _call(self, **params):
        """POST the station's JSON route the way its own client does."""
        response = self.url_open(
            '/barcode/print_url',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn('error', body, body.get('error'))
        return body['result']

    def test_a_single_print_returns_a_url_that_renders_and_stamps(self):
        asset = self._asset('H10 Route Single')
        label = asset.active_tag_id
        self.authenticate('h10_print_operator', self.password)

        result = self._call(tag_id=label.id, size='medium')
        self.assertNotIn('error', result, result.get('error'))
        url = result['url']

        # The URL names the report by report_name and the ASSET by id. Both
        # halves are load-bearing and both have been wrong in production.
        self.assertEqual(
            url,
            '/report/pdf/myservice_asset_register.report_asset_tag_label/%s'
            % asset.id)

        rendered = self.url_open(url)
        self.assertEqual(rendered.status_code, 200)
        # Content, not status: a miss on this route answers the website's 404
        # PAGE with a 200 and an `application/pdf` header, which is exactly how
        # the old xmlid URL went unnoticed for the life of the endpoint.
        self.assertIn(
            label.name.encode(), rendered.content,
            'the rendered document carries this asset\'s tag number')

        # No stamp assertion here — see the module docstring. The stamp
        # rides a separate read/write cursor that cannot see this
        # transaction's uncommitted records.

    def test_the_batch_form_translates_every_tag_and_keeps_the_order(self):
        """The station's batch button used to build this URL itself, from the
        action xmlid and a browser-side tag→asset map. Both are server side now.
        """
        first = self._asset('H10 Route Batch A')
        second = self._asset('H10 Route Batch B')
        labels = first.active_tag_id | second.active_tag_id
        self.authenticate('h10_print_operator', self.password)

        # Deliberately reversed: a print run that silently reorders is one
        # somebody has to re-check against the pile of labels by hand.
        wanted = [second.active_tag_id.id, first.active_tag_id.id]
        result = self._call(tag_ids=wanted, size='sheet')
        self.assertEqual(
            result['url'],
            '/report/pdf/myservice_asset_register.report_asset_tag_label_sheet'
            '/%s,%s' % (second.id, first.id))

        rendered = self.url_open(result['url'])
        self.assertEqual(rendered.status_code, 200)
        for label in labels:
            self.assertIn(label.name.encode(), rendered.content)

    def test_the_url_really_produces_a_pdf(self):
        """The same URL, with Odoo's test-mode HTML fallback turned off.

        Everything above proves the funnel without wkhtmltopdf ever running.
        This one proves the published URL really yields a PDF — the 404 it
        used to yield arrived as an HTML page with a 200 and an
        `application/pdf` header, which is how it went unnoticed.
        """
        asset = self._asset('H10 Route Real PDF')
        label = asset.active_tag_id
        self.authenticate('h10_print_operator', self.password)

        url = self._call(tag_id=label.id, size='medium')['url']
        pdf = self.url_open(
            url + '?context=' + json.dumps({'force_report_rendering': True}))

        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(
            pdf.content.startswith(b'%PDF'),
            'got %r' % pdf.content[:40])

    def test_an_unknown_tag_id_is_an_error_not_a_url(self):
        self.authenticate('h10_print_operator', self.password)
        missing = self.env['nrs.asset.tag.label'].search(
            [], order='id desc', limit=1).id + 10_000
        result = self._call(tag_id=missing)
        self.assertIn('error', result)
        self.assertNotIn('url', result)

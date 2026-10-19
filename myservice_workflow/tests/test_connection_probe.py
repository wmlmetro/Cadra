"""Test Connection that tells the truth — handoff 64 §3b.

The button GET `<base URL>/ping` with the bearer token. Vendra has no
`/ping`, and Frappe answers 401 to any bearer request on a path no auth hook
covers, so it said *failed* for every Vendra target whether or not delivery
worked. For an `asset_events` target it now POSTs a probe (no event id) to
each configured endpoint with the delivery's own headers: 400 means the
token got through and the receiver refused the probe for its content.

Run with:
    odoo -d test19f -u myservice_workflow --test-enable \\
         --test-tags /myservice_workflow:TestConnectionProbe \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

_POST = 'requests.post'
_GET = 'requests.get'


def _answer(status):
    r = MagicMock()
    r.status_code = status
    r.text = ''
    return r


@tagged('post_install', '-at_install')
class TestConnectionProbe(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.target = self.env['workflow.config'].create({
            'name': 'Vendra (64 probe)', 'purpose': 'asset_events',
            'adapter_type': 'rest', 'rest_base_url': 'http://vendra.test/',
            'rest_endpoint_event': '/api/method/vendra_network.api.cadra.tag_event',
            'rest_endpoint_register_state':
                '/api/method/vendra_network.api.cadra.register_state_event',
            'rest_auth_type': 'bearer', 'rest_api_key': 'k64',
            'event_enabled': False})

    def test_a_400_on_both_endpoints_is_reachable_and_accepted(self):
        with patch(_POST, return_value=_answer(400)) as post, \
                patch(_GET) as get:
            result = self.target.action_test_connection()
        get.assert_not_called()          # no /ping any more
        message = result['params']['message']
        self.assertEqual(message, (
            'Tag events: reachable, token accepted. '
            'Register-state events: reachable, token accepted.'))
        urls = [c.args[0] for c in post.call_args_list]
        self.assertEqual(urls, [
            'http://vendra.test/api/method/vendra_network.api.cadra.tag_event',
            'http://vendra.test/api/method/vendra_network.api.cadra.'
            'register_state_event'])
        for call in post.call_args_list:
            headers = call.kwargs['headers']
            self.assertEqual(headers['Authorization'], 'Bearer k64')
            # Never an event: no id to dedupe on, so it cannot be stored.
            self.assertNotIn('X-Idempotency-Key', headers)
            self.assertNotIn('X-Event-Id', headers)
            self.assertNotIn('event_id', call.kwargs['json'])

    def test_a_401_on_one_endpoint_says_which_and_why(self):
        with patch(_POST, side_effect=[_answer(400), _answer(401)]):
            with self.assertRaises(UserError) as raised:
                self.target.action_test_connection()
        text = str(raised.exception)
        self.assertIn('Tag events: reachable, token accepted.', text)
        self.assertIn('Register-state events: reachable, but the token was '
                      'refused (HTTP 401)', text)

    def test_unreachable_and_missing_paths_are_said(self):
        with patch(_POST, side_effect=[requests.ConnectionError('down'),
                                       _answer(404)]):
            with self.assertRaises(UserError) as raised:
                self.target.action_test_connection()
        text = str(raised.exception)
        self.assertIn('Tag events: unreachable (ConnectionError).', text)
        self.assertIn('nothing receives at this path (HTTP 404)', text)

    def test_no_register_state_endpoint_is_said_not_failed(self):
        self.target.rest_endpoint_register_state = False
        with patch(_POST, return_value=_answer(400)) as post:
            result = self.target.action_test_connection()
        self.assertEqual(post.call_count, 1)
        self.assertIn('Register-state events: no endpoint set, so none are '
                      'sent.', result['params']['message'])

    def test_another_purpose_keeps_the_ping(self):
        sap = self.env['workflow.config'].create({
            'name': 'SAP (64 probe)', 'purpose': 'workspace',
            'adapter_type': 'rest', 'rest_base_url': 'http://sap.test',
            'rest_auth_type': 'bearer', 'rest_api_key': 'k'})
        with patch(_GET, return_value=_answer(200)) as get, \
                patch(_POST) as post:
            sap.action_test_connection()
        self.assertEqual(get.call_args.args[0], 'http://sap.test/ping')
        post.assert_not_called()

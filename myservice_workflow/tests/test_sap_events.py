"""The SAP asset legs — INT-06, INT-07 and INT-09.

The transport underneath these events was proven in `test_outbound_events.py`
and is deliberately not re-proven here: backoff, dead-lettering, `event_id`
stability and the write guard belong to the queue and are the same machinery
whichever receiver is on the other end. What is new — and therefore what this
file argues about — is the *triggers* (a capitalisation follows a confirmed
tag, never a record creation), the *payloads* (one authoritative cost, a null
asset class rather than a guess), the *response* (INT-07 writing SAP's own
number back onto the register) and the *dual-code control* the whole thing
exists to make visible.

Run with:
    odoo -d <db> -u myservice_workflow --test-enable \\
         --test-tags /myservice_workflow --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
import json
from unittest.mock import patch

from odoo import fields
from odoo.tools import mute_logger
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

SAP_LOGGER = 'odoo.addons.myservice_workflow.models.sap_asset_events'

EVENT_CREATE = 'asset.master.create'
EVENT_TRANSFERRED = 'asset.transferred'
EVENT_CUSTODIAN = 'asset.custodian_changed'
EVENT_DISPOSED = 'asset.disposed'
EVENT_TAG_AFFIXED = 'asset.tag.affixed'


class FakeAdapter:
    """Stands in for SAP. Returns whatever the test told it to."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def deliver(self, payload, event_id, request_ref=None):
        self.calls.append({'payload': payload, 'event_id': event_id,
                           'request_ref': request_ref})
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def ok_result(body=None, status=200, ref='SAP-DOC-0001'):
    """A delivered INT-06. `body` is SAP's answer — the INT-07 half."""
    if body is None:
        body = {}
    return {'ok': True, 'retryable': False, 'status': status,
            'body': body if isinstance(body, str) else json.dumps(body),
            'external_ref': ref, 'acknowledged': True, 'error': None}


def fail_result(status=503, retryable=True):
    return {'ok': False, 'retryable': retryable, 'status': status,
            'body': 'SAP gateway said no', 'external_ref': None,
            'acknowledged': False, 'error': 'HTTP %s' % status}


@tagged('post_install', '-at_install')
class TestSAPAssetEvents(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['workflow.dispatch.log']
        # `get_event_config` takes the first active row for a purpose, so a
        # target that arrived with a data file would silently be resolved
        # ahead of the one this file created. Start from a tenant whose only
        # event targets are the ones each test makes.
        self.env['workflow.config'].search([
            ('purpose', 'in', ('asset_events', 'sap_assets')),
        ]).write({'active': False})

        self.category = self.env['nrs.asset.category'].create({
            'name': 'INT-06 Test Category',
            'code': 'T06',
        })
        self.config = self.env['workflow.config'].create({
            'name': 'SAP (test)',
            'purpose': 'sap_assets',
            'adapter_type': 'stub',
            'event_enabled': True,
            'sap_company_code': 'NRS1',
            'retry_max_attempts': 3,
            'retry_base_seconds': 60,
            'retry_cap_seconds': 600,
        })

    # ── helpers ───────────────────────────────────────────────────────

    def _asset(self, **overrides):
        vals = {
            'name': 'INT-06 Probe',
            'category_id': self.category.id,
            'serial_number': 'SN-INT06-001',
            'grn_reference': 'GRN-2026-00042',
            'purchase_order_reference': 'PO-2026-00913',
            'purchase_vendor': 'Zenith Systems Ltd',
            'import_source': 'vendra',
        }
        vals.update(overrides)
        return self.env['nrs.asset'].create(vals)

    def _employee(self, name):
        return self.env['hr.employee'].sudo().with_company(
            self.env.company).create({'name': name})

    def _location(self, name):
        return self.env['generic.location'].create({'name': name})

    def _affix(self, asset, **kwargs):
        label = asset.active_tag_id
        self.assertTrue(label, 'asset should have an auto-generated tag')
        label._mark_affixed(label.name, **kwargs)
        return label

    def _events(self, asset, event_type):
        return self.Log.search([('asset_id', '=', asset.id),
                                ('event_type', '=', event_type)])

    def _payload(self, event):
        event.ensure_one()
        return json.loads(event.payload_sent)

    def _deliver(self, event, adapter):
        with patch.object(type(self.config), '_get_adapter',
                          return_value=adapter):
            return event._deliver_once()

    # ── INT-06: what makes a capitalisation due ───────────────────────

    def test_a_confirmed_tag_is_what_asks_sap_to_capitalise(self):
        """Tagging is the trigger, and the asset says so while it waits.

        An asset record is a claim; a confirmed tag is evidence. Putting a
        value on NRS's books for something nobody has proven exists in a
        building is what the tag capture work was built to prevent.
        """
        asset = self._asset()
        self.assertEqual(asset.sap_posting_state, 'none')

        self._affix(asset, affixed_by_name='J. Okafor')

        events = self._events(asset, EVENT_CREATE)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.status, 'pending')
        self.assertEqual(events.attempts, 0)
        self.assertEqual(events.config_id, self.config,
                         'the SAP leg must post to the SAP target')
        # Snapshotted, so retuning the SAP policy cannot resurrect or kill a
        # capitalisation already in flight.
        self.assertEqual(events.max_attempts, 3)
        self.assertEqual(asset.sap_posting_state, 'queued')

        payload = self._payload(events)
        self.assertEqual(payload['event'], EVENT_CREATE)
        self.assertEqual(payload['event_id'], events.event_id,
                         'the body must carry the same key as the header')
        self.assertEqual(payload['source'], 'cadra')
        self.assertEqual(payload['company_code'], 'NRS1',
                         'a SAP asset number is only unique within a company '
                         'code, so every message carries one')

    def test_a_repeat_affix_confirmation_does_not_post_a_second_master(self):
        """One physical act is one capitalisation request.

        The event fires on the state TRANSITION: `_mark_affixed` refuses to
        rewrite the original record, so a retrying client does not ask SAP to
        capitalise the same asset twice.
        """
        asset = self._asset()
        label = asset.active_tag_id
        label._mark_affixed(label.name, affixed_by_name='J. Okafor')
        label._mark_affixed(label.name, affixed_by_name='Someone Else')

        self.assertEqual(len(self._events(asset, EVENT_CREATE)), 1)

    def test_an_untagged_asset_is_never_posted_to_sap(self):
        """Printing a label is not evidence that anything was tagged."""
        asset = self._asset()
        self.assertFalse(self._events(asset, EVENT_CREATE))

        asset.active_tag_id._mark_printed()

        self.assertEqual(asset.active_tag_id.label_state, 'printed')
        self.assertFalse(self._events(asset, EVENT_CREATE),
                         'a print instruction is not a capitalisation')
        self.assertEqual(asset.sap_posting_state, 'none')

    def test_a_tenant_with_no_sap_target_queues_nothing_and_does_not_fail(self):
        """The ordinary state on every tenant that has no SAP.

        Queueing events that could only ever dead-letter would turn "no SAP
        here" into a permanent alarm — and the capture must stand either way.
        """
        self.config.unlink()
        asset = self._asset()
        self._affix(asset)

        self.assertFalse(self._events(asset, EVENT_CREATE))
        self.assertEqual(asset.sap_posting_state, 'none')
        # Transport being unconfigured must never cost Cadra the record.
        self.assertEqual(asset.active_tag_id.label_state, 'affixed')

    def test_an_asset_that_already_carries_a_sap_number_is_not_posted_again(self):
        """A legacy asset already on SAP's books is not capitalised twice.

        Linking the existing SAP asset numbers onto the legacy register is how
        the opening balance of the dual-code control gets built; tagging those
        assets afterwards must not ask SAP to create an asset master it
        already has.
        """
        asset = self._asset(sap_asset_number='4000009001',
                            sap_code_source='import')
        self._affix(asset)

        self.assertFalse(self._events(asset, EVENT_CREATE))
        self.assertEqual(asset.sap_posting_state, 'none')

    # ── INT-06: the payload ───────────────────────────────────────────

    def test_the_asset_master_carries_both_codes_the_tag_and_the_provenance(self):
        """Everything SAP needs to post it and everything an auditor needs to
        trace it back: the Cadra code, the physical label, and the PO/GRN the
        asset arrived on."""
        asset = self._asset()
        label = self._affix(asset, affixed_by_name='J. Okafor')
        payload = self._payload(self._events(asset, EVENT_CREATE))
        block = payload['asset']

        self.assertEqual(block['cadra_asset_code'], asset.asset_code)
        self.assertEqual(block['cadra_asset_id'], asset.id)
        self.assertEqual(block['description'], 'INT-06 Probe')
        self.assertEqual(block['serial_number'], 'SN-INT06-001')
        # Cadra registers one row per physical unit — a GRN line of five
        # laptops is five assets with five tags. There is nothing else to send.
        self.assertEqual(block['quantity'], 1)

        self.assertEqual(block['procurement']['po_number'], 'PO-2026-00913')
        self.assertEqual(block['procurement']['grn_number'], 'GRN-2026-00042')
        self.assertEqual(block['procurement']['vendor_name'],
                         'Zenith Systems Ltd')

        self.assertEqual(block['tag']['number'], label.name)
        self.assertEqual(block['tag']['label_state'], 'affixed')
        self.assertTrue(block['tag']['affixed_at'].endswith('Z'),
                        'timestamps must carry an explicit offset')
        self.assertTrue(payload['occurred_at'].endswith('Z'))

    def test_the_cost_basis_names_the_field_the_amount_came_from(self):
        """One authoritative number, and a word saying where it came from.

        Two parallel cost fields exist on the register. Sending both and
        leaving SAP to choose would make the amount on a capitalisation
        ambiguous, which is worse than making it missing.
        """
        both = self._asset(acquisition_cost=1250000.0, purchase_value=999.0)
        self._affix(both)
        cap = self._payload(
            self._events(both, EVENT_CREATE))['asset']['capitalisation']
        self.assertEqual(cap['cost_basis'], 'acquisition_cost')
        self.assertEqual(cap['amount'], 1250000.0)

        purchase_only = self._asset(purchase_value=750000.0)
        self._affix(purchase_only)
        cap = self._payload(
            self._events(purchase_only, EVENT_CREATE))['asset']['capitalisation']
        self.assertEqual(cap['cost_basis'], 'purchase_value')
        self.assertEqual(cap['amount'], 750000.0)

        # The overwhelming majority of the live register. Sent honestly as
        # zero so SAP can reject it — a capitalisation Cadra quietly declined
        # to request would be invisible to both sides.
        costless = self._asset()
        self._affix(costless)
        event = self._events(costless, EVENT_CREATE)
        self.assertEqual(len(event), 1,
                         'a missing cost must not suppress the event')
        cap = self._payload(event)['asset']['capitalisation']
        self.assertEqual(cap['cost_basis'], 'none')
        self.assertEqual(cap['amount'], 0.0)

    def test_an_unmapped_category_posts_a_null_asset_class_not_a_guess(self):
        """A null is rejected on the way in, which looks like a failure. The
        wrong asset class gets the wrong useful life and the wrong
        depreciation key, and nothing about that looks like anything.
        """
        unmapped = self._asset()
        self._affix(unmapped)
        klass = self._payload(
            self._events(unmapped, EVENT_CREATE))['asset']['asset_class']
        self.assertIsNone(klass['sap_asset_class'])
        # Cadra's own classification still travels, so the mapping can be
        # completed from the message itself.
        self.assertEqual(klass['cadra_category_code'], 'T06')
        self.assertEqual(klass['cadra_category'], 'INT-06 Test Category')

        # ...and it is null because the mapping is absent, not always null.
        self.category.sap_asset_class = '3100'
        mapped = self._asset()
        self._affix(mapped)
        klass = self._payload(
            self._events(mapped, EVENT_CREATE))['asset']['asset_class']
        self.assertEqual(klass['sap_asset_class'], '3100')

    # ── INT-07: reading SAP's answer back ─────────────────────────────

    def test_a_returned_sap_number_lands_as_evidence_not_as_a_claim(self):
        """The second half of the dual-code control closing.

        `sap_code_source` is what separates a number SAP returned from one a
        person typed in; the audit is the reason the two must not look alike.
        """
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset, EVENT_CREATE)
        self.assertEqual(asset.sap_reconciliation_state, 'pending')

        self.assertTrue(self._deliver(event, FakeAdapter(ok_result({
            'cadra_asset_code': asset.asset_code,
            'sap_asset_number': '4000001234',
            'sap_asset_subnumber': '0000',
            'company_code': 'NRS1',
            'asset_class': '3100',
            'capitalisation_date': '2026-09-06',
            'capitalised_amount': 1250000.0,
        }))))

        self.assertEqual(asset.sap_asset_number, '4000001234')
        self.assertEqual(asset.sap_asset_subnumber, '0000')
        self.assertEqual(asset.sap_code_source, 'integration')
        self.assertEqual(asset.sap_posting_state, 'posted')
        self.assertEqual(asset.sap_reconciliation_state, 'reconciled')
        self.assertTrue(asset.sap_synced_at)
        # SAP's posted date, not the one Cadra proposed — period-close rules
        # are SAP's to apply.
        self.assertEqual(fields.Date.to_string(asset.sap_capitalisation_date),
                         '2026-09-06')
        self.assertIn('4000001234', event.delivery_history)

    def test_a_response_for_a_different_asset_is_refused_and_recorded(self):
        """Correlation has gone wrong somewhere, and writing the code anyway
        would link a SAP asset to the wrong physical thing — exactly what the
        unique-code constraint was added to prevent."""
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset, EVENT_CREATE)

        with mute_logger(SAP_LOGGER):
            self._deliver(event, FakeAdapter(ok_result({
                'cadra_asset_code': 'NRS/AST/999999',
                'sap_asset_number': '4000009999',
            })))

        self.assertFalse(asset.sap_asset_number)
        self.assertFalse(asset.sap_code_source)
        # Refused loudly enough that somebody can find it afterwards.
        self.assertIn('response rejected', event.delivery_history)
        self.assertIn('NRS/AST/999999', event.delivery_history)

    def test_not_capitalised_is_recorded_and_is_not_a_sap_asset_number(self):
        """SAP declining to capitalise is a legitimate answer, and it is not
        the same fact as an asset still awaiting its code."""
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset, EVENT_CREATE)

        self._deliver(event, FakeAdapter(ok_result({
            'status': 'not_capitalised',
            'reason': 'below the capitalisation threshold',
        })))

        self.assertFalse(asset.sap_asset_number)
        self.assertFalse(asset.sap_code_source)
        self.assertEqual(asset.sap_posting_state, 'posted',
                         'SAP took the message; it just declined to book it')
        self.assertIn('declined to capitalise', event.delivery_history)
        notes = self.env['mail.message'].search([
            ('model', '=', 'nrs.asset'), ('res_id', '=', asset.id),
        ])
        self.assertTrue(
            any('did not' in (m.body or '') for m in notes),
            'the decision must reach the asset, not just the log')

    def test_a_body_that_is_not_json_is_a_delivery_but_not_a_code(self):
        """Delivered is not the same as acknowledged with a number.

        Marking the asset reconciled on a `200` alone would record a SAP code
        that does not exist.
        """
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset, EVENT_CREATE)

        with mute_logger(SAP_LOGGER):
            self.assertTrue(self._deliver(
                event, FakeAdapter(ok_result('<html>Gateway OK</html>'))))

        self.assertFalse(asset.sap_asset_number)
        self.assertEqual(asset.sap_posting_state, 'posted')
        self.assertEqual(asset.sap_reconciliation_state, 'pending',
                         'still awaiting its code, not reconciled')

    def test_a_response_that_omits_a_figure_does_not_blank_the_one_on_file(self):
        """Absent and zero are different answers, and only one is a figure."""
        asset = self._asset()
        asset.sudo().write({
            'sap_net_book_value': 500000.0,
            'sap_accumulated_depreciation': 120000.0,
        })

        self.assertTrue(asset._set_sap_master({
            'sap_asset_number': '4000002222',
            'capitalised_amount': 900000.0,
        }))

        self.assertEqual(asset.sap_asset_number, '4000002222')
        self.assertEqual(asset.sap_capitalised_amount, 900000.0)
        self.assertEqual(asset.sap_net_book_value, 500000.0)
        self.assertEqual(asset.sap_accumulated_depreciation, 120000.0)

    # ── INT-09: lifecycle ─────────────────────────────────────────────

    def test_a_completed_transfer_is_one_move_not_a_move_and_a_reassignment(self):
        """A transfer writes the custodian as well as the location.

        Raising `asset.transferred` and `asset.custodian_changed` for the same
        physical act would give SAP two events a receiver has no way to tell
        from a move followed by a reassignment.
        """
        here = self._location('HQ Store')
        there = self._location('Ikeja Office')
        outgoing = self._employee('A. Adeyemi')
        incoming = self._employee('B. Balogun')
        asset = self._asset(sap_asset_number='4000003333',
                            sap_code_source='import',
                            location_id=here.id,
                            custodian_id=outgoing.id)

        transfer = self.env['nrs.asset.transfer'].create({
            'asset_id': asset.id,
            'from_location_id': here.id,
            'to_location_id': there.id,
            'from_custodian_id': outgoing.id,
            'to_custodian_id': incoming.id,
            'reason': 'Office relocation',
        })
        transfer.action_approve()
        transfer.action_complete()

        moves = self._events(asset, EVENT_TRANSFERRED)
        self.assertEqual(len(moves), 1)
        self.assertFalse(self._events(asset, EVENT_CUSTODIAN),
                         'the move already carries the custodian change')

        payload = self._payload(moves)
        self.assertEqual(payload['asset']['sap_asset_number'], '4000003333')
        self.assertEqual(payload['asset']['cadra_asset_code'], asset.asset_code)
        change = payload['change']
        self.assertEqual(change['transfer_reference'], transfer.name)
        self.assertEqual(change['reason'], 'Office relocation')
        self.assertEqual(change['from']['location']['name'], 'HQ Store')
        self.assertEqual(change['to']['location']['name'], 'Ikeja Office')
        self.assertEqual(change['from']['custodian']['name'], 'A. Adeyemi')
        self.assertEqual(change['to']['custodian']['name'], 'B. Balogun')

    def test_a_custodian_change_outside_a_transfer_raises_its_own_event(self):
        """Reassignment without a move is still a change SAP has to hear."""
        outgoing = self._employee('A. Adeyemi')
        incoming = self._employee('B. Balogun')
        asset = self._asset(sap_asset_number='4000004444',
                            sap_code_source='import',
                            custodian_id=outgoing.id)

        asset.write({'custodian_id': incoming.id})

        events = self._events(asset, EVENT_CUSTODIAN)
        self.assertEqual(len(events), 1)
        self.assertFalse(self._events(asset, EVENT_TRANSFERRED))
        change = self._payload(events)['change']
        self.assertEqual(change['from']['custodian']['name'], 'A. Adeyemi')
        self.assertEqual(change['to']['custodian']['name'], 'B. Balogun')
        self.assertTrue(change['changed_at'].endswith('Z'))

    def test_disposal_is_announced_with_the_reason_it_was_disposed_for(self):
        """SAP has to retire the asset master, and the reason is why."""
        asset = self._asset(sap_asset_number='4000005555',
                            sap_code_source='import')

        asset.write({
            'state': 'disposed',
            'disposal_reason': 'Beyond economic repair',
            'disposal_date': '2026-08-31',
            'condition': 'decommissioned',
        })

        events = self._events(asset, EVENT_DISPOSED)
        self.assertEqual(len(events), 1)
        change = self._payload(events)['change']
        self.assertEqual(change['disposal_type'], 'disposal')
        self.assertEqual(change['disposal_reason'], 'Beyond economic repair')
        self.assertEqual(change['disposal_date'], '2026-08-31')
        self.assertEqual(change['condition_at_disposal'], 'decommissioned')

    def test_a_disposal_beside_a_warranty_field_is_announced_ONCE_per_asset(
            self):
        """Handoff 34's verification pass. A write naming a warranty field is
        resolved one asset at a time, and the first draft did it by calling
        `write` again — from the TOP of the chain, so this override ran once
        for the set and once per asset, and SAP was told each asset had been
        disposed of twice. Two assets, one write, one event each."""
        one = self._asset(sap_asset_number='4000005571',
                          sap_code_source='import')
        two = self._asset(sap_asset_number='4000005572',
                          sap_code_source='import', serial_number='SN-2')

        (one | two).write({'state': 'disposed',
                           'warranty_reference': 'WC-AT-DISPOSAL'})

        self.assertEqual(len(self._events(one, EVENT_DISPOSED)), 1)
        self.assertEqual(len(self._events(two, EVENT_DISPOSED)), 1)
        self.assertEqual((one | two).mapped('warranty_reference'),
                         ['WC-AT-DISPOSAL', 'WC-AT-DISPOSAL'])

    def test_a_scrapping_is_announced_to_sap_as_a_RETIREMENT(self):
        """The one key on this event whose VALUE changed in handoff 16.

        `disposal_type` was the literal `'disposal'` on every event ever
        sent, because there was no field on the register to answer with.
        `SAP_DISPOSAL_TYPE` now maps Cadra's route onto the two words the
        requirements document §4.2 specifies, and the accounting line is
        that an asset which leaves through a transaction with somebody is a
        disposal while one that ceases to exist in place is a retirement.

        Asserted from THIS call site deliberately. The mapping table has its
        own exhaustive test, and a table proven correct in isolation says
        nothing about whether the payload builder reads it — which is the
        whole of what SAP will receive.
        """
        asset = self._asset(sap_asset_number='4000005560',
                            sap_code_source='import')
        asset.write({'state': 'disposed', 'disposal_method': 'scrapped'})

        change = self._payload(self._events(asset, EVENT_DISPOSED))['change']
        self.assertEqual(change['disposal_type'], 'retirement')
        self.assertEqual(change['disposal_method'], 'scrapped')

    def test_a_disposal_with_no_recorded_method_still_sends_the_old_value(self):
        """The non-breaking half, and the reason this change is additive.

        Every disposal SAP has ever received said `'disposal'`. An asset
        with no recorded method — which is every asset on every tenant
        today — must keep saying exactly that, or a live integration keying
        on the value starts seeing something new for records that did not
        change.
        """
        asset = self._asset(sap_asset_number='4000005561',
                            sap_code_source='import')
        asset.write({'state': 'disposed'})

        change = self._payload(self._events(asset, EVENT_DISPOSED))['change']
        self.assertEqual(change['disposal_type'], 'disposal')
        self.assertIsNone(change['disposal_method'])

    def test_the_disposal_event_carries_the_authorisation_and_the_proceeds(self):
        """§4.2 asks this event for an approver, and it never had one.

        The transfer event a hundred lines below has carried `approved_by`
        and `approved_at` since the day it was written; the disposal event
        announced that an asset had left the estate and said nothing about
        who authorised it. `proceeds` travels with its currency because a
        money figure with no currency beside it is how two systems agree on
        a number and disagree on what it is worth.
        """
        asset = self._asset(sap_asset_number='4000005562',
                            sap_code_source='import')
        asset.write({
            'state': 'disposed',
            'disposal_method': 'auction',
            'disposal_reference': 'BOS/2026/014',
            'disposal_proceeds': 450000.0,
            'disposal_approved_by': self.env.user.id,
            'disposal_approved_date': '2026-08-30 10:15:00',
        })

        change = self._payload(self._events(asset, EVENT_DISPOSED))['change']
        self.assertEqual(change['disposal_type'], 'disposal')
        self.assertEqual(change['reference'], 'BOS/2026/014')
        self.assertEqual(change['approved_by'], self.env.user.name)
        self.assertTrue(change['approved_at'].startswith('2026-08-30'))
        self.assertEqual(change['proceeds'], 450000.0)
        self.assertEqual(change['proceeds_currency'],
                         asset.currency_id.name)

    def test_an_undocumented_disposal_sends_NULLS_rather_than_omitting_the_keys(self):
        """Null is the honest answer and it has to be ON the wire.

        Today every disposal on every tenant is undocumented, so this is
        not the edge case — it is the case. A receiver that sees the key
        with a null knows Cadra does not know; one that sees no key at all
        cannot tell that from a Cadra too old to send it.
        """
        asset = self._asset(sap_asset_number='4000005563',
                            sap_code_source='import')
        asset.write({'state': 'disposed'})

        change = self._payload(self._events(asset, EVENT_DISPOSED))['change']
        for key in ('reference', 'approved_by', 'approved_at',
                    'proceeds', 'proceeds_currency', 'disposal_method'):
            self.assertIn(key, change,
                          "%s must be present and null, not absent" % key)
            self.assertIsNone(change[key])

    def test_a_lifecycle_event_for_an_asset_sap_has_never_heard_of_is_not_sent(self):
        """No SAP asset number means no asset master to update.

        Nor is the change lost: the INT-06 create carries the asset's CURRENT
        location and custodian, so whatever moved before capitalisation is
        already in the create payload when it finally fires.
        """
        outgoing = self._employee('A. Adeyemi')
        incoming = self._employee('B. Balogun')
        asset = self._asset(custodian_id=outgoing.id)
        self.assertFalse(asset.sap_asset_number)

        asset.write({'custodian_id': incoming.id})
        self.assertFalse(self._events(asset, EVENT_CUSTODIAN))

        asset.write({'state': 'disposed', 'disposal_reason': 'Scrapped'})
        self.assertFalse(self._events(asset, EVENT_DISPOSED))

        # The register still records both facts; only the announcement is
        # withheld.
        self.assertEqual(asset.custodian_id, incoming)
        self.assertEqual(asset.state, 'disposed')

    def test_rewriting_a_custodian_to_the_value_it_already_holds_is_not_an_event(self):
        """State is read before and after rather than inferred from `vals`.

        A receiver cannot tell a no-op reassignment from a real one, so a
        no-op must not become a message.
        """
        custodian = self._employee('A. Adeyemi')
        asset = self._asset(sap_asset_number='4000006666',
                            sap_code_source='import',
                            custodian_id=custodian.id)
        before = self.Log.search_count([('asset_id', '=', asset.id)])

        asset.write({'custodian_id': custodian.id})

        self.assertEqual(self.Log.search_count([('asset_id', '=', asset.id)]),
                         before, 'a write that changes nothing is not an event')

    # ── The dual-code control ─────────────────────────────────────────

    def test_the_four_dual_code_states_are_the_four_situations_they_name(self):
        """Only one of the four is a finding, and it has to be the only one.

        Colouring `not_tagged` red would bury the real cases in eleven
        thousand false ones, and an exception report nobody can read is the
        same as no exception report.
        """
        asset = self._asset()
        self.assertEqual(asset.sap_reconciliation_state, 'not_tagged',
                         'an untagged asset is not yet DUE a SAP code')

        self._affix(asset)
        self.assertEqual(asset.sap_reconciliation_state, 'pending',
                         'posted and awaiting its code is not yet a finding')

        event = self._events(asset, EVENT_CREATE)
        self._deliver(event, FakeAdapter(ok_result(
            {'sap_asset_number': '4000007777'})))
        self.assertEqual(asset.sap_reconciliation_state, 'reconciled')

        abandoned = self._asset()
        self._affix(abandoned)
        abandoned.sudo().write({'sap_posting_state': 'failed'})
        self.assertEqual(abandoned.sap_reconciliation_state, 'exception',
                         'tagged, demonstrably real, and unbooked')

    def test_an_abandoned_asset_master_becomes_a_dual_code_exception(self):
        """A permanently pending row is the quiet failure this control exists
        to remove — so the queue giving up has to show up on the asset."""
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset, EVENT_CREATE)
        self.assertEqual(asset.sap_posting_state, 'queued')
        self.assertEqual(asset.sap_reconciliation_state, 'pending')

        # A 4xx does not become valid by being resent: dead on attempt one.
        self.assertFalse(self._deliver(
            event, FakeAdapter(fail_result(400, retryable=False))))

        self.assertEqual(event.status, 'dead')
        self.assertEqual(asset.sap_posting_state, 'failed')
        self.assertEqual(asset.sap_reconciliation_state, 'exception')

    def test_a_legacy_asset_with_a_sap_number_and_no_tag_is_reconciled(self):
        """The opening balance of the control, and not twelve thousand
        exceptions. A legacy asset linked to an existing SAP asset number is
        genuinely complete even though Cadra never posted it."""
        legacy = self._asset(sap_asset_number='4000008888',
                             sap_code_source='import')

        self.assertNotEqual(legacy.tag_label_state, 'affixed')
        self.assertEqual(legacy.sap_posting_state, 'none')
        self.assertEqual(legacy.sap_reconciliation_state, 'reconciled')
        # ...and it is still visibly a claim rather than evidence.
        self.assertEqual(legacy.sap_code_source, 'import')

    # ── Isolation from INT-05 ─────────────────────────────────────────

    def test_one_affix_feeds_both_vendra_and_sap_from_their_own_targets(self):
        """The two legs are independent and neither swallows the other.

        Vendra and SAP fail differently and are separate config records for
        that reason; one physical act produces one message to each, and each
        message is addressed to its own target.
        """
        vendra = self.env['workflow.config'].create({
            'name': 'Vendra (test)',
            'purpose': 'asset_events',
            'adapter_type': 'stub',
            'event_enabled': True,
        })
        asset = self._asset()
        self._affix(asset)

        rows = self.Log.search([('asset_id', '=', asset.id),
                                ('event_type', '!=', False)])
        by_type = {row.event_type: row for row in rows}
        self.assertEqual(set(by_type), {EVENT_TAG_AFFIXED, EVENT_CREATE})
        self.assertEqual(by_type[EVENT_TAG_AFFIXED].config_id, vendra)
        self.assertEqual(by_type[EVENT_CREATE].config_id, self.config)
        # Two events, two idempotency keys — a receiver deduping on one must
        # not discard the other.
        self.assertNotEqual(by_type[EVENT_TAG_AFFIXED].event_id,
                            by_type[EVENT_CREATE].event_id)
        self.assertEqual(asset.sap_posting_state, 'queued')

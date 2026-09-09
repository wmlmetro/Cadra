"""One bad payload spoils one payload.

Handoff 15. `nrs.sap.sync.log.process_sap_payload` used to call
`self.env.cr.rollback()` in its exception handler, and a rollback is not
row-scoped: it discards everything since the last commit. Both bulk callers
loop over this method — the xlsx import job, which commits every 200 rows, and
`POST /api/v1/integrations/sap/employee-sync`, which runs the whole request in
one transaction — so a single unmappable employee erased every employee written
before it in the same batch, while the route's per-row results went on saying
`"status": "success"` for the rows it had just destroyed. That is the worst
shape a failure can take: the caller is told the work landed, and the evidence
that it did not is gone.

The regression this file pins is therefore NOT "a bad payload is reported as an
error" — it always was. It is "the payload BEFORE it survives", which is the
assertion nothing in the repo made.

A `TransactionCase`: nothing here needs HTTP. The route is a five-line loop over
`process_sap_payload`, and `_batch()` below is that loop, reading the same two
return values off the same method.
"""
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSapPayloadRowIsolation(TransactionCase):

    GOOD_A = "IR-H15-ISO-A"
    BAD_B = "IR-H15-ISO-B"
    GOOD_C = "IR-H15-ISO-C"

    #: Why the middle payload fails, and why it fails on every tenant.
    #:
    #: `hireDate` maps to `employment_start_date` through `SAP_FIELD_MAP`, and
    #: that is a `fields.Date`. Odoo converts it inside `hr.employee.create()`,
    #: which is inside the savepoint, and `Date.to_date` runs `strptime` on the
    #: first ten characters — so this raises `ValueError` there, deterministically,
    #: with no dependency on what the tenant holds and nothing monkeypatched.
    #:
    #: It is deliberately the ONLY difference between the three payloads: the
    #: good ones carry the same key with a value that parses.
    BAD_HIRE_DATE = "not-a-date"
    GOOD_HIRE_DATE = "2024-01-15"

    def setUp(self):
        super().setUp()
        self.Log = self.env["nrs.sap.sync.log"]
        self.Employee = self.env["hr.employee"]
        # The batch below IS the fixture, so it has to start from nothing:
        # `process_sap_payload` UPDATES an existing IR number instead of
        # creating one, and an update takes a different branch.
        self.assertFalse(
            self.Employee.search_count(
                [("ir_number", "in", [self.GOOD_A, self.BAD_B, self.GOOD_C])]),
            "these IR numbers are reserved for this test; a tenant holding one "
            "would send the batch down the update branch instead")

    def _batch(self):
        """Three payloads, the middle one unmappable.

        Byte for byte what `sap_employee_sync` does with a JSON array: loop,
        call, and record `log.status` and the employee id per row.
        """
        payloads = [
            {"ir_number": self.GOOD_A, "displayName": "H15 First",
             "hireDate": self.GOOD_HIRE_DATE},
            {"ir_number": self.BAD_B, "displayName": "H15 Second",
             "hireDate": self.BAD_HIRE_DATE},
            {"ir_number": self.GOOD_C, "displayName": "H15 Third",
             "hireDate": self.GOOD_HIRE_DATE},
        ]
        results = []
        for payload in payloads:
            employee, log = self.env["nrs.sap.sync.log"].process_sap_payload(
                payload, sync_type="api")
            # Reading `log.status` here is itself load-bearing. Under the old
            # handler the rollback had already deleted this row, so every
            # caller that reads it — all five of them — got a MissingError off
            # a recordset it had just been handed.
            results.append({
                "ir_number": payload["ir_number"],
                "status": log.status,
                "employee_id": employee.id if employee else None,
                "log_id": log.id,
            })
        return results

    def test_a_failing_payload_does_not_erase_the_one_before_it(self):
        """This is the regression. Before handoff 15 the first employee was
        gone by the time the third was processed — reported `success`,
        counted, and not there."""
        results = self._batch()

        self.assertEqual(results[0]["status"], "success")
        first = self.Employee.search([("ir_number", "=", self.GOOD_A)])
        self.assertTrue(
            first,
            "the employee written by the FIRST payload has to survive the "
            "second one failing; a transaction-wide rollback took it out")
        self.assertEqual(
            first.id, results[0]["employee_id"],
            "and it must be the same row the caller was told about, not a "
            "re-creation that happens to answer the same search")

    def test_the_batch_continues_past_the_failure(self):
        """A failure that stops the batch is a different defect with the same
        symptom, so the row after the bad one is asserted too."""
        results = self._batch()

        self.assertEqual(results[2]["status"], "success")
        third = self.Employee.search([("ir_number", "=", self.GOOD_C)])
        self.assertTrue(third, "the third payload never ran, or was rolled back")
        self.assertEqual(third.id, results[2]["employee_id"])

    def test_the_failure_is_reported_as_an_error_and_writes_nothing(self):
        """The bad payload is allowed to fail — it is required to fail
        visibly, and to leave no half-written employee behind."""
        results = self._batch()

        self.assertEqual(
            results[1]["status"], "error",
            "the caller reads this key to decide whether the row landed")
        self.assertIsNone(results[1]["employee_id"])
        self.assertFalse(
            self.Employee.search_count([("ir_number", "=", self.BAD_B)]),
            "the savepoint has to take back whatever the failed create wrote")

    def test_the_error_message_names_the_exception_type(self):
        """Not decoration. The handler catches an open set — a `ValidationError`
        from a tenant constraint, a `KeyError` from `generic.location` where the
        FM modules are absent, a psycopg2 error from a duplicate IR — and
        several of those stringify to `''` or to a bare quoted key. An error row
        whose `error_message` is empty tells an operator that something failed
        and nothing about what, which is most of the way back to swallowing it.

        So the assertion is on the SHAPE (`<Type>: <text>`) rather than on this
        particular `ValueError`'s wording, which is CPython's to change.
        """
        results = self._batch()
        log = self.Log.browse(results[1]["log_id"])

        self.assertTrue(
            (log.error_message or "").strip(),
            "an errored sync row with an empty message is a silent failure "
            "wearing a status")
        self.assertRegex(
            log.error_message, r"^[A-Za-z_][A-Za-z0-9_.]*: ",
            "the exception type is prefixed precisely so that an error which "
            "stringifies to nothing still names itself")

    def test_the_error_lands_on_the_row_that_was_created_pending(self):
        """The `pending` row is created BEFORE the savepoint and flushed on the
        way in, so the failure is written onto the row the caller is already
        holding rather than onto a replacement. That distinction is what makes
        `log.status` readable after the call at all.

        Holding the id means catching it mid-flight, so `_map_sap_to_odoo` is
        wrapped — read-only, and it calls the real mapping, so the failure is
        still the data's. It is the only hook between the row being created and
        the exception being raised; the alternative, inferring it from
        consecutive row ids, would fail for reasons unrelated to the property.
        """
        Log = self.env["nrs.sap.sync.log"]
        model_cls = type(Log)
        original = model_cls._map_sap_to_odoo
        pending_ids = {}

        def spy(records, payload):
            ir = payload.get("ir_number")
            if ir and ir not in pending_ids:
                pending_ids[ir] = Log.search(
                    [("ir_number", "=", ir)], order="id desc", limit=1).id
            return original(records, payload)

        with patch.object(model_cls, "_map_sap_to_odoo", spy):
            results = self._batch()

        self.assertTrue(
            pending_ids.get(self.BAD_B),
            "the pending row is created before the savepoint, so it must "
            "already exist by the time the mapping runs")
        self.assertEqual(
            results[1]["log_id"], pending_ids[self.BAD_B],
            "the caller was handed a different row from the one that was "
            "opened for this payload")
        self.assertEqual(
            Log.search_count([("ir_number", "=", self.BAD_B)]), 1,
            "one payload, one log row — a second row means the first was "
            "abandoned rather than completed")

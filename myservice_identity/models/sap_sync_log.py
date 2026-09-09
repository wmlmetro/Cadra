import time
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

SAP_STATUS_MAP = {
    'active': 'active', 'Active': 'active',
    'terminated': 'exited', 'Terminated': 'exited',
    'suspended': 'suspended', 'Suspended': 'suspended',
    'onLeave': 'on_leave', 'On Leave': 'on_leave',
    'transferred': 'transferred', 'Transferred': 'transferred',
}

SAP_FIELD_MAP = {
    'userId': 'sap_user_id',
    'jobTitle': 'job_title',
    'department': 'sap_department',
    'costCenter': 'cost_centre',
    'gradeCode': 'grade_level',
    'managerIR': 'sap_manager_ir',
    'email': 'work_email',
    'phone': 'work_phone',
    'mobile': 'mobile_phone',
    'hireDate': 'employment_start_date',
    'terminationDate': 'employment_end_date',
}


class NRSSapSyncLog(models.Model):
    _name = 'nrs.sap.sync.log'
    _description = 'SAP SuccessFactors Sync Log'
    _order = 'create_date desc'
    _rec_name = 'ir_number'

    ir_number = fields.Char(string='IR Number', required=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', ondelete='set null',
    )
    sync_type = fields.Selection([
        ('webhook', 'SAP Webhook'),
        ('api', 'REST API'),
        ('manual', 'Manual'),
        ('csv_import', 'CSV Import'),
        ('scheduled', 'Scheduled Pull'),
    ], string='Sync Type', required=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('error', 'Error'),
        ('skipped', 'Skipped — No Change'),
    ], string='Status', default='pending')
    sap_event = fields.Char(
        string='SAP Event',
        help='e.g. HireEmployee, TransferEmployee, TerminateEmployee',
    )
    payload = fields.Text(string='Raw Payload')
    changes_applied = fields.Text(string='Changes Applied')
    error_message = fields.Text(string='Error Message')
    duration_ms = fields.Integer(string='Duration (ms)')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @api.model
    def process_sap_payload(self, payload, sync_type='webhook'):
        """Process an SAP SuccessFactors employee dict.

        Returns ``(employee, log)`` where *employee* may be ``None``
        on error.
        """
        start = time.time()

        ir_number = (
            payload.get('ir_number')
            or payload.get('userId')
            or payload.get('personIdExternal')
        )
        if not ir_number:
            log = self.create({
                'ir_number': 'UNKNOWN',
                'sync_type': sync_type,
                'status': 'error',
                'error_message': 'No IR number in payload',
                'payload': str(payload),
            })
            return None, log

        log = self.create({
            'ir_number': ir_number,
            'sync_type': sync_type,
            'status': 'pending',
            'payload': str(payload),
            'sap_event': payload.get('event', ''),
        })

        try:
            # One payload, one savepoint. What stood here was
            # `self.env.cr.rollback()` in the handler below, and a rollback is
            # not payload-scoped: it discards everything since the last commit.
            # Both bulk callers loop over this method — the xlsx import job
            # (200 rows between commits) and the SAP webhook (one transaction
            # for the whole request) — so one unmappable employee silently
            # destroyed every employee written before it in the batch, while
            # the job's counters and the webhook's per-row `"status":
            # "success"` went on reporting them as written. The savepoint also
            # leaves the `pending` log row above intact, because it was created
            # OUTSIDE the savepoint and flushed on the way in, so the error is
            # recorded on the row the caller is already holding rather than on
            # a replacement.
            with self.env.cr.savepoint():
                vals = self._map_sap_to_odoo(payload)
                vals['sap_last_sync'] = fields.Datetime.now()
                vals['sap_sync_status'] = 'synced'

                employee = self.env['hr.employee'].search(
                    [('ir_number', '=', ir_number)], limit=1,
                )
                changes = []

                if employee:
                    for k, v in vals.items():
                        old = getattr(employee, k, None)
                        if hasattr(old, 'id'):
                            old = old.id
                        if old != v:
                            changes.append('%s: %s -> %s' % (k, old, v))
                    if changes:
                        employee.write(vals)
                        log.write({
                            'status': 'success',
                            'changes_applied': '\n'.join(changes),
                        })
                    else:
                        log.write({
                            'status': 'skipped',
                            'changes_applied': 'No changes detected',
                        })
                else:
                    vals['ir_number'] = ir_number
                    # Use company context so resource.resource gets calendar_id
                    company = self.env['res.company'].sudo().search([], limit=1)
                    if 'company_id' not in vals:
                        vals['company_id'] = company.id
                    Employee = self.env['hr.employee'].sudo().with_company(company)
                    employee = Employee.create(vals)
                    changes.append('Created new employee: %s' % employee.name)
                    log.write({
                        'status': 'success',
                        'changes_applied': '\n'.join(changes),
                    })

                self._handle_status_triggers(
                    employee,
                    payload.get('sap_status') or payload.get('employmentStatus'),
                    payload.get('previous_status'),
                )

                log.write({
                    'employee_id': employee.id,
                    'duration_ms': int((time.time() - start) * 1000),
                })
            return employee, log

        except Exception as e:
            # catch-all: reported — the payload is third-party JSON mapped onto
            # whatever a tenant's hr.employee looks like, so the set is open
            # (ValidationError from a constraint, ValueError from a field the
            # tenant does not have, psycopg2 from a duplicate IR, KeyError from
            # `generic.location` where the FM modules are not installed). The
            # traceback is logged and the failure is written onto the log row
            # the caller reads `status` off, so it reaches the operator as an
            # errored row rather than as a missing one.
            _logger.exception('SAP sync error for IR %s', ir_number)
            # No inner handler: the savepoint above means the transaction is
            # usable here, so the only way this write can now fail is a dead
            # connection — and swallowing that produced a `log` recordset the
            # rollback had already erased, which every caller then read
            # `log.status` off and got a MissingError from. Raising is the
            # honest answer; the caller's own row handler catches it.
            log.write({
                'status': 'error',
                # The type as well as the text: several ORM and psycopg2
                # errors stringify to '' or to a bare quoted key.
                'error_message': '%s: %s' % (type(e).__name__, e),
                'duration_ms': int((time.time() - start) * 1000),
            })
            return None, log

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _map_sap_to_odoo(self, payload):
        vals = {}

        # Name
        if payload.get('displayName'):
            vals['name'] = payload['displayName']
        elif payload.get('firstName') and payload.get('lastName'):
            vals['name'] = '%s %s' % (payload['firstName'], payload['lastName'])

        # Scalar fields
        for sap_key, odoo_key in SAP_FIELD_MAP.items():
            if payload.get(sap_key) is not None:
                vals[odoo_key] = payload[sap_key] or False

        # Status
        raw_status = payload.get('employmentStatus') or payload.get('sap_status')
        if raw_status:
            vals['sap_status'] = SAP_STATUS_MAP.get(raw_status, 'active')

        # Location by name
        loc_name = payload.get('locationName') or payload.get('location')
        if loc_name:
            loc = self.env['generic.location'].search(
                [('name', 'ilike', loc_name)], limit=1,
            )
            if loc:
                vals['sap_location_id'] = loc.id

        # Department
        dept_name = payload.get('department')
        if dept_name:
            dept = self.env['hr.department'].search(
                [('name', 'ilike', dept_name)], limit=1,
            )
            if not dept:
                dept = self.env['hr.department'].create({'name': dept_name})
            vals['department_id'] = dept.id

        return vals

    @staticmethod
    def _handle_status_triggers(employee, new_status, previous_status):
        if not new_status or new_status == previous_status:
            return

        mapped = SAP_STATUS_MAP.get(new_status, new_status)

        if mapped == 'exited':
            employee.action_flag_retrieval()
            employee.message_post(
                body='Employee status changed to EXITED via SAP. '
                     'Assets flagged for retrieval.',
            )
        elif mapped == 'transferred':
            employee.message_post(
                body='Employee transferred. Review asset assignments and location.',
            )
        elif mapped == 'suspended':
            employee.message_post(body='Employee suspended via SAP SuccessFactors.')

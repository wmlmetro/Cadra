from odoo import models, fields


class NrsAsset(models.Model):
    _inherit = 'nrs.asset'

    # ── Retrieval fields (custodian_id already exists on nrs.asset) ──
    assigned_ir_number = fields.Char(
        string='IR Number',
        related='custodian_id.ir_number',
        store=True,
        readonly=True,
    )
    assigned_employee_dept = fields.Char(
        string='SAP Department',
        related='custodian_id.sap_department',
        store=True,
        readonly=True,
    )
    assignment_date = fields.Date(string='Assignment Date')
    retrieval_flag = fields.Boolean(
        string='Pending Retrieval',
        default=False,
        tracking=True,
        help='Automatically set when assigned employee exits',
    )
    retrieval_reason = fields.Selection([
        ('employee_exit', 'Employee Exit'),
        ('employee_transfer', 'Employee Transfer'),
        ('damage', 'Damaged / Lost'),
        ('reallocation', 'Reallocation'),
        ('manual', 'Manual Flag'),
    ], string='Retrieval Reason')
    retrieval_date = fields.Date(string='Retrieved On')

    def action_mark_retrieved(self):
        """An asset coming back from somebody who has left.

        `cadra_approval_exempt='clearance'` — handoff 35 §A. This clears
        `custodian_id`, which since that handoff needs a second person to
        agree when a PERSON is deciding to put an asset in somebody else's
        hands. This is not that: it takes custody away and hands it to
        nobody, at the end of a departure that SAP has already confirmed
        (`sap_sync_log._apply` flags the retrieval on `exited`). There is no
        second person to ask about an asset returning to the store, and
        requiring one would leave a leaver's assets assigned to them while a
        queue drained.

        The chain of custody still records it — the recorder in
        `nrs.asset.write` sits underneath the exemption, not behind it.
        """
        self.with_context(cadra_approval_exempt='clearance').write({
            'retrieval_flag': False,
            'retrieval_date': fields.Date.today(),
            'custodian_id': False,
            'assignment_date': False,
        })
        self.message_post(body='Asset retrieved and unassigned.')

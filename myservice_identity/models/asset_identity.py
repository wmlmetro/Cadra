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
        self.write({
            'retrieval_flag': False,
            'retrieval_date': fields.Date.today(),
            'custodian_id': False,
            'assignment_date': False,
        })
        self.message_post(body='Asset retrieved and unassigned.')

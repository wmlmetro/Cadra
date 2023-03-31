import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericContractTemplate(models.Model):
    _name = 'generic.contract.template'
    _inherit = [
        'mail.thread',
    ]
    _description = 'Generic Contract Template'
    _order = 'name'

    name = fields.Char(
        index=True, translate=True, tracking=True, required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company)
    partner_type = fields.Selection(
        required=True, default='customer',
        selection=[('customer', 'Customer'),
                   ('supplier', 'Supplier')],
        tracking=True)
    number_sequence_id = fields.Many2one(
        'ir.sequence', string='Sequence', tracking=True)
    contract_ids = fields.One2many(
        'generic.contract', 'template_id', readonly=True, string='Contracts')
    contract_count = fields.Integer(
        readonly=True, compute='_compute_contract_count')
    active = fields.Boolean(
        default=True, index=True, tracking=True)
    description = fields.Html(translate=True)

    service_contract_line_ids = fields.One2many(
        'generic.contract.template.service.line', 'contract_template_id',
        string='Service Lines')

    @api.depends('contract_ids')
    def _compute_contract_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='contract_ids')
        for record in self:
            record.contract_count = mapped_data.get(record.id, 0)

    def _prepare_contract_values(self, partner, user, date_start, date_end):
        service_contract_line_ids_data = []
        for service_contract_line in self.service_contract_line_ids:
            service_contract_line_ids_data.append(
                (0, 0, service_contract_line.prepare_contract_service_line())
            )

        return {
            'name': self.name,
            'partner_type': self.partner_type,
            'template_id': self.id,
            'partner_id': partner.commercial_partner_id.id,
            'date_start': date_start,
            'date_end': date_end,
            'user_id': user.id if user else False,
            'description': self.description,
            'service_contract_line_ids': service_contract_line_ids_data
        }

    def _postprocess_created_contract(self, contract):
        """ Could be called by third-party modules, to add some postprocessing
            of created contract
        """

    def create_contract(self, partner, user=None,
                        date_start=None, date_end=None):
        self.ensure_one()

        root_contract = self.env['generic.contract'].create(
            self._prepare_contract_values(
                partner, user, date_start, date_end))
        self._postprocess_created_contract(root_contract)

        # TODO: copy translations
        return root_contract

    def action_view_template_contracts(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_contract.generic_contract_action',
            context={'default_template_id': self.id},
            domain=[('template_id', '=', self.id)])

    def action_open_contract_create_wizard(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_contract.action_generic_contract_create_wizard',
            context={
                'default_template_id': self.id,
                'default_partner_type': self.partner_type,
            })

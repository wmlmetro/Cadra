from odoo.osv import expression
from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class ResPartner(models.Model):
    _inherit = 'res.partner'

    generic_contract_ids = fields.One2many(
        'generic.contract', 'partner_id', 'Contracts')
    generic_contract_count = fields.Integer(
        compute="_compute_generic_contract_count", readonly=True,
        string="Count of contracts", compute_sudo=True)

    @api.depends('generic_contract_ids')
    def _compute_generic_contract_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='generic_contract_ids', sudo=True)
        for record in self:
            record.generic_contract_count = mapped_data.get(record.id, 0)

    def get_generic_contract(self, states=None, extra_domain=None):
        """ Get contract for partner

            :param str/list states: single state or list of contract states to
                                    look for. By default ['pending', 'active']
            :param list extra_domain: Additional domain to look for contract
            :return RecordSet('generic.contract'): contract found or empty
                                                   recordset
        """
        self.ensure_one()
        if states is None:
            states = ['pending', 'active']
        elif isinstance(states, str):
            states = [states]

        domain = [
            ('partner_id', '=', self.commercial_partner_id.id),
            ('state', 'in', states),
        ]

        if extra_domain is not None:
            domain = expression.AND([
                domain,
                extra_domain,
            ])

        return self.env['generic.contract'].search(domain, limit=1)

    def action_show_partner_contracts(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_contract.generic_contract_action',
            domain=[('partner_id', '=', self.id)])

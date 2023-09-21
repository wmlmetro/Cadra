import logging

from odoo import models, fields, api
from odoo.osv import expression
from odoo.addons.generic_request.models.request_request import (
    TRACK_FIELD_CHANGES,
    KANBAN_READONLY_FIELDS,
)
from odoo.addons.generic_mixin import post_write
from odoo.addons.generic_request import service_level_guesser


_logger = logging.getLogger(__name__)

KANBAN_READONLY_FIELDS.add('contract_id')
TRACK_FIELD_CHANGES.add('contract_id')


class RequestRequest(models.Model):
    _inherit = 'request.request'

    contract_id = fields.Many2one(
        'generic.contract', index=True, string='Contract', ondelete='restrict')

    @classmethod
    def _get_contract_id_dependency_fields(cls):
        """ Return list of fields that have to trigger contract recomputation.
            Could be extended by other addons
        """
        return ['author_id', 'partner_id', 'service_id']

    @classmethod
    def _init_constraints_onchanges(cls):
        # Overloading this method to dinamically create onchange handler with
        # dynamically computed fields. This is required to be able to add
        # dependency fields in other addons.
        cls._onchange_update_contract._onchange = tuple(
            cls._get_contract_id_dependency_fields())
        return super(RequestRequest, cls)._init_constraints_onchanges()

    @api.onchange()
    def _onchange_update_contract(self):
        """ This method will be called to update contract_id with onchanges.

            This onchange will track fields returned by
            _get_contract_id_dependency_fields method
        """
        # Check access right to contract model, because not all of users that
        # has access to request model has access to this contract model and
        # it raised exception
        if not self.env['generic.contract'].check_access_rights(
                'read', raise_exception=False):
            return None
        if (self.contract_id and self.partner_id and
                self.contract_id.partner_id != self.partner_id):
            # Clear seelcted contract, if selected partner does not match
            # contract's partner
            self.contract_id = False

        self.contract_id = self._guess_contract()
        return {
            'domain': {
                'contract_id': self._guess_contract_get_domain(),
            }
        }

    def _guess_contract_get_domains_required(self):
        """ Return list of required domains.
            All domains in this list will be joined via AND condition.
        """
        self.ensure_one()
        partner = self.partner_id if self.partner_id else self.author_id
        return [[
            ('partner_id', '=', partner.id),
            ('state', '=', 'active'),
        ]]

    def _guess_contract_get_domain_optional(self):
        """ Return list of optional domains.
            This domains will be joined via OR condition
        """
        self.ensure_one()

        # We have to update the search domain for contract only if
        # request have defined service. Otherwise, system have to guess
        # contract in default way (by partner or via other criterions).
        if self.service_id:
            return [
                [('contracts_service_ids.id', '=', self.service_id.id)],
            ]
        return []

    def _guess_contract_get_domain(self):
        """ Return domain to guess contract for this request
        """
        self.ensure_one()
        required_domain = self._guess_contract_get_domains_required()
        optional_domain = self._guess_contract_get_domain_optional()

        if optional_domain:
            return expression.AND([
                expression.AND(required_domain),
                expression.OR(optional_domain),
            ])
        return expression.AND(required_domain)

    def _guess_contract(self):
        """ Try to guess contract for this request
        """
        self.ensure_one()

        domain = self._guess_contract_get_domain()
        return self.env['generic.contract'].search(domain, limit=1)

    @api.model
    def _add_missing_default_values(self, values):
        res = super(RequestRequest, self)._add_missing_default_values(values)

        if 'contract_id' not in values:
            contract = self.sudo().new(res)._guess_contract()
            if contract:
                res['contract_id'] = contract.id

        return res

    def _postprocess_write_changes(self, changes):
        res = super(RequestRequest, self)._postprocess_write_changes(changes)

        # Update contract_id if at least one of fields returned by
        # _get_contract_id_dependency_fields changed
        if set(self._get_contract_id_dependency_fields()).intersection(
                set(changes.keys())):
            self.contract_id = self._guess_contract()

        return res

    @post_write('contract_id')
    def _after_contract_id_changed(self, changes):
        self.trigger_event('contract-changed', {
            'old_contract_id': changes['contract_id'][0].id,
            'new_contract_id': changes['contract_id'][1].id, })

    @classmethod
    def _get_service_level_dependency_fields(cls):
        return super(
            RequestRequest, cls
        )._get_service_level_dependency_fields() + [
            'contract_id', 'service_id',
        ]

    @service_level_guesser(600)
    def _get_service_level__from_contract(self):
        if self.contract_id and self.service_id:
            service_line = self.contract_id.sudo().get_service_line_for(
                self.service_id)
            if service_line:
                return service_line.service_level_id
        return self.env['generic.service.level'].browse()

    @api.depends('contract_id')
    def _compute_service_category_type_domains(self):
        # Required to modify domain for service field in request
        res = super(
            RequestRequest, self)._compute_service_category_type_domains()
        return res

    def _get_service_id_domain(self):
        service_domain = super(RequestRequest, self)._get_service_id_domain()
        if self.contract_id:
            allowed_services = (
                self.contract_id.contracts_service_ids
            )
            service_domain = expression.AND([
                service_domain,
                [('id', 'in', allowed_services.ids)],
            ])
        return service_domain

    @api.onchange('service_id', 'is_new_request', 'contract_id', 'type_id')
    def _onchange_contract_id_restrict_service(self):
        if not self.contract_id:
            return

        allowed_services = (
            self.contract_id.contracts_service_ids
        )
        if self.service_id not in allowed_services:
            self.service_id = False

    @post_write('service_id', 'contract_id')
    def _update_service_level_on_write(self, changes):
        return super(RequestRequest, self)._update_service_level_on_write(
            changes)

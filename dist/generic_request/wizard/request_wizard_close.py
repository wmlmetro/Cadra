from odoo import models, fields, api, exceptions, _
from odoo.osv import expression


class RequestWizardClose(models.TransientModel):
    _name = 'request.wizard.close'
    _description = 'Request Wizard: Close'

    request_id = fields.Many2one(
        'request.request', 'Request', required=True, ondelete='cascade')
    close_route_id = fields.Many2one(
        'request.stage.route', 'Close as', required=True, ondelete='cascade')
    require_response = fields.Boolean(
        related="close_route_id.require_response", readonly=True)
    response_text = fields.Html('Response')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'request_wizard_close_attachment_rel',
        'request_wizard_close_id', 'attachment_id', 'Attachments',
        help="You may attach files to response")

    # Reopen section
    reopen_as = fields.Selection(
        selection=[
            ('subrequest', 'Subrequest'),
            ('independed-request', 'Independed Request')],
        default='subrequest')
    reopen = fields.Boolean(compute='_compute_reopen', readonly=True)
    new_request_type_id = fields.Many2one(
        'request.type', string='New type', ondelete='cascade')
    new_request_category_id = fields.Many2one(
        'request.category', string='New category', ondelete='cascade')
    new_request_text = fields.Html()
    new_request_service_id = fields.Many2one(
        'generic.service', string='New Service', ondelete='cascade')

    # TODO: Check onchanges, wheh no selected new_request_type_id
    # in form view shown all categories in new_request_category_id

    def _get_next_route_domain(self):
        self.ensure_one()
        return [
            ('close', '=', True),
            ('stage_from_id', '=', self.request_id.stage_id.id),
        ]

    @api.depends('close_route_id.reopen_as_type_ids')
    def _compute_reopen(self):
        for rec in self:
            rec.reopen = bool(rec.close_route_id.reopen_as_type_ids)

    @api.onchange('request_id')
    def onchange_request_id(self):
        self.ensure_one()
        if self.request_id:
            self.response_text = self.request_id.response_text
            if not self.close_route_id:
                self.close_route_id = self.env['request.stage.route'].search(
                    self._get_next_route_domain(), limit=1)
            return {
                'domain': {
                    'close_route_id': self._get_next_route_domain(),
                },
            }
        return {}

    @api.onchange('request_id')
    def onchange_request_id_new_request_text(self):
        """
            Set default new_request_text
        """
        for rec in self:
            if not rec.new_request_text:
                rec.new_request_text = rec.request_id.request_text

    @api.onchange('close_route_id')
    def onchange_close_route_id(self):
        for rec in self:
            rec.response_text = rec.close_route_id.default_response_text

    @api.onchange('close_route_id', 'new_request_category_id',
                  'new_request_type_id', 'new_request_service_id')
    def onchange_update_domain_type_categ(self):
        """
            Clears out new_request_type_id field.
            Returns domain for new_request_type_id field.
        """
        # TODO: need to optimise this method
        # pylint: disable=too-many-branches
        allowed_types = self.close_route_id.reopen_as_type_ids
        if self.new_request_category_id and self.new_request_service_id:
            if (self.new_request_service_id not in
                    self.new_request_category_id.service_ids):
                self.new_request_category_id = False
        elif self.new_request_category_id and not self.new_request_service_id:
            if self.new_request_category_id.service_ids:
                self.new_request_category_id = False
        if self.new_request_type_id and self.new_request_category_id:
            # Clear type if it is not in allowed types for selected category
            # Or if request category is not selected
            if (self.new_request_type_id not in
                    self.new_request_category_id.request_type_ids):
                self.new_request_type_id = False
        elif self.new_request_type_id and not self.new_request_category_id:
            # Clear type if there is no category selected, but type has bound
            # category
            if self.new_request_type_id.category_ids:
                self.new_request_type_id = False

        res = {'domain': {
            'new_request_category_id': [
                ('request_type_ids.id', 'in', allowed_types.ids),
            ]
        }}
        domain = res['domain']
        if self.new_request_category_id:
            domain['new_request_type_id'] = [
                ('category_ids.id', '=', self.new_request_category_id.id),
                ('id', 'in', allowed_types.ids),
            ]
        else:
            domain['new_request_type_id'] = [
                ('category_ids', '=', False),
                ('id', 'in', allowed_types.ids),
            ]

        domain['new_request_service_id'] = [
            ('request_type_ids.id', 'in', allowed_types.ids)
        ]
        if self.new_request_service_id:
            if (self.new_request_type_id not in
                    self.new_request_service_id.request_type_ids):
                # Clean up type only if self is not saved to database
                self.new_request_type_id = None

        if self.new_request_service_id:
            domain['new_request_type_id'] = expression.AND([
                domain['new_request_type_id'],
                [('service_ids', '=', self.new_request_service_id.id)],
            ])
            domain['new_request_category_id'] = expression.AND([
                domain['new_request_category_id'],
                [('service_ids', '=', self.new_request_service_id.id)],
            ])
        else:
            domain['new_request_type_id'] = expression.AND([
                domain['new_request_type_id'], [('service_ids', '=', False)],
            ])
            domain['new_request_category_id'] = expression.AND([
                domain['new_request_category_id'],
                [('service_ids', '=', False)],
            ])

        return res

    def _reopen_prepare_data(self):
        """ Prepare data that will be overwritten in in new request.
        """
        res = {
            'service_id': self.new_request_service_id.id,
            'type_id': self.new_request_type_id.id,
            'category_id': self.new_request_category_id.id,
            'request_text': self.new_request_text,
            'author_id': self.request_id.author_id.id,
            'partner_id': self.request_id.partner_id.id,
        }
        if self.reopen_as == 'subrequest':
            res.update({'parent_id': self.request_id.id})
        return res

    def action_close_request(self):
        self.ensure_one()

        if self.response_text == '<p><br></p>':
            self.response_text = False

        if self.require_response and not self.response_text:
            raise exceptions.UserError(_("Response text is required!"))

        # Set response_text here, because it may be used in conditions
        # that checks if it is allowed to move request by specified route
        self.request_id.response_text = self.response_text

        # If wizard has response attachments,
        # bind them to request (to get access portal users) and
        # add to request response attachments
        if self.attachment_ids:
            self._request_bind_response_attachments(self.request_id.id)
            self.request_id.response_attachment_ids = self.attachment_ids.ids

        self.request_id.stage_id = self.close_route_id.stage_to_id

        if self.reopen:
            # And create new request if it is required
            new_request = self.request_id.copy(
                self._reopen_prepare_data())
            action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_request.action_request_window',
                domain=[('id', '=', new_request.id)])
            action['res_id'] = new_request.id

            # Display only form view
            action['views'] = [v for v in action['views'] if v[1] == 'form']
            return action
        return None

    def _request_bind_response_attachments(self, request_id):
        """
            Bind the response attachments of this wizard
            to the given request id.

            :param request_id: The id of request record to which
                               the attachments should be bound.
            :type request_id: int

            This method binds all the response attachments of this wizard
            to the given request_id.

            :return: None
            """
        self.ensure_one()
        for attachment in self.attachment_ids:
            attachment.sudo().write({
                'res_model': 'request.request',
                'res_id': request_id,
            })

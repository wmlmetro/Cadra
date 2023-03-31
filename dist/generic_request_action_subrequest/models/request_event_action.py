import time
import logging
import datetime

from odoo import models, fields
from odoo.osv import expression
from odoo.addons.generic_request.tools.jinja import render_jinja_string

_logger = logging.getLogger(__name__)

DEFAULT_ARCH_BASE = (
    "<?xml version='1.0'?>"
    "\n<t name='' t-name=''>"
    "\n\t<t t-esc='request.request_text'/>"
    "\n\t"
    "\n\t<!-- Variables available: -->"
    "\n\t<!-- <t t-esc='user.name'/> -->"
    "\n\t<!-- <t t-esc='request.name'/> -->"
    "\n\t<!-- <t t-esc='env'/> -->"
    "\n\t<!-- <t t-esc='time'/> -->"
    "\n\t<!-- <t t-esc='datetime'/> -->"
    "\n</t>")


class RequestStageRouteAction(models.Model):
    _inherit = "request.event.action"

    act_type = fields.Selection(selection_add=[('subrequest', 'Subrequest')],
                                ondelete={'subrequest': 'cascade'})

    # Subrequest info
    subrequest_template_id = fields.Many2one(
        'request.creation.template', ondelete='restrict',
        tracking=True)
    subrequest_type_id = fields.Many2one(
        related='subrequest_template_id.request_type_id',
        string='Subrequest type', store=False, readonly=True)
    subrequest_category_id = fields.Many2one(
        related='subrequest_template_id.request_category_id',
        string='Subrequest Category', store=False, readonly=True)
    subrequest_start_stage_id = fields.Many2one(
        related='subrequest_template_id.request_type_id.start_stage_id',
        string='Subrequest stage', store=False, readonly=True)
    subrequest_subscribe_partner_ids = fields.Many2many(
        'res.partner',
        'request_route_action_subrequest_subscribe_partner_rel',
        'action_id', 'partner_id', 'Subrequest subscribe partners')
    subrequest_trigger_route_id = fields.Many2one(
        'request.stage.route', 'Subrequest trigger route',
        ondelete='restrict', tracking=True)
    subrequest_text = fields.Html(
        help="You can use jinja2 placeholders in this field"
    )
    subrequest_text_template_id = fields.Many2one(
        'ir.ui.view', ondelete='restrict', domain=[('type', '=', 'qweb')],
        context={
            'default_type': 'qweb',
            'default_arch_base': DEFAULT_ARCH_BASE},
        tracking=True)
    subrequest_same_author = fields.Boolean()
    subrequest_same_deadline = fields.Boolean()
    subrequest_transfer_field_ids = fields.Many2many(
        comodel_name='ir.model.fields',
        relation='request_act_subrequest_transfer_fields_rel',
        column1='action_id',
        column2='field_id',
        domain=expression.AND([
            [('model', '=', 'request.request')],
            [('ttype', 'not in', ('many2many', 'one2many'))],
            [('related', '=', False)],
            [('compute', '=', False)],
            expression.OR([
                [('store', '=', True)],
                [('store', '=', False), ('copied', '=', True)],
            ]),
        ]),
        help='List of fields to transfer to subrequesst from parent request.')

    def _run_subrequest_prepare_transfer_fields(self, request, event):
        """ Prepare values for fields that have to be transfered from parent
            request to child request
        """
        res = {}
        Request = self.env['request.request']
        for field in self.sudo().subrequest_transfer_field_ids:
            res[field.name] = Request._fields[field.name].convert_to_write(
                request[field.name], request)

        return res

    def _run_subrequest_prepare_data(self, request, event):
        """ Prepare data for subrequest
        """
        res = {
            'parent_id': request.id,
        }

        # Apply template for request_text for subrequest
        if self.subrequest_text_template_id:
            val = {
                'user': self.env.user,
                'env': self.env,
                'request': request,
                'time': time,
                'datetime': datetime,
            }
            res['request_text'] = self.subrequest_text_template_id.render(val)
        else:
            res['request_text'] = render_jinja_string(
                self.subrequest_text,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event),
            )

        # Update author of subrequest if required
        if self.subrequest_same_author:
            res['author_id'] = request.author_id.id

        # Update deadline of subrequest
        if self.subrequest_same_deadline:
            res['deadline_date'] = request.deadline_date

        if self.sudo().subrequest_transfer_field_ids:
            res.update(
                self._run_subrequest_prepare_transfer_fields(request, event)
            )

        return res

    def _run_subrequest_create_subrequest(self, request, event):
        return self.subrequest_template_id.do_create_request(
            self._run_subrequest_prepare_data(request, event))

    def _run_subrequest_postprocess_subrequest(self, request, event,
                                               subrequest):
        subrequest.message_subscribe(
            partner_ids=self.subrequest_subscribe_partner_ids.mapped('id'))

        if self.subrequest_trigger_route_id:
            trigger_route = self.subrequest_trigger_route_id
            if subrequest.stage_id == trigger_route.stage_from_id:
                # Ensure, request was not moved to other stage yet
                subrequest.write({
                    'stage_id': trigger_route.stage_to_id.id,
                })

    def _run_subrequest(self, request, event):
        subrequest = self._run_subrequest_create_subrequest(request, event)
        self._run_subrequest_postprocess_subrequest(
            request, event, subrequest)

    def _dispatch(self, request, event):
        if self.act_type == 'subrequest' and self.subrequest_template_id:
            return self._run_subrequest(request, event)
        return super(RequestStageRouteAction, self)._dispatch(request, event)

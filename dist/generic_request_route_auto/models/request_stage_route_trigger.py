import logging

from odoo import models, fields, api, tools, _

from odoo.addons.generic_mixin import post_write, post_create

_logger = logging.getLogger(__name__)


class RequestStageRouteTrigger(models.Model):
    _name = "request.stage.route.trigger"
    _inherit = [
        'mail.thread',
        'generic.mixin.track.changes',
    ]
    _description = "Request Stage Route Trigger"
    _order = "route_sequence ASC, sequence ASC, name ASC, id ASC"

    name = fields.Char(required=True, index=True, translate=True)
    sequence = fields.Integer(default=5, index=True, required=True)
    route_sequence = fields.Integer(
        related='route_id.sequence', store=True, index=True, readonly=True,
        string="Route Priority")
    route_id = fields.Many2one(
        'request.stage.route', required=True, index=True, auto_join=True,
        ondelete='cascade', tracking=True)
    route_stage_from_id = fields.Many2one(
        'request.stage', readonly=True,
        related='route_id.stage_from_id', store=True, index=True,
        auto_join=True,
        help="Source stage of related route.")
    request_type_id = fields.Many2one(
        'request.type', related='route_id.request_type_id',
        store=True, index=True, auto_join=True, readonly=True)
    dummy_request_type_id = fields.Many2one(
        'request.type', store=False,
        help='Dummy technical field to handle UI route restriction when '
             'opening from request type form view')
    event_type_ids = fields.Many2many(
        comodel_name='generic.system.event.type',
        relation='request_stage_route_trigger__event_type__rel',
        column1='trigger_id',
        column2='event_type_id')
    trigger = fields.Selection(
        [('auto_on_write', 'Auto: On write'),
         ('cron_daily', 'Cron: Daily'),
         ('cron_hourly', 'Cron: Hourly'),
         ('event', 'Event')],
        index=True,
        required=True,
        help="Try to move requests by this route on trigger condition",
        tracking=True)
    condition_ids = fields.Many2many(
        'generic.condition',
        'request_stage_route_trigger_trigger_conditions_rel',
        'trigger_id', 'condition_id', string='Trigger Conditions',
        help="This conditions will be checked before triggering request move",
        tracking=True)
    event_condition_ids = fields.Many2many(
        'generic.condition',
        'request_stage_route_trigger_trigger_event_conditions_rel',
        'trigger_id', 'condition_id', string='Event Conditions',
        help="This conditions will chack request event before "
             "triggering request move",
        tracking=True)
    sudo_enable = fields.Boolean(
        'Trigger as superuser',
        help="Trigger this route as superuser. Note that this is not "
             "applied to trigger conditions. If you need to check conditions "
             "as superuser, then that conditions should be marked as 'sudo'.",
        tracking=True)
    sudo_user_id = fields.Many2one(
        'res.users', 'Trigger as user', help='Trigger this route as user',
        tracking=True)
    trigger_on_write_field_ids = fields.Many2many(
        'ir.model.fields', string="Trigger on write (fields)",
        domain=[('model_id.model', '=', 'request.request')],
        tracking=True)
    active = fields.Boolean(
        index=True, default=True, tracking=True)

    @api.onchange('trigger', 'route_id')
    def onchange_gen_trigger_name(self):
        trigger_map = dict(self._fields['trigger'].selection)
        for record in self:
            route = record.route_id
            if record.trigger and not record.route_id:
                record.name = trigger_map.get(record.trigger)
            elif not record.trigger and record.route_id:
                record.name = route.name or route.display_name
            elif record.trigger and record.route_id:
                record.name = "%s | %s" % (
                    trigger_map.get(record.trigger),
                    route.name or route.display_name,
                )
            else:
                record.name = ""

    @api.onchange('dummy_request_type_id')
    def onchange_dummy_request_type_id(self):
        for record in self:
            if record.dummy_request_type_id:
                return {'domain': {'route_id': [
                    ('request_type_id', '=', record.dummy_request_type_id.id),
                ]}}
            return {'domain': {'route_id': []}}

    def _trigger(self, req, req_event=None):
        """ Try to move specified request via route_id.
            Also check trigger conditions

            :param req: Recordset with single request.
            :param req_event: Recordset with single request event.
            :return: True if request moved,
                     False if is not possible to move via this route
        """
        triggerevent = self.env['request.stage.route.trigger.event']
        # Here we create event before running trigger to ensure events have
        # correct ordering (by id), thus if new trigger events will be created
        # during trigger run, then they will be displayed after this event.
        event = triggerevent.sudo().create({
            'date': fields.datetime.now(),
            'trigger_id': self.id,
            'request_id': req.id,
            'user_id': self.env.user.id,
            'request_event_id': req_event and req_event.id,
        })
        if (req_event and self.event_condition_ids and
                not self.event_condition_ids.check(req_event)):
            event.write({
                'success': False,
                'message': _("Denied by request event conditions conditions"),
            })
            # If request does not match trigger conditions, skip it
            return False

        if (self.condition_ids and
                not self.condition_ids.check(req)):
            event.write({
                'success': False,
                'message': _("Denied by trigger conditions"),
            })
            # If request does not match trigger conditions, skip it
            return False

        # Do we use sudo for this trigger
        if self.sudo_enable and not self.sudo_user_id:
            req = req.sudo()
        elif self.sudo_enable and self.sudo_user_id:
            req = req.with_user(self.sudo_user_id)

        event.success = self.route_id.trigger_route(
            req, trigger=self, event=event)
        return event.success

    @api.model
    def _scheduler_trigger_cron(self, cron_type):
        for trigger in self.search([('trigger', '=', cron_type)]):
            requests = self.env['request.request'].search(
                [('type_id', '=', trigger.request_type_id.id),
                 ('stage_id', '=', trigger.route_id.stage_from_id.id)])
            for req in requests:
                trigger._trigger(req)

    @tools.ormcache('stage_id')
    def _get_auto_on_write_trigger_ids_for_stage(self, stage_id):
        """ Return list of IDs of triggers of type 'auto-write'
        """
        return self.search(
            [('route_stage_from_id', '=', stage_id),
             ('trigger', '=', 'auto_on_write')]
        ).ids

    def get_auto_on_write_triggers_for_stage(self, stage):
        """ Return RecordSet with 'auto_on_write' triggers for specified
            request stage.

            :param RecordSet stage: Stage of request to get triggers for
        """
        return self.browse(
            self._get_auto_on_write_trigger_ids_for_stage(stage.id)
        )

    @post_create()
    @post_write('route_id', 'trigger')
    def _after_route_and_trigger_changed_clear_caches(self, changes):
        self._get_auto_on_write_trigger_ids_for_stage.clear_cache(self)

    def unlink(self):
        res = super().unlink()
        self._get_auto_on_write_trigger_ids_for_stage.clear_cache(self)
        return res

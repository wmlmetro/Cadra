import logging

from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class RequestStageRouteTriggerEvent(models.Model):
    _name = "request.stage.route.trigger.event"
    _description = "Request Stage Route Trigger Event"
    _log_access = False
    _order = "id DESC"

    date = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True, readonly=True)
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        readonly=True)
    request_id = fields.Many2one(
        'request.request', required=True, index=True, readonly=True,
        ondelete='cascade')
    request_event_id = fields.Many2one(
        'request.event', readonly=True)
    trigger_id = fields.Many2one(
        'request.stage.route.trigger', required=True, readonly=True,
        ondelete='cascade')
    route_id = fields.Many2one(
        'request.stage.route', readonly=True,
        related='trigger_id.route_id', store=False)
    is_stage_from = fields.Boolean(compute='_compute_is_stage_from')
    message = fields.Text(readonly=True)
    error = fields.Html(readonly=True, help="Error description")
    success = fields.Boolean(default=True, readonly=True, index=True)

    def name_get(self):
        res = []
        for rec in self:
            name = "%s: %s" % (rec.trigger_id.name, rec.route_id.display_name)
            res.append((rec.id, name))
        return res

    @api.model_create_multi
    def create(self, vals):
        values = []
        for v in vals:
            if v.get('error'):
                v = dict(v, success=False)
            values += [v]

        return super().create(values)

    @api.depends('request_id', 'trigger_id', 'request_id.stage_id',
                 'route_id.stage_from_id')
    def _compute_is_stage_from(self):
        for rec in self:
            rec.is_stage_from = (
                rec.request_id.stage_id == rec.route_id.stage_from_id)

    def action_retry_trigger(self):
        self.ensure_one()
        if self.is_stage_from and not self.success:
            self.trigger_id.with_user(self.user_id)._trigger(
                self.request_id, self.request_event_id)
        elif not self.is_stage_from:
            raise exceptions.UserError(_(
                "Cannot retry this trigger event! "
                "Request has already changed its state!"))
        else:
            raise exceptions.UserError(_(
                "Cannot retry this trigger event! "
                "This event was successful!"))

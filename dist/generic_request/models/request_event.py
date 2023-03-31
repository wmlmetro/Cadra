import logging
from odoo import models, fields, api
from .request_request import (AVAILABLE_PRIORITIES,
                              AVAILABLE_IMPACTS,
                              AVAILABLE_URGENCIES)
_logger = logging.getLogger(__name__)


class RequestEvent(models.Model):
    _name = 'request.event'
    _inherit = [
        'generic.system.event.data.mixin',
    ]
    _description = 'Request Event'
    _order = 'event_date DESC, id DESC'
    _log_access = False

    # Deprecated
    request_id = fields.Many2one(
        'request.request', index=True, required=False, readonly=True,
        ondelete='cascade')

    # Assign related events
    old_user_id = fields.Many2one('res.users', readonly=True)
    new_user_id = fields.Many2one('res.users', readonly=True)

    # Author changed
    old_author_id = fields.Many2one('res.partner', readonly=True)
    new_author_id = fields.Many2one('res.partner', readonly=True)

    # Partner changed
    old_partner_id = fields.Many2one('res.partner', readonly=True)
    new_partner_id = fields.Many2one('res.partner', readonly=True)

    # Change request description
    old_text = fields.Html(readonly=True)
    new_text = fields.Html(readonly=True)

    # Change request deadline
    old_deadline = fields.Date()
    new_deadline = fields.Date()

    # Request stage change
    route_id = fields.Many2one('request.stage.route', readonly=True)
    old_stage_id = fields.Many2one('request.stage', readonly=True)
    new_stage_id = fields.Many2one('request.stage', readonly=True)

    # Request Category Change
    old_category_id = fields.Many2one('request.category', readonly=True)
    new_category_id = fields.Many2one('request.category', readonly=True,)

    # Priority changed
    old_priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES, readonly=True)
    new_priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES, readonly=True)

    old_impact = fields.Selection(
        selection=AVAILABLE_IMPACTS, readonly=True)
    new_impact = fields.Selection(
        selection=AVAILABLE_IMPACTS, readonly=True)

    old_urgency = fields.Selection(
        selection=AVAILABLE_URGENCIES, readonly=True)
    new_urgency = fields.Selection(
        selection=AVAILABLE_URGENCIES, readonly=True)

    # Kanban state changed
    old_kanban_state = fields.Selection(
        selection="_get_selection_kanban_state",
        readonly=True)
    new_kanban_state = fields.Selection(
        selection="_get_selection_kanban_state",
        readonly=True)

    # Archive related events
    request_active = fields.Selection(
        selection=[
            ('request-archived', 'Archived'),
            ('request-unarchived', 'Unarchived')],
        readonly=True)

    # Timetracking
    timesheet_line_id = fields.Many2one(
        'request.timesheet.line', 'Timesheet line',
        readonly=True, ondelete='cascade')

    assign_comment = fields.Text()

    # Request parent
    subrequest_id = fields.Many2one('request.request')
    subrequest_old_stage_id = fields.Many2one('request.stage', readonly=True)
    subrequest_new_stage_id = fields.Many2one('request.stage', readonly=True)

    parent_route_id = fields.Many2one('request.stage.route', readonly=True)
    parent_old_stage_id = fields.Many2one('request.stage', readonly=True)
    parent_new_stage_id = fields.Many2one('request.stage', readonly=True)

    parent_old_id = fields.Many2one('request.request', readonly=True)
    parent_new_id = fields.Many2one('request.request', readonly=True)

    old_service_id = fields.Many2one('generic.service', readonly=True)
    new_service_id = fields.Many2one('generic.service', readonly=True)

    old_service_level_id = fields.Many2one('generic.service.level',
                                           readonly=True)
    new_service_level_id = fields.Many2one('generic.service.level',
                                           readonly=True)

    def _get_selection_kanban_state(self):
        return self.env['request.request']._fields['kanban_state'].selection

    @api.model
    def create(self, vals):
        event = super().create(vals)
        event.request_id.invalidate_cache(
            ['request_event_ids', 'request_event_count'])
        return event

    def unlink(self):
        to_invalidate_cache = self.mapped('request_id')
        res = super().unlink()
        to_invalidate_cache.invalidate_cache(
            ['request_event_ids', 'request_event_count'])
        return res

    def get_context(self):
        """ Used in notifications and actions to be backward compatible
        """
        self.ensure_one()
        return {
            'old_user': self.old_user_id,
            'new_user': self.new_user_id,
            'old_text': self.old_text,
            'new_text': self.new_text,
            'route': self.route_id,
            'old_stage': self.old_stage_id,
            'new_stage': self.new_stage_id,
            'old_priority': self.old_priority,
            'new_priority': self.new_priority,
            'old_kanban_state': self.old_kanban_state,
            'new_kanban_state': self.new_kanban_state,
            'old_author_id': self.old_author_id,
            'new_author_id': self.new_author_id,
            'old_partner_id': self.old_partner_id,
            'new_partner_id': self.new_partner_id,
            'request_active': self.request_active,
            'request_event': self,
        }

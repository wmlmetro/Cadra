import logging
from odoo import models, fields
from odoo.addons.generic_request.models.request_request import (
    AVAILABLE_PRIORITIES, AVAILABLE_IMPACTS, AVAILABLE_URGENCIES)
_logger = logging.getLogger(__name__)


class RequestEventAction(models.Model):
    _inherit = 'request.event.action'

    act_type = fields.Selection(
        selection_add=[('set_priority', 'Set priority'), ],
        ondelete={'set_priority': 'cascade'})
    act_priority_type = fields.Selection([
        ('set', 'Set Priority'),
        ('increase', 'Increase Priority'),
        ('decrease', 'Decrease Priority')])
    act_priority_priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES,
    )
    act_priority_impact = fields.Selection(selection=AVAILABLE_IMPACTS)
    act_priority_urgency = fields.Selection(selection=AVAILABLE_URGENCIES)
    act_priority_priority_modifier = fields.Integer(default=1)
    act_priority_impact_modifier = fields.Integer(default=1)
    act_priority_urgency_modifier = fields.Integer(default=1)
    act_priority_is_priority_complex = fields.Boolean(
        related='request_type_id.complex_priority', readonly=True)

    def _run_priority_set_priority(self, request, event):
        if request.is_priority_complex:
            request.impact = self.act_priority_impact
            request.urgency = self.act_priority_urgency
        else:
            request.priority = self.act_priority_priority

    def _run_priority_increase_priority(self, request, event):
        if request.is_priority_complex:
            new_impact = (
                int(request.impact) +
                self.act_priority_impact_modifier)
            request.impact = str(max(0, min(new_impact, 3)))
            new_urgency = (
                int(request.urgency) +
                self.act_priority_urgency_modifier)
            request.urgency = str(max(0, min(new_urgency, 3)))
        else:
            new_priority = (
                int(request.priority) +
                self.act_priority_priority_modifier)
            request.priority = str(max(0, min(new_priority, 5)))

    def _run_priority_decrease_priority(self, request, event):
        if request.is_priority_complex:
            new_impact = (
                int(request.impact) -
                self.act_priority_impact_modifier)
            request.impact = str(min(3, max(new_impact, 0)))
            new_urgency = (
                int(request.urgency) -
                self.act_priority_urgency_modifier)
            request.urgency = str(min(3, max(new_urgency, 0)))
        else:
            new_priority = (
                int(request.priority) -
                self.act_priority_priority_modifier)
            request.priority = str(min(5, max(new_priority, 0)))

    def _run_priority(self, request, event):
        if self.act_priority_type == 'set':
            return self._run_priority_set_priority(request, event)
        if self.act_priority_type == 'increase':
            return self._run_priority_increase_priority(request, event)
        if self.act_priority_type == 'decrease':
            return self._run_priority_decrease_priority(request, event)
        return False

    def _dispatch(self, request, event):
        if self.act_type == 'set_priority':
            return self._run_priority(request, event)
        return super(RequestEventAction, self)._dispatch(request, event)

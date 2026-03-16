from odoo import models, fields, api


class SecurityIncidentEscalate(models.TransientModel):
    _name = 'security.incident.escalate'
    _description = 'Escalate Security Incident'

    incident_id = fields.Many2one(
        comodel_name='security.incident',
        string='Incident',
        required=True,
    )
    escalate_to = fields.Many2one(
        comodel_name='res.users',
        string='Escalate To',
        required=True,
    )
    reason = fields.Text(string='Escalation Reason', required=True)
    notify_police = fields.Boolean(string='Notify Police', default=False)
    police_station = fields.Char(string='Police Station')
    police_report_number = fields.Char(string='Police Report Number')

    def action_escalate(self):
        self.incident_id.write({
            'state': 'escalated',
            'assigned_to': self.escalate_to.id,
        })
        if self.notify_police and self.police_report_number:
            self.incident_id.write({
                'police_report_number': self.police_report_number,
                'police_station': self.police_station,
            })
        # Post message
        self.incident_id.message_post(
            body=f"<p><strong>Escalated to {self.escalate_to.name}</strong></p>"
                 f"<p>Reason: {self.reason}</p>",
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}

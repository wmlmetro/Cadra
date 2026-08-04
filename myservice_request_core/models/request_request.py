from odoo import models, fields, api
from odoo.tools import html2plaintext


class RequestRequest(models.Model):
    """In-house service request — the NRS-owned replacement for CRND's
    ``generic_request``. Provides the ``request.request`` model name so the
    existing myservice_* extensions (which ``_inherit = 'request.request'``)
    and the /api/v1 serializer keep working unchanged, with zero CRND ties.

    Field surface is driven by the frontend API contract in
    myservice_api/controllers/v1_requests.py (the serializer is the spec).
    """
    _name = 'request.request'
    _description = 'Service Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        index=True, default=lambda self: ('New'))
    active = fields.Boolean(default=True)

    # ── Classification ────────────────────────────────────────────────
    type_id = fields.Many2one('request.type', string='Type', tracking=True)
    category_id = fields.Many2one('request.category', string='Category', tracking=True)
    tag_ids = fields.Many2many('request.tag', string='Tags')

    # ── Stage / lifecycle ─────────────────────────────────────────────
    stage_id = fields.Many2one(
        'request.stage', string='Stage', tracking=True, index=True,
        group_expand='_read_group_stage_ids',
        default=lambda self: self._default_stage_id())
    stage_type_id = fields.Many2one(
        'request.stage.type', string='Stage Type',
        related='stage_id.stage_type_id', store=True, readonly=True)
    closed = fields.Boolean(
        string='Closed', compute='_compute_closed', store=True, tracking=True)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked'),
    ], string='Kanban State', default='normal')

    # ── ITIL fields (kept for API/frontend parity) ────────────────────
    priority = fields.Selection([
        ('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Critical'),
    ], default='1', tracking=True)
    impact = fields.Selection([
        ('1', 'Low'), ('2', 'Medium'), ('3', 'High'),
    ], string='Impact')
    urgency = fields.Selection([
        ('1', 'Low'), ('2', 'Medium'), ('3', 'High'),
    ], string='Urgency')

    # ── Content ───────────────────────────────────────────────────────
    request_text = fields.Html(string='Description', sanitize_style=True)
    response_text = fields.Html(string='Response', sanitize_style=True)
    request_text_sample = fields.Char(
        string='Subject', compute='_compute_request_text_sample', store=True,
        help='Short plain-text preview of the description, for list views.')

    @api.depends('request_text')
    def _compute_request_text_sample(self):
        for rec in self:
            text = html2plaintext(rec.request_text or '').strip()
            rec.request_text_sample = (text[:100] + '…') if len(text) > 100 else text

    # ── People ────────────────────────────────────────────────────────
    author_id = fields.Many2one(
        'res.partner', string='Author', tracking=True,
        default=lambda self: self.env.user.partner_id)
    user_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Contact')

    # ── Related domain objects (LGPL generics we keep) ────────────────
    service_id = fields.Many2one('generic.service', string='Service', tracking=True)
    team_id = fields.Many2one('generic.team', string='Team', tracking=True)
    generic_location_id = fields.Many2one(
        'generic.location', string='Location', tracking=True, index=True)

    # ── Structure ─────────────────────────────────────────────────────
    parent_id = fields.Many2one('request.request', string='Parent Request', ondelete='set null')
    child_ids = fields.One2many('request.request', 'parent_id', string='Sub-requests')

    # ── Dates ─────────────────────────────────────────────────────────
    date_created = fields.Datetime(
        string='Created On', default=fields.Datetime.now, readonly=True)
    date_assigned = fields.Datetime(string='Assigned On', readonly=True)
    date_moved = fields.Datetime(string='Last Stage Change', readonly=True)
    date_closed = fields.Datetime(string='Closed On', readonly=True)
    deadline_date = fields.Date(string='Deadline')

    # ── Audit / attachments ───────────────────────────────────────────
    request_event_ids = fields.One2many('request.event', 'request_id', string='Events')
    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id', string='Attachments',
        domain=[('res_model', '=', 'request.request')], auto_join=True)

    # ── Defaults / computes ───────────────────────────────────────────
    @api.model
    def _default_stage_id(self):
        stage = self.env['request.stage'].search([], order='sequence, id', limit=1)
        return stage.id or False

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return self.env['request.stage'].search([], order='sequence, id')

    @api.depends('stage_id', 'stage_id.closed')
    def _compute_closed(self):
        for rec in self:
            rec.closed = bool(rec.stage_id and rec.stage_id.closed)

    @api.onchange('type_id')
    def _onchange_type_id(self):
        for rec in self:
            if rec.type_id and rec.type_id.start_stage_id:
                rec.stage_id = rec.type_id.start_stage_id
            if rec.type_id and rec.type_id.category_id and not rec.category_id:
                rec.category_id = rec.type_id.category_id

    # ── Create / write hooks ──────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'request.request') or '/'
            if not vals.get('stage_id'):
                type_id = vals.get('type_id')
                if type_id:
                    rtype = self.env['request.type'].browse(type_id)
                    if rtype.start_stage_id:
                        vals['stage_id'] = rtype.start_stage_id.id
                if not vals.get('stage_id'):
                    vals['stage_id'] = self._default_stage_id()
        records = super().create(vals_list)
        for rec in records:
            rec._log_event('created')
            if rec.user_id and not rec.date_assigned:
                rec.date_assigned = fields.Datetime.now()
        return records

    def write(self, vals):
        track_stage = 'stage_id' in vals
        track_assign = 'user_id' in vals
        if track_stage:
            vals.setdefault('date_moved', fields.Datetime.now())
        res = super().write(vals)
        if track_stage:
            for rec in self:
                rec._log_event('stage_changed')
                if rec.stage_id.closed and not rec.date_closed:
                    rec.date_closed = fields.Datetime.now()
        if track_assign:
            for rec in self:
                if rec.user_id and not rec.date_assigned:
                    rec.date_assigned = fields.Datetime.now()
        return res

    # ── Helpers ───────────────────────────────────────────────────────
    def _log_event(self, code):
        self.ensure_one()
        etype = self.env['request.event.type'].search([('code', '=', code)], limit=1)
        self.env['request.event'].create({
            'request_id': self.id,
            'event_type_id': etype.id or False,
            'user_id': self.env.user.id,
        })

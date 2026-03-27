from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class NRSAsset(models.Model):
    _name = 'nrs.asset'
    _description = 'NRS Fixed Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'asset_code'

    # ── Identity ─────────────────────────────────────────────
    name = fields.Char('Asset Name', required=True, tracking=True)
    asset_code = fields.Char(
        'Asset Code', copy=False, tracking=True,
        help='Unique asset identifier / barcode tag number')
    asset_tag = fields.Char('Physical Tag No.', tracking=True,
                             help='Barcode or QR tag affixed to the physical asset')
    serial_number = fields.Char('Serial Number')
    model_number = fields.Char('Model / Part No.')
    manufacturer = fields.Char('Manufacturer / Brand')

    # ── Classification ────────────────────────────────────────
    category_id = fields.Many2one(
        'nrs.asset.category', string='Category', required=True, tracking=True)
    domain = fields.Selection([
        ('building',  'Building Services'),
        ('plant',     'Plant & Machinery'),
        ('plumbing',  'Plumbing & Drainage'),
        ('fleet',     'Fleet Management'),
        ('security',  'Security & Safety'),
        ('it',        'IT & Communications'),
        ('furniture', 'Furniture & Fittings'),
        ('other',     'Other'),
    ], string='FM Domain', required=True, default='plant', tracking=True)

    # ── Location & Custodian ──────────────────────────────────
    location_id = fields.Many2one(
        'generic.location', string='NRS Location', tracking=True)
    floor_room = fields.Char('Floor / Room / Area',
                              help='E.g. Ground Floor, Server Room, Car Park')
    custodian_id = fields.Many2one(
        'hr.employee', string='Custodian', tracking=True,
        help='Staff member responsible for this asset')
    department = fields.Char('Department')

    # ── Condition & Status ────────────────────────────────────
    condition = fields.Selection([
        ('new',       'New'),
        ('good',      'Good'),
        ('fair',      'Fair'),
        ('poor',      'Poor'),
        ('condemned', 'Condemned'),
        ('missing',   'Missing / Unverified'),
    ], string='Condition', default='good', tracking=True)

    state = fields.Selection([
        ('active',    'Active'),
        ('in_repair', 'Under Repair'),
        ('disposed',  'Disposed'),
        ('transferred','Transferred'),
        ('missing',   'Missing'),
    ], string='Status', default='active', tracking=True)

    # ── Financial ─────────────────────────────────────────────
    acquisition_date = fields.Date('Acquisition Date')
    acquisition_cost = fields.Float('Acquisition Cost (₦)', digits=(14, 2))
    current_value = fields.Float('Current Value (₦)', digits=(14, 2))
    disposal_date = fields.Date('Disposal Date')
    disposal_reason = fields.Text('Disposal Reason')

    # ── Verification ─────────────────────────────────────────
    last_verified_date = fields.Date('Last Verified', tracking=True)
    last_verified_by = fields.Many2one('res.users', string='Verified By')
    verification_notes = fields.Text('Verification Notes')
    is_verified = fields.Boolean('Verified', compute='_compute_verified', store=True)

    # ── PM ────────────────────────────────────────────────────
    pm_schedule_ids = fields.One2many(
        'nrs.asset.pm', 'asset_id', string='PM Schedules')
    pm_count = fields.Integer('PM Schedules', compute='_compute_pm_count')
    last_service_date = fields.Date('Last Serviced')
    next_service_date = fields.Date('Next Service Due', compute='_compute_next_service', store=True)

    # ── Maintenance requests ──────────────────────────────────
    request_ids = fields.One2many(
        'request.request', 'nrs_asset_id', string='Maintenance Requests')
    request_count = fields.Integer('Requests', compute='_compute_request_count')

    # ── Transfer history ──────────────────────────────────────
    transfer_ids = fields.One2many(
        'nrs.asset.transfer', 'asset_id', string='Transfers')

    # ── Notes ─────────────────────────────────────────────────
    notes = fields.Text('Notes')
    image = fields.Image('Asset Photo', max_width=1024, max_height=1024)

    @api.model
    def create(self, vals):
        if not vals.get('asset_code'):
            vals['asset_code'] = self.env['ir.sequence'].next_by_code('nrs.asset') or '/'
        return super().create(vals)

    @api.depends('last_verified_date')
    def _compute_verified(self):
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=365)
        for r in self:
            r.is_verified = bool(r.last_verified_date and r.last_verified_date >= cutoff)

    @api.depends('pm_schedule_ids')
    def _compute_pm_count(self):
        for r in self:
            r.pm_count = len(r.pm_schedule_ids)

    @api.depends('pm_schedule_ids.next_due_date')
    def _compute_next_service(self):
        for r in self:
            upcoming = r.pm_schedule_ids.filtered(
                lambda p: p.next_due_date and p.active
            ).sorted('next_due_date')
            r.next_service_date = upcoming[0].next_due_date if upcoming else False

    @api.depends('request_ids')
    def _compute_request_count(self):
        for r in self:
            r.request_count = len(r.request_ids)

    def action_verify(self):
        from datetime import date
        self.write({
            'last_verified_date': date.today(),
            'last_verified_by': self.env.uid,
        })
        self.message_post(body=_('Asset verified by %s') % self.env.user.name)

    def action_condemn(self):
        self.write({'condition': 'condemned', 'state': 'disposed'})

    def action_mark_missing(self):
        self.write({'condition': 'missing', 'state': 'missing'})

    def action_view_pm_schedules(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'PM Schedules — %s' % self.name,
            'res_model': 'nrs.asset.pm',
            'view_mode': 'tree,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_requests(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Maintenance Requests — %s' % self.name,
            'res_model': 'request.request',
            'view_mode': 'tree,form',
            'domain': [('nrs_asset_id', '=', self.id)],
            'context': {'default_nrs_asset_id': self.id},
        }

    _sql_constraints = [
        ('asset_code_unique', 'unique(asset_code)', 'Asset code must be unique.'),
    ]


class NRSAssetCategory(models.Model):
    _name = 'nrs.asset.category'
    _description = 'Asset Category'
    _order = 'name'

    name = fields.Char('Category Name', required=True)
    code = fields.Char('Code')
    domain = fields.Selection([
        ('building',  'Building Services'),
        ('plant',     'Plant & Machinery'),
        ('plumbing',  'Plumbing & Drainage'),
        ('fleet',     'Fleet'),
        ('security',  'Security & Safety'),
        ('it',        'IT & Communications'),
        ('furniture', 'Furniture & Fittings'),
        ('other',     'Other'),
    ], string='FM Domain')
    pm_interval_days = fields.Integer(
        'Default PM Interval (days)',
        help='Default number of days between preventive maintenance for this category')
    description = fields.Text('Description')
    asset_count = fields.Integer('Assets', compute='_compute_asset_count')

    @api.depends()
    def _compute_asset_count(self):
        for c in self:
            c.asset_count = self.env['nrs.asset'].search_count([('category_id', '=', c.id)])

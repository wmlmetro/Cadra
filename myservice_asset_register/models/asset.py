from odoo import models, fields, api, release, _
from odoo.exceptions import ValidationError

# Odoo 19 removed `_sql_constraints`: orm/model_classes.py logs "no longer
# supported" and creates nothing, so a constraint declared the old way
# silently ceases to exist. Both spellings are kept until the 15 production
# stack is retired. `models.Constraint` names the constraint
# "<table>_<attribute name without its leading underscore>", which is exactly
# what the legacy list produced, so the two are interchangeable in the
# database and no 15→19 database ends up with an orphan.
_ODOO_MAJOR = release.version_info[0]


class NRSAsset(models.Model):
    _name = 'nrs.asset'
    _description = 'Fixed Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'asset_code'

    # ── Identity ─────────────────────────────────────────────
    name = fields.Char('Asset Name', required=True, tracking=True)
    asset_code = fields.Char(
        string='Asset Code', readonly=True, copy=False, tracking=True, index=True,
        help='Unique system-generated asset identifier')
    asset_tag = fields.Char(string='Tag Code', tracking=True,
                             help='Barcode or QR tag affixed to the physical asset')
    legacy_asset_code = fields.Char(string='Legacy Asset Code')
    serial_number = fields.Char(string='Serial Number')
    make = fields.Char(string='Make / Brand')
    model_name = fields.Char(string='Model')
    manufacturer = fields.Char('Manufacturer / Brand')

    # ── Classification ────────────────────────────────────────
    category_id = fields.Many2one(
        'nrs.asset.category', string='Category', required=True, tracking=True)
    subcategory_id = fields.Many2one(
        'nrs.asset.subcategory', string='Sub-Category', tracking=True)
    asset_type_id = fields.Many2one(
        'nrs.asset.type', string='Asset Type', tracking=True)
    asset_level = fields.Selection([
        ('group',     'Asset Group'),
        ('asset',     'Asset'),
        ('sub_asset', 'Sub-Asset'),
        ('component', 'Component'),
    ], string='Asset Level', default='asset', tracking=True)
    domain = fields.Selection(
        string='FM Domain', related='category_id.domain', store=True,
        readonly=False, tracking=True)

    # ── Hierarchy ─────────────────────────────────────────────
    parent_id = fields.Many2one('nrs.asset', string='Parent Asset', index=True)
    child_ids = fields.One2many('nrs.asset', 'parent_id', string='Sub-Assets')

    # ── Location & Custodian ──────────────────────────────────
    building_id = fields.Many2one(
        'generic.location', string='Building', tracking=True)
    floor_id = fields.Many2one(
        'generic.location', string='Floor', tracking=True,
        domain="[('parent_id', '=', building_id)]")
    room_id = fields.Many2one(
        'generic.location', string='Room', tracking=True,
        domain="[('parent_id', '=', floor_id)]")
    location_id = fields.Many2one(
        'generic.location', string='Location', tracking=True)
    floor_room = fields.Char(string='Floor / Room')
    address_display = fields.Text(
        string='Address', compute='_compute_address_display')
    latitude_display = fields.Char(
        string='Latitude', compute='_compute_geo_display')
    longitude_display = fields.Char(
        string='Longitude', compute='_compute_geo_display')
    custodian_id = fields.Many2one(
        'hr.employee', string='Custodian', tracking=True,
        help='Staff member responsible for this asset')
    department = fields.Char('Department')

    # ── Condition & Status ────────────────────────────────────
    condition = fields.Selection([
        ('new',              'New'),
        ('good',             'Good'),
        ('fair',             'Fair'),
        ('poor',             'Poor'),
        ('decommissioned',   'Decommissioned'),
    ], string='Condition', default='good', tracking=True)

    state = fields.Selection([
        ('active',    'Active'),
        ('in_repair', 'Under Repair'),
        ('disposed',  'Disposed'),
        ('transferred','Transferred'),
        ('missing',   'Missing'),
    ], string='Status', default='active', tracking=True)

    # ── Financial ─────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.ref('base.NGN', raise_if_not_found=False))
    purchase_date = fields.Date(string='Purchase Date')
    warranty_expiry = fields.Date(string='Warranty Expiry')
    purchase_value = fields.Monetary(string='Purchase Value (₦)', currency_field='currency_id')
    replacement_cost = fields.Monetary(string='Replacement Cost (₦)', currency_field='currency_id')
    acquisition_date = fields.Date('Acquisition Date')
    acquisition_cost = fields.Float('Acquisition Cost (₦)', digits=(14, 2))
    current_value = fields.Float('Current Value (₦)', digits=(14, 2))
    disposal_date = fields.Date('Disposal Date')
    disposal_reason = fields.Text('Disposal Reason')

    # ── Acquisition provenance (INT-03) ───────────────────────
    # Where this asset came from, carried in from the goods-receipt system.
    # Char rather than relational on purpose: Vendra owns the authoritative
    # GRN/PO records and SAP owns the purchase order, so modelling them here
    # would mean maintaining a shadow copy of another system's master data.
    # Indexed because `?grn_reference=` is the audit lookup these exist for.
    grn_reference = fields.Char(
        string='GRN Reference', index=True,
        help='Goods Receipt Note that brought this asset onto the register')
    purchase_order_reference = fields.Char(
        string='PO Reference', index=True,
        help='Purchase Order this asset was procured against')
    purchase_vendor = fields.Char(
        string='Purchase Vendor', index=True,
        help='Supplier the asset was bought from. Distinct from the '
             'Primary Maintenance Vendor, which is who services it.')

    # ── Vendor ────────────────────────────────────────────────
    maintenance_vendor_id = fields.Many2one(
        'res.partner', string='Primary Maintenance Vendor')

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

    @api.onchange('building_id')
    def _onchange_building_id(self):
        self.floor_id = False
        self.room_id = False

    @api.onchange('floor_id')
    def _onchange_floor_id(self):
        self.room_id = False

    @api.onchange('room_id')
    def _onchange_room_id(self):
        if self.room_id:
            self.location_id = self.room_id
            floor_code = self.floor_id.zone_code or ''
            room_code = self.room_id.zone_code or ''
            self.floor_room = '%s — %s' % (floor_code, room_code) if floor_code and room_code else ''
        elif self.floor_id:
            self.location_id = self.floor_id
        elif self.building_id:
            self.location_id = self.building_id

    @api.depends('building_id', 'building_id.street', 'building_id.street2',
                 'building_id.city', 'building_id.state_name',
                 'building_id.country_name')
    def _compute_address_display(self):
        for r in self:
            b = r.building_id
            if b:
                parts = [p for p in [b.street, b.street2, b.city,
                                     b.state_name, b.country_name] if p]
                r.address_display = ', '.join(parts) if parts else ''
            else:
                r.address_display = ''

    @api.depends('building_id', 'building_id.latitude', 'building_id.longitude')
    def _compute_geo_display(self):
        for r in self:
            b = r.building_id
            if b and (b.latitude or b.longitude):
                lat = b.latitude
                lon = b.longitude
                lat_dir = 'N' if lat >= 0 else 'S'
                lon_dir = 'E' if lon >= 0 else 'W'
                r.latitude_display = '%.4f°%s' % (abs(lat), lat_dir)
                r.longitude_display = '%.4f°%s' % (abs(lon), lon_dir)
            else:
                r.latitude_display = ''
                r.longitude_display = ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('asset_code'):
                vals['asset_code'] = self.env['ir.sequence'].next_by_code('nrs.asset') or '/'
        return super().create(vals_list)

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
        self.write({'condition': 'decommissioned', 'state': 'disposed'})

    def action_mark_missing(self):
        self.write({'state': 'missing'})

    def action_view_requests(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Maintenance Requests — %s' % self.name,
            'res_model': 'request.request',
            'view_mode': 'tree,form',
            'domain': [('nrs_asset_id', '=', self.id)],
            'context': {'default_nrs_asset_id': self.id},
        }

    # One asset per code is an identity guarantee, not a tidiness rule: the
    # September Integration Flow makes dual-code reconciliation a control
    # point, and INT-06/07 matches a SAP asset code to exactly one Cadra
    # asset. Two assets sharing a code would let that match the wrong one.
    if _ODOO_MAJOR >= 19:
        _asset_code_unique = models.Constraint(
            'UNIQUE (asset_code)',
            'Asset code must be unique.',
        )
    else:
        _sql_constraints = [
            ('asset_code_unique', 'unique(asset_code)', 'Asset code must be unique.'),
        ]


class NRSAssetCategory(models.Model):
    _name = 'nrs.asset.category'
    _description = 'Asset Category'
    _order = 'name'

    name = fields.Char('Category Name', required=True)
    code = fields.Char('Code')
    sequence = fields.Integer('Sequence', default=10)
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


class NRSAssetSubcategory(models.Model):
    _name = 'nrs.asset.subcategory'
    _description = 'Asset Sub-category'
    _order = 'sequence, name'

    name = fields.Char('Sub-category Name', required=True)
    code = fields.Char('Code')
    sequence = fields.Integer('Sequence', default=10)
    category_id = fields.Many2one(
        'nrs.asset.category', string='Category', required=True, ondelete='cascade')
    description = fields.Text('Description')
    asset_count = fields.Integer('Assets', compute='_compute_asset_count')

    @api.depends()
    def _compute_asset_count(self):
        for r in self:
            r.asset_count = self.env['nrs.asset'].search_count([('subcategory_id', '=', r.id)])


class NRSAssetType(models.Model):
    _name = 'nrs.asset.type'
    _description = 'Asset Type'
    _order = 'code, name'

    name = fields.Char('Type Name', required=True)
    code = fields.Char('Code')
    subcategory_id = fields.Many2one(
        'nrs.asset.subcategory', string='Sub-category', required=True, ondelete='cascade')
    category_id = fields.Many2one(
        'nrs.asset.category', string='Category', related='subcategory_id.category_id', store=True)
    description = fields.Text('Description')
    asset_count = fields.Integer('Assets', compute='_compute_asset_count')

    @api.depends()
    def _compute_asset_count(self):
        for r in self:
            r.asset_count = self.env['nrs.asset'].search_count([('asset_type_id', '=', r.id)])

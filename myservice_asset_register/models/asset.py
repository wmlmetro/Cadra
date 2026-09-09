from datetime import timedelta

from odoo import models, fields, api, release, _
from odoo.exceptions import ValidationError
from odoo.tools import config

from .asset_custody import CUSTODY_REASON_KEY

# How long a physical verification counts as current, when the asset's category
# does not state its own window. Database-per-tenant means a config parameter
# IS per-tenant.
PARAM_VERIFICATION_INTERVAL = 'cadra.assets.verification_interval_days'
DEFAULT_VERIFICATION_INTERVAL_DAYS = 365

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
    # `required` is what makes the unique constraint below mean what INT-06/07
    # assumes. Postgres does not compare NULLs for uniqueness, so without NOT
    # NULL the guarantee is only "one asset per *non-null* code" — and SAP
    # dual-code reconciliation matches a SAP code to exactly one Cadra asset.
    # Filled by `create()` below, never by a caller: it is absent from the
    # API's `_WRITABLE_FIELDS` and readonly in the form.
    asset_code = fields.Char(
        string='Asset Code', readonly=True, required=True, copy=False,
        tracking=True, index=True,
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

    # ── Chain of custody ──────────────────────────────────────
    # `copy=False` is load-bearing, not tidiness. Odoo's Duplicate action
    # copies a one2many by re-creating its lines, so without this the new
    # asset would open with the ORIGINAL asset's custody links — same
    # timestamps, same actors, same `source` — and they are append-only, so
    # the fabrication could never be removed. `transfer_ids` has the same
    # shape and is merely untidy; here it would be invented evidence.
    custody_ids = fields.One2many(
        'nrs.asset.custody', 'asset_id', string='Chain of Custody',
        readonly=True, copy=False)

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
                code = self.env['ir.sequence'].next_by_code('nrs.asset')
                if not code:
                    # This used to fall back to '/'. With asset_code now unique
                    # and NOT NULL, that placeholder made the FIRST asset look
                    # fine and every one after it fail on a constraint whose
                    # message says nothing about the real problem. A missing
                    # sequence is a provisioning fault; say so once, clearly.
                    raise ValidationError(_(
                        'The asset code sequence "nrs.asset" is missing from '
                        'this database, so no asset code can be generated. '
                        'This is a provisioning fault — restore the sequence '
                        'before creating assets.'))
                vals['asset_code'] = code
        records = super().create(vals_list)
        # An asset created already assigned to somebody is the FIRST link of
        # its chain, not a state that precedes the chain. The chatter
        # tracking rows this model replaces record creation the same way
        # (`old_value_integer = 0`), so leaving it out would make the
        # backfilled half and the live half disagree about what a chain
        # begins with.
        for record in records:
            if record.custodian_id:
                record._record_custody_change(
                    self.env['hr.employee'], record.custodian_id)
        return records

    def write(self, vals):
        """Record every custodian change, whoever made it.

        The handoff scoped this to `POST /assets/<id>/transfer-custody`, on
        the grounds that it is the only writer. It is not: `custodian_id` is
        in the API's `_WRITABLE_FIELDS`, so both `POST /assets` and `PATCH
        /assets/<id>` write it; `nrs.asset.transfer.action_complete` writes
        it; `action_mark_retrieved` in `myservice_identity` clears it; and it
        is an editable field on the Odoo form. Recording in the route would
        have produced a chain that was incomplete on its first day — which
        is the one failure an append-only model cannot recover from, because
        a gap in it is indistinguishable from a period of no movement.

        So the recorder sits at the ORM, where every writer passes. Callers
        that know why they are writing declare it through
        `CUSTODY_SOURCE_KEY` in the context; everything else is `direct`.
        """
        if 'custodian_id' not in vals:
            return super().write(vals)
        before = {record.id: record.custodian_id for record in self}
        result = super().write(vals)
        for record in self:
            was = before.get(record.id, self.env['hr.employee'])
            now = record.custodian_id
            if was.id != now.id:
                record._record_custody_change(was, now)
        return result

    def _record_custody_change(self, from_custodian, to_custodian):
        """Append one link to this asset's chain.

        `reason` is read off the context because the ORM write that carries a
        custody change carries no room for one — the transfer-custody route
        supplies it there alongside the source.
        """
        self.ensure_one()
        return self.env['nrs.asset.custody']._record(
            self, from_custodian, to_custodian,
            reason=self.env.context.get(CUSTODY_REASON_KEY),
        )

    @api.depends('last_verified_date',
                 'category_id', 'category_id.verification_interval_days')
    def _compute_verified(self):
        """True while the last physical verification is still inside its window.

        The window is resolved per record because it is a per-category setting:
        a fire extinguisher and a filing cabinet are not verified on the same
        cycle. `category_id.verification_interval_days` is in `@api.depends`
        so that shortening a category's window flags its assets immediately
        rather than at the next cron tick.

        Note what is NOT a dependency and cannot be: today's date. Nothing in
        the database changes on the day a verification lapses, which is why
        `_cron_refresh_verification` exists.
        """
        # fields.Date.today(), NOT context_today(). context_today resolves the
        # READER's timezone, and this field is stored: in the 23:00-00:00 UTC
        # band a Lagos user (UTC+1) would compute a cutoff one day ahead of the
        # cron (OdooBot, tz unset, so UTC), and the column would flip and
        # un-flip depending on who last triggered the compute. `action_verify`
        # writes `last_verified_date` server-local too, so this matches the
        # value it is compared against.
        today = fields.Date.today()
        default_days = self._verification_interval_days()
        for r in self:
            days = r.category_id.verification_interval_days or default_days
            cutoff = today - timedelta(days=days)
            r.is_verified = bool(r.last_verified_date and r.last_verified_date >= cutoff)

    @api.model
    def _verification_interval_days(self):
        """The tenant-wide fallback window, in days.

        Used for assets whose category states no window of its own. A tenant
        that counts its estate quarterly wants a shorter default than the
        annual one, and auditors ask for the number to be stated rather than
        buried in code. A missing, non-numeric or non-positive parameter falls
        back to the documented default rather than producing a nonsense cutoff
        — a `0` here would mean "verified only if verified today", which is
        not a setting anybody intends to type.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            PARAM_VERIFICATION_INTERVAL, DEFAULT_VERIFICATION_INTERVAL_DAYS)
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = DEFAULT_VERIFICATION_INTERVAL_DAYS
        return days if days > 0 else DEFAULT_VERIFICATION_INTERVAL_DAYS

    @api.model
    def _cron_refresh_verification(self, batch_size=2000):
        """Re-evaluate is_verified against today's date.

        is_verified is stored, and everything it depends on is static: an asset
        verified 364 days ago stays flagged verified for ever, because nothing
        in the database changes on the day it lapses. Same shape as the monthly
        depreciation recompute — the value moves with the calendar, so a cron
        has to push it.

        The field is marked directly and flushed per batch. Marking the field
        rather than a dependency matters: this cron exists precisely because no
        dependency covers the clock, so a refresh routed through the dependency
        graph would become a no-op the day someone edits `@api.depends`. And
        without the flush the write waits for the transaction's own commit —
        which under test never comes, so the method would report a count for
        work that had not been done.
        """
        assets = self.search([('last_verified_date', '!=', False)])
        field = self._fields['is_verified']
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        for i in range(0, len(assets), batch_size):
            batch = assets[i:i + batch_size]
            # Read the current value first: a recomputed field is written only
            # when the new value differs from what is in cache, and "absent
            # from cache" counts as different. Without this the daily sweep
            # UPDATEs every row it looks at and bumps every write_date to say
            # nothing changed.
            batch.fetch(['is_verified'])
            # Mark the FIELD, not something it depends on. This cron exists
            # because no dependency covers the clock, so routing the refresh
            # through the dependency graph would turn it into a no-op the day
            # someone edits @api.depends.
            self.env.add_to_compute(field, batch)
            self.env.flush_all()
            # Commit per batch so a long run over a large register does not
            # hold one transaction open — but never inside a test, where
            # committing breaks the surrounding rollback.
            if not in_test:
                self.env.cr.commit()
        return len(assets)

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
    verification_interval_days = fields.Integer(
        'Verification Interval (days)',
        help='How long a physical verification of an asset in this category '
             'stays current, in days. Leave at 0 to use the tenant-wide '
             'default (the "cadra.assets.verification_interval_days" system '
             'parameter, 365 days if unset).')
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

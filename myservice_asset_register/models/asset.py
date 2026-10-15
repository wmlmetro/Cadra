from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, release, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

from ..approval_policy import (
    APPROVAL_KEY, EXEMPT_KEY, EXEMPT_REASONS, approval_required, set_command)
from .asset_custody import CUSTODY_REASON_KEY, CUSTODY_SOURCE_KEY
from .asset_movement import MOVEMENT_REASON_KEY, MOVEMENT_SOURCE_KEY
from .asset_event import (
    EVENT_REASON_KEY, EVENT_SOURCE_KEY, EVENT_REFERENCE_CHANGED,
    EVENT_STATUS_CHANGED, EVENT_VERIFICATION_DATE_SET, EVENT_VERIFIED,
    EVENT_WARRANTY_CHANGED, REFERENCE_FIELDS, WARRANTY_FIELDS)

# The status nothing leaves. See `NRSAsset._assert_disposed_is_terminal`.
STATE_DISPOSED = 'disposed'

# The sources under which the ACTOR of a verification is the verifier —
# `action_verify` and the route that calls it. Under any other source somebody
# wrote a verification DATE, and the record does not say who checked anything.
_VERIFIER_SOURCES = ('action', 'api_verify')


# The longest warranty the register will take, in months. Fifty years is past
# anything a manufacturer quotes; a figure above it is a typo — a year typed
# into the months box — and refusing it is kinder than an expiry in 2226.
WARRANTY_MAX_MONTHS = 600

def warranty_expiry_of(start, months):
    """The day a warranty of `months` from `start` expires.

    Calendar months, clamped to the end of a short month: 24 months from 29
    February 2024 is 28 February 2026. The expiry day itself is still inside
    the warranty — *"expires 12 March 2028"* is read by everybody who says it
    as covered on the 12th.
    """
    return start + relativedelta(months=months)


def _event_value(value):
    """A warranty field's value as the event records it: a date as its ISO
    string, a duration as its number, a name as typed, nothing as nothing."""
    if not value:
        return False
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _m2o_id(value):
    """The id a many2one value in `vals` names. `False` for empty."""
    if isinstance(value, models.BaseModel):
        return value.id or False
    return value or False

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
    # DESCENDING, and the `desc` is the whole point. `asset_code` is a
    # zero-padded `ir.sequence` (`NRS-AST-000001`), so lexical order IS
    # creation order — and ascending put every newly created asset on the
    # last page of the list, which is where a user who had just created one
    # went looking for it. Sorting the sequence backwards buys newest-first
    # AND keeps the register ordered by code; `create_date desc` would have
    # given the first and lost the second.
    #
    # This is the model default, so it reaches list, kanban and every other
    # view at once. It does NOT reach the API: `paginate()` sorts on `id`
    # explicitly (`myservice_api/controllers/utils.py`) rather than falling
    # back to `_order`, so `GET /api/v1/assets` and its cursor are unaffected
    # and this is not a change Vendra can observe.
    _order = 'asset_code desc'

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

    # ── Warranty (handoff 34) ─────────────────────────────────
    # A fact about a CONTRACT, not about the asset. An expired warranty is
    # not a condition, not a lifecycle state and not a review status, and
    # nothing here feeds a pill, a filter default or any count read as
    # working stock — the register has twice been bitten by exactly that
    # confusion (*Good · Cleared* on a disposed asset; 282 assets no filter
    # could reach).
    #
    # Everything is optional. Most assets have no warranty and never will,
    # and an asset without one is the ordinary case, not a gap.
    #
    # `warranty_expiry` keeps its name, its type and its published key. It
    # existed before this handoff with a form input and a published key,
    # and no value had ever reached it (0 of 1,335 on `cadra19`, 0 of 4,164
    # on `jaizbankplc`).
    #
    # THE ANSWER AND THE WORKING. When a start date and a duration are both
    # recorded, the expiry is DERIVED from them in `_resolve_warranty` and a
    # contradicting date is refused — *"24 months from 12 March 2026"* can be
    # checked against the certificate; a bare *"expires 12 March 2028"*
    # cannot. An expiry with no basis stays accepted, because somebody
    # holding only a date should be able to record it; the API then says it
    # was entered as a date.
    #
    # NOT tracked in the chatter: a change to any of the five is an
    # append-only `nrs.asset.event` (`warranty_changed`), which is their
    # record. Tracking them as well would add them to the register
    # snapshot's roll-back contract, which warranty is not part of.
    warranty_expiry = fields.Date(
        string='Warranty Expiry',
        help='The last day the warranty covers. Derived from the start date '
             'and the duration when both are recorded.')
    warranty_start_date = fields.Date(
        string='Warranty Start',
        help='The day the warranty runs from — usually the day the asset '
             'was received.')
    warranty_months = fields.Integer(
        string='Warranty Duration (months)',
        help='How long the warranty runs, as quoted: 24 for two years.')
    # A NAME as recorded, and not a link to a partner record. Cadra holds no
    # vendor record for an asset arriving from Vendra, and the custody
    # chain's rule is the precedent: the name as it stood when the record
    # was made, so a partner deleted or renamed later cannot empty the row.
    warrantor = fields.Char(
        string='Warranty Honoured By',
        help='Who honours the warranty — the manufacturer, the supplier or '
             'a service agent — as named on the certificate.')
    warranty_reference = fields.Char(
        string='Warranty Certificate / Reference',
        help='The certificate or document number to quote when claiming.')
    # Three states and not two: `none` is the honest third — nothing has
    # been recorded — and it is almost every asset on every register.
    # Folding it into `expired` would be the system asserting a lapsed
    # contract it has never seen. Written inline because
    # `tests/test_frontend_enums.py` reads a published Selection statically.
    warranty_status = fields.Selection([
        ('under_warranty', 'Under warranty'),
        ('expired',        'Expired'),
        ('none',           'No warranty recorded'),
    ], string='Warranty',
        compute='_compute_warranty_status',
        search='_search_warranty_status',
        help='Judged against today in Lagos. Not stored: it moves with the '
             'calendar, and a stored column would need a job to push it.')
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
    #
    # TRACKED since handoff 28. The API's `_WRITABLE_FIELDS` carried a comment
    # saying a later change to these "is tracked on the asset's mail.thread",
    # and for as long as that comment existed it was false: none of them was.
    # They are exactly what an auditor traces back to Vendra and to SAP, and a
    # mis-stated GRN could be rewritten over PATCH leaving nothing anywhere.
    # What tracking buys is VISIBILITY, not protection — the change is a
    # chatter line, deletable by the same people who can make it. And it
    # reaches back only to `cadra.provenance_tracked_from`, which migration
    # 19.0.1.15.0 stamps on each database; the register snapshot reads that
    # rather than claiming a history these fields do not have.
    grn_reference = fields.Char(
        string='GRN Reference', index=True, tracking=True,
        help='Goods Receipt Note that brought this asset onto the register')
    purchase_order_reference = fields.Char(
        string='PO Reference', index=True, tracking=True,
        help='Purchase Order this asset was procured against')
    purchase_vendor = fields.Char(
        string='Purchase Vendor', index=True, tracking=True,
        help='Supplier the asset was bought from. Distinct from the '
             'Primary Maintenance Vendor, which is who services it.')

    # ── Vendor ────────────────────────────────────────────────
    maintenance_vendor_id = fields.Many2one(
        'res.partner', string='Primary Maintenance Vendor')

    # ── Verification ─────────────────────────────────────────
    last_verified_date = fields.Date('Last Verified', tracking=True)
    # TRACKED since handoff 28, so that a verifier being replaced — or
    # cleared by a date that arrived without one, see `write` — is a line in
    # the history rather than a silent overwrite. Two verifications on one
    # day change no DATE, and without this the asset would say Bob while the
    # only `verified` line in its history said Alice.
    last_verified_by = fields.Many2one(
        'res.users', string='Verified By', tracking=True)
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

    # `copy=False` for the reason above, word for word: a duplicated asset
    # would otherwise arrive carrying another asset's moves, and they could
    # never be removed.
    movement_ids = fields.One2many(
        'nrs.asset.movement', 'asset_id', string='Movement Record',
        readonly=True, copy=False)

    # `copy=False` for the reason above, a third time: verifications, status
    # changes and reference changes that happened to ANOTHER asset.
    event_ids = fields.One2many(
        'nrs.asset.event', 'asset_id', string='Event Record',
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
        vals_list = [self.browse()._resolve_warranty(vals)
                     for vals in vals_list]
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
            # The same argument, for where it is: an asset created AT a
            # location begins its movement record there, from nowhere.
            if record.location_id:
                record._record_movement(
                    self.env['generic.location'], record.location_id)
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
        # WHERE IT IS gets the same treatment as WHO HOLDS IT, since handoff
        # 28, and for the same reason. Handoff 27 measured the writers of
        # `location_id`: only `POST /assets/<id>/move` and a completed
        # transfer left a row, and PATCH, this model's own form, the
        # building/floor/room onchanges and the importer left a deletable
        # chatter line — 1,146 of them on `nrs19` against one transfer row.
        # Both are read BEFORE `super()` and compared AFTER, so a write that
        # names a field without changing it records nothing, and a
        # multi-record write records one row per asset that actually moved.
        # A VERIFICATION DATE THAT ARRIVES WITHOUT A VERIFIER HAS NONE.
        # `last_verified_date` is writable over the API and on the form;
        # `last_verified_by` is written by `action_verify`. So a PATCH of the
        # date used to leave the PREVIOUS verifier standing beside it: Alice
        # verifies in January, an integration PATCHes a June date, and the
        # asset reads "verified in June, by Alice" — who checked nothing in
        # June. That is naming a person the record does not have, and the
        # first draft of handoff 28 published three sentences saying it could
        # not happen. Here rather than in the route, for the reason the two
        # recorders below are: the date has more than one writer.
        if 'last_verified_date' in vals and 'last_verified_by' not in vals:
            vals = dict(vals, last_verified_by=False)
        # A warranty's expiry is resolved against the record's OWN start and
        # duration, so a write naming them is resolved one record at a time:
        # "36 months" on two assets with different start dates is two
        # different expiries, and one `vals` cannot say both.
        #
        # Per record through `_write_recorded`, NOT by calling `write` again.
        # The first draft re-entered `record.write(vals)`, which starts again
        # at the TOP of the chain — so every override above this one ran
        # once for the set and once per record. `myservice_workflow`'s SAP
        # lifecycle events read the state before, call super and queue after,
        # with no dedup: a disposal written to two assets with a warranty
        # field beside it would have told SAP each asset was disposed twice
        # (found by the verification pass; no caller did it yet).
        if set(WARRANTY_FIELDS) & set(vals) and self:
            if len(self) > 1:
                for record in self:
                    record._write_recorded(record._resolve_warranty(vals))
                return True
            vals = self._resolve_warranty(vals)
        return self._write_recorded(vals)

    def _write_recorded(self, vals):
        """The write itself, with its guard and its recorders — everything
        in `write` after the values are settled. Separate only so a warranty
        resolved per record can be written per record without re-entering
        the overrides above `write`; nothing else should call it."""
        # BEFORE anything is written, and here rather than in a route for the
        # reason everything else in `write` is here.
        self._assert_disposed_is_terminal(vals)
        # A receipt candidate is not on the register: no custodian, no move,
        # no disposal (handoff 58, P5). Before the approval gate, which has
        # exemptions this rule must not inherit, and after the terminal rule,
        # which speaks first for the same reason it does on the routes.
        # Defined with the gates, in `asset_gates.py`.
        self._assert_on_the_register(vals)
        # And, since handoff 35, whether a second person has agreed to it.
        # Same placement, same argument: `location_id` has twelve writers and
        # `custodian_id` thirteen, and a rule enforced in the three the app
        # happens to call is a rule with ten doors round it.
        self._assert_change_is_approved(vals)
        track_custody = 'custodian_id' in vals
        track_location = 'location_id' in vals
        # WHAT HAS HAPPENED TO IT, since handoff 30 — a verification, a
        # change of status, a change to one of the three references an
        # auditor reconciles against Vendra and SAP. `nrs.asset.event`,
        # append-only, under every writer, for the reason the two recorders
        # above are: `state` has the API's PATCH, three action methods, a
        # completed transfer and the form; `sap_asset_number` has the INT-07
        # setter, the importer and the form.
        track_status = 'state' in vals
        track_verified = 'last_verified_date' in vals
        track_refs = [f for f in REFERENCE_FIELDS if f in vals]
        # After `_resolve_warranty`, so a derived expiry is watched too.
        track_warranty = [f for f in WARRANTY_FIELDS if f in vals]
        if not (track_custody or track_location or track_status
                or track_verified or track_refs or track_warranty):
            return super().write(vals)
        held = {r.id: r.custodian_id for r in self} if track_custody else {}
        placed = {r.id: r.location_id for r in self} if track_location else {}
        status = {r.id: r.state for r in self} if track_status else {}
        checked = ({r.id: (r.last_verified_date, r.last_verified_by.id)
                    for r in self} if track_verified else {})
        refs = {r.id: {f: r[f] for f in track_refs} for r in self}
        warranty = {r.id: {f: _event_value(r[f]) for f in track_warranty}
                    for r in self}
        result = super().write(vals)
        for record in self:
            if track_custody:
                was = held.get(record.id, self.env['hr.employee'])
                now = record.custodian_id
                if was.id != now.id:
                    record._record_custody_change(was, now)
            if track_location:
                was = placed.get(record.id, self.env['generic.location'])
                now = record.location_id
                if was.id != now.id:
                    record._record_movement(was, now)
            if track_status and status.get(record.id) != record.state:
                record._record_event(
                    EVENT_STATUS_CHANGED,
                    from_value=status.get(record.id), to_value=record.state,
                    reason=self.env.context.get(EVENT_REASON_KEY))
                if record.state == STATE_DISPOSED:
                    # `vals` and not the record: only a date that arrived in
                    # THIS write is the caller's. See `_stamp_disposal`.
                    record._stamp_disposal(vals)
            if track_verified:
                record._record_verification(
                    *checked.get(record.id, (False, False)), vals=vals)
            for name in track_refs:
                was = refs[record.id][name] or False
                now = record[name] or False
                if was != now:
                    record._record_event(
                        EVENT_REFERENCE_CHANGED, field_name=name,
                        from_value=was, to_value=now)
            for name in track_warranty:
                was = warranty[record.id][name]
                now = _event_value(record[name])
                if was != now:
                    record._record_event(
                        EVENT_WARRANTY_CHANGED, field_name=name,
                        from_value=was, to_value=now)
        return result

    def _resolve_warranty(self, vals):
        """`vals` with the warranty made consistent, or a refusal.

        Called on an EMPTY recordset from `create` and on ONE record from
        `write`, so "the value now" is the one in `vals` if it names it and
        the record's otherwise. Four rules, and a refusal happens before
        anything is written:

        1. **A duration and a start date go together.** Either alone is half
           a basis: *"24 months"* from when? The storekeeper who knows the
           duration knows the day the asset arrived.
        2. **A duration is a whole number of months, 1 to
           `WARRANTY_MAX_MONTHS`.**
        3. **With both, the expiry is derived** — and an expiry SENT beside
           them that says anything else is refused, not overwritten. Two
           statements of the same fact that disagree is a question for
           whoever sent them; silently keeping one is this programme's
           oldest defect. Sending the same date is accepted: a form that
           re-sends what it displayed is not contradicting anything.
        4. **An expiry derived from a basis goes with it.** Clearing the
           start and the duration in a write that does not name the expiry
           clears the expiry too, rather than leaving a date that now reads
           as *entered as a date* when nobody entered it.
        """
        if not set(WARRANTY_FIELDS) & set(vals):
            return vals

        def current(name):
            if name in vals:
                return vals[name] or False
            return self[name] if self else False

        start = current('warranty_start_date')
        start = fields.Date.to_date(start) if start else False
        months = current('warranty_months')
        months = (self._warranty_months_of(months)
                  if months not in (False, None) else False)
        if months is not False and not 1 <= months <= WARRANTY_MAX_MONTHS:
            raise ValidationError(_(
                "A warranty duration must be between 1 and %(max)s months; "
                "%(months)s was sent.", max=WARRANTY_MAX_MONTHS,
                months=months))
        if bool(start) != bool(months):
            raise ValidationError(_(
                "A warranty's duration and its start date go together: "
                "\"%(months)s months\" needs the day it runs from, and a "
                "start date needs how long it runs. Send both, or neither.",
                months=months or '…'))
        out = dict(vals)
        if 'warranty_months' in vals:
            out['warranty_months'] = months or 0
        if start and months:
            derived = warranty_expiry_of(start, months)
            if 'warranty_expiry' in vals:
                sent = vals['warranty_expiry']
                sent = fields.Date.to_date(sent) if sent else False
                if sent != derived:
                    raise ValidationError(_(
                        "The warranty expiry sent (%(sent)s) contradicts its "
                        "own basis: %(months)s months from %(start)s is "
                        "%(derived)s. Send the start date and the duration "
                        "and the expiry is worked out, or correct whichever "
                        "of them is wrong.",
                        sent=sent or _('none'), months=months,
                        start=start.isoformat(),
                        derived=derived.isoformat()))
            out['warranty_expiry'] = derived
        elif ('warranty_expiry' not in vals and self
              and self.warranty_start_date and self.warranty_months):
            out['warranty_expiry'] = False
        return out

    @api.onchange('warranty_start_date', 'warranty_months')
    def _onchange_warranty_basis(self):
        """Show the derived expiry on the Odoo form as soon as the basis is
        complete — the field is read-only there, and without this it kept
        the old date until the record was saved. Display only: the form does
        not send a read-only field, and `_resolve_warranty` derives it on
        save whatever this showed."""
        months = self.warranty_months
        if (self.warranty_start_date and months
                and 1 <= months <= WARRANTY_MAX_MONTHS):
            self.warranty_expiry = warranty_expiry_of(
                self.warranty_start_date, months)

    def _warranty_months_of(self, value):
        """A duration as a whole number of months, or raise.

        Checked here and not left to the ORM, which would turn `24.7` into
        24 and `true` into 1 without a word — a duration nobody sent. A
        method rather than a module function so the refusal can be
        translated: `_()` finds the language through `self`.
        """
        if isinstance(value, bool):
            raise ValidationError(_(
                "A warranty duration is a number of months."))
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValidationError(_(
                "A warranty duration is a number of months, not %r.")
                % (value,))
        if not number.is_integer():
            raise ValidationError(_(
                "A warranty duration is a whole number of months, not %s.")
                % value)
        return int(number)

    @api.depends('warranty_expiry')
    def _compute_warranty_status(self):
        """Under warranty through the expiry day itself, expired after it,
        and `none` where nothing is recorded — against a LAGOS day.

        `snapshot_today`, not `fields.Date.today()`: the container's clock
        is UTC, and *"expires today"* judged in UTC is wrong for one hour
        every night — report 29 found exactly that in the register snapshot.
        One definition of the day, shared with it.
        """
        from .asset_snapshot import snapshot_today
        today = snapshot_today()
        for record in self:
            if not record.warranty_expiry:
                record.warranty_status = 'none'
            elif record.warranty_expiry >= today:
                record.warranty_status = 'under_warranty'
            else:
                record.warranty_status = 'expired'

    def _search_warranty_status(self, operator, value):
        """The same three rules as the compute above, as a domain — so a
        filter on the status and the status each row publishes cannot
        disagree. Odoo 19 hands a search method `in` and negates it
        itself."""
        if operator != 'in':
            return NotImplemented
        from .asset_snapshot import snapshot_today
        today = snapshot_today()
        terms = {
            'none': [('warranty_expiry', '=', False)],
            'under_warranty': [('warranty_expiry', '>=', today)],
            'expired': [('warranty_expiry', '<', today)],
        }
        chosen = [terms[v] for v in value if v in terms]
        if not chosen:
            return [('id', 'in', [])]
        return ['|'] * (len(chosen) - 1) + [t for c in chosen for t in c]

    # ── Nobody moves an asset alone (handoff 35) ──────────────────────

    #: Which field is gated, and which context key declares ITS source. A
    #: move is announced through the movement key and a handover through the
    #: custody key, because that is how the two recorders already work and a
    #: third spelling of the same fact is how two answers start to differ.
    _APPROVED_FIELDS = {
        'location_id': MOVEMENT_SOURCE_KEY,
        'custodian_id': CUSTODY_SOURCE_KEY,
    }

    def _assert_change_is_approved(self, vals):
        """Refuse a move or a handover that nobody has agreed to.

        HERE, under every writer, and not in the three routes the Cadra app
        happens to call. Handoff 35 §A asked for the writers to be enumerated
        before the rule was written, and the enumeration found **twelve**
        distinct production writers of `location_id` and **thirteen** of
        `custodian_id`. The two previous handoffs that guessed this list were
        both wrong — handoff 14 said the transfer route was the only writer
        of `custodian_id` and an exhaustive search found six — so a gate in
        the routes would have been a gate with nine doors round it, one of
        which is an editable field on the Odoo form.

        WHAT IS GATED, AND WHAT IS NOT
        ------------------------------
        The owner's ruling is that **approval is about a person deciding to
        move something.** A registration is not a move; an integration
        delivering an asset is not a move; a bulk import is not a move. So:

        * **`create` is never gated.** It is not overridden for this at all.
          An asset registered at a location, or registered already assigned
          to somebody, is a record being opened — there is no previous state
          for a second person to be protecting. This is the door INT-03 from
          Vendra comes through, and gating it would dead-letter every receipt.
        * **Every `write` that CHANGES one of the two fields is gated**,
          unless it declares itself. A write that NAMES a field without
          changing it passes — the Cadra app's edit form re-sends every
          field on every save, and refusing that would break saving a note on
          an asset. This is the trap `CLAUDE.md` names: *a screen that
          PATCHes back the object it GET-ed now fails the day the serializer
          gains a read-only key.*
        * **Clearing a field passes.** Un-assigning a custodian or taking an
          asset off a location hands it to nobody — the same argument the
          `clearance` exemption makes. Setting either from empty to a value
          is a grant and is gated, so this buys a caller nothing.
        * **A declared exemption passes**, and every one is a row in §A's
          table with an argument for why that writer is not a person deciding
          to move something. `EXEMPT_REASONS` is the list; an unrecognised
          value is treated as no exemption at all, which is
          `approval_policy`'s rule applied to the other end.
        * **An approved request passes**, and the clearance is checked rather
          than believed — see `_approval_clears`.

        The two writers this method cannot see are the two the database does
        by itself, and both were already handled by handoff 28 and by
        `asset_custody.HrEmployee.unlink`: deleting a location empties
        `location_id` through `ON DELETE SET NULL`, and deleting an employee
        empties `custodian_id` the same way. No ORM write runs, so no gate
        can stand in front of them. Both are destructive administrative acts
        that take custody or location AWAY rather than hand it to somebody,
        and both already refuse outright when a disposed asset is involved
        and append a record for every other. They are outside the rule on
        purpose and are named in §A's table.

        The guarantee is Python, like every other rule on this model. A
        writer that goes round the ORM — raw SQL, `_write()`, a DBA's query
        — is not gated, and `tests/test_recorder_bypass_guard.py` is what
        watches for the first two.
        """
        gated = [f for f in self._APPROVED_FIELDS if f in vals]
        if not gated or not self:
            return
        # The switch, read the way `database_class` is read — one indexed
        # SELECT, never `get_param`. See `approval_policy` for the measured
        # reason, which is that an ormcache once served `client` for a
        # database whose row had been deleted while another worker said
        # `test`, and twenty-four writing tests went through.
        if not approval_required(self.env):
            return
        context = self.env.context
        exempt = context.get(EXEMPT_KEY)
        if exempt in EXEMPT_REASONS:
            return
        for record in self:
            for field in gated:
                if not record._change_is_real(field, vals[field]):
                    # Named, not changed. Not a move.
                    continue
                if not _m2o_id(vals[field]):
                    # CLEARING IS NOT A GRANT, and this is the same argument
                    # the `clearance` exemption already makes in words:
                    # taking an asset back from somebody, or off a location,
                    # hands it to nobody, and there is no second person to
                    # ask about an asset returning to the store.
                    #
                    # It is here because the alternative was a DEAD END, and
                    # the dead end was real: the verification pass found that
                    # `PATCH {"custodian_id": false}` was refused with a
                    # message naming `POST /transfer-custody`, and that route
                    # answers *"`to_custodian_id` is required"* — so
                    # un-assigning a custodian became impossible through the
                    # API, having worked for the whole life of the register.
                    # The same for `location_id`. A refusal that names a
                    # remedy which cannot work is worse than one that names
                    # none.
                    #
                    # **It is not a way round the rule.** Going from nobody
                    # to somebody, or from nowhere to somewhere, IS a grant
                    # and IS gated — so a person can drop custody of an asset
                    # and still cannot hand it to anyone without a second
                    # person agreeing. Two writes buy nothing that one does
                    # not, and the chain of custody records both.
                    continue
                if record._approval_clears(field, vals[field]):
                    continue
                raise UserError(record._approval_needed_message(field, vals))

    def _change_is_real(self, field, value):
        """Whether writing `value` to `field` actually changes this record.

        The same before/after comparison the three recorders make after
        `super().write()`, made before it. Without it the gate would refuse
        every save of the app's edit form, which sends `location_id` and
        `custodian_id` on every save whether or not the user touched them.
        """
        self.ensure_one()
        current = self[field]
        return (current.id or False) != (_m2o_id(value) or False)

    def _approval_clears(self, field, value):
        """Whether an approved request in the context covers THIS change.

        **Checked, never believed.** The id arrives in the context, which any
        caller controls, so a bare flag would mean *approval required* could
        be turned off by anybody who had read the source. The request is
        re-read from the database and has to be for this asset, still open or
        just approved, and asking for exactly the change being written.

        This is the same forgery path `nrs.asset.movement._record` closed for
        `transfer_id`, in the same words: *a transfer belonging to another
        asset, or one that names a different destination, would let somebody
        borrow an approval for a move it never covered.* That comment was
        written in handoff 28 about the approvals NRS had asked for and did
        not yet have. This is them.
        """
        self.ensure_one()
        request_id = self.env.context.get(APPROVAL_KEY)
        # An INTEGER, checked as one. `if not request_id` let `True` through
        # to `browse(True)`, which dies with `TypeError: 'bool' object is not
        # iterable` — where every other bad clearance gets a clean refusal.
        # A bare `True` is the first thing somebody probing this reaches for,
        # and a crash is a worse answer than a no. Found by the verification
        # pass.
        if not isinstance(request_id, int) or isinstance(request_id, bool) \
                or request_id <= 0:
            return False
        request = self.env['nrs.asset.change.request'].sudo().browse(
            request_id).exists()
        if not request or request.asset_id.id != self.id:
            return False
        # APPROVED, WITH A DECIDER. Nothing else, ever.
        #
        # This used to accept `pending` as well, because `action_approve`
        # wrote the asset before stamping its own decision — and that was a
        # two-call bypass of the whole feature: raise a request properly,
        # then write `location_id` directly over `call_kw` with
        # `cadra_approval_id` naming your own PENDING request, and the gate
        # waved it through. The approve path now stamps first (see
        # `action_change_request.action_approve`), so the clearance can
        # demand the thing only that method can produce.
        #
        # `approved_by_id` is checked separately from the state rather than
        # trusted to follow it: the state is a Selection a future migration
        # or a `_write_recorded` somewhere could set, and the decider is the
        # fact that matters. And it must not be the requester — belt and
        # braces over `_assert_may_decide`, because this is the last gate in
        # front of the write itself.
        if request.state != 'approved':
            return False
        if not request.approved_by_id:
            return False
        if request.approved_by_id.id == request.requested_by_id.id:
            return False
        # SPENT. An approval authorises ONE change, and once it has produced
        # its append-only record it authorises nothing further.
        #
        # Without this the clearance was a reusable key with no expiry: once
        # request R (move asset A to room X) was approved, anybody could write
        # `location_id = X` on A at any later date with `cadra_approval_id =
        # R` and the gate waved it through — and a second, legitimate
        # approval moving A to Y did not retire R, so an asset that had ever
        # been approved into a room could be put back there, repeatedly, by
        # one person. Found by the verification pass.
        #
        # The check is on the RECORD the approval produced rather than on a
        # flag, because that record is append-only and cannot be cleared to
        # make the key live again.
        if request.movement_id or request.custody_id:
            return False
        # And the premise must STILL hold at the instant of the write, not
        # merely at the instant somebody clicked. `action_approve` checks it
        # before stamping; this is the same question asked one step later,
        # where the write actually happens.
        holds, _unused = request._premise_check()
        if not holds:
            return False
        wanted = {'location_id': request.to_location_id.id,
                  'custodian_id': request.to_custodian_id.id}.get(field)
        return bool(wanted) and wanted == (_m2o_id(value) or False)

    def _approval_needed_message(self, field, vals):
        """What somebody reads when the register asks for a second person.

        Names the asset, says what would have changed, and names the remedy
        in full — including the command that turns the rule off for a tenant
        that does not want it, for the reason `database_class.mark_command`
        exists: an error naming a remedy the reader has to go and look up is
        worse than one naming none.
        """
        self.ensure_one()
        if field == 'location_id':
            what = _(
                "Moving %(asset)s to %(where)s needs somebody else to "
                "approve it.",
                asset=self.display_name,
                where=self.env['generic.location'].browse(
                    _m2o_id(vals[field])).display_name or _("a new location"))
            how = _(
                "Raise the move from the asset's page — the Move button "
                "creates a request and asks somebody to agree to it — or use "
                "POST /api/v1/assets/<id>/move, which does the same.")
        else:
            what = _(
                "Handing %(asset)s to %(who)s needs somebody else to approve "
                "it.",
                asset=self.display_name,
                who=self.env['hr.employee'].browse(
                    _m2o_id(vals[field])).display_name or _("a new custodian"))
            how = _(
                "Raise it from the asset's page — Transfer custody creates a "
                "request and asks somebody to agree to it — or use POST "
                "/api/v1/assets/<id>/transfer-custody, which does the same.")
        return "%s\n\n%s\n\n%s\n\n%s" % (
            what, how,
            _("If this register should not require a second person, an "
              "administrator sets it once for this database:"),
            set_command(self.env.cr.dbname))

    def _assert_disposed_is_terminal(self, vals):
        """Nothing leaves `disposed`, and a disposed asset is not moved or
        handed to anybody. Refused here, where every writer passes.

        Until handoff 30 a disposed asset could be marked missing — which
        overwrote `disposed` and put it back on the register with a 200 —
        and completing a transfer raised on one set it `active` without
        anybody having asked. Disabling a button fixes one door and leaves
        the API, the importer and the shell open; the movement recorder is
        in this method for that reason and so is this.

        **There is no way round it, on purpose.** A context flag would be a
        way round that an RPC caller could set. Whether a disposal can be
        REVERSED — a deliberate, recorded act by somebody entitled to do it —
        was asked of the Architect rather than built: across the eight local
        databases the only asset that ever left `disposed` was the fixture
        handoff 29 used to discover that it could
        (`docs/handoffs/30-REPORT.md` §2).

        A write that NAMES one of the three fields without changing it is
        not refused: the Cadra app's edit form re-sends `state` and the
        location on every save, and a disposed asset's paperwork —
        `disposal_method`, `disposal_reference`, the approval — is completed
        AFTER it is disposed. Compared here, before `super()`, so that a
        refusal happens before anything is written.

        A FOURTH field is guarded, and only against being EMPTIED. Handoff
        31 put a date on every disposal whichever door it came by, and
        report 31 §C1 then found the door that takes one off again:
        `disposal_date` is in the API's `_WRITABLE_FIELDS`, so `PATCH
        {"disposal_date": null}` un-dated a disposal made ten minutes
        earlier — the one remaining way to manufacture the disposal
        report's `no_disposal_date` finding against a NEW disposal, on a
        register whose real opening balance for it is zero. Correcting the
        date to another day is a proper act and is untouched; taking it
        away is not. An undated disposal that was already undated stays
        undated and is not refused, for the reason the three above are
        compared rather than counted: it is the state of a legacy row and
        the app's edit form re-sends it on every save.
        """
        if not ({'state', 'location_id', 'custodian_id', 'disposal_date'}
                & set(vals)):
            return
        for record in self:
            if record.state != STATE_DISPOSED:
                continue
            if 'disposal_date' in vals and not vals['disposal_date'] \
                    and record.disposal_date:
                raise UserError(_(
                    "%(asset)s has been disposed of, and the day it was "
                    "disposed of cannot be taken off its record. Correcting "
                    "it to another day is a proper thing to do; leaving the "
                    "disposal with no day at all is not — the register would "
                    "no longer be able to say when the asset left it.",
                    asset=record.display_name))
            if 'state' in vals and vals['state'] != STATE_DISPOSED:
                raise UserError(_(
                    "%(asset)s has been disposed of, and a disposed asset's "
                    "status cannot be changed — it cannot be marked missing, "
                    "put under repair or returned to service. Disposal is "
                    "the end of an asset's record.",
                    asset=record.display_name))
            if 'location_id' in vals \
                    and _m2o_id(vals['location_id']) != record.location_id.id:
                raise UserError(_(
                    "%(asset)s has been disposed of, and a disposed asset "
                    "cannot be moved. Its record keeps the location it was "
                    "disposed of from.", asset=record.display_name))
            if 'custodian_id' in vals \
                    and _m2o_id(vals['custodian_id']) != record.custodian_id.id:
                raise UserError(_(
                    "%(asset)s has been disposed of, and a disposed asset "
                    "cannot change custodian. Its record keeps whoever held "
                    "it when it was disposed of.", asset=record.display_name))

    def _stamp_disposal(self, vals):
        """A disposal gets its date and its condition — through ANY door.

        Until handoff 31 only `action_condemn` did this, in two overrides.
        `POST /assets/<id>/condemn` was the proper door and did not close the
        others: `PATCH {"state": "disposed"}`, the Odoo form and the shell
        all disposed of an asset and stamped nothing, which is how the
        disposal report came to have a `no_disposal_date` finding for
        disposals made last week. Here, underneath every writer, for the
        reason the recorders above are.

        The date is a LAGOS day (`snapshot_today`), not `context_today` —
        that is UTC for every API credential, whose users have no timezone.
        A date the caller sent IN THIS WRITE is respected: an integration
        carrying a disposal made elsewhere knows when it happened and this
        does not.
        The condition is not negotiable. `decommissioned` is what disposed
        MEANS on this register, and a disposed asset in `good` condition is
        how the condition tiles came to count things that are gone.

        **THE CALLER'S DATE IS THE ONE IN THIS WRITE, and not one that was
        already sitting on the record** (report 31 §C2). The first draft
        read `self.disposal_date` after `super()`, which cannot tell a date
        sent WITH the disposal from one PATCHed months before it —
        `disposal_date` is writable on a LIVE asset, so an asset given last
        year's date while still in service and disposed of today was dated
        last year, and the register said it left a year before it did.
        `vals` is the whole difference and it is in scope at the one call
        site, in `write`, so the two are told apart rather than guessed at.
        A stale date is therefore OVERWRITTEN by today — which is a tracked
        change, so the day that was there before is still in the record.
        This does reverse handoff 31's "paperwork written up before the
        act": a date agreed at a board of survey a week before the status
        follows must now be sent WITH the status, or corrected afterwards,
        which is a legitimate write and stays one.

        NOT on `create`. An asset REGISTERED as already disposed was disposed
        of on some earlier day this system never saw; stamping today would
        replace a finding the disposal report can show — no date — with a
        date that is wrong, which it cannot.
        """
        self.ensure_one()
        from .asset_snapshot import snapshot_today
        stamp = {}
        if self.condition != 'decommissioned':
            stamp['condition'] = 'decommissioned'
        # Falsy covers the caller who disposed of the asset and cleared the
        # date in the same breath: nothing was sent, so the server dates it.
        if not vals.get('disposal_date'):
            today = snapshot_today()
            if self.disposal_date != today:
                stamp['disposal_date'] = today
        if stamp:
            self.write(stamp)

    def _record_event(self, event_type, **payload):
        """Append one `nrs.asset.event`. The source is read off the context
        by the model, as custody's and movement's are."""
        self.ensure_one()
        return self.env['nrs.asset.event']._record(self, event_type, **payload)

    def _record_verification(self, previous_date, previous_verifier, vals):
        """Every time this asset was checked — or a date was written.

        Two different facts, and two event TYPES. When `action_verify` made
        the write, the ACTOR VERIFIED THE ASSET, today — `verified` — and
        every such call is an event even when the date does not change: two
        checks on one day are two checks, and one overwritten column is
        exactly what could not say so.

        Anything else is somebody writing a verification DATE — over PATCH,
        on the form, by import: `verification_date_set`, recorded when the
        date actually changes. The context says which it is, and the context
        is caller-controlled, so the claim is only honoured when the write
        also names the actor as the verifier and dates it today — which is
        what `action_verify` does, and what a caller claiming it would have
        to do as well, at which point the claim is true.
        """
        self.ensure_one()
        claimed = self.env.context.get(EVENT_SOURCE_KEY)
        by_actor = (
            claimed in _VERIFIER_SOURCES
            and _m2o_id(vals.get('last_verified_by')) == self.env.uid
            and self.last_verified_date == fields.Date.today())
        before = previous_date and previous_date.isoformat()
        after = self.last_verified_date and self.last_verified_date.isoformat()
        if by_actor:
            return self._record_event(
                EVENT_VERIFIED, from_value=before, to_value=after,
                notes=self.verification_notes or False)
        # The same date written again, over nobody: nothing happened. The
        # same date written again OVER A VERIFIER is not nothing — `write`
        # has just cleared them, and an asset that said "checked by Ada" now
        # says nobody checked it. That is recorded.
        if (previous_date == self.last_verified_date
                and previous_verifier == self.last_verified_by.id):
            return None
        return self._record_event(
            EVENT_VERIFICATION_DATE_SET,
            # A verifier label on a write that was not one is not honoured.
            source='direct' if claimed in _VERIFIER_SOURCES else None,
            from_value=before, to_value=after)

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

    def _record_movement(self, from_location, to_location):
        """Append one row to the record of where this asset has been.

        The reason and the transfer, where there is one, are read off the
        context by `nrs.asset.movement._record` for the reason custody's
        reason is: the write that carries a move has nowhere to put them.
        """
        self.ensure_one()
        return self.env['nrs.asset.movement']._record(
            self, from_location, to_location,
            reason=self.env.context.get(MOVEMENT_REASON_KEY),
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

    def action_verify(self, notes=None):
        """Record that somebody checked this asset, and WHO.

        The only FIRST-PARTY writer of `last_verified_by` — nothing on the
        model guards the column, and an asset manager can write it over
        XML-RPC; `readonly` on the form is a client not offering an input.
        What `write` does guarantee is the converse: a date that arrives
        without a verifier clears the old one. `last_verified_date` is also
        in the API's `_WRITABLE_FIELDS`, and until handoff 28 the Cadra app's
        own Verify button was a PATCH of that date — so a verification made
        from the app recorded a day and nobody. A verification with a date
        and no person is a date. `POST /assets/<id>/verify` calls this.
        """
        from datetime import date
        vals = {
            'last_verified_date': date.today(),
            'last_verified_by': self.env.uid,
        }
        # ALWAYS written, empty included. The notes describe THIS
        # verification; leaving the previous verifier's notes in place would
        # attribute them to somebody who never wrote them.
        vals['verification_notes'] = notes or False
        # Since handoff 30 each call is also an append-only `verified` event
        # (`_record_verification`): the pair of columns above is the LAST
        # verification, overwritten by the next; the events are all of them.
        self._with_event_source('action').write(vals)
        self.message_post(body=_('Asset verified by %s') % self.env.user.name)

    def _with_event_source(self, default, reason=None):
        """This recordset, saying where the event it is about to cause came
        from. A route that has already said so (`api_verify`, `api_condemn`,
        `api_mark_missing`) is left standing; a button press is `action`."""
        ctx = {}
        if not self.env.context.get(EVENT_SOURCE_KEY):
            ctx[EVENT_SOURCE_KEY] = default
        if reason:
            ctx[EVENT_REASON_KEY] = reason
        return self.with_context(**ctx) if ctx else self

    def action_condemn(self, reason=None):
        """Dispose of the asset. `reason` is recorded twice, deliberately:
        on `disposal_reason`, which is the editable paperwork the disposal
        report reads, and on the append-only `status_changed` event, which
        is what was said AT THE TIME and also names who carried it out."""
        vals = {'condition': 'decommissioned', 'state': STATE_DISPOSED}
        if reason:
            vals['disposal_reason'] = reason
        # An asset ALREADY disposed is left alone. The write would change no
        # status, so it would record no event — and would still have
        # overwritten the reason the disposal was given at the time, with
        # nothing anywhere to say so. The route answers 409 before it gets
        # here; this is the same answer for the ORM and the Odoo button.
        live = self.filtered(lambda r: r.state != STATE_DISPOSED)
        live._with_event_source('action', reason).write(vals)

    def action_mark_missing(self, reason=None):
        """Mark the asset missing, and say WHY where somebody knows.

        An asset that cannot be found may be a loss, and *why* is the first
        question anybody asks. Until handoff 30 it had nowhere to live: the
        Cadra app's dialog asked for no reason because the API had nowhere
        to put one (report 29 Q2). It lives on the append-only
        `status_changed` event — evidence of what was said when it was
        marked, not a note somebody can tidy up afterwards.
        """
        self._with_event_source('action', reason).write({'state': 'missing'})

    def action_mark_found(self, reason=None):
        """A missing asset turned up. Say WHERE, where somebody knows.

        *Where it turned up* is as much an audit fact as *why it went
        missing* — and until handoff 31 an asset reappeared through a bare
        PATCH of `state`, which records the most interesting event in its
        life as a change of one word. The reason lives on the append-only
        `status_changed` event, as the reason for going missing does.

        Only a MISSING asset. Anything else is left alone: the route answers
        409 before it gets here, and this is the same answer for the ORM and
        the Odoo button.
        """
        missing = self.filtered(lambda r: r.state == 'missing')
        missing._with_event_source('action', reason).write({'state': 'active'})

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
        """ONE grouped count for every category in `self` (handoff 61,
        ruling 6 on report 60): `GET /asset-categories` computes this for
        the whole taxonomy at once, and one `search_count` per row was 160
        queries on `test19` — most of a ~3 s answer. `_read_group` goes
        through `nrs.asset._search` like `search_count` did, so the
        register's implicit filter (candidates excluded, handoff 57) counts
        exactly what it counted before."""
        counts = {}
        if self.ids:
            counts = {
                category.id: n for category, n in
                self.env['nrs.asset']._read_group(
                    [('category_id', 'in', self.ids)],
                    ['category_id'], ['__count'])}
        for c in self:
            c.asset_count = counts.get(c.id, 0)


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

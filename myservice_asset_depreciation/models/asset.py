from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import config

from odoo.addons.myservice_asset_register.models.asset_snapshot import (
    snapshot_today,
)

from . import depreciation_engine as engine
from .depreciation_engine import (
    COMPUTED_METHODS,
    METHOD_ERP_MANAGED,
    METHOD_NONE,
    METHOD_SELECTION,
    METHOD_DECLINING_BALANCE,
    SOURCE_CREATED,
    SOURCE_MANUAL,
    SOURCE_SELECTION,
    STATE_ERP_MANAGED,
    STATE_NOT_APPLICABLE,
    STATE_SELECTION,
)

#: Policy that a category can hand down to its assets.
POLICY_FIELDS = (
    'depreciation_method', 'useful_life_months', 'declining_rate', 'salvage_rate',
)

#: Any of these changing invalidates the stored depreciation figures.
DEPRECIATION_INPUTS = POLICY_FIELDS + (
    'category_id', 'use_category_policy',
    'acquisition_cost', 'purchase_value',
    'acquisition_date', 'purchase_date',
    'depreciation_start_date', 'state', 'disposal_date',
)


class NRSAsset(models.Model):
    """Depreciation for the asset register — PRD §8.6.

    Design note: `accumulated_depreciation`, `current_book_value`,
    `depreciation_state` and `depreciation_end_date` are PLAIN stored fields
    updated by `_apply_depreciation()`, not `compute=`. Two reasons:

    1. ERP-managed assets (NRS spec §6.2) must keep figures written from
       outside. A stored compute would have to read its own value to preserve
       it, which risks recursion.
    2. These figures drift with *time*, not just with their inputs — nothing
       changes in the database when a month passes. So a monthly cron is
       required either way, and `@api.depends` would buy less than it appears.

    The genuinely safe derivations (`depreciable_cost`, `salvage_value`) stay as
    ordinary computes.
    """
    _inherit = 'nrs.asset'

    # ── Policy (defaults from the category, overridable here) ──
    use_category_policy = fields.Boolean(
        'Use Category Policy', default=True,
        help='Inherit the depreciation policy from this asset\'s category. '
             'Untick to set a different method or life for this asset alone.')
    depreciation_method = fields.Selection(
        METHOD_SELECTION, string='Depreciation Method', default=METHOD_NONE,
        tracking=True, index=True,
        help='ERP-managed means an external system owns the figures and Cadra '
             'never calculates them.')
    useful_life_months = fields.Integer('Useful Life (months)')
    declining_rate = fields.Float('Declining Rate (%/yr)', digits=(5, 2))
    salvage_rate = fields.Float('Salvage Rate (%)', digits=(5, 2), default=0.0)

    # ── Start of depreciation ─────────────────────────────────
    depreciation_start_date = fields.Date(
        'Depreciation Start',
        help='Defaults to the acquisition date, then the purchase date, then '
             'the date the record was created.')
    depreciation_start_source = fields.Selection(
        SOURCE_SELECTION, string='Start Date Source', readonly=True,
        help='Where the start date came from. "Record created" means it was '
             'inferred because the asset has no acquisition or purchase date.')
    depreciation_start_is_estimated = fields.Boolean(
        'Start Date Estimated', compute='_compute_start_is_estimated', store=True,
        help='True when the start date was inferred rather than recorded. '
             'These assets need a real date backfilled.')

    # ── Cost basis ────────────────────────────────────────────
    # acquisition_cost and purchase_value are two parallel, unrelated fields on
    # the register. Rather than reconcile them here (a separate data-cleanup job
    # with its own migration risk) the precedence is made explicit and both are
    # left alone.
    depreciable_cost = fields.Monetary(
        'Depreciable Cost', currency_field='currency_id',
        compute='_compute_depreciable_cost', store=True,
        help='Acquisition cost, falling back to purchase value.')
    salvage_value = fields.Monetary(
        'Salvage Value', currency_field='currency_id',
        compute='_compute_salvage_value', store=True,
        help='Residual worth at end of life. Depreciation stops here.')

    # ── Derived figures (see class docstring) ─────────────────
    accumulated_depreciation = fields.Monetary(
        'Accumulated Depreciation', currency_field='currency_id',
        help='Total written off to date. Supplied externally for ERP-managed assets.')
    current_book_value = fields.Monetary(
        'Net Book Value', currency_field='currency_id',
        help='Depreciable cost less accumulated depreciation.')
    depreciation_state = fields.Selection(
        STATE_SELECTION, string='Depreciation Status', readonly=True,
        default=STATE_NOT_APPLICABLE, index=True)
    depreciation_end_date = fields.Date('Fully Depreciated On', readonly=True)

    # ── Computes ──────────────────────────────────────────────

    @api.depends('depreciation_start_source')
    def _compute_start_is_estimated(self):
        for r in self:
            r.depreciation_start_is_estimated = (
                r.depreciation_start_source == SOURCE_CREATED)

    @api.depends('acquisition_cost', 'purchase_value')
    def _compute_depreciable_cost(self):
        for r in self:
            r.depreciable_cost = r.acquisition_cost or r.purchase_value or 0.0

    @api.depends('depreciable_cost', 'salvage_rate')
    def _compute_salvage_value(self):
        for r in self:
            r.salvage_value = round(
                (r.depreciable_cost or 0.0) * (r.salvage_rate or 0.0) / 100.0, 2)

    # ── Policy inheritance ────────────────────────────────────

    def _sync_policy_from_category(self):
        """Copy category defaults onto assets that follow their category.

        Explicit rather than a stored compute: an asset that has opted out must
        keep its own values, and a compute cannot leave a field unassigned.

        ONE write per category, not one per asset (handoff 63, ruling 3):
        every asset following a category takes the same four values, so the
        whole class is one recordset write. Saving a category's policy on
        `test19`'s class of 18,008 made 18,008 writes here and eight more
        per asset below — 162,072 trips through the register's write chain
        and mail tracking, 68 s — while the database saw 208 queries.
        """
        by_category = {}
        for r in self:
            if r.use_category_policy and r.category_id:
                by_category.setdefault(r.category_id, []).append(r.id)
        for cat, ids in by_category.items():
            # One write, not four assignments. Field-at-a-time would validate
            # after each one, so setting the method to declining_balance before
            # the rate lands trips _check_asset_depreciation_policy on a policy
            # that is actually valid.
            self.browse(ids).write({
                'depreciation_method': cat.depreciation_method or METHOD_NONE,
                'useful_life_months': cat.useful_life_months or 0,
                'declining_rate': cat.declining_rate or 0.0,
                'salvage_rate': cat.salvage_rate or 0.0,
            })

    @api.onchange('category_id', 'use_category_policy')
    def _onchange_depreciation_policy_source(self):
        """Reflect the inherited policy in the form as soon as it's picked."""
        self._sync_policy_from_category()

    # ── Start date ────────────────────────────────────────────

    def _resolve_start_date(self):
        """Fill in the start date and record where it came from.

        A date the user set by hand is never overwritten.
        """
        for r in self:
            if r.depreciation_start_source == SOURCE_MANUAL:
                continue
            created = r.create_date.date() if r.create_date else None
            start, source = engine.resolve_start_date(
                r.acquisition_date, r.purchase_date, created)
            r.depreciation_start_date = start
            r.depreciation_start_source = source

    # ── The derived figures ───────────────────────────────────

    def _depreciation_policy(self):
        """Engine kwargs for this asset, including the tenant's conventions."""
        self.ensure_one()
        options = self.env['cadra.depreciation.settings'].engine_options()
        return dict(
            **options,
            cost=self.depreciable_cost,
            start_date=self.depreciation_start_date,
            life_months=self.useful_life_months,
            method=self.depreciation_method,
            salvage=self.salvage_value,
            annual_rate_pct=self.declining_rate,
            disposal_date=self.disposal_date if self.state == 'disposed' else None,
        )

    def _apply_depreciation(self, as_of=None):
        """Recalculate and store the summary figures.

        ERP-managed assets are skipped entirely — Cadra reads but does not
        compute (NRS spec §6.2).

        `as_of` defaults to the LAGOS day (`snapshot_today`), not
        `context_today`, because it is compared with `disposal_date` — which
        `nrs.asset._stamp_disposal` writes as a Lagos day, underneath every
        writer of `state`. `context_today` is the UTC day for any user with
        no timezone (every API credential, and the superuser the test runner
        acts as), so between 23:00 and 24:00 UTC the stamp was TOMORROW
        relative to `as_of`, the engine's `as_of >= disposal_date` check
        missed, and a freshly disposed asset read `fully_depreciated` — the
        two red tests of report 36, red for one hour a night and green the
        other twenty-three. One definition of the day, used on both sides
        of the comparison (`asset_snapshot.snapshot_today`'s own rule).
        """
        as_of = as_of or snapshot_today()
        changed = []
        for r in self:
            if r.depreciation_method == METHOD_ERP_MANAGED:
                # Keep the externally-supplied figures; only label the state.
                new = (r.accumulated_depreciation, r.current_book_value,
                       STATE_ERP_MANAGED, False)
            else:
                policy = r._depreciation_policy()
                accumulated, book_value, state = engine.value_at(
                    as_of, **policy)
                # As the columns will hold them: money rounded to the
                # currency (what a Monetary write stored), no end date
                # `False` (the engine says `None` when there is no schedule
                # — method none, no start, no cost — and the cache says
                # `False`; compared raw, every such asset looked changed on
                # every recompute: 19,453 of 22,042 on `test19`, found by the
                # verification pass).
                rnd = r.currency_id.round if r.currency_id else (
                    lambda v: round(v, 2))
                new = (rnd(accumulated or 0.0), rnd(book_value or 0.0),
                       state or False,
                       engine.schedule_end_date(**policy) or False)
            old = (r.accumulated_depreciation or 0.0,
                   r.current_book_value or 0.0,
                   r.depreciation_state or False,
                   r.depreciation_end_date or False)
            if new != old:
                changed.append((r.id,) + new)
        self._store_depreciation_figures(changed)

    #: The four figures `_apply_depreciation` derives. Nothing computes
    #: from them (no `@api.depends` names one), no recorder watches them and
    #: none is tracked.
    _DEPRECIATION_FIGURES = ('accumulated_depreciation', 'current_book_value',
                             'depreciation_state', 'depreciation_end_date')

    def _store_depreciation_figures(self, rows):
        """Write `(id, accumulated, book value, state, end date)` rows in
        one statement per thousand rather than four ORM writes per asset.

        Handoff 63, ruling 3. Each `r.field = value` above used to be a
        `write()` — four per asset, each through the register's whole write
        chain (gates, recorders, SAP events) and `mail.thread` tracking, for
        figures none of those look at. They are pure derivations, so they
        are written as data: flushed first (a pending ORM write of the same
        column must not land on top afterwards), stored by SQL, the cache
        invalidated so the next read sees them. Only rows whose figures
        CHANGED are written, and only they move `write_date` — a recompute
        that changes nothing is no longer a change to every asset, which
        `GET /assets?updated_since=` (handoff 61 §6) would hand a phone as
        thousands of changed records."""
        if not rows:
            return
        records = self.browse([r[0] for r in rows])
        records.flush_recordset(list(self._DEPRECIATION_FIGURES))
        from psycopg2.extras import execute_values
        execute_values(
            self.env.cr,
            "UPDATE nrs_asset a SET accumulated_depreciation = v.acc, "
            "       current_book_value = v.bv, depreciation_state = v.st, "
            "       depreciation_end_date = v.ed, write_uid = %d, "
            "       write_date = (now() AT TIME ZONE 'UTC') "
            "  FROM (VALUES %%s) AS v (id, acc, bv, st, ed) "
            " WHERE a.id = v.id" % self.env.uid,
            [(i, acc or 0.0, bv or 0.0, st or None, ed or None)
             for i, acc, bv, st, ed in rows],
            template='(%s, %s::numeric, %s::numeric, %s::varchar, %s::date)',
            page_size=1000)
        records.invalidate_recordset(
            list(self._DEPRECIATION_FIGURES) + ['write_date', 'write_uid'])

    def get_depreciation_schedule(self, as_of=None):
        """The period-by-period board, generated on demand.

        Not persisted: ~12k assets x ~60-120 periods would be a million rows of
        pure derivation, and regenerating them on every cost edit is churn for
        no gain. Because the board is a pure function of the policy, an `as_of`
        in the past yields a genuine point-in-time view (PRD §13.4).
        """
        self.ensure_one()
        if self.depreciation_method not in COMPUTED_METHODS:
            return []
        periods = engine.build_schedule(**self._depreciation_policy())
        if as_of:
            periods = [p for p in periods if p.period_end <= as_of]
        return [{
            'sequence': p.sequence,
            'period_end': p.period_end,
            'charge': p.charge,
            'accumulated': p.accumulated,
            'book_value': p.book_value,
        } for p in periods]

    # ── Hooks ─────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        # nrs.asset.create() is already overridden twice (sequence in the
        # register, tag generation in asset_tag). super() first so those run.
        assets = super().create(vals_list)
        for asset, vals in zip(assets, vals_list):
            if not any(f in vals for f in POLICY_FIELDS):
                asset._sync_policy_from_category()
            if 'depreciation_start_date' in vals:
                asset.depreciation_start_source = SOURCE_MANUAL
        assets._resolve_start_date()
        assets._apply_depreciation()
        return assets

    def write(self, vals):
        cleared_start = (
            'depreciation_start_date' in vals and not vals['depreciation_start_date'])
        # A hand-set start date is the user's, not ours to recompute later.
        if vals.get('depreciation_start_date'):
            vals.setdefault('depreciation_start_source', SOURCE_MANUAL)
        elif cleared_start:
            # Clearing it hands control back to the fallback chain — otherwise
            # the record would stay pinned to 'manual' with no date, forever.
            vals.setdefault('depreciation_start_source', False)

        res = super().write(vals)

        if 'category_id' in vals or 'use_category_policy' in vals:
            self._sync_policy_from_category()
        if cleared_start or any(f in vals for f in ('acquisition_date', 'purchase_date')):
            self._resolve_start_date()
        if any(f in vals for f in DEPRECIATION_INPUTS):
            # Safe for ERP-managed assets: _apply_depreciation leaves their
            # externally-supplied figures untouched. A write of nothing but
            # those figures skips this entirely and simply stands.
            self._apply_depreciation()
        return res

    # ── Actions ───────────────────────────────────────────────

    def action_recompute_depreciation(self):
        self._resolve_start_date()
        self._apply_depreciation()

    # `action_condemn` was overridden here to stamp `disposal_date`, because
    # depreciation must stop on the day of disposal. The register stamps it
    # itself now, for every writer (`nrs.asset._stamp_disposal`, handoff 31),
    # and `disposal_date` is a depreciation input — so that write re-enters
    # `write()` above and recomputes, whichever door the disposal came by.

    # ── Register-wide reporting ───────────────────────────────

    @api.model
    def get_depreciation_report(self, domain=None):
        """Register-wide depreciation totals for the report page.

        Aggregates the STORED summary fields with read_group rather than
        walking schedules — this is why those figures are stored at all.
        """
        domain = domain or []
        totals = self.read_group(
            domain, ['depreciable_cost:sum', 'accumulated_depreciation:sum',
                     'current_book_value:sum'], [])
        agg = totals[0] if totals else {}

        by_category = []
        for g in self.read_group(
                domain + [('depreciation_method', 'in', list(COMPUTED_METHODS))],
                ['depreciable_cost:sum', 'accumulated_depreciation:sum',
                 'current_book_value:sum'],
                ['category_id']):
            if not g.get('category_id'):
                continue
            by_category.append({
                'id': g['category_id'][0],
                'name': g['category_id'][1],
                'asset_count': g['category_id_count'],
                'depreciable_cost': g.get('depreciable_cost') or 0.0,
                'accumulated_depreciation': g.get('accumulated_depreciation') or 0.0,
                'current_book_value': g.get('current_book_value') or 0.0,
            })
        by_category.sort(key=lambda c: c['current_book_value'], reverse=True)

        by_state = {
            g['depreciation_state']: g['depreciation_state_count']
            for g in self.read_group(domain, ['id'], ['depreciation_state'])
            if g.get('depreciation_state')
        }
        by_method = {
            g['depreciation_method']: g['depreciation_method_count']
            for g in self.read_group(domain, ['id'], ['depreciation_method'])
            if g.get('depreciation_method')
        }

        return {
            'totals': {
                'asset_count': self.search_count(domain),
                'depreciable_cost': agg.get('depreciable_cost') or 0.0,
                'accumulated_depreciation': agg.get('accumulated_depreciation') or 0.0,
                'current_book_value': agg.get('current_book_value') or 0.0,
            },
            'by_category': by_category,
            'by_state': by_state,
            'by_method': by_method,
            # The backfill queue: assets whose start date was inferred from the
            # date the record was created rather than a real business date.
            # Scoped to computed methods — a start date is meaningless for an
            # erp_managed asset (Cadra never derives anything from it), and
            # counting those would drown the real queue. On the NRS tenant that
            # is the difference between 0 and 11,878.
            'needs_start_date': self.search_count(
                domain + [('depreciation_method', 'in', list(COMPUTED_METHODS)),
                          ('depreciation_start_is_estimated', '=', True)]),
            # Assets with a computed method but nothing to compute from.
            'missing_cost': self.search_count(
                domain + [('depreciation_method', 'in', list(COMPUTED_METHODS)),
                          ('depreciable_cost', '<=', 0)]),
        }

    # ── Cron ──────────────────────────────────────────────────

    @api.model
    def _cron_recompute_depreciation(self, batch_size=2000):
        """Monthly refresh. These figures move with the calendar, so nothing in
        the database changes to trigger a recompute on its own."""
        assets = self.search([('depreciation_method', 'in', list(COMPUTED_METHODS))])
        # Registry.in_test_mode() was removed in Odoo 19; the config flag is
        # what's left to distinguish a test run.
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        for i in range(0, len(assets), batch_size):
            batch = assets[i:i + batch_size]
            batch._apply_depreciation()
            # Commit per batch so a long run over a large register doesn't hold
            # one transaction open — but never inside a test, where committing
            # breaks the surrounding rollback.
            if not in_test:
                self.env.cr.commit()
        # Stamped last so it reflects a run that actually completed — the
        # settings screen shows it, and "last recomputed" claiming a run that
        # died halfway would be worse than showing nothing.
        self.env['ir.config_parameter'].sudo().set_param(
            'cadra.depreciation.last_recompute',
            fields.Datetime.to_string(fields.Datetime.now()))
        return len(assets)

    # ── Validation ────────────────────────────────────────────

    @api.constrains('salvage_rate', 'declining_rate', 'useful_life_months',
                    'depreciation_method')
    def _check_asset_depreciation_policy(self):
        for r in self:
            if r.useful_life_months < 0:
                raise ValidationError(_('Useful life cannot be negative.'))
            if not 0 <= r.salvage_rate <= 100:
                raise ValidationError(_('Salvage rate must be between 0 and 100%.'))
            if not 0 <= r.declining_rate <= 100:
                raise ValidationError(_('Declining rate must be between 0 and 100%.'))
            if r.depreciation_method == METHOD_DECLINING_BALANCE and not r.declining_rate:
                raise ValidationError(_(
                    'Asset "%s" uses declining balance, so it needs an annual rate.'
                ) % r.name)

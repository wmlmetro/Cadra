"""R43 — what writing a category's verification window actually costs.

`nrs.asset.is_verified` is a stored compute with
`@api.depends('category_id.verification_interval_days')`. That dotted
dependency is what makes "shortening a category's window bites immediately"
true, and it is also a bill: writing the window marks every asset in the
category to recompute, synchronously, inside the HTTP request that wrote it —
and `verification_interval_days` is writable over
`PATCH /api/v1/settings/categories/{id}` under `settings:write`, behind a proxy
timeout.

Handoff 09 flagged the trade and kept correctness. Handoff 10 R43 ruled: keep
correctness, then MEASURE it, and only move to a queued job with a `202` if
the number says so. The alternative — dropping the dotted depends — makes a
category change bite within a day instead of immediately, which is a
correctness loss traded for a latency problem nobody had measured.

This test measures it at whatever scale the database it runs on actually has,
topping up to a floor so a fresh CI database still measures something real.
The number that settled the ruling was taken on `nrs19`'s largest category —
10,259 assets — and is recorded in `docs/handoffs/10-REPORT.md`.

Two things are asserted, and only one of them is a clock:

  * the wall time fits inside a generous ceiling. Machine-dependent, so the
    ceiling is loose; it is here to fail if the operation ever becomes
    quadratic, not to police a millisecond budget.
  * the flush issues a BOUNDED number of UPDATE statements rather than one per
    asset. That is the machine-independent half — a recompute that degrades to
    row-at-a-time is the failure mode that turns a seconds-long write into a
    minutes-long one, and it would still pass a loose clock on a small tenant.
"""
import logging
import time

from odoo.tests import TransactionCase, tagged

_logger = logging.getLogger(__name__)

# Enough rows that a row-at-a-time regression is unmissable, few enough that a
# cold CI database can create them in the time a test is allowed — and low
# enough that both populated tenants clear it on data they already hold:
# `nrs19`'s largest category is 10,259 assets and `jaizbankplc`'s is 1,778, so
# neither creates a row. A scale test that manufactures its own scale measures
# the manufacturing.
FLOOR = 1500
# Loose on purpose — see the module docstring.
CEILING_SECONDS = 90.0
# `is_verified` is a boolean, so a batched flush groups the writes by value:
# two UPDATEs is the floor, and anything within an order of magnitude of that
# is still batched. One per asset is what this is watching for. Zero is also a
# pass and is the common case here — a recompute writes only where the value
# CHANGED, and on real data almost nothing does; `assertTrue(seen)` is what
# stops that zero being confused with a counter that never ran.
MAX_UPDATES = 64


@tagged('post_install', '-at_install')
class TestCategoryWindowAtScale(TransactionCase):

    def _population(self):
        """The largest real category here, topped up to FLOOR if it is small.

        Preferring what the database already holds means this measures 10,259
        real assets on `nrs19` and creates nothing, while still measuring
        something on a tenant that has none.
        """
        Category = self.env['nrs.asset.category']
        groups = self.env['nrs.asset']._read_group(
            [('category_id', '!=', False)], ['category_id'], ['__count'])
        biggest = max(groups, key=lambda row: row[1], default=None)
        if biggest and biggest[1] >= FLOOR:
            return biggest[0], biggest[1], 0

        category = Category.create(
            {'name': 'H10 Scale Category', 'code': 'H10SCALE'})
        self.env['nrs.asset'].create([{
            'name': 'H10 Scale Asset %05d' % i,
            # Supplied so the test does not spend its time in the sequence,
            # and `tag_source` set away from 'auto' so no tag label is minted
            # per asset. Neither is what is being measured.
            'asset_code': 'H10SCALE%06d' % i,
            'tag_source': 'other',
            'category_id': category.id,
        } for i in range(FLOOR)])
        self.env.flush_all()
        return category, FLOOR, FLOOR

    def test_writing_a_category_window_recomputes_its_assets_in_one_pass(self):
        category, count, created = self._population()
        seen = []
        real_execute = self.env.cr.execute

        def counting_execute(query, params=None, *args, **kwargs):
            # Odoo 19 passes `SQL` objects here, not strings, and `code` is
            # where the text lives. Everything is recorded, not just the
            # UPDATEs, so that `all_statements` below can prove this hook fired
            # at all — a counter that silently never runs reports zero, and
            # zero is indistinguishable from the perfect result it is asserting.
            seen.append(getattr(query, 'code', None) or str(query))
            return real_execute(query, params, *args, **kwargs)

        self.env.cr.execute = counting_execute
        try:
            start = time.time()
            category.write({'verification_interval_days': 111})
            marked = time.time() - start
            self.env.flush_all()
            elapsed = time.time() - start
        finally:
            self.env.cr.execute = real_execute

        updates = [q for q in seen
                   if 'UPDATE' in q.upper() and 'nrs_asset' in q]

        _logger.info(
            "R43: category %r, %s assets (%s created for this test) — "
            "write() returned in %.3fs, flush complete at %.3fs, "
            "%s statements total, %s of them UPDATEs on nrs_asset",
            category.name, count, created, marked, elapsed,
            len(seen), len(updates))

        self.assertGreaterEqual(count, FLOOR,
                                'measured at a scale worth measuring')
        self.assertTrue(
            seen,
            'the statement counter never fired, so its zero means nothing')
        self.assertLess(
            elapsed, CEILING_SECONDS,
            'recomputing %s assets took %.1fs — past this the PATCH route '
            'needs to become a queued job returning 202' % (count, elapsed))
        self.assertLessEqual(
            len(updates), MAX_UPDATES,
            'the recompute issued %s UPDATEs for %s assets — it has stopped '
            'batching, which is what turns this from seconds into minutes'
            % (len(updates), count))

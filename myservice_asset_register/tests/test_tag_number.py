"""The next tag number is found by arithmetic, not by walking every number.

Handoff 46 found `_generate_tag` taking the highest number issued under a
prefix by a TEXT sort — `NRS-GEN-999` outranks `NRS-GEN-8305` — so past 999
labels of one prefix every new asset began at 1000 and counted its way up
through every number already issued, one query each: about 7,300 queries and
11 seconds per asset on `test19`, and the same walk on one `nrs19` prefix and
eight `jaizbankplc` prefixes. Nothing was wrong with the numbers issued,
which is why it went unnoticed; the cost grew with every tag.

Both outcomes are pinned: the number (the one after the highest, as a
number) and the cost (bounded, whatever the count of labels beneath it).
"""
import uuid

from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

#: Labels placed past 999 under the probe prefix. The old walk issued one
#: COUNT per taken number, so it spends more than this many queries; the
#: arithmetic spends a handful whatever the number.
LABELS_PAST_999 = 400
QUERY_BUDGET = 120


@tagged('post_install', '-at_install')
class TestTagNumber(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        code = 'Q%s' % uuid.uuid4().hex[:5].upper()
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'Tag number test %s' % code, 'code': code})
        self.first = self.env['nrs.asset'].create(
            {'name': 'tag number probe 1', 'category_id': self.category.id})
        self.prefix = self.first.asset_tag[:-3]
        self.assertTrue(self.first.asset_tag.endswith('001'),
                        'a fresh prefix starts at 001: %s' % self.first.asset_tag)

    def _place(self, numbers):
        self.env['nrs.asset.tag.label'].create([{
            'name': '%s%03d' % (self.prefix, n),
            'asset_id': self.first.id,
            'source': 'other',
            'state': 'scrapped',
        } for n in numbers])

    def test_past_999_the_next_number_follows_the_highest_numerically(self):
        self._place([999] + list(range(1000, 1000 + LABELS_PAST_999)))
        before = self.env.cr.sql_log_count
        second = self.env['nrs.asset'].create(
            {'name': 'tag number probe 2', 'category_id': self.category.id})
        spent = self.env.cr.sql_log_count - before
        self.assertEqual(second.asset_tag,
                         '%s%d' % (self.prefix, 1000 + LABELS_PAST_999))
        self.assertLess(
            spent, QUERY_BUDGET,
            "creating one asset spent %d queries with %d labels past 999 under "
            "its prefix — the tag number is being found by walking every "
            "number already issued" % (spent, LABELS_PAST_999 + 1))

    def test_below_1000_numbering_is_unchanged(self):
        second = self.env['nrs.asset'].create(
            {'name': 'tag number probe 2', 'category_id': self.category.id})
        self.assertEqual(second.asset_tag, self.prefix + '002')

    def test_numbering_continues_after_the_highest_not_after_the_count(self):
        """Two labels exist (001 and 007); the next is 008, not 003."""
        self._place([7])
        second = self.env['nrs.asset'].create(
            {'name': 'tag number probe 2', 'category_id': self.category.id})
        self.assertEqual(second.asset_tag, self.prefix + '008')

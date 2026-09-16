"""Where a newly created asset appears in the list.

`nrs.asset._order` was `asset_code` — ascending. `asset_code` is a zero-padded
`ir.sequence` (`NRS-AST-000001`), so ascending code order IS ascending creation
order, and the asset a user had just created was deterministically placed on
the LAST page of the register. That is not an ordering nobody thought about;
it is an ordering that puts the one record the user is looking for as far from
them as the dataset allows, and it reached list, kanban and every other view at
once because it is the model default.

The fix is `asset_code desc` rather than `create_date desc`, and the choice is
the thing these tests pin. Because the code is the creation sequence,
descending code gives newest-first AND keeps the register ordered by code —
both properties from one clause. `create_date desc` would have bought the first
and quietly lost the second, so `test_the_order_is_the_code_sequence_not_the_row_id`
below creates its records with codes DELIBERATELY out of insertion order: it
fails for `create_date desc` and for `id desc` and passes only for the
code-ordered clause, which is what stops a later "tidy-up" swapping one for the
other without noticing what it costs.

Nothing here asserts anything about the REST API, and that is deliberate:
`paginate()` sorts on `id` explicitly rather than falling back to `_order`
(`myservice_api/controllers/utils.py`), so `GET /api/v1/assets` and its cursor
do not observe this change at all. If that ever stops being true, this order
becomes API surface and Vendra is downstream of it.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged('post_install', '-at_install')
class TestAssetDefaultOrder(CadraTransactionCase):
    """The default order, exercised through `search()` rather than read off."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['nrs.asset.category'].create(
            {'name': 'Order Test Category', 'code': 'ORDTEST'})

    def _create(self, *codes):
        """Create assets with the given codes, in the order given.

        `tag_source` is set away from 'auto' so no tag label is minted per
        asset — irrelevant to ordering and needless work.
        """
        return self.env['nrs.asset'].create([{
            'name': 'Order Test %s' % code,
            'asset_code': code,
            'tag_source': 'other',
            'category_id': self.category.id,
        } for code in codes])

    def _codes(self, records):
        return [a.asset_code for a in records]

    def test_the_newest_asset_is_first(self):
        """The whole point: create one, and it is at the top, not the bottom."""
        self._create('ORDTEST000001', 'ORDTEST000002', 'ORDTEST000003')
        newest = self._create('ORDTEST000004')
        self.env.flush_all()

        found = self.env['nrs.asset'].search(
            [('category_id', '=', self.category.id)])

        self.assertEqual(
            found[0], newest,
            "the most recently created asset must lead the default order; "
            "found %r at the top" % (found[0].asset_code,))

    def test_the_default_order_is_descending_across_the_page(self):
        """Not just the first row — the whole list reads newest to oldest."""
        self._create('ORDTEST000001', 'ORDTEST000002', 'ORDTEST000003',
                     'ORDTEST000004')
        self.env.flush_all()

        found = self.env['nrs.asset'].search(
            [('category_id', '=', self.category.id)])

        self.assertEqual(
            self._codes(found),
            ['ORDTEST000004', 'ORDTEST000003', 'ORDTEST000002',
             'ORDTEST000001'])

    def test_the_order_is_the_code_sequence_not_the_row_id(self):
        """Codes deliberately out of insertion order.

        This is the test that distinguishes `asset_code desc` from the two
        orderings it would be easy to replace it with. Rows are INSERTED
        1, 2, 3 but carry codes 2, 3, 1 — so `id desc` and `create_date desc`
        both yield codes [1, 3, 2] and only a code-ordered clause yields
        [3, 2, 1].
        """
        self._create('ORDTEST000002')
        self._create('ORDTEST000003')
        self._create('ORDTEST000001')
        self.env.flush_all()

        found = self.env['nrs.asset'].search(
            [('category_id', '=', self.category.id)])

        self.assertEqual(
            self._codes(found),
            ['ORDTEST000003', 'ORDTEST000002', 'ORDTEST000001'],
            "the default order must follow the asset code sequence, not the "
            "insertion order of the rows")

    def test_an_explicit_order_still_wins(self):
        """`_order` is a default, not a constraint — callers can override.

        `asset_sap_views.xml` pins its own `default_order`, and several
        reports pass `order=`. Those must keep working.
        """
        self._create('ORDTEST000001', 'ORDTEST000002', 'ORDTEST000003')
        self.env.flush_all()

        found = self.env['nrs.asset'].search(
            [('category_id', '=', self.category.id)], order='asset_code asc')

        self.assertEqual(
            self._codes(found),
            ['ORDTEST000001', 'ORDTEST000002', 'ORDTEST000003'])

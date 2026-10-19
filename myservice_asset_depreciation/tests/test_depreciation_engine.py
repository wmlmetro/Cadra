"""`summary_at` is `value_at` and `schedule_end_date` from one schedule.

Handoff 63b: restating a class after a category policy save built every
asset's schedule twice — once for the value, once for the end date — 76,168
builds on `test19`'s class of 19,042. `_apply_depreciation` now asks
`summary_at` for both. It is only allowed to be faster: this pins its answer
equal to the two calls it replaced, for every method, both prorations,
salvage, a disposal, and the inputs that produce no schedule at all.
"""
import itertools
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.myservice_asset_depreciation.models import (
    depreciation_engine as engine,
)


@tagged("post_install", "-at_install")
class TestSummaryAtIsTheTwoCalls(BaseCase):

    def test_summary_at_answers_what_value_at_and_schedule_end_date_did(self):
        methods = (engine.METHOD_NONE, engine.METHOD_STRAIGHT_LINE,
                   engine.METHOD_DECLINING_BALANCE, engine.METHOD_ERP_MANAGED,
                   'unknown')
        costs = (0, 0.004, 1000, 100000.555, 2500000)
        starts = (None, date(2019, 1, 31), date(2024, 2, 29),
                  date(2026, 10, 19))
        lives = (0, 1, 36, 132)
        as_ofs = (date(2018, 12, 31), date(2026, 10, 19), date(2040, 1, 1))
        checked = 0
        for (method, cost, start, life, as_of, salvage, rate, disposal,
             switch, proration) in itertools.product(
                methods, costs, starts, lives, as_ofs, (0, 150.0),
                (None, 33.3), (None, date(2025, 6, 15)), (True, False),
                (engine.PRORATION_WHOLE_MONTH, engine.PRORATION_DAILY)):
            policy = dict(cost=cost, start_date=start, life_months=life,
                          method=method, salvage=salvage,
                          annual_rate_pct=rate, disposal_date=disposal,
                          switch_to_straight_line=switch, proration=proration)
            try:
                expected = (engine.value_at(as_of, **policy)
                            + (engine.schedule_end_date(**policy),))
            except Exception as refused:  # the same refusal, then
                with self.assertRaises(type(refused), msg=repr(policy)):
                    engine.summary_at(as_of, **policy)
            else:
                self.assertEqual(engine.summary_at(as_of, **policy), expected,
                                 msg=repr((as_of, policy)))
            checked += 1
        self.assertEqual(checked, 5 * 5 * 4 * 4 * 3 * 2 * 2 * 2 * 2 * 2)

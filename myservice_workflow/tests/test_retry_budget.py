"""Handoff 63, ruling 8: the delivery retry budget covers a day.

The default is 32 attempts (26 h 3 min at the 60 s base and 3,600 s cap);
the 19.0.3.4.0 migration moves every target still on the OLD default
(8 / 60 / 3,600) and leaves a customised one alone. The outage itself is
measured in `test_register_state_event.TestADayWithoutVendra`.
"""
import importlib.util
import os

from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

_MIGRATION = os.path.join(os.path.dirname(__file__), '..', 'migrations',
                          '19.0.3.4.0', 'post-migrate.py')


def _migration():
    spec = importlib.util.spec_from_file_location('retry_budget_63',
                                                  _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestRetryBudget(CadraTransactionCase):

    def _target(self, name, **policy):
        return self.env['workflow.config'].create(dict({
            'name': name, 'purpose': 'asset_events', 'adapter_type': 'stub',
            'event_enabled': True}, **policy))

    def test_a_new_target_tries_for_a_day_and_more(self):
        t = self._target('63 budget probe')
        self.assertEqual((t.retry_max_attempts, t.retry_base_seconds,
                          t.retry_cap_seconds), (32, 60, 3600))
        # The ladder the drain uses (`_backoff_seconds`), summed over the
        # 31 waits between 32 attempts.
        waits = [min(60 * 2 ** n, 3600) for n in range(31)]
        self.assertEqual(sum(waits), 93780)          # 26 h 3 min
        self.assertGreater(sum(waits), 24 * 3600)
        # 30 — the number the ruling named — is a day with 3 min to spare.
        self.assertEqual(sum(waits[:29]), 24 * 3600 + 180)

    def test_the_migration_moves_the_old_default_and_leaves_a_custom(self):
        old = self._target('63 old default', retry_max_attempts=8,
                           retry_base_seconds=60, retry_cap_seconds=3600)
        custom = self._target('63 customised', retry_max_attempts=8,
                              retry_base_seconds=60, retry_cap_seconds=300)
        tuned = self._target('63 more attempts', retry_max_attempts=12,
                             retry_base_seconds=60, retry_cap_seconds=3600)
        self.env.flush_all()
        with self.assertLogs('retry_budget_63', 'INFO') as logs:
            _migration().migrate(self.env.cr, '19.0.3.3.0')
        self.env.invalidate_all()
        self.assertEqual(old.retry_max_attempts, 32)
        self.assertEqual((custom.retry_max_attempts, custom.retry_cap_seconds),
                         (8, 300))
        self.assertEqual(tuned.retry_max_attempts, 12)
        line = logs.output[0]
        self.assertIn('#%d 63 old default' % old.id, line)
        self.assertIn('#%d 63 customised: 8/60s/300s' % custom.id, line)
        self.assertIn('customised, left alone', line)

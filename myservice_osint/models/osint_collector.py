from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class OsintCollector(models.AbstractModel):
    """
    Scheduled action entry points.
    """
    _name = 'osint.collector'
    _description = 'OSINT Collector Scheduler'

    @api.model
    def cron_fetch_all_sources(self):
        """Fetch all due sources — runs every hour."""
        self.env['osint.source.config'].run_all_scheduled()

    @api.model
    def cron_recompute_threat_scores(self):
        """Recompute state threat scores — runs daily at 03:00."""
        self.env['security.state.threat'].recompute_all()

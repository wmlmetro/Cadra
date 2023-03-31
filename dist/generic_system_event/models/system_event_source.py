import logging
import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions, _

_logger = logging.getLogger(__name__)


class GenericSystemEventSource(models.Model):
    _name = 'generic.system.event.source'
    _order = 'name ASC, id DESC'
    _description = 'Generic System Event Source'

    model_id = fields.Many2one(
        'ir.model', required=True, index=True, readonly=True, auto_join=True,
        string="Event Source Model", delegate=True, ondelete='cascade')
    event_data_model_id = fields.Many2one(
        'ir.model', required=True, index=True, readonly=True,
        string="Event Data Model", ondelete='cascade')

    event_handler_ids = fields.One2many(
        comodel_name='generic.system.event.source.handler.map',
        inverse_name='event_source_id',
        readonly=True, auto_join=True,
    )

    # Vacuum
    vacuum_time = fields.Integer(
        default=90,
        help='The time after which, event will be deleted')
    vacuum_time_uom = fields.Selection(
        selection=[
            ('days', 'Days'),
            ('weeks', 'Weeks'),
            ('months', 'Months'),
        ],
        default='days',
        help='The unit of measurement of Vacuum Time.')
    vacuum_enable = fields.Boolean(
        default=False, index=True,
        help='Enable automatic removal of old events.'
    )
    _sql_constraints = [
        (
            'model_id_uniq',
            'UNIQUE (model_id)',
            (
                'For each Odoo model only one Generic System Event Source '
                'can be created!'
            ),
        )
    ]

    @api.model
    @tools.ormcache('source_model')
    def _get_event_source_id(self, source_model):
        source = self.sudo().search(
            [('model_id.model', '=', source_model)], limit=1)
        return source.id if source else False

    @api.model
    def get_event_source(self, source_model):
        source_id = self._get_event_source_id(source_model)
        return self.browse(source_id) if source_id else self.browse()

    @api.model
    @tools.ormcache('source_model')
    def get_event_data_model(self, source_model):
        """ Return name of model to store events for envent source specified
            by 'source_model' param

            :param str source_model: Name of model of event source
            :return str: name of model to store events.
        """
        return self.sudo().get_event_source(
            source_model).event_data_model_id.model

    def handle_system_event(self, record, event):
        """ Do nothing, could be overridden by other modules

            :param RecordSet record: record that triggered event.
            :param RecordSet event: event to be handled
        """
        self.ensure_one()

        # Run programmatic event handlers (defined by 'on_event' decorator)
        # Handler Data is dict: event_code -> [EventHandler]
        handler_data = self.env[
            'generic.system.event.handler.mixin'
        ]._generic_system_event_handler_full_data.get(self.sudo().model, {})

        # Find specific event handlers
        event_handlers = handler_data.get(event.event_code, [])

        # Add wildcard event handlers if they are defined
        if handler_data.get('*'):
            # NOTE: Be careful here to avoid modification of event handlers
            #       in the global dict. Here we have to create new list,
            #       that is combination of event handlers for this event,
            #       and global event handlers.
            event_handlers = event_handlers + handler_data['*']

            # Sort resulting list of handlers by priority
            event_handlers.sort(key=lambda h: h.priority)

        # Run event handlers
        for handler in event_handlers:
            handler.handle(record, event)

    def _vacuum_get_date(self):
        self.ensure_one()
        if self.vacuum_time_uom == 'days':
            delta = relativedelta(days=self.vacuum_time)
        elif self.vacuum_time_uom == 'weeks':
            delta = relativedelta(days=self.vacuum_time*7)
        elif self.vacuum_time_uom == 'months':
            delta = relativedelta(months=self.vacuum_time)
        else:
            raise exceptions.UserError(_(
                "Incorrect configuration of auto vacuum for events"))
        return datetime.datetime.now() - delta

    @api.model
    def _scheduler_vacuum_events(self):
        for src in self.search([('vacuum_enable', '=', True)]):
            vacuum_date = src._vacuum_get_date()
            self.sudo().env[src.event_data_model_id.model].search(
                [('event_date', '<', fields.Datetime.to_string(vacuum_date))],
            ).unlink()

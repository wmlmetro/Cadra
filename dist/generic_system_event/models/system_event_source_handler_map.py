import logging
import collections
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericSystemEventSourceHandlerMap(models.Model):
    """ This model holds info about models that allowed to
        handle events from specific event source.
        And also, it describes have to reach handler models from
        event_source record
    """
    _name = 'generic.system.event.source.handler.map'
    _description = 'Generic System Event Source: Handler Map'
    _log_access = False

    event_source_id = fields.Many2one(
        'generic.system.event.source', required=True,
        index=True, auto_join=True, readonly=True, ondelete='cascade')
    event_source_model = fields.Char(
        related='event_source_id.model_id.model',
        store=True, index=True, readonly=True,
        string="Event Source Model")
    event_handler_model_id = fields.Many2one(
        'ir.model', required=True, index=True, auto_join=True, readonly=True,
        ondelete='cascade')
    event_handler_model_name = fields.Char(
        related='event_handler_model_id.model',
        store=True, index=True, readonly=True,
        string="Event Handler Model")

    source_to_handler_path = fields.Char(
        required=True,
        help="Path how to reach event handler record from event source record")

    _sql_constraints = [
        ('unique_source_handler',
         'UNIQUE(event_source_id, event_handler_model_id)',
         'There could be only one path from source to handler.')
    ]

    @property
    def _source_handler_path_map(self):
        res = collections.defaultdict(dict)
        for rec in self.sudo().search([]):
            res[rec.event_handler_model_name][rec.event_source_model] = (
                rec.source_to_handler_path)

        # Memoize result on class
        type(self)._source_handler_path_map = dict(res)
        return res

    @api.model
    def _setup_complete(self):
        res = super()._setup_complete()

        type(self)._source_handler_path_map = (
            GenericSystemEventSourceHandlerMap._source_handler_path_map)

        return res

    def _update_source_handler_map(self, source_model, handler_model, path):
        src_model = self.env['ir.model']._get(source_model)
        h_model = self.env['ir.model']._get(handler_model)

        if not src_model.system_event_source_id:
            # Source is not event handler
            _logger.warning(
                "Attempt to add path from model that is not event source")
            return

        self.env.cr.execute("""
            INSERT INTO generic_system_event_source_handler_map (
                event_source_id,
                event_source_model,
                event_handler_model_id,
                event_handler_model_name,
                source_to_handler_path)
            VALUES (
                %(es_id)s,
                %(es_model)s,
                %(hmodel_id)s,
                %(hmodel)s,
                %(path)s)
            ON CONFLICT ON CONSTRAINT
              generic_system_event_source_handler_map_unique_source_handler
            DO UPDATE SET source_to_handler_path = %(path)s;
        """, {
            'es_id': src_model.system_event_source_id.id,
            'es_model': src_model.model,
            'hmodel_id': h_model.id,
            'hmodel': h_model.model,
            'path': path,
        })

        type(self)._source_handler_path_map = (
            GenericSystemEventSourceHandlerMap._source_handler_path_map)

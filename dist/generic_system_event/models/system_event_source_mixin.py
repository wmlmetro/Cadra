import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class GenericSystemEventSourceMixin(models.AbstractModel):
    """ Use this mixin to make model capable for triggering
        system events.

        All you need to make model event source is to do following:
        - inherit model from this mixin
        - define attribute _generic_system_event_source__event_data_model
          that have to specify name of model to store events in
        - define attribute _generic_system_event_source__auto_create and
          set it to True. This is needed to allow system to create
          record in generic.system.event.source model automatically.

        For example:

            class MyEvent(models.Model):
                _name = 'my.event'
                _inherit = 'generic.system.event.data.mixin'

            class MyEventSource(models.Model):
                _name = 'my.event.source'
                _inherit = 'generic.system.event.source.mixin'

                # Automatically create event source
                _generic_system_event_source__auto_create = True

                # name of data model for events from this event source
                _generic_system_event_source__event_data_model = 'my.event'

                def my_method(self):
                    # Now you can trigger events
                    self.trigger_event("my-event-code", {some event params})

        Note that, created event source will have automatically-generated
        XMLID in format: %(module_name)s.system_event_source__%(model)s
        Where:
            - module_name - name of current module (where this model defined)
            - model - name of model with '.' replaced by '_'
    """
    _name = 'generic.system.event.source.mixin'
    _inherit = [
        'generic.system.event.handler.mixin',
        'generic.mixin.track.changes',
    ]
    _description = 'Generic System Event Source Mixin'

    # Automatically create event source
    _generic_system_event_source__auto_create = False

    # name of data model for events from this event source
    _generic_system_event_source__event_data_model = None

    # TODO: Possibly define defaults for auto vacuum events as attributes
    # TODO: Add attribute for specific XMLID for event source. Could be used
    #       to easily migrate already existing event sources to automatically
    #       created/updated event sources

    generic_event_count = fields.Integer(
        string='System Events', compute='_compute_event_count')

    @api.depends()
    def _compute_event_count(self):
        if self.ids:
            event_model = self.env[
                'generic.system.event.source'
            ].get_event_data_model(self._name)
            event_data = {}
            for e in self.env[event_model].sudo().read_group(
                    [('event_source_record_id', 'in', self.ids)],
                    ['event_source_record_id'],
                    ['event_source_record_id']):
                event_data[e['event_source_record_id']] = (
                    e['event_source_record_id_count'])

        else:
            event_data = dict()

        for record in self:
            record.generic_event_count = event_data.get(record.id, 0)

    def _generic_system_event_source__prepare_es_data(self):
        """ Prepare data to create event source for this model
            automatically.
        """
        model = self.env['ir.model']._get(self._name)
        event_model = self.env['ir.model']._get(
            self._generic_system_event_source__event_data_model)

        if not event_model:
            raise AssertionError(
                "Event model %s not loaded for %s. "
                "Possibly it have to be defined before event source. "
                "Check import order in module or models init file." % (
                    self._generic_system_event_source__event_data_model,
                    self._name)
            )

        return {
            'model_id': model.id,
            'event_data_model_id': event_model.id,
        }

    def _generic_system_event_source__register_handler_map(self,
                                                           handler_model,
                                                           path):
        """ Register new path to specified handler model
        """
        self.env[
            'generic.system.event.source.handler.map'
        ]._update_source_handler_map(
            source_model=self._name,
            handler_model=handler_model,
            path=path)

    def _auto_init(self):
        # We override this method, to be able to automatically register event
        # source for any model inherited from this mixin, thus avoiding
        # unnecessary redefinition of event source in XML
        res = super()._auto_init()

        if self._abstract:
            return res

        if not getattr(self,
                       '_generic_system_event_source__auto_create', False):
            # Automatic recreation of event source is disabled, so skipping..
            return res

        # During module install / update there is 'module' variable available
        # in context, that represents name of module been updated at the moment
        # of calling this method
        module = self.env.context.get('module')
        if not module:
            # It seems that it is not update
            return res

        @self.pool.post_init
        def create_or_update_event_source():
            """ Do actual creation/registration of event source for this
                model
            """
            _logger.info(
                "Registering auto-generated Event Source for %s (module: %s)",
                self._name, module)
            es_data = self._generic_system_event_source__prepare_es_data()
            es = self.env['generic.system.event.source'].search(
                [('model_id.model', '=', self._name)],
                limit=1)
            if es:
                # In case when event source already exists, then all we need
                # is to update it (if something changed)
                es.write(es_data)
            else:
                # Create new event source if there is no existing event source
                es = self.env['generic.system.event.source'].create(es_data)

            # Update xmlid for created event source
            self.env['ir.model.data']._update_xmlids([{
                'xml_id': '%s.system_event_source__%s' % (
                    module, self._name.replace('.', '_')),
                'noupdate': False,
                'record': es,
            }])

        return res

    def trigger_event(self, event_type_code, event_data_vals=None):
        """ Trigger event for this model

            :param str event_type_code: code of event type to trigger
            :param dict event_data_vals: Extra data for event
        """
        self.ensure_one()

        event_source = self.env[
            'generic.system.event.source'
        ].get_event_source(self._name)

        event_type = self.env[
            'generic.system.event.type'
        ].get_event_type(event_type_code, event_source)

        event_data = event_data_vals if event_data_vals is not None else {}
        event_data.update({
            'user_id': self.env.user.id,
            'event_date': fields.Datetime.now(),
            'event_source_record_id': self.id,
            'event_type_id': event_type.id,
            'event_source_id': event_source.id,
        })
        event = self.env[
            event_source.sudo().event_data_model_id.model
        ].sudo().create(event_data)

        # Run process of handling this event
        event_source.handle_system_event(self, event)
        return event

    @api.model_create_multi
    def create(self, vals):
        records = super().create(vals)
        for record in records:
            record.trigger_event('record-created', {})
        return records

    def _get_generic_tracking_fields(self):
        # Add 'active' to fields tracked by 'generic.mixin.track.fields'
        # if it is not tracked yet
        res = super()._get_generic_tracking_fields()
        if 'active' in self._fields and 'active' not in res:
            return set(res) | set(['active'])
        return res

    def _postprocess_write_changes(self, changes):
        # If object has field active, then we have to trigger
        # automatically archive/unarchive events.
        # Implementing this way instead of @post_write, because
        # some models may not have 'active' field.
        if changes.get('active'):
            c_active = changes['active']
            if c_active.old_val and not c_active.new_val:
                self.trigger_event('record-archived')
            elif not c_active.old_val and c_active.new_val:
                self.trigger_event('record-unarchived')
        return super()._postprocess_write_changes(changes)

    def unlink(self):
        # We have to delete related events,
        # before deletion event source records,
        # to ensure no garbage data left in database.
        event_model = self.env[
            'generic.system.event.source'
        ].get_event_data_model(self._name)

        # We have to delete these events as superuser to avoid possible
        # access rights issues
        self.env[event_model].sudo().search([
            ('event_source_record_id', 'in', self.ids)
        ]).unlink()

        return super().unlink()

    def action_show_related_system_events(self):
        self.ensure_one()
        event_model = self.env[
            'generic.system.event.source'
        ].get_event_data_model(self._name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Events'),
            'res_model': event_model,
            'view_mode': 'tree,form',
            'domain': [('event_source_record_id', 'in', self.ids)],
        }

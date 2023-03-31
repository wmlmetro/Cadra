import re
import logging
import inspect
import functools
import collections
from odoo import models, api

_logger = logging.getLogger(__name__)

DEFAULT_PRIORITY = 40


# TODO: Allow to call handler on multiple records
#       if call from different source and multiple target records
#       could be connected to same source record.
#       Do we need this?
def on_event(*event_codes, event_source="self", priority=None):
    """ Decorator to mark method that have to be called when event bubbles

        :param event_codes: event codes to listen to. Event code '*' means
            any event.
        :param str event_source: name of model of event source to listen to.
            By default is set to 'self' which means same model decorated
            method belongs to. Handling different event source will work only
            if there is path from event source model to event handler model
            defined in model 'system.event.source.handler.model'.
        :param int priority: Optionally specify priority of handler.
            This param defined the order used to call multiple event handlers.
            Event handlers with lower values will be called first.

        For example, you can add methods like following in your
        event source model:

            @on_event('my-event1', 'my_event2')
            def _on_my_event(self, event):
                pass

        Such methods will be called with following context:
            - self - single record that triggered event
            - event - record representing event itself

        Also, it is possible to configure handler to catch all events
        for this source:

            @on_event('*')
            def _on_all_events(self, event):
                pass

        In case of event handler that handles events from different
        event source, at first in XML we have to define (or ensure that
        it is already defined) path from source record to target record.

            <record id="path_source_to_handler"
                    model='generic.system.event.source.handler.model'>
                <field name="event_source_id"
                       ref="my_event_source"/>
                <field name="event_handler_model_id"
                       ref="model_my_event_handler"/>
                <field name="source_to_handler_path">my_handler_id</field>
            </record>

        Then, in ``@on_event`` decorator in handler model, we have to specify
        the source from which we have to handle event:

            @on_event('my-event', event_source='my.event.source')
            def _on_my_event_from_my_event_source(self, event):
                ...  # Do some meaningful
    """
    def decorator(func):
        if not hasattr(func, '_on_generic_system_event'):
            func._on_generic_system_event = EventHandlerInfo()
        func._on_generic_system_event.add_info(
            event_source,
            event_codes,
            priority)
        return func
    return decorator


def is_event_handler(func):
    """ Check if method (func) is handler
    """
    if not callable(func):
        return False
    if hasattr(func, '_on_generic_system_event'):
        return True
    return False


class EventHandlerInfo:
    """ This class is used to store information about handled events directly
        on event handler method.
    """
    def __init__(self):
        # Source:
        #     event_code:
        #          priority: None
        # We have such complex data structure here, because we want to be able
        # to define method that handles multiple events from multiple event
        # sources
        self._events_info = {}

    def add_info(self, source, event_codes, priority):
        """ Update handler info with new values
        """
        if source not in self._events_info:
            self._events_info[source] = {}
        for ecode in event_codes:
            if ecode not in self._events_info[source]:
                self._events_info[source][ecode] = {}
            self._events_info[source][ecode].update({
                'priority': priority,
            })

    def iter_events(self):
        """ Iterate over event info in this instance.

            Yields tuples that consist of three elements:
            - source
            - event_code
            - event_info
        """
        for source, edata in self._events_info.items():
            for event_code, event_info in edata.items():
                yield source, event_code, event_info


class EventHandler:
    """ Event handler representation.

        Contains all necessary info to run event handler
    """
    def __init__(self, source_model, event_code,
                 target_model, target_method,
                 target_path, extra_info=None):
        self._source_model = source_model
        self._event_code = event_code
        self._target_method = target_method
        self._target_model = target_model
        self._target_path = target_path
        self._extra_info = extra_info

        # TODO: Add validation

    def __str__(self):
        return "Handler %s: %s -> %s: %s" % (
            self._source_model, self._event_code,
            self._target_model, self._target_method
        )

    def __repr__(self):
        return str(self)

    @property
    def priority(self):
        """ Priority of this event handler.
            Used to determine in what order event handlers for same event
            have to be ran.
            By default is set to 40
        """
        if self._extra_info.get('priority', None) is not None:
            return self._extra_info['priority']
        return DEFAULT_PRIORITY

    def _find_targets__self(self, source_record):
        """ Simple case, when target is same as source record.
        """
        return source_record

    def _find_targets__delegation_implementation(self, source_record):
        """ This is special case when event source is Interface
            (inherits generic.mixin.delegation.interface)
            and target (handler) model is Implementation of that interface.
            So, in this case we are already have enough data to find the
            way to reach implementation model from event source (interface)
        """
        implementation_model = source_record[
            source_record._generic_mixin_implementation_model_field
        ]
        if implementation_model != self._target_model:
            # Interface's implementation has different model,
            # then expected by this handler. Thus return empty recordset
            return source_record.env[self._target_model].browse()

        # Normally, target of this handler is implementation
        # of source's interface
        return source_record.env[implementation_model].browse(
            source_record[
                source_record._generic_mixin_implementation_id_field
            ]
        )

    def _find_targets__generic_m2o(self, source_record):
        """ Find targets specified by generic many2one field on source record.

            In this case, target is specified by 2 fields:
            - model
            - res_id

            So, we have to try to find target record (if target model matches
            handler's model).

            :param recordset source_record: record that triggered event
        """
        # TODO: Make parsing as cached property to improve performance
        m = re.match(
            r"^generic-m2o:(?P<model>\w+):(?P<res_id>\w+)$",
            self._target_path)
        if not m:
            return source_record.env[self._target_model].browse()
        gm2o_model = source_record[m.group('model')]
        gm2o_res_id = source_record[m.group('res_id')]
        if not (gm2o_model and gm2o_res_id):
            # No data for generic m2o field. Thus return empty recordset
            return source_record.env[self._target_model].browse()
        if gm2o_model != self._target_model:
            # Generic many2one model does not match target model,
            # thus return empty recordset
            return source_record.env[self._target_model].browse()
        # Return recordset with with record pointed by generic m2o field
        # on source record.
        return source_record.env[gm2o_model].browse(gm2o_res_id)

    def _find_targets__default(self, source_record):
        """ Default implementation of find targets.

            Simply call source's `mapped` method to find target records.
        """
        return source_record.mapped(self._target_path)

    def find_targets(self, source_record):
        """ Find target records to run handler on
        """
        if self._target_path == 'self':
            return self._find_targets__self(source_record)
        if self._target_path == 'delegation:interface-to-implementation':
            return self._find_targets__delegation_implementation(source_record)
        if self._target_path.startswith('generic-m2o:'):
            return self._find_targets__generic_m2o(source_record)

        return self._find_targets__default(source_record)

    def handle(self, source_record, event):
        """ Run this handler for specified source_record and event

            :param source_record: RecordSet that contains single record of
                event source model, that triggered event.
            :param event: RecordSet that contains single event that have
                to be handled by this handler
        """
        for target in self.find_targets(source_record):
            method = getattr(target, self._target_method)
            method(event)


class GenericSystemEventHandlerMixin(models.AbstractModel):
    """ This mixin could be used to make some model capable to handle
        system events.
        It is automatically applied for Event Source modles,
        but also may be manually applied to any other model related to
        some event source.
    """
    _name = 'generic.system.event.handler.mixin'
    _description = 'Generic System Event Handler Mixin'

    # Map: source -> path to handler (current model)
    @property
    def _gse__handler__source_map(self):
        """ Return mapping of event source to path, that could be used
            to determine how to reach records of event handler model from
            record of event source model.

            :returns dict: mapping {'event.source.model': 'path.to.this.model'}
        """
        return self.env[
            'generic.system.event.source.handler.map'
        ]._source_handler_path_map.get(self._name, {})

    @property
    def _generic_system_event_handler_data(self):
        """ Compute event handlers info for this model.

            :return dict: Mapping of format described below.

            Return format:
                {
                    'event.source.model': {
                        'event-code': [EventHandler],
                    },
                }

        """
        cls = type(self)

        if cls._abstract:
            # Do not look for handlers on abstract models
            return {}

        # Dict:
        #     Source:
        #         Event Code: [EventHandler]
        event_handlers = collections.defaultdict(
            functools.partial(collections.defaultdict, list))

        for method_name, __ in inspect.getmembers(cls, is_event_handler):
            # Dict:
            #     event_source:
            #         event_code: dict
            method_event_info = collections.defaultdict(
                functools.partial(collections.defaultdict, dict))

            # Here we have to process it in reversed MRO to ensure that
            # newer overloads updates event info
            for base in reversed(cls.__mro__):
                if method_name not in base.__dict__:
                    continue
                handler_info = getattr(
                    base.__dict__[method_name],
                    '_on_generic_system_event', None)
                if handler_info is None:
                    continue
                for source, e_code, e_info in handler_info.iter_events():
                    method_event_info[source][e_code].update(e_info)

            # Add info about this event handler to result
            for source, e_data in method_event_info.items():
                if source == 'self':
                    source = self._name
                for event_code, event_info in e_data.items():
                    if source == self._name:
                        target_path = 'self'
                    elif source in self._gse__handler__source_map:
                        target_path = self._gse__handler__source_map[source]
                    else:
                        _logger.warning(
                            "There is no path defined for "
                            "handler (%(handler)s) from source (%(source)s).\n"
                            "Current map (source -> path) for %(handler)s:\n"
                            "%(handler_map)s", {
                                'handler': self._name,
                                'source': source,
                                'handler_map': self._gse__handler__source_map,
                            })
                        raise ValueError(
                            "There is no path defined for "
                            "handler (%(handler)s) from source (%(source)s)."
                            "" % {
                                'handler': self._name,
                                'source': source,
                            })
                    event_handlers[source][event_code].append(
                        EventHandler(
                            source_model=source,
                            event_code=event_code,
                            target_model=self._name,
                            target_method=method_name,
                            target_path=target_path,
                            extra_info=event_info,
                        ))

        # optimization: memoize result on cls, it will not be recomputed
        cls._generic_system_event_handler_data = event_handlers
        return event_handlers

    @property
    def _generic_system_event_handler_full_data(self):
        """ Determine full map of handlers.
            This method/property will find all handlers defined on
            any model inherited from 'generic.system.event.handler.mixin'
            model.

            :return dict: Mapping source -> event_code -> [EventHandler]

            Returns data in format:
                {
                    'event.source.model': {
                        'event-code': [EventHandler],
                    },
                }
        """
        cls = type(self)

        # Dict:
        #     Source:
        #         Event Code: [EventHandler]
        event_handlers = collections.defaultdict(
            functools.partial(collections.defaultdict, list))

        # Find all models inherited from this one and find event handlers on
        # each of them
        handler_models = self.pool.descendants(
            ['generic.system.event.handler.mixin'],
            '_inherit')

        # Merge handlers from all models inherited from this one
        for model_name in handler_models:
            Model = self.sudo().env[model_name]
            if Model._abstract:
                # Skip abstract models
                continue

            for source, ed in Model._generic_system_event_handler_data.items():
                for event_code, handlers in ed.items():
                    event_handlers[source][event_code] += handlers

        # Sort handlers by priority
        for source, event_data in event_handlers.items():
            for event_code, handlers in event_data.items():
                handlers.sort(key=lambda h: h.priority)

        # optimization: memoize result on cls, it will not be recomputed
        cls._generic_system_event_handler_full_data = event_handlers
        return event_handlers

    def _generic_system_event_handler__cleanup_caches(self):
        """ Clean up handler-related memoized computations
        """
        cls = type(self)

        # Cleanup memoized event handlers computations.
        cls._gse__handler__source_map = (
            GenericSystemEventHandlerMixin._gse__handler__source_map)
        cls._generic_system_event_handler_data = (
            GenericSystemEventHandlerMixin._generic_system_event_handler_data)
        cls._generic_system_event_handler_full_data = (
            GenericSystemEventHandlerMixin.
            _generic_system_event_handler_full_data)

    @api.model
    def _setup_complete(self):
        res = super()._setup_complete()

        # Clean up cached info about registered event handlers when new model
        # initialized.
        self._generic_system_event_handler__cleanup_caches()

        return res

    def _auto_init(self):
        # Here, we use this method to automatically register
        # mapping interface->implementation for cases when implementation
        # is event handler and interface is event source.
        # For this case, we have to use special path.
        # Also, because this mapping is computed automaticall, there is no
        # need to define it manually in XML
        res = super()._auto_init()

        if self._abstract:
            return res

        @self.pool.post_init
        def update_delegation_handlers_mapping():
            """ Do actual update of mappings
            """
            # Check if current module implements some interfaces
            is_interface_implementation = getattr(
                self, '_generic_mixin_delegation__get_interfaces_info', False)
            if not is_interface_implementation:
                # If this model does not implemen any interfaces,
                # then we could safely skip it.
                return

            interface_map = (
                self._generic_mixin_delegation__get_interfaces_info())
            for interface_model in interface_map.values():
                # For each interface implemented by this model, we have
                # to create handler mapping that could allow us to handle
                # events triggered by interface on this model

                # Here we test if interface model is event source.
                # The easiest way to check this, is to check if there is
                # method _generic_system_event_source__register_handler_map
                # present in model, that is used to update handler mapping
                # for that source.
                if not hasattr(
                        self.env[interface_model],
                        '_generic_system_event_source__register_handler_map'):
                    # This interface is not event source.
                    # Thus skip it...
                    continue

                # Update source->handler mapping for this inteface and current
                # model.
                self.env[
                    interface_model
                ]._generic_system_event_source__register_handler_map(
                    handler_model=self._name,
                    path='delegation:interface-to-implementation')

        return res

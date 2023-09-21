import inspect
import functools
import collections
import logging

from odoo import models, api

from ..tools.event_handler import (
    EventHandler,
    is_event_handler,
)
from ..tools.event_handler_path import EventHandlerPath

_logger = logging.getLogger(__name__)


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

            :returns dict: mapping {'event.source.model': EventHandlerPath}
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
                        target_path = EventHandlerPath(
                            source_model=source,
                            target_model=source,
                            target_path='self')
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
                            event_code=event_code,
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
        # Also, because this mapping is computed automatically, there is no
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
                # If this model does not implement any interfaces,
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

            # TODO: add ability to automatically generate handler map
            #       for standard many2one fields that point to event sources

        return res

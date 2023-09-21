import logging

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
            By default, is set to 'self' which means same model decorated
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

        Contains all necessary info to run event handler.

        :param str event_code: Code of the event type to catch.
        :param str target_method: Method to call to handle event.
        :param EventHandlerPath target_path: path from source model to
             target model.
    """
    def __init__(self, event_code, target_method,
                 target_path, extra_info=None):
        self._path = target_path
        self._event_code = event_code
        self._target_method = target_method
        self._extra_info = extra_info

        # TODO: Add validation

    def __str__(self):
        return "Handler %s: %s -> %s: %s" % (
            self._path.source_model, self._event_code,
            self._path.target_model, self._target_method
        )

    def __repr__(self):
        return str(self)

    @property
    def path(self):
        return self._path

    @property
    def priority(self):
        """ Priority of this event handler.
            Used to determine in what order event handlers for same event
            have to be run.
            By default, priority is set to 40
        """
        if self._extra_info.get('priority', None) is not None:
            return self._extra_info['priority']
        return DEFAULT_PRIORITY

    def handle(self, source_record, event):
        """ Run this handler for specified source_record and event

            :param source_record: RecordSet that contains single record of
                event source model, that triggered event.
            :param event: RecordSet that contains single event that have
                to be handled by this handler
        """
        for target in self._path.find_targets(source_record):
            method = getattr(target, self._target_method)
            method(event)

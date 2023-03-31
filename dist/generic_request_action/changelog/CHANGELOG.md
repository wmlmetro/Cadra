# Changelog

## Version 4.2.0

Added functionality that allows you to configure the automatic removal from the followers at the request of a previosly assigned user.
(Request FR2211959)


## Version 4.1.0

Apply correct domain to event types allowed to select on action.
Before this change, there was ability to select event types that
are not related to request, and thus they were not working.


## Version 4.0.0

Migrated to use Generic System Events.


## Version 3.11.0

Added new action type Validate, that allows to validate request on some event
and raise error if request is not valid.


## Version 3.6.0

Added ability to change *Kanban State* of request via automated actions


## Version 3.5.0

Added filters Global, Type Specific and Route Specific to
Global Action menu for see type-specifications.


## Version 3.4.0

Merged `generic_request_action_condition` module.
Now all actions could be run conditionally.


## Version 3.1.0

Refactored to be able to provide `event` instance for jinja2 templates.
Pass Request Event everywhere through action logic.


## Version 3.0.0

Added ability to create global request actions


## Version 2.3.0

Added assign type Field for action type Activity.
This allows to assign mail activities (created by event actions)
to assignee of request or to creator of request.


## Version 2.1.0

Added support for [jinja2](http://jinja.pocoo.org/) templating



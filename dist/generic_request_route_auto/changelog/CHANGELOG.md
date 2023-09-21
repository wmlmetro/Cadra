# Changelog

## Version 3.5.0

Fixed access right issue, when user who triggered event does not have access to request that handles the event.
This happens for example, when some user that does not have access to request, changes stage of project task related to request.
Related to Q2305561


## Version 3.1.0

Apply correct domain to event types allowed to select on route trigger.
Before this change, there was ability to select event types that
are not related to request, and thus they were not working.


## Version 3.0.0

Migrated to use Generic System Event


## Version 2.3.0

Improved UI/UX for Request Route Triggers


## Version 2.0.0

- Integration addon `generic_request_route_auto_project` and
  `generic_request_route_auto_subrequest` removed.
- All existing triggers migrated to use request events instead.


## Version 1.6.0

Move *Trigger Events* stat-button to *Technical* page on request form view


## Version 1.3.0

- Added ability to bind route triggers to request events
- Removed trigger type 'Auto: On Create'.
  Request events could be used for this case



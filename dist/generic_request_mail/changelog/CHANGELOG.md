# Changelog

## Version 1.12.0

Added optional ability to attach incoming mail 
to existing requests by its name, mentioned in mail subject.


## Version 1.10.0

Added ability to validate incoming messages via conditions.
This could be used as some kind of black or white list, to prevent creating unwanted requests.


## Version 1.1.0

Added global setting to set default Mail Source for all requests.
This allows to use one mail address for all communications within all requests.


## Version 1.0.0

Added new request event types:
- New Mail Activity
- Mail Activity Done
- Mail Activity Delete
- Mail Activity Changed


## Version 0.8.0

Added ability to create requests for all emails not hanled
in standard way via fetchmail servers.
There was added option that allows to select request creation template
to be used to create request if email not handled by aliases or
other standard ways.


## Version 0.6.0

`generic_request_mail_service` and `generic_request_mail_tag` merged into core.


## Version 0.3.9

Added request event types: *Mail Comment* and *Mail Note*.


## Version 0.3.6

Added ability to edit *Canned Responses* from *Requests / Settings* menu


## Version 0.3.0

- Added kanban view for Mail Sources
- Show Mail Source on request form (see tab Other)
- Added demo-data for Mail Sources



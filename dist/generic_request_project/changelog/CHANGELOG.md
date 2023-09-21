# Changelog

## Version 3.11.0

- Use correct action to open Project Tasks from Request.
This is needed to be compatible with Odoo Enterprise
(be able to use gantt view for task related to requests)
Implemented within request Q2303536.


## Version 3.5.0

- Added fields `Request Service`, `Request Category`, `Request Type` on Task page *Other*
- Added submenu *Tasks* in *Requests* menu for tasks, related to requests


## Version 3.4.0

Module `generic_request_project_timesheet` was merged into the `generic_request_project`


## Version 2.0.0

- Added field *Project* to *Request* model.
- Added new request event *Project Changed* that could be handled by automated actions.


## Version 1.8.0

- Added 'use_subtasks' field to request.type (default=False)
- Hide statbutton 'Tasks' if field use_subtasks = False


## Version 1.2.0

- Add request event category Project Task Events
- Added new request event types:
    - Task stage changed
    - Task closed
    - All tasks closed


## Version 1.0.2

Use separate buttons to create task and view related tasks on request form


## Version 1.0.0

Changed *Task <-> Request* relation from *many2many* to *many2one*.

**This is backward incompatible change**

Data is automatically migrated, but in case when single task have
multiple related requests then only first request will be saved.
Old data kept unchanged, but hidden from UI and will be removed
in one of next versions

---

Improved UI: added `request_id` field to search view and form view




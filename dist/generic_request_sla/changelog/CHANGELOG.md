# Changelog

## Version 2.1.0

Added support for *SLA Compute Type: Conditional*,
that allows to choose what *SLA Control Line* have to be used
to compute SLA for request via generic conditions.


## Version 1.14.0

- Added ability to specify Request Channels for different SLA


## Version 1.13.0

Added `fa-search-plus` link on SLA Control Line on request,
that allows to easily find how this SLA Control Line computed its
total time via SLA Log lines.


## Version 1.12.0

Update SLA control lines before other `post_write` methods calles.
This neede to recompute SLA before request event's triggered.


## Version 1.9.0

- Added new public method ```get_sla_control_by_code``` on
  ```request.request``` model, that could be used to obtain instance of
  ```request.sla.control``` by its code.
  This could be used in emails, if you need to show warn/limit time for
  specific SLA rule.
- Improved UI/UX of *SLA Rule Type*: Show there list of SLA rules of this type.
  Thus, now it is possible to edit SLA rules from SLA Rule Type forms too.
- During adding SLA Rule, when SLA Rule type selected, the SLA Rule's name and
  code will be updated automatically.


## Version 1.5.0

Added new option for computation of SLA on request.
Before this change, the SLA state and SLA dates on request were computed based on
so called *Main SLA rule* that was defined on *Request Type* level.
Now, there new option *SLA Compute Type* added on *Request Type* form view,
that could be one of (*Main SLA Rule*, *Least Date Worst Status*).
In case when *Main SLA Rule* selected (the default one), everything will go old way.
In case when *Least Date Worst Status* selected, new logic will be applies:
    - Worst SLA status of all SLA Control lines will be set on request
    - The minimal SLA dates will be set on request.


## Version 1.1.0

Automatically increase sequence for next SLA rule created.
This prevents unexpected change of Main SLA rule on request.


## Version 1.0.0

Now SLA rule can track `kanban_state` changes too.
For example, now it is possible to track time only for cases when
`kanban_state` is *Ready* or *In Progress*


## Version 0.14.0

- Added ability to specify different Working Time (Calendar) for different SLA rules and rule lines
- Added demo data to demonstrate such complex configuration
- Bigfix, recompute SLA when category changes (because there may be rule lines that depend on request category)


## Version 0.11.0

Added graph view for SLA Control lines


## Version 0.8.4

- Add integration with [web_tree_dynamic_colored_field](https://github.com/OCA/web/tree/11.0/web_tree_dynamic_colored_field)
  If this module is installed, SLA state field will be colored on tree view



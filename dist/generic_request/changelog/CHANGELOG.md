# Changelog

## Version 4.7.0

- Introducing a new feature: Requests now supports using of Service Groups in web interface.
- This addition allows users to conveniently organize requests by service groups using filter and grouping.

This option is configurable on Request Settings level.


## Version 4.2.0

Added ability to use Datetime format for Deadline field.
This option is configurable on Request Type level.


## Version 4.0.0

This release changes the way of configuration of relations between
services, categories and types of request.
In previous versions, it was required to configure these relations in few different places:

- *request type - request category* was configurable from both sides (type and category), but not from service.
- *request type - service* was configurable from both sides (type and service), but not from category.
- *request category - service* was configurable from both sides (category and service), but not from type.

Thus, it was difficult to understand what service is related to what type and categories.
With this version, we introduce new entity *Request Classifier*, that
represents triple relation (service, category, type) in single row.

Starting from this version, the Classifiers table is the only place to set up
relations between services, categories and type. This way, it will be possible
to look at all allowed combinations of service, category and type in single place.
Also, all classifiers related to specific request type will be displayed,
on request type's form view.

This update includes automatic migration, so all data from previous relations,
have to be automatically migrated during module update.

But, ***it is recommended to take backup of your database before applying this update***.


## Version 3.33.0

Added ability to make description field required in timelog for certain timesheet activities.


## Version 3.32.0

Added a diagram view feature to visualize the request workflow.


## Version 3.17.0

Fixed count of opened/closed author related requests on request form.
Now displays the valid number of author requests regardless of user rights.
Implemented within request BUG231020.


## Version 3.15.0

Added few warnings to wizard that pops-up when user stop tracking time.
- In case when amount to be logged is between 8 and 12 hour,
  the yellow warning will be shown, that asks user to check if entered amount is correct.
- In case when amount to be logged is greater than 12 hours,
  then danger (red) warning will be shown, that asks user to double-check entered amount.
- When user starts work on new request, but have unfinished work
  (time tracking started, but not completed) on other request,
  then warning will be shown, that asks user to carefully review info in wizard,
  noting, that this is wizard related to unfinished request.

This should help to reduce amount if incorrectly logged time.


## Version 3.3.0

Add response attachment files when closing requests.


## Version 3.0.0

- Merged services into the core
- Services in requests are now optional and could be enabled/disabled in settings.


## Version 2.19.0

- Added ability to search timesheet reports by:
  - Request Stage Type
  - Request Channel
  - Request Partner
  - Activity
- Added new filters to timesheet reports:
  - Request Closed
  - Request Open
- Added ability to group timesheet reports by:
  - Request Stage Type
  - Request Stage
  - Request Channel


## Version 2.14.0

- Added filter "Closed Today"


## Version 2.12.0

***BUG220980***
- Fixed incorrect behavior of filters related to time


## Version 2.10.0

Added new `company_id` field to request.
Currently, no access rules added for this field,
but this change will be starting point for
introducing multi-company support for requests.

The provided migration will automatically to automatically set company_id
based on following rules:
1. Try to get company for request's website
2. If not found get company from user who created the request.

If `company_id` field was added to request by other third-party module,
then it will not be changed.


## Version 2.6.0

Added functionality that allows you to configure the automatic removal from the followers at the request of a previosly assigned user.
(Request FR2211959)


## Version 2.5.0

Fixed bug with incorrect handling of record-created event actions.


## Version 2.4.0

Added support for saving positions in diagram view


## Version 2.3.0

***BUG220963***
Fix bug when request assigned on inactive channels


## Version 2.2.0

- Change default order of requests:
    - Before, requests were ordered only by `date_created DESC`
    - After, requests will be ordered by `priority DESC, date_created DESC`
    - This, fixes regression introduces in 1.30.0 version (when priorities were merged to the core)
- Improve UI, selection of related types and services on category form now moved to separate pages.
  This way, it is much easier to configure systems with large amount of services and categories.


## Version 2.0.0

Start using Generic System Events under the hood.

**Do not forget to take backup before updating.**


## Version 1.187.0

Changed access restrictions.
Now in order to have access to Assign/Reassign and Change Parent Request the user must belong to `Request User` group.


## Version 1.186.0

Added tracking visibility when changing `deadline` field


## Version 1.185.0

Added new *Internal Notes* page on request form.
There team can add some internal notes related to request,
that will not be displayed on website for customer and
that will not be forgotten in chat history.


## Version 1.182.0

New request event categories:
- *Deadline Tomorrow*
- *Deadline Today*
- *Deadline Overdue*


## Version 1.181.0

***BUG220930***
Fixed bug, when contact related request count shown wrong after merging them


## Version 1.178.0

Refactored settings UI: moved mail-related settings to separate section


## Version 1.173.0

Fixed bug in event notifications, 
that happens when default notification settings set to False
and event messages of subrequest didn't  deliver to parent request.


## Version 1.171.0

***FR2207947***

Added notifications about subrequest events, 
such as ```created```, ```assigned```, ```closed```, ```reopened```, in parent request.


## Version 1.170.0

Improved appearance of request tags on kanban view


## Version 1.167.0

Added settings menu for request mail templates


## Version 1.164.1

Added ability to show/hide columns in tree view


## Version 1.156.0

Added ability to search requests by following fields:
- author_id.phone
- author_id.mobile
- author_id.name
- partner_id.phone
- partner_id.mobile
- partner_id.name


## Version 1.153.0

Merge the generic_request_parent as module into the generic_request module


## Version 1.152.0

Merge the generic_request_reopen_as module into the generic_request module


## Version 1.151.0

Added ability to specify access groups for request category and request type.
Previously this functionality was available only in crnd_wsd module, but now
it will be available in the core module.


## Version 1.148.0

Changed status view in requests.
Now there is only the current status of request.


## Version 1.146.0

Added option in configuration to show/hide searchpanel on requests view


## Version 1.145.0

Changed 'Automatically create contacts for requests' option in the requests settings:
- now it allows to autocreate contact (if not exist) only for author of incoming message
 
Added options in the requests settings:
- availability to autocreate new contact (if not exist), mentioned in the CC header of incoming mail
- automatically subscribing the contacts, mentioned in the CC header on incoming mail


## Version 1.142.0

Refactored the UI for changing stages of request and closing request.
Now, instead of changing request stage via statusbar widget in right-top corner of the form,
there will be buttons present in view (left-top corner of ther form) that will be used to move request via route.
Also, the names of that buttons (and their styles) could be configured on route level.
And when the route is closing route, then automatically will be show closing wizard with pre-selected route.
This way, it have to be more user-friendly.


## Version 1.138.0

Added configuration option, that allows to select preferred view for requests: list or kanban.
Currently this works only for standard menu *Requests*


## Version 1.137.0

Added *searchpanel* to requests, thus now it is possible to easily filter requests by category, type, service, tags and stage type.


## Version 1.131.0

- Do not allow to create requests from emails that come from email addresses that are aliases (managed by odoo).
  This is needed to avoid possible infinite loops when two emails start sending autoreplies to each other.
- Starting from this version in *Email* field on request, only email address will be saved.
  The author name will be saved in *Author name* field.
  Previously, author name was saved in *Author name* field, but it also was
  present in *Email* field in format ```Author name <author@email.com>```.


## Version 1.126.0

Added I (info) button to author, partner, and user fields.
Click on this new button will shoe popover with additional info on partner/user,
that allows to easily and fast copy phone, email, or name of partner/author/user


## Version 1.120.0

Show open/closed requests stat for request's partner and author


## Version 1.114.0

- Add new request events (Request Archived / Request Unarchived).
- Add filters in search view.
- Add simplet tests.


## Version 1.112.0

- Add field `active` to model request.request.
- Add a group whose users are allowed to archive / unarchive requests.


## Version 1.111.0

#### Version 1.111.0
Added new request event types: 'author-changed' and 'partner-changed'.
 

## Version 1.103.0

Added global configuration, that allows to chooses if it is needed to suggest
Global CC as recipients of request


## Version 1.101.0

- Add `email_cc` data to suggested recipients.
- Add global option that allows to automatically create partners,
  if request created from incoming email, and author of email and cc of email
  are not present in odoo's contacts database


## Version 1.99.0

Add global setting that could be used to show/hide request statistics on kanban views of
request-related objects like Request Category, Request type, etc


## Version 1.89.0

Now requests created via xml-RPC or json RPC will get *API* channel automatically
(if not provided in creation parameters)


## Version 1.85.0

- Added new search filters for requests
    - Today
    - 24 hours
    - Week
    - Month
    - Year
- Added new group by filters for request's search view
    - Assignee
    - Is Closed
- Added request statistics (requests open/closed for today, 24h, week, etc) to
  following models:
    - Request Type
    - Request Category
    - Request Channel
    - Request Kind


## Version 1.84.0

Added *Requests* page to user form view, that is used to display request statistics for user.


## Version 1.83.0

Added button to generate default stages and route on request type that has no
request stages.


## Version 1.81.0

Added new request event types:
- Timetracking / Start Work
- Timetracking / Stop Work


## Version 1.72.0

Added new request stage type 'Progress'


## Version 1.70.0

Added new field Channel to request. The field could be used to determine source of request Website / Web / Mail / Other
Automatically set correct channels for requests created from Web and E-mail


## Version 1.68.0

Remove obsolete modules from settings page.
Obsolte modules are:
- `generic_request_action_condition`


## Version 1.67.0

Added *kanban_state* feature to requests.
Now it is possible to define additional Blocked or Ready states on request.
Also, changes of kanban state triggers event *Kanban State*


## Version 1.58.0

Merge with generic_request_timesheet module


## Version 1.56.0

Enable *create_edit* and *quick_create* features of *author* and *partner*
fields of request 


## Version 1.54.0

Added ability to assign multiple requests with a single operations.
Just select requests from list view and call context action *Assign*.


## Version 1.53.0

- Automatically move created stage to the end of list of stages.
  This is required to avoid case when new stage become first one and
  thus it become starting stage for requests.
- Better support for handling mails received from unknown contacts.
  In this case `email_from` will be saved on request
- Save `email_cc` on request (if first email contains `cc`)
- Automatically subscribe partners mentioned in ``CC`` header of incoming mail
- Implement partner suggestions for mailing for requests.
  Odoo will automatically suggest to subscribe partner and / or author of request
  if that is not following request yet


## Version 1.52.0

Use different colors for deadline icon, depending on its value.


## Version 1.47.0

Update form view of Request Type


## Version 1.46.0

Module `generic_request_tag` merged into `generic_request`


## Version 1.45.0

- Intoruced new field: *Deadline*
- Small improvements to UI
- Fixed regression, missing *Kind* field on request form view


## Version 1.44.0

Fix regression in detection of author when creator is specified directly,
but author is not specified.


## Version 1.41.0

Introduced *Request Creation Templates* feature,
that have to be used mostly by other modules to create requests with default values.


## Version 1.39.0

- Fixed bug when with incorrect display of images in request text,
  when request was created by email.
- Added `lessc` to external dependencies, to avoid confusion for users that
  have not installed `lessc` compiler. It become optional for 12.0+ installations.


## Version 1.37.0

Fix Readmore feature: update state when images (that are in request text) loaded


## Version 1.35.0

Implemented Readmore / Readless functionality for request text and request response



## Version 1.34.0

Added categories for request event types


## Version 1.32.0

- Change UI of request form view to be consistent with frontend and other places.
  This change allows to select category before request type on request creation.
- Move *Request Events* stat-buttons to separate *Technical* page


## Version 1.31.0

Added graph view for requests


## Version 1.30.0

Merge `generic_request_priority` into core (`generic_request`)


## Version 1.29.0

- Module `generic_request_kind` merged into `generic_request`
- Added demo request with long description and images
- [FIX] display of images in request body


## Version 1.28.0

- Added ability to add comment in assign wizard for request
- Added button *Assign to me* on request


## Version 1.24.0

Request name in title displayed as `h2` instead of `h1` as before


## Version 1.20.0

Add global settings:
- 'Automatically remove events older then',
- 'Event Live Time',
- 'Event Live Time Uom'


## Version 1.17.0

- Make it possible to change request category for already created request
- New request event *Category Changed*
- Show *Requests* stat-button on user's form


## Version 1.16.4

#### Version 1.16.4
Add security groups user_see_all_requests and user_write_all_requests and rules for this groups


## Version 1.16.2

#### Version 1.16.2
Added generic_request_survey to request settings list.


## Version 1.16.1

#### Version 1.16.1
Added dynamic_popover widget to description field on request tree view.


## Version 1.16.0

Added `active` field to Request Stage


## Version 1.15.6

More information in error messages


## Version 1.13.11

#### Version 1.13.11
Added the ability to include request and response texts to mail notifications.


## Version 1.13.5

#### Version 1.13.5
- Automatically subscribe request author to request



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

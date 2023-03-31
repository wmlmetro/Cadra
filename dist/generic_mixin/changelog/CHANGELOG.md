# Changelog

## Version 1.70.0

Added new function useful in migration, especially, mergin modules:
- `generic_mixin.tools.migration_utils.migrate_xmlids_to_module`
- `generic_mixin.tools.migration_utils.cleanup_module_data`


## Version 1.69.0

Delegation mixins now implement their own decorator `interface_proxy` that
could be used to mark methods of interface model,
that have to be proxied to implementation model.


## Version 1.67.0

Added new `generic_mixin.tools.xmlid` module, that contains utility functions
to manage xmlid. These functions are mostly useful for migration scripts
to manipulate xmlids.


## Version 1.63.0

Added new mixins:
- `generic.mixin.delegation.interface` - Implements Interface concept (inheritance via delegation)
- `generic.mixin.delegation.implementation` - Implements Interface Implementation concept (inheritance via delegation)


## Version 1.62.0

Added few new methods to `generic_mixin.tools.sql`:
- `xmlid_to_id(cr, xmlid)` that could be used to convert `xmlid` to ID of referenced object
- `unlink_view(cr, xmlid)` that could be used to remove view by xmlid. This could be helpful during migrations.


## Version 1.59.0

Added new context manager `generic_mixin.tests.common.FindNew`
that could be used to easily find new records
created during execution of with block.


## Version 1.57.0

Added new base class in tests.common - `WebTourCase` that could be used
to easily run js tours.


## Version 1.56.0

Added new mixin `generic.mixin.entity.lifecycle` that adds
`lifecycle_state` field and dates of `lifecycle_state` changes.
Also, this mixin added additional logic to prevent deletion of *active*
entities and control changes of lifecycle states.


## Version 1.44.0

Added ability to delay refresh view notifications,
and send some group of such notifications with a single call.
This could be used to improve performance in long-running operations that
produce a lot of updates.

To use this feature, you can use following example:

```python
with self.env['generic.mixin.refresh.view'].with_delay_refresh():
    # Do some long running operation with a lot of refresh view calls.
```

All notifications will be sent after `with` block completed.
Also, `with` blocks could be nested, and in this case,
all notofications will be sent after top-level with block completed.


## Version 1.39.0

`generic.mixin.uuid`: now if uuid is specified during object creation, it will not be regenerated, instead provided value will be used.


## Version 1.38.0

Added new function `generic_mixin.tools.sql.create_sql_view`,
that could be used to simplify creation of postgresql views.


## Version 1.36.0

Added new function `deactivate_records_for_model` in `tests.common` module.
This function could be used in tests to deactivate records created by
installed but not activated (yet) modules.


## Version 1.34.0

- Added `@pre_create` and `@post_create` decorators, that allow to run
  some method before or after creation of record.
  The syntax is same as for `@pre_write` and `@post_write` decorators.
  Also, it is possible to decorate same method with pair of `@pre_` or `@post_`
  decorators, to run some method after creation and after changes of some fields
  of record.
- `changes` argument provided to tracking handler, now use *namedtuples* to represent field changes.
  Now it is possible to easily access *new* or *old* value as attribute.
  So, instead of old version `new_val = changes['my_field'][1]` now you can use `new_val = changes['my_field'].new_val`


## Version 1.30.0

Added new mixin `generic.mixin.namesearch_by_fields`


## Version 1.22.0

Added new mixin `generic.mixin.uuid` that could be used to automatically
generate uuids for records in specific model


## Version 1.19.0

Added new context switch for `name_get` in mixin `generic.mixin.parent.names`,
that allows to use standard `name_get` implementation
if `_use_standart_name_get_` is set to `True` in context.


## Version 1.18.0

Now `tools.jinja.render_jinja_string` can receive custom jinja env.


## Version 1.17.0

Added new mixin `generic.mixin.name.by.sequence` that could be used to
automatically add `name` field to model and automatically generate name based on
specified sequence. Useful for cases, when you have to create custom model like Sale Order, etc.


## Version 1.15.0

Added new mixin `generic.mixin.refresh.view` that could be used to trigger
refresh of web client views via python


## Version 1.14.0

- Added new method to `generic.mixin.transaction.utils` - `_iter_in_transact`,
  thus it is possible to iterate over records and process each record in separate transaction.
- Added new function `generic_mixin.tools.jinja.render_jinja_string` that
  could be imported via `from odoo.addons.generic_mixin import render_jinja_string`.
  This function allows to render jinja template passed as a string.


## Version 1.13.0

Added new mixin `generic.mixin.get.action` that could be used for compatability
with 14.0 for cases, when python method have to return action read from xml
by xmlid.

Also added definition for variables *TEST_URL*, *HOST*, *PORT*
in `generic_mixin.tests.common` module. this is also for compatability
with 14.0, so, using this variables in 12.0+ could help to write code that
is easier to port to next odoo versions


## Version 1.12.0

Make `post_write` and `pre_write` decorators propagatable.
Now when you override same `post_write` method in different subclasses,
all dependency fields will be merged,
and same method will will be called on change of each field.

Additionally added `priority` param for `pre_write` and `post_write` handlers,
thus you can define the order handlers will be executred in.


## Version 1.9.0

Added new mixin `generic.mixin.data.updatable`, that provides new fields
that describes corresponding `ir.model.data` records


## Version 1.8.0

Changed `generic.mixin.name_with_code`: generate new code only if there is no code


## Version 1.7.0

Changed `generic.mixin.name_with_code`: generate new code only if record
is not saved yet


## Version 1.6.0

Added `pre_write` and `post_write` decorators.


## Version 1.4.0

Added mixin 'generic.mixin.transaction.utils'


## Version 1.3.0

Added mixins and utils for test-cases:
- hide_log_messages (decorator and contextmanager that allow to hide log msgs)
- ReduceLoggingMixin (reduce logging output)
- AccessRulesFixMixinST
- AccessRulesFixMixinMT


## Version 1.1.0

Added new mixin `generic.mixin.track.changes`



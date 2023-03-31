# Changelog

## Version 2.2.0

- Change `_rec_name` to `name` instead of `complete_name`,
  because it is already used as default way to compute `display_name` in
  `name_get` implementation.
- Added context switch `_use_standart_name_get_` to be able to use `name`
  as `display_name` if this switch is set to `True` in context.


## Version 2.0.0

Added wizard to manage tags on multiple objects.
This wizard available in *Actions* dropdown on objects list and form view



## Version 1.2.1

Removed `no_tag_id` field in favor of `search_no_tag_id`



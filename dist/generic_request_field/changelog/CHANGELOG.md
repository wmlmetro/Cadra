# Changelog

## Version 3.22.0

Fixed bug due to which the request user could not edit the request field value


## Version 3.21.0

**BUG220973** Added ability to use jinja2 templates for default values for request fields.


## Version 3.18.0

Show custom request fields on request close wizard, when reopening request.


## Version 3.15.0

- Added new field on request `request_field_values_json` that could be used to read/update request fields via json dict.
- **Possible backward incompatibility**. Fields validation moved to lower level. Before, request fields were validated only when edited via UI.
  But now, request fields will be validated on any create/save operation.
  This could cause some errors, when request with fields
  created programmatically without provided values for mandatory fields.
- Add support of copying field values on copy of request


## Version 2.10.0

Added ability to search by field values


## Version 2.5.0

Added ability to specify help text and placeholder for request fields


## Version 2.0.0

- Implemented widget to display requesst fields
- Added ability to specify number of columns for field in grid.



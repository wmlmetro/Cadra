- Added new field on request `request_field_values_json` that could be used to read/update request fields via json dict.
- **Possible backward incompatibility**. Fields validation moved to lower level. Before, request fields were validated only when edited via UI.
  But now, request fields will be validated on any create/save operation.
  This could cause some errors, when request with fields
  created programmatically without provided values for mandatory fields.
- Add support of copying field values on copy of request

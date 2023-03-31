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

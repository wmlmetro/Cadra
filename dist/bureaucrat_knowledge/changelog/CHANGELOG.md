# Changelog

## Version 0.29.0

- Added complex (computed) field 'code' to document
This field have to consist of three parts: category_code, document_type_code, 
  document_number

- Added field to document 'document_number'. 
As default values for already existing documents (or for new documents)
  we use sequence defined on document type. 
  Added generator for 'document_number'


## Version 0.28.0

Added document types as separate model.
Now it is possible to customize available document types.


## Version 0.27.0

Rename `document_type` field to `document_format`.
This is needed to introduce new document types as separate model.
For backward compatability there is `document_type` field
added as compute+inverse to automatically write values for document format


## Version 0.26.0

Added required codes to bureaucrat knowledge categories


## Version 0.23.0

Added 'sequence' field in document and category settings to set priority view.


## Version 0.13.0

Added support for different types of documents (currently HTML and PDF)


## Version 0.9.0

Added super flexible access rights management for knowledge base


## Version 0.4.0

- Display category contents on category form view:
    - Display direct subcategories as list (links)
    - Display related documents as list (links)
- Fix handling of content history
  (do not create new history record if contents are same)
- Changed menu layout - now *Categories* and *Documents* are direct childs
  of root app menu
- By default show only top-level categories in menu



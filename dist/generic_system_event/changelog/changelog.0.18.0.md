- Added new default events:
    - Record archived
    - Record unarchived
- Added minimal support of generic many2one fields in target path for event handler mapping.
  So, no it is possible to handle events on records specified by generic many2one field
  (res_model, res_id) on event source.
- Event Source Mixin now inherited from `generic.mixin.track.changes`.
  - Thus, all other models that inherit `generic.system.event.source.mixin`
    **must not** inherit from `generic.mixin.track.changes`, because of odoo limitation.
  - **Note, this is possible backward incompatible change, code that implements event source interface possibly have to be adapted to new version.**

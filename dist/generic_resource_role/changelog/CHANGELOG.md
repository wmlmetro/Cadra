# Changelog

## Version 2.30.0

- Show role fields on resource only for role manager (for especific resource) or for Resource Manager group
- Make resource_visibility editable only for role manager or resource manager


## Version 2.26.0

- Add the ability in the role manger wizard to change resource
  visibility for multiple resources


## Version 2.16.0

Now subroles could use `x2many` fields to automatically add roles on related resources.


## Version 2.10.0

On module install automatically create actions, that allows to open wizard
that allows to manage access rights on multiple resources


## Version 2.8.0

- Display active role links on resource's form view
- Add wizard to manage roles on multiple resources


## Version 2.7.0

[FIX] Do not forward context to stat-button actions to avoid conflicts


## Version 2.0.0

- Added support for sub-roles.
  Sub-roles allows to automatically add role-links to related resources when
  role is added to resource.
- Added group *Generic Resouce: Manage Roles*
- New role field: 'Can Manage Roles'


## Version 1.5.0

Resource-visibility field moved to `generic_resource` addon



## Version 1.4.0

Refactored access rigths internal logic.
Should not have any visible changes.


## Version 1.3.2

#### Version 1.3.2

- Removed sql constraint 'unique_role_resource_partner' from resource_role_link


## Version 1.3.0

#### Version 1.3.0

- Added `resource_visibility`: `public` to make resource visible for public users
- Added `can_unlink` param on *Resource Role* object.



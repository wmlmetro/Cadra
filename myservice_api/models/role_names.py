# -*- coding: utf-8 -*-
"""The one place a role's published name is chosen rather than read.

Handoff 44 §3. Until then the alias below lived in the controller
(`v1_users._PUBLISHED_NAMES`), so `/users` and `/roles` said *System
Administrator* while the guard in `access_guard.py` — a model, which never
imported the controller's table — refused with Odoo's own name for the same
group, *Role / Administrator*. One group, two names, in one response stream
(report 42 §F.5). The table is here now, beside the models that say the name,
and every place that names a group asks it first:

  * `/users`, `/users/<id>` and `/roles` (`controllers/v1_users.py`)
  * the guard's refusals (`access_guard.py`)
  * the access-change record's `group_name` snapshot (`access_change.py`)
  * the access report's roster membership (`audit_access.py`)

Every other group keeps the name each of those places already used — this
module does not rename anything it does not list. A group that needs a name a
person would recognise gets a row here, and only here.

Odoo 19's own name for `base.group_system` is *Role / Administrator* (15
called it *Settings*, `full_name` *Administration / Settings*). Neither says
what the role is: it is the omnipotent one, able to execute arbitrary server
actions, and NRS should read that from its name.
"""

#: xmlid → the name published for it, everywhere.
PUBLISHED_ROLE_NAMES = {
    "base.group_system": "System Administrator",
}


def role_alias(group):
    """The published name chosen for `group`, or None when its own stands.

    `group` is a `res.groups` record (one, or empty). Resolved through
    `env.ref` per alias rather than `get_external_id()`, so it costs one
    cached lookup per row of the table and reads no `ir.model.data` for the
    groups the table does not name.
    """
    if not group:
        return None
    env = group.env
    for xmlid, name in PUBLISHED_ROLE_NAMES.items():
        aliased = env.ref(xmlid, raise_if_not_found=False)
        if aliased and aliased.id == group.id:
            return name
    return None

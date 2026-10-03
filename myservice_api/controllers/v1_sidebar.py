"""
Cadra API v1 — what this tenant's sidebar shows (handoff 48).

**This is presentation, not permission, and every response says so.**
Switching an item off stops the app drawing it on this tenant. It does not
stop anybody opening the page by its address, and no API route reads these
settings: the server answers exactly as it did. What a person may do is
decided by their role (`GROUP_SCOPES`); whether a tenant has a module at all
is decided by installing it. An administrator who switched Fleet off and
believed Fleet was now secured would have been misled by an instrument that
appears to measure something it does not — the defect this programme keeps
finding — so the statement is in the payload, not only on the screen.

**Two axes, kept apart.** The app draws an item when the TENANT has it on
(here) AND the PERSON's scopes open it (`lib/navigation.ts`, handoff 46).
Neither is consulted by the other.

## The identifier

Each item and group is keyed by a literal declared once, in `SIDEBAR_GROUPS`
below and beside the item in `lib/navigation.ts` — not its label, not its
path, not its scope. A label is renamed for wording, a path for routing and a
scope for the role model (handoff 47 is about to change several), and any of
those, used as the key, would silently switch an item back on the day it
changed. The key changes only when somebody edits the key, and
`tests/test_sidebar_catalog.py` fails if a key that was ever published leaves
this table without being moved to `SIDEBAR_RETIRED`, and if the app's table
and this one disagree.

## Storage, and why one parameter per switch

`ir.config_parameter`, one row per switch: `cadra.sidebar.item.<key>` and
`cadra.sidebar.group.<key>`, value `on` or `off`. **Absent means on**, so no
tenant loses anything the day this ships and an item added later appears
rather than hiding until somebody notices. One row per switch, rather than
one row holding a list, because the configuration-change report
(`/reports/configuration-changes`, `models/audit_configuration.py`) can only
say who LAST wrote a row: with a list, switching Fleet off and then Staff Bus
off would leave one row naming the second person as the author of both.
Switching an item back on writes `on` and never deletes the row, because a
deleted parameter leaves no tombstone in that report.

## Groups

A group's switch is a master switch: an item is shown when its own switch is
on AND its group's is on. Switching a group off hides every item in it
without touching their own switches, so switching it back on restores
exactly what was there before. That is the rule a person can predict from
the screen — the alternative ("an item switched on overrides its group")
makes a group switch that sometimes does nothing.

## The lockout

The Sidebar screen (`sidebar_settings`) is where this is changed, so neither
it nor the group it sits in can be switched off: with either off, nothing
could be switched back on from the app. Refused at the door, before anything
is written, AND ignored on read — a row put there by the back office or a
shell does not hide it either. Nothing else is locked, because everything
else can be switched back on from that screen while it is drawn.
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    SCOPE_ADMIN,
    err,
    get_params,
    refuse_unwritable,
)
from .v1 import cadra_route

#: Group key → its item keys, in sidebar order. Keep in step with
#: `ALL_NAV_GROUPS` in `Frontend/.../src/lib/navigation.ts`; the static guard
#: compares the two.
SIDEBAR_GROUPS = (
    ("dashboards", ("facility_command_center", "fleet_command",
                    "it_assets_command")),
    ("asset_register", ("asset_dashboard", "all_assets", "approvals",
                        "new_asset")),
    ("operations", ("locations", "new_location")),
    ("hr_staff", ("employees", "sap_sync", "bulk_import")),
    ("fleet_transport", ("fleet",)),
    ("reports", ("fleet_roster", "asset_inventory", "maintenance_readiness",
                 "location_coverage", "tag_adoption", "depreciation_report")),
    ("settings", ("asset_categories", "branding", "depreciation_settings",
                  "sidebar_settings")),
    ("audit", ("access_changes",)),
    ("administration", ("users",)),
    ("tools", ("barcode_station",)),
)

#: Keys that were published and have since left the table. A retired key is
#: never reused: a tenant that switched the old item off still has the row,
#: and a new item taking the name would inherit it.
#:
#: `staff_bus` and `identity_clearance` left the sidebar in handoff 47 §1b:
#: both rendered sample data built into the app and asked the server
#: nothing, so with everything defaulting to on, every new client was shown
#: two screens of invented content about their own organisation. The routes
#: still serve by address; the clearance screen is owed to NRS for real
#: (docs/GO-LIVE.md) rather than dropped.
SIDEBAR_RETIRED = frozenset({"staff_bus", "identity_clearance"})

#: The screen this is changed from. Its group is locked with it.
LOCKED_ITEMS = frozenset({"sidebar_settings"})

PARAM_PREFIX = "cadra.sidebar."
ON, OFF = "on", "off"

STATEMENT = (
    "This decides what the sidebar shows on this tenant. It is not a "
    "permission: an item switched off can still be opened by its address, "
    "and the server answers exactly as it did. What a person may do is "
    "decided by their role. A tenant that must not have a module at all "
    "needs it uninstalled, not switched off here.")

LOCK_REASON = (
    "The Sidebar screen is where these switches are changed. With it, or the "
    "group it sits in, switched off, nothing could be switched back on from "
    "the app.")


def _group_of(item_key):
    for group, items in SIDEBAR_GROUPS:
        if item_key in items:
            return group
    return None


def locked_groups():
    return frozenset(_group_of(k) for k in LOCKED_ITEMS)


def _item_keys():
    return [k for _g, items in SIDEBAR_GROUPS for k in items]


def _group_keys():
    return [g for g, _items in SIDEBAR_GROUPS]


def _param(kind, key):
    return "%s%s.%s" % (PARAM_PREFIX, kind, key)


def _actor(user):
    return {"id": user.id, "name": user.name} if user else None


class CadraSidebarV1(http.Controller):

    def _rows(self):
        """`{param key: ir.config_parameter}` for every sidebar row stored.

        Read as records rather than through `get_param` because the screen
        shows who last changed each switch and when, and `get_param` returns
        the value alone.
        """
        params = request.env["ir.config_parameter"].sudo().search(
            [("key", "=like", PARAM_PREFIX + "%")])
        return {p.key: p for p in params}

    def _switch(self, rows, kind, key, locked):
        row = rows.get(_param(kind, key))
        stored = (row.value or "").strip().lower() if row else None
        return {
            "key": key,
            # Only the word `off` switches anything off; absent, `on` and a
            # value nobody recognises all leave it on — the default is the
            # safe side of a presentation setting, and a locked switch is on
            # whatever its row says.
            "enabled": locked or stored != OFF,
            "configured": row is not None,
            "locked": locked,
            "changed_by": _actor(row.write_uid) if row else None,
            "changed_at": row.write_date if row else None,
        }

    def _payload(self):
        rows = self._rows()
        lgroups = locked_groups()
        groups, hidden = [], []
        for gkey, items in SIDEBAR_GROUPS:
            group = self._switch(rows, "group", gkey, gkey in lgroups)
            group["items"] = []
            for ikey in items:
                item = self._switch(rows, "item", ikey, ikey in LOCKED_ITEMS)
                item["shown"] = group["enabled"] and item["enabled"]
                if not item["shown"]:
                    hidden.append(ikey)
                group["items"].append(item)
            groups.append(group)
        return {
            "statement": STATEMENT,
            "is_a_permission": False,
            "default_when_unset": True,
            "rule": ("An item is shown when its own switch and its group's "
                     "switch are both on. A group switched off hides every "
                     "item in it and leaves their own switches as they are."),
            "locked_reason": LOCK_REASON,
            "parameter_prefix": PARAM_PREFIX,
            "groups": groups,
            "hidden_items": hidden,
        }

    @cadra_route("/api/v1/settings/sidebar", method="GET",
                 summary="What this tenant's sidebar shows (presentation, "
                         "not permission)",
                 # Any signed-in caller: the app asks on every screen to draw
                 # the sidebar, for every role, and the answer is not
                 # sensitive — it says which menu items this organisation
                 # uses.
                 scopes=[],
                 response_schema={
                     "type": "object",
                     "properties": {
                         "statement": {"type": "string"},
                         "is_a_permission": {"type": "boolean",
                                             "enum": [False]},
                         "default_when_unset": {"type": "boolean"},
                         "rule": {"type": "string"},
                         "locked_reason": {"type": "string"},
                         "parameter_prefix": {"type": "string"},
                         "hidden_items": {"type": "array",
                                          "items": {"type": "string"}},
                         "groups": {"type": "array", "items": {
                             "type": "object",
                             "properties": {
                                 "key": {"type": "string"},
                                 "enabled": {"type": "boolean"},
                                 "configured": {"type": "boolean"},
                                 "locked": {"type": "boolean"},
                                 "changed_by": {"type": "object",
                                                "nullable": True},
                                 "changed_at": {"type": "string",
                                                "format": "date-time",
                                                "nullable": True},
                                 "items": {"type": "array", "items": {
                                     "type": "object",
                                     "properties": {
                                         "key": {"type": "string"},
                                         "enabled": {"type": "boolean"},
                                         "shown": {"type": "boolean"},
                                         "configured": {"type": "boolean"},
                                         "locked": {"type": "boolean"},
                                         "changed_by": {"type": "object",
                                                        "nullable": True},
                                         "changed_at": {
                                             "type": "string",
                                             "format": "date-time",
                                             "nullable": True},
                                     }}},
                             }}},
                     },
                 })
    def get_sidebar(self, **kwargs):
        return self._payload()

    @cadra_route("/api/v1/settings/sidebar", method="PATCH",
                 summary="Switch sidebar items or groups on or off for this "
                         "tenant (presentation, not permission)",
                 scopes=[SCOPE_ADMIN],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "items": {"type": "object",
                                   "additionalProperties": {"type": "boolean"},
                                   "description": "item key → shown"},
                         "groups": {"type": "object",
                                    "additionalProperties": {"type": "boolean"},
                                    "description": "group key → shown"},
                     },
                 },
                 request_example={"groups": {"fleet_transport": False},
                                  "items": {"fleet_command": False}})
    def patch_sidebar(self, **kwargs):
        """Every refusal before any write: an unknown body key, an unknown
        item or group, a value that is not a boolean, and the lockout."""
        body = get_params()
        writable = {"items", "groups"}
        rejected = [k for k in body if k not in writable]
        if rejected:
            return refuse_unwritable(rejected, writable)
        # `None` is absent; anything else that is not an object is refused
        # below, falsy or not — `"groups": false` beside a valid `items` was
        # dropped with a 200 until the verification pass found it.
        if not any(body.get(k) for k in writable) and not any(
                k in body and body[k] is not None
                and not isinstance(body[k], dict) for k in writable):
            return err(ERR_INVALID_REQUEST,
                       "Name at least one item or group to switch. Nothing "
                       "was written.",
                       details={"writable": sorted(writable)})

        known = {"items": _item_keys(), "groups": _group_keys()}
        changes = []
        for kind in ("items", "groups"):
            asked = body.get(kind)
            if asked is None:
                continue
            if not isinstance(asked, dict):
                return err(ERR_INVALID_REQUEST,
                           "`%s` must be an object of key → true/false. "
                           "Nothing was written." % kind,
                           details={kind: asked})
            unknown = sorted(k for k in asked if k not in known[kind])
            if unknown:
                return err(ERR_INVALID_REQUEST,
                           "Unknown %s: %s. Nothing was written."
                           % (kind[:-1], ", ".join(unknown)),
                           details={"unknown": unknown,
                                    "allowed_values": known[kind]})
            not_bool = sorted(k for k, v in asked.items()
                              if not isinstance(v, bool))
            if not_bool:
                return err(ERR_INVALID_REQUEST,
                           "Each switch is true (shown) or false (hidden); "
                           "%s is not. Nothing was written."
                           % ", ".join(not_bool),
                           details={"not_boolean": not_bool})
            for key, shown in asked.items():
                changes.append((kind[:-1], key, shown))

        lgroups = locked_groups()
        locked = sorted(
            "the %s `%s`" % (kind, key) for kind, key, shown in changes
            if not shown and (key in LOCKED_ITEMS if kind == "item"
                              else key in lgroups))
        if locked:
            return err(ERR_INVALID_REQUEST,
                       "%s cannot be switched off. %s Nothing was written."
                       % (" and ".join(locked).capitalize(), LOCK_REASON),
                       details={"locked_items": sorted(LOCKED_ITEMS),
                                "locked_groups": sorted(lgroups)})

        icp = request.env["ir.config_parameter"].sudo()
        rows = self._rows()
        for kind, key, shown in changes:
            name = _param(kind, key)
            # Switching on something nobody ever switched off changes
            # nothing, and writing a row for it would put a "change" in the
            # configuration report that changed nothing. Otherwise the word
            # is always written, never deleted: `set_param(key, False)`
            # deletes the row, and a deleted row leaves no tombstone.
            if shown and name not in rows:
                continue
            icp.set_param(name, ON if shown else OFF)

        return self._payload()

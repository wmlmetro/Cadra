"""A published name still answers to a field. Handoff 32 §A.

**Twice now a published key and the thing underneath it have stopped
agreeing, and both times nothing failed.**

  - A category's `depreciation_method` was published by the settings screen
    as `method`; the screen sent the one key the API refused, got a 200 and
    said "policy saved". Nobody could change a depreciation method from its
    own settings screen and nobody knew (handoff 30).
  - `request.request.location_id` became `generic_location_id` in the move
    to Odoo 19 and `v1_requests` went on asking for `location_id`. Every
    request raised through the API was saved without its location, the
    serializer published `location: null` whatever the request held, and
    `?location_id=` filtered nothing — for the life of the route (handoff
    31).

Both were found by accident, months apart, each after a rename nobody
reconciled. **There is no reason to believe there were exactly two**, and a
sweep done once is a fact about one afternoon. This is the sweep kept.

It watches the two halves, which fail differently:

**The write side** — a key we accept that lands on a field the model does
not have. Since handoff 31 that is a loud `400` at runtime, so this test is
not what catches it first; what it catches is the day a rename lands, before
a caller does.

**The read side** — a serializer publishing a key off a field renamed
underneath it. A bare `r.whatever` raises `AttributeError` and is loud, so
the quiet ones are exactly the DEFENSIVE spellings: `"x" in rec._fields`,
`getattr(rec, "x", None)`, `hasattr(rec, "x")`. Each of those was written to
mean *this module may not be installed* and each reads identically to *this
field has been renamed and we now publish null for ever*. `serialize_request`
had four of them, and the one that had gone bad was invisible among them.

**Both halves are driven by something that cannot miss.** The routes come
from the routing attribute Odoo puts on every routed method, on every module
found by LISTING the controllers directory — not from `_ROUTE_REGISTRY`,
which the nine pre-envelope routes never joined, and not from a search for
allow-lists, which `POST /home/quick-submit` does not have; that is why the
search that found handoff 31's eleven routes could see neither. The guarded
reads come from parsing the same directory. A route or a guarded read these
tables do not name FAILS, rather than being skipped.

**The first draft of this file failed its own rule twice**, and both were
found by somebody attacking it rather than reading it. Its module list was a
hand-written dict of ten, so a NEW controller file would have had its reads
parsed and its routes missed entirely — a maintained list beside a
mechanical one, in the file written against exactly that. And a route
declaring no `methods` was read as GET, when Odoo accepts every method on
one; such a route is now reported as `ANY` and must be classified.

**Where it stops.** The census is `/api/v1/*` on this addon's controllers.
It does not see the first-party routes outside that prefix
(`docs/api/EXTERNAL-SURFACES.md`), and in particular not the public twin
`POST /api/myservice/quick-submit` — which is the same Python function as
the v1 route and declares its accepted keys in the addon that owns the form,
so the two are checked here THROUGH that shared declaration rather than by
being routes. A published name added to a surface outside `/api/v1` is not
watched by anything here.

Run with:
    odoo -d <db> -u myservice_api --test-enable \\
         --test-tags /myservice_api --stop-after-init
"""
import ast
import importlib
import inspect
import os

from odoo import http
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..controllers import v1

_CONTROLLER_DIR = os.path.dirname(inspect.getfile(v1))


def _controller_modules():
    """Every module in `myservice_api/controllers/`, found by LISTING THE
    DIRECTORY.

    It was a hand-written dict of ten until the verification pass went
    looking for a way past this file. A new controller file would have been
    parsed by the read side, which walks the directory, and **missed
    entirely by the route census**, which walked the dict — so a route that
    creates records from an unfiltered body could be added and all twelve
    tests would still pass. A census with a list somebody maintains beside a
    census that reads the tree is the defect this file is about, written
    into the file itself.

    Both halves read the same directory now.
    """
    package = v1.__name__.rsplit(".", 1)[0]
    out = {}
    for name in sorted(os.listdir(_CONTROLLER_DIR)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        stem = name[:-3]
        out[stem] = importlib.import_module("%s.%s" % (package, stem))
    return out


# ─── the write side ──────────────────────────────────────────────────

#: Every route that can carry a body, and what its body keys ARE.
#:
#: `model` — the model whose field names the keys are, so this test can ask
#: the registry whether each one still resolves.
#: `accepted` — where the route's gate is declared, as
#: (module, attribute) or (module, class, attribute). Read from the gate
#: itself, never copied here: a copy is the defect this file exists to catch.
#: `reason` — for a route whose body names no model's fields, why.
#:
#: A route missing from this table fails `test_every_route_that_takes_a_body
#: _is_classified`. That is the point: the two doors handoff 31 missed were
#: missed because the search asked which routes DECLARE an allow-list, and
#: these two create records without declaring one.
_BODY_ROUTES = {
    # ── resource routes: the body is a dict of the model's fields ──
    ("POST", "/api/v1/assets"):
        ("nrs.asset", ("v1_assets", "_WRITABLE_FIELDS"), None),
    ("PATCH", "/api/v1/assets/<int:id>"):
        ("nrs.asset", ("v1_assets", "_WRITABLE_FIELDS"), None),
    ("POST", "/api/v1/requests"):
        ("request.request", ("v1_requests", "_WRITABLE_FIELDS"), None),
    ("PATCH", "/api/v1/requests/<int:id>"):
        ("request.request", ("v1_requests", "_WRITABLE_FIELDS"), None),
    ("POST", "/api/v1/locations"):
        ("generic.location", ("v1_locations", "_WRITABLE_FIELDS"), None),
    ("PATCH", "/api/v1/locations/<int:id>"):
        ("generic.location", ("v1_locations", "_WRITABLE_FIELDS"), None),
    ("POST", "/api/v1/asset-categories"):
        ("nrs.asset.category", ("v1_settings", "_CATEGORY_WRITABLE"), None),
    ("PATCH", "/api/v1/asset-categories/<int:id>"):
        ("nrs.asset.category", ("v1_settings", "_CATEGORY_WRITABLE"), None),

    # ── the twelfth and thirteenth doors: routes that CREATE a record
    #    from a body without declaring an allow-list, closed in handoff 32 §B
    ("POST", "/api/v1/home/quick-submit"):
        ("request.request",
         ("odoo.addons.myservice_website_theme.controllers.api",
          "QUICK_SUBMIT_FIELDS"), None),
    ("POST", "/api/v1/integrations/sap/employee-sync"):
        ("hr.employee",
         ("odoo.addons.myservice_identity.models.sap_sync_log",
          "SAP_PAYLOAD_KEYS"), None),

    # ── routes whose body names no model's fields ──
    ("DELETE", "/api/v1/asset-categories/<int:id>"):
        (None, None, "no body"),
    ("POST", "/api/v1/settings/depreciation/recompute"):
        (None, None, "no body"),
    ("PATCH", "/api/v1/settings/branding"):
        (None, None,
         "writes `ir.config_parameter` rows, not fields of a record; the "
         "parameter names are in `CadraConfigV1._BRAND_PARAMS`. `name` and "
         "(handoff 45) `sender_email` write the main `res.company`'s "
         "`name` and `email`"),
    ("PATCH", "/api/v1/settings/depreciation"):
        (None, None,
         "writes `ir.config_parameter` rows, not fields of a record"),
    # Handoff 48. `items` / `groups` are maps of switch keys, validated
    # against `SIDEBAR_GROUPS` by the route itself.
    ("PATCH", "/api/v1/settings/sidebar"):
        (None, None,
         "writes `ir.config_parameter` rows (`cadra.sidebar.*`), not fields "
         "of a record; the keys are the catalog in `v1_sidebar.py`"),
    ("POST", "/api/v1/auth/token"):
        (None, None, "credentials"),
    ("POST", "/api/v1/auth/login"):
        (None, None, "credentials"),
    ("POST", "/api/v1/auth/refresh"):
        (None, None, "a refresh token"),
    ("POST", "/api/v1/auth/revoke"):
        (None, None, "a refresh token"),
    # Handoff 45: a letter's token redeemed in the app. Each refuses any key
    # it does not read (`v1_signup._*_KEYS`), and none names a field.
    ("POST", "/api/v1/auth/password-token/inspect"):
        (None, None, "a signup token"),
    ("POST", "/api/v1/auth/password-token/redeem"):
        (None, None, "a signup token and the password it sets"),
    ("POST", "/api/v1/auth/password-reset"):
        (None, None, "a login to send a reset letter to"),
    ("POST", "/api/v1/integrations/employees/import"):
        (None, None, "a multipart xlsx upload, not a JSON body"),
    ("POST", "/api/v1/barcode/generate"):
        (None, None, "a list of asset ids to print for"),
    ("POST", "/api/v1/integrations/workflow/callback"):
        (None, None,
         "an external engine's DECISION — `outcome`, `comment`, `reference` "
         "— applied by `myservice_workflow`; two of its keys do land on "
         "fields and are covered by the guarded reads below"),

    # ── action routes: the body is ARGUMENTS to an act, not fields ──
    #
    # Whether these should refuse a stray key as the resource routes do is
    # NOT ruled (`docs/GO-LIVE.md` §16.3 item 11). They are classified here
    # so that ruling is a change to this table rather than a hole in it.
    ("POST", "/api/v1/assets/<int:id>/approve-disposal"):
        (None, None, "action: no body keys, and it already refuses any"),
    ("POST", "/api/v1/assets/<int:id>/condemn"):
        (None, None, "action: `reason`, recorded on the event"),
    # Handoff 35. The three decisions on an approval request. Their bodies
    # carry at most a `reason` — WHO decided is taken from the bearer token
    # and a body naming it is refused 400, which is why none of them names a
    # model's fields.
    ("POST", "/api/v1/approvals/<int:id>/approve"):
        (None, None, "action: `reason`, recorded on the decision"),
    ("POST", "/api/v1/approvals/<int:id>/reject"):
        (None, None, "action: `reason`, REQUIRED and recorded"),
    ("POST", "/api/v1/approvals/<int:id>/withdraw"):
        (None, None, "action: `reason`, optional and recorded"),
    # Handoff 45: re-pointing a pending request at somebody else.
    ("POST", "/api/v1/approvals/<int:id>/renominate"):
        (None, None,
         "action: `approver_id` (a nomination checked by "
         "`_renomination_target_problem`) and `reason`, passed to "
         "`action_renominate`"),
    # Handoff 38. A tag replacement is the same two-person shape on
    # `nrs.asset.tag.label`: `reason` here is a SELECTION value (the model's
    # `replacement_reason`) rather than free text, `notes` is the free text,
    # and `approver_id` is a nomination resolved by `_resolve_approver` —
    # none of them is written as a field of the same name, which is why the
    # route is an action and not a resource.
    ("POST", "/api/v1/tags/<int:id>/request-replacement"):
        (None, None, "action: `reason` (a selection value), `notes` and "
                     "`approver_id`, passed to "
                     "`action_request_replacement`"),
    ("POST", "/api/v1/tags/<int:id>/approve-replacement"):
        (None, None, "action: `reason`, recorded as `decision_reason`"),
    ("POST", "/api/v1/tags/<int:id>/reject-replacement"):
        (None, None, "action: `reason`, REQUIRED and recorded as "
                     "`decision_reason`"),
    ("POST", "/api/v1/assets/<int:id>/mark-found"):
        (None, None, "action: `reason`, recorded on the event"),
    ("POST", "/api/v1/assets/<int:id>/mark-missing"):
        (None, None, "action: `reason`, recorded on the event"),
    ("POST", "/api/v1/assets/<int:id>/move"):
        (None, None, "action: `to_location_id` and `reason`"),
    ("POST", "/api/v1/assets/<int:id>/tag-affixed"):
        (None, None, "action: what was affixed, and by whom"),
    ("POST", "/api/v1/assets/<int:id>/transfer-custody"):
        (None, None, "action: `to_custodian_id` and `reason`"),
    ("POST", "/api/v1/assets/<int:id>/verify"):
        (None, None, "action: `notes`"),
    ("POST", "/api/v1/requests/<int:id>/assign"):
        (None, None, "action: the user to assign to"),
    ("POST", "/api/v1/requests/<int:id>/comment"):
        (None, None, "action: a message posted to the thread"),
    ("POST", "/api/v1/requests/<int:id>/transition"):
        (None, None, "action: the stage route to take"),
    # Handoff 42. The one writer of membership on the API. `roles` is the
    # FULL set of DIRECT role keys the account should hold, among
    # `v1_users.ROLE_KEYS`; each key is resolved to its `res.groups` record
    # and the set is written as ONE `(6, 0, ids)` on `res.users.group_ids`,
    # restricted to the vocabulary's groups so nothing outside it moves.
    # `dry_run` is a savepoint the route rolls back. Neither key is a field
    # of any model, and the body's gate is `v1_users.ROLE_CHANGE_BODY_KEYS`
    # (a stray key is `refuse_unwritable`'s 400). What may be WRITTEN is
    # decided on the model (`models/access_guard.py`), not in the route.
    ("POST", "/api/v1/users/<int:user_id>/roles"):
        (None, None, "action: `roles` (direct role keys, resolved to "
                     "groups and written as `group_ids`) and `dry_run`; "
                     "grantability is refused on the model"),
    # Handoff 43. Creating a person: `name` and `email` ARE `res.users`
    # fields (`email` is also written as `login`), `roles` is the same
    # vocabulary as the route above and `send_invitation` is an action.
    # Classified as an action rather than against the model because two of
    # its four keys are not fields and the row it answers with is
    # `_user_row`, which `tests/test_users.py` holds key by key; the body's
    # gate is `v1_users.USER_CREATE_BODY_KEYS`.
    ("POST", "/api/v1/users"):
        (None, None, "action: `name`, `email` (written as `login` too), "
                     "`roles` (as /users/<id>/roles) and `send_invitation`; "
                     "the groups are refused on the model, the letter is "
                     "`res.users._action_reset_password`"),
    ("POST", "/api/v1/users/<int:user_id>/invite"):
        (None, None, "action: no body key is accepted; re-sends the "
                     "invitation letter"),
    ("POST", "/api/v1/users/<int:user_id>/deactivate"):
        (None, None, "action: no body key is accepted; writes "
                     "`active = False`"),
    ("POST", "/api/v1/users/<int:user_id>/reactivate"):
        (None, None, "action: no body key is accepted; writes "
                     "`active = True`"),
}

#: A published key whose model field has a different name. **The published
#: key is the contract and translating it is the controller's job** — but a
#: translation nobody has written down is indistinguishable from a key that
#: is being dropped, which is exactly how `location_id` survived the whole
#: migration. Each entry is checked BOTH ways: the published name must NOT be
#: a field, and the field it names must exist.
_DECLARED_TRANSLATIONS = {
    ("request.request", "location_id"): "generic_location_id",
    ("request.request", "description"): "request_text",
}


def _translations():
    """The declared translations, plus SAP's own, READ FROM SAP'S OWN MAP.

    `SAP_FIELD_MAP` is the thing that does the translating, so copying its
    twelve pairs here would be a second copy of a rule — the failure this
    whole handoff series is named after. It is imported instead, which means
    a pair added to it is checked against `hr.employee` on the same day.
    """
    from odoo.addons.myservice_identity.models.sap_sync_log import (
        SAP_FIELD_MAP)
    out = dict(_DECLARED_TRANSLATIONS)
    out.update({("hr.employee", k): v for k, v in SAP_FIELD_MAP.items()})
    return out


#: A published key that IS a field and is deliberately translated onto a
#: different one anyway. Ordinarily that is the defect — it means the model
#: now has two ways to be written and the route picked one silently — so each
#: of these needs a reason, and the reason has to be that writing the
#: same-named field would write something else entirely.
_TRANSLATED_DESPITE_A_FIELD = {
    ("hr.employee", "email"):
        "`hr.employee.email` is a NON-STORED related to `user_id.email` — "
        "the linked Odoo user's login address, not the employee's. SAP's "
        "`email` is the employee's, so it goes to `work_email`; writing "
        "`email` would rewrite a user account, and for the employees who "
        "have no user account it would write nowhere at all",
    ("hr.employee", "phone"):
        "`hr.employee.phone` is a non-stored related to `user_id.phone`, "
        "for the same reason as `email` above",
}

#: A published key that is not a field of the route's model and is not meant
#: to be, with what the route does with it instead.
_NOT_A_FIELD = {
    ("request.request", "reporter_name"):
        "composed into `request_text`; there is no reporter field",
    ("request.request", "reporter_contact"):
        "resolved to a `res.partner` and stored as the author",
    # SAP's own spellings that `nrs.sap.sync.log` reads without mapping onto
    # a column of the same name. The twelve it DOES map arrive from
    # `SAP_FIELD_MAP` above rather than being listed here.
    ("hr.employee", "personIdExternal"):
        "a match key — identifies the row, is not stored under that name",
    ("hr.employee", "event"):
        "recorded on the sync log row, not on the employee",
    ("hr.employee", "displayName"):
        "used for `name` only when `firstName`/`lastName` are absent",
    ("hr.employee", "firstName"): "half of `name`",
    ("hr.employee", "lastName"): "half of `name`",
    ("hr.employee", "employmentStatus"):
        "mapped through `SAP_STATUS_MAP` onto `sap_status`",
    ("hr.employee", "previous_status"):
        "compared against, to decide whether anything changed; not stored",
    ("hr.employee", "locationName"):
        "a location looked up BY NAME, then stored as `sap_location_id`",
    ("hr.employee", "location"):
        "the fallback spelling of `locationName`",
}


# ─── the read side ───────────────────────────────────────────────────

#: Every DEFENSIVE field check in the controllers, and the model the record
#: it guards belongs to. Keyed by (file, function, variable, field).
#:
#: These are the quiet half. `"vehicle_id" in r._fields` was written to mean
#: *`myservice_fleet` may not be installed here*; it reads identically to
#: *this field has been renamed and we publish null now*, and only the
#: registry can tell the two apart. On a database carrying our modules the
#: field must exist — so this table turns every one of them from a shrug into
#: an assertion.
#:
#: A site the parser finds and this table does not name FAILS. `None` as the
#: model means the variable is not a record and the check is not about a
#: field — with the reason.
_GUARDED_READS = {
    ("v1_requests.py", "serialize_request", "r", "vehicle_id"):
        "request.request",
    ("v1_requests.py", "serialize_request", "r", "nrs_asset_id"):
        "request.request",
    ("v1_requests.py", "serialize_request", "r", "workflow_payment_ref"):
        "request.request",
    ("v1_requests.py", "serialize_request", "r", "workspace_ref"):
        "request.request",
    ("v1_requests.py", "_list_domain", "Req", "nrs_asset_id"):
        "request.request",
    # `for name in ("location_id", "generic_location_id")`. The names are not
    # literals at the point of the test, so no parser can check them from
    # here; `test_the_name_this_deployment_does_not_have_is_still_the_one
    # _missing` checks the pair by hand instead, in both directions, because
    # this helper is only correct while the OLD name is the absent one.
    ("v1_requests.py", "_location_field", "Req", "<names held in `name`>"):
        None,
    # The general translator: the name is whatever key the body carried, so
    # the set it can spell is `v1_requests._WRITABLE_FIELDS` and the write
    # side above already checks every member of it against the model.
    ("v1_requests.py", "_model_field", "Req", "<names held in `key`>"):
        None,
    ("v1_requests.py", "serialize_request", "e", "event_type_id"):
        "request.event",
    ("v1_requests.py", "serialize_request", "e", "user_id"):
        "request.event",
    ("v1_assets.py", "serialize_asset", "p", "name"):
        "nrs.asset.pm",
    ("v1_assets.py", "_ref", "rec", "name"):
        # `_ref(rec, name_field="name")`. The parser sees the DEFAULT; every
        # call site passes that default or nothing, so there is no dynamic
        # name here to drift. Three modules carry a copy of `_ref`.
        None,
    ("v1_identity.py", "_ref", "rec", "name"): None,
    # Handoff 35's fourth copy of the same three-line helper. Same reasoning
    # as `v1_assets._ref` above: the parser sees the DEFAULT `name_field`,
    # and every caller passes a record of a different model.
    ("v1_approvals.py", "_ref", "rec", "name"): None,
    ("v1_requests.py", "_ref", "rec", "name"): None,
    # `request` is werkzeug's, not a record: these read per-request state
    # the API puts there itself.
    ("utils.py", "_meta", "request", "cadra_request_id"): None,
    ("utils.py", "_new_request_id", "request", "cadra_request_id"): None,
    ("utils.py", "_set_request_user", "request", "update_env"): None,
    ("utils.py", "caller_holds", "request", "jwt_claims"): None,
    ("utils.py", "_request_is_frontend", "request", "jwt_claims"): None,
    ("utils.py", "_limit_claim", "request", "jwt_claims"): None,
    ("utils.py", "truncation_warning", "request", "cadra_truncation"): None,
    ("v1.py", "whoami", "request", "jwt_claims"): None,
    ("v1_meta.py", "meta_database", "request", "jwt_claims"): None,
}

#: The one published key that must NOT resolve — see `_location_field`.
_MUST_NOT_RESOLVE = {("request.request", "location_id")}


#: Every serializer, and the model of the record it reads. Its first
#: positional argument is the record. Completeness is checked: a function in
#: these controllers with `serialize` in its name and no entry here FAILS.
_SERIALIZERS = {
    ("v1_assets.py", "_serialize_depreciation"): "nrs.asset",
    ("v1_assets.py", "_serialize_tagging"): "nrs.asset",
    ("v1_assets.py", "_serialize_sap"): "nrs.asset",
    ("v1_assets.py", "_serialize_disposal"): "nrs.asset",
    ("v1_assets.py", "_serialize_warranty"): "nrs.asset",
    ("v1_assets.py", "_serialize_custody"): "nrs.asset.custody",
    ("v1_assets.py", "serialize_asset"): "nrs.asset",
    ("v1_requests.py", "serialize_request"): "request.request",
    # Handoff 35. NOTE the name collision with the line above: two functions
    # called `serialize_request` in two controllers, for two unrelated models
    # — a service-desk request and an approval request. This table is keyed
    # by (file, function) so it is unambiguous here, but it is the kind of
    # drift the last three defects in this codebase were made of, and the
    # next person to add a third should rename rather than add.
    ("v1_approvals.py", "serialize_request"): "nrs.asset.change.request",
    # Handoff 38. Reads `t.asset_id.asset_code` and `.serial_number` through
    # the Many2one as well; the parser sees only the attributes on `t`
    # itself, which is the record this names.
    ("v1_tags.py", "serialize_tag"): "nrs.asset.tag.label",
    ("v1_locations.py", "serialize_location"): "generic.location",
    ("v1_identity.py", "serialize_employee"): "hr.employee",
    ("v1_fleet.py", "serialize_vehicle"): "fleet.vehicle",
    ("v1_settings.py", "_serialize_category"): "nrs.asset.category",
}

#: A field a route accepts and no serializer reads back — so a caller can
#: write it and can never see what it wrote.
#:
#: **This is the depreciation-method bug from the other side.** A screen
#: reads an object, edits it and sends it back; the day the name it read
#: differs from the name the route accepts, the write is refused (since
#: handoff 31) or dropped (before it). The keys below are not that — they are
#: writable and not published at all — and each is here with the reason, so a
#: new one has to be argued for rather than noticed three years later.
_WRITE_ONLY = {
    ("nrs.asset", "salvage_rate"):
        "published as the derived amount `financial.depreciation."
        "salvage_value`, not as the rate; a caller can see the effect of "
        "what it sent but not the figure",
    ("nrs.asset", "verification_notes"):
        "published only in the response to `POST /assets/<id>/verify`, "
        "never on a GET of the asset",
    ("request.request", "generic_location_id"):
        "read through `_location_field(r)` at runtime, so no parser sees "
        "the name here; `GET /requests/<id>` publishes it as `location`",
    ("hr.employee", "mobile_phone"):
        "SAP sends `mobile` and the sync stores it; `serialize_employee` "
        "publishes `work_phone` and not this one, so an integration can "
        "set a mobile number and never read it back. Found by this test on "
        "the day the SAP route was given an allow-list (handoff 32 §A); "
        "publishing it would be additive and is not this handoff's",
}


class _GuardedReads(ast.NodeVisitor):
    """Every `"x" in <v>._fields`, `getattr(<v>, "x", …)` and
    `hasattr(<v>, "x")` in one controller, with the function it sits in."""

    def __init__(self):
        self.stack = []
        self.found = []          # (function, variable, field, lineno)

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _fn(self):
        return self.stack[-1] if self.stack else "<module>"

    def visit_Compare(self, node):
        if (len(node.ops) == 1 and isinstance(node.ops[0], ast.In)
                and isinstance(node.comparators[0], ast.Attribute)
                and node.comparators[0].attr == "_fields"
                and isinstance(node.comparators[0].value, ast.Name)):
            left = node.left
            if isinstance(left, ast.Constant) and isinstance(left.value, str):
                field = left.value
            elif isinstance(left, ast.Name):
                # `for name in (...): if name in Req._fields` — the shape
                # `_location_field` is written in, and the FIRST DRAFT OF
                # THIS TEST COULD NOT SEE IT. A parser that reads only
                # literals is blind to the one helper this whole file was
                # written about. Reported as its own kind so the table has
                # to name it and a person has to say what it can spell.
                field = "<names held in `%s`>" % left.id
            else:
                field = "<computed>"
            self.found.append((self._fn(), node.comparators[0].value.id,
                               field, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "hasattr")
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            self.found.append((self._fn(), node.args[0].id,
                               node.args[1].value, node.lineno))
        self.generic_visit(node)


def _default_named_args(tree):
    """`name_field="name"` in a signature — a field name reaching a record
    through a default rather than through the source of the call. `_ref` is
    the only one, in three copies, and every call site takes the default; a
    day when one does not is a published name nothing here can see."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.args.args:
            continue
        args = node.args
        pairs = list(zip(args.args[len(args.args) - len(args.defaults):],
                         args.defaults))
        for arg, default in pairs:
            if (arg.arg.endswith("_field")
                    and isinstance(default, ast.Constant)
                    and isinstance(default.value, str)):
                out.append((node.name, args.args[0].arg, default.value,
                            node.lineno))
    return out


class _RecordAttributes(ast.NodeVisitor):
    """Every `<var>.<attr>` in one function, by variable."""

    def __init__(self, target):
        self.target = target
        self.stack = []
        self.attrs = set()

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Attribute(self, node):
        if (self.stack and self.stack[0] == self.target
                and isinstance(node.value, ast.Name)):
            self.attrs.add((node.value.id, node.attr))
        self.generic_visit(node)


def _fields_read_by_serializers():
    """model → the set of field names its serializers read off the record.

    Static, because what is being watched for is a NAME going out of step
    with a field — which a run against one record cannot see.
    """
    read = {}
    seen = set()
    for name in sorted(os.listdir(_CONTROLLER_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(_CONTROLLER_DIR, name)) as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if "serialize" not in node.name:
                continue
            seen.add((name, node.name))
            model = _SERIALIZERS.get((name, node.name))
            if not model or not node.args.args:
                continue
            record = node.args.args[0].arg
            scan = _RecordAttributes(node.name)
            scan.visit(node)
            read.setdefault(model, set()).update(
                attr for var, attr in scan.attrs if var == record)
    return read, seen


def _scan_controllers():
    """(file, function, variable, field, lineno) for every guarded read."""
    rows = []
    for name in sorted(os.listdir(_CONTROLLER_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(_CONTROLLER_DIR, name)) as fh:
            tree = ast.parse(fh.read())
        scan = _GuardedReads()
        scan.visit(tree)
        for fn, var, field, line in scan.found + _default_named_args(tree):
            rows.append((name, fn, var, field, line))
    return rows


def _routes_with_a_body():
    """Every non-GET route on our controllers, read off the routing attribute
    Odoo stamps on the method — so a route cannot hide by declining a
    decorator of ours."""
    out = {}
    for stem, mod in _controller_modules().items():
        for obj in vars(mod).values():
            if not (inspect.isclass(obj) and issubclass(obj, http.Controller)
                    and obj is not http.Controller):
                continue
            for fname, fn in vars(obj).items():
                routing = (getattr(fn, "original_routing", None)
                           or getattr(fn, "routing", None))
                if not routing:
                    continue
                for path in routing.get("routes") or ():
                    if not path.startswith("/api/v1/"):
                        continue
                    # A route that declares no `methods` accepts ALL of them
                    # in Odoo, so it takes a body. Reading the absence as GET
                    # would let the next one be written outside this census —
                    # and the nine pre-envelope routes use bare `@http.route`,
                    # which is exactly where it would be written.
                    methods = routing.get("methods")
                    if not methods:
                        out[("ANY", path)] = "%s.%s" % (stem, fname)
                        continue
                    for method in methods:
                        if method != "GET":
                            out[(method, path)] = "%s.%s" % (stem, fname)
    return out


def _resolve(ref):
    """(module, attr…) → the declared set, read from the gate itself.

    The module is one of ours by short name, or any importable path — the two
    doors handoff 32 closed declare their accepted keys in the addon that
    owns the form, not in this one.
    """
    head, rest = ref[0], ref[1:]
    mods = _controller_modules()
    obj = mods[head] if head in mods else importlib.import_module(head)
    for part in rest:
        obj = getattr(obj, part)
    return set(obj)


def _schema_properties(schema, depth=0):
    if depth > 4 or not isinstance(schema, dict):
        return []
    out = list((schema.get("properties") or {}).keys())
    for key in ("oneOf", "anyOf", "allOf"):
        for sub in schema.get(key) or ():
            out += _schema_properties(sub, depth + 1)
    if schema.get("type") == "array":
        out += _schema_properties(schema.get("items") or {}, depth + 1)
    return out


@tagged("post_install", "-at_install")
class TestPublishedNamesResolve(CadraTransactionCase):

    # ── the census ───────────────────────────────────────────────────

    def test_every_route_that_takes_a_body_is_classified(self):
        """A new route is refused until somebody says what its body keys are.

        Driven by the routing attribute rather than by `_ROUTE_REGISTRY`,
        which the nine pre-envelope routes never joined, or by a search for
        allow-lists, which `POST /home/quick-submit` does not have.
        """
        live = _routes_with_a_body()
        unclassified = {k: v for k, v in live.items() if k not in _BODY_ROUTES}
        self.assertFalse(
            unclassified,
            "These routes accept a body and this test does not know what "
            "its keys are. Add each to `_BODY_ROUTES` with the model whose "
            "fields they name, or with None and the reason they name "
            "none:\n  " + "\n  ".join(
                "%s %s  (%s)" % (m, p, fn)
                for (m, p), fn in sorted(unclassified.items())))

    def test_the_table_names_no_route_that_is_gone(self):
        """A table entry outlasting its route is how a guard quietly stops
        guarding anything."""
        live = _routes_with_a_body()
        stale = sorted(k for k in _BODY_ROUTES if k not in live)
        self.assertFalse(
            stale, "`_BODY_ROUTES` names routes that no longer exist: %s"
            % (stale,))

    # ── the write side ───────────────────────────────────────────────

    def test_every_key_a_route_accepts_resolves_to_a_field(self):
        """The whole sweep, in one assertion.

        `_WRITABLE_FIELDS` carrying `location_id` while `request.request`
        carried `generic_location_id` is what this catches — on the day of
        the rename rather than three years later.
        """
        broken = []
        translated = _translations()
        for (method, path), (model, ref, _why) in sorted(_BODY_ROUTES.items()):
            if not model:
                continue
            fields = self.env[model]._fields
            for key in sorted(_resolve(ref)):
                if key in fields:
                    continue
                if (model, key) in translated:
                    target = translated[(model, key)]
                    if target not in fields:
                        broken.append(
                            "%s %s: `%s` is translated to `%s`, which %s "
                            "does not have either" % (method, path, key,
                                                      target, model))
                    continue
                if (model, key) in _NOT_A_FIELD:
                    continue
                broken.append(
                    "%s %s accepts `%s`; %s has no such field, and no "
                    "translation is declared for it. Either the model was "
                    "renamed underneath the route — translate it in the "
                    "controller and record it where the translation is "
                    "should not be published."
                    % (method, path, key, model))
        self.assertFalse(broken, "\n".join(broken))

    def test_a_declared_translation_is_still_a_translation(self):
        """A translation whose published name became a real field again is no
        longer translating anything, and leaving it in place means the model
        now has two ways to be written."""
        wrong = []
        for (model, published), target in sorted(_translations().items()):
            fields = self.env[model]._fields
            if published in fields and (model, published) not in _TRANSLATED_DESPITE_A_FIELD:
                wrong.append(
                    "`%s` IS a field on %s now, so translating it to `%s` "
                    "writes the wrong one — unless writing the same-named "
                    "field would write something else, in which case say so "
                    "in `_TRANSLATED_DESPITE_A_FIELD`"
                    % (published, model, target))
            if target not in fields:
                wrong.append("%s has no `%s` to translate `%s` onto"
                             % (model, target, published))
        self.assertFalse(wrong, "\n".join(wrong))

    def test_every_documented_body_key_is_one_the_route_accepts(self):
        """Since handoff 31 a key the gate does not accept is a 400 — so a
        key the OpenAPI document publishes and the gate refuses is not a
        documentation slip any more, it is a route that answers 400 to
        callers following our own specification."""
        registry = {(e["method"], e["path"]): e for e in v1._ROUTE_REGISTRY}
        broken = []
        for (method, path), (model, ref, _why) in sorted(_BODY_ROUTES.items()):
            if not model:
                continue
            entry = registry.get((method, path))
            if not entry or not entry.get("request_schema"):
                continue
            accepted = _resolve(ref)
            for key in sorted(set(_schema_properties(entry["request_schema"]))):
                if key not in accepted:
                    broken.append(
                        "%s %s documents `%s` and the route refuses it"
                        % (method, path, key))
        self.assertFalse(broken, "\n".join(broken))

    # ── the two sides against each other ─────────────────────────────

    def test_every_serializer_is_classified(self):
        """A serializer nobody has bound to a model is a published shape
        nothing below checks."""
        _read, seen = _fields_read_by_serializers()
        unclassified = sorted(s for s in seen if s not in _SERIALIZERS)
        self.assertFalse(
            unclassified,
            "Add each to `_SERIALIZERS` with the model of the record it is "
            "given: %s" % (unclassified,))

    def test_every_key_a_route_accepts_can_be_read_back(self):
        """What you can write, you can see.

        The depreciation-method bug was a screen reading one name and writing
        another. A field that is writable and published NOWHERE is the same
        asymmetry with nothing to compare against: a caller sets it, gets a
        201, and has no way to find out whether it took. Since handoff 31 a
        mismatch in the other direction is a 400, which is loud; this one
        stays quiet for ever.
        """
        read, _seen = _fields_read_by_serializers()
        translated = _translations()
        blind = []
        for (method, path), (model, ref, _why) in sorted(_BODY_ROUTES.items()):
            if not model:
                continue
            published = read.get(model, set())
            for key in sorted(_resolve(ref)):
                field = translated.get((model, key), key)
                if field in published or (model, key) in _NOT_A_FIELD:
                    continue
                if (model, field) in _WRITE_ONLY:
                    continue
                blind.append(
                    "%s %s accepts `%s` (%s.%s) and no serializer publishes "
                    "it, so a caller cannot read back what it wrote."
                    % (method, path, key, model, field))
        self.assertFalse(blind, "\n".join(sorted(set(blind))))

    def test_the_write_only_list_names_nothing_that_is_published(self):
        """A waiver that has quietly stopped being true is worse than no
        waiver: it says a gap was considered when it no longer exists."""
        read, _seen = _fields_read_by_serializers()
        wrong = sorted(
            "%s.%s is published after all" % (model, field)
            for (model, field) in _WRITE_ONLY
            if field in read.get(model, set()))
        self.assertFalse(wrong, "\n".join(wrong))

    # ── the read side ────────────────────────────────────────────────

    def test_every_guarded_read_is_classified(self):
        """`"x" in rec._fields` means either *that module may be absent* or
        *that field has been renamed and we answer null now*, and nothing in
        the source tells them apart. Every one is named here, so a new one
        has to be thought about once."""
        unclassified = [
            "%s:%s  %s.%s → \"%s\"" % (f, line, fn, var, field)
            for f, fn, var, field, line in _scan_controllers()
            if (f, fn, var, field) not in _GUARDED_READS
        ]
        self.assertFalse(
            unclassified,
            "These reads are guarded against a missing field and this test "
            "does not know what they guard. Add each to `_GUARDED_READS` "
            "with the record's model, or None and the reason it is not a "
            "record:\n  " + "\n  ".join(sorted(unclassified)))

    def test_the_table_names_no_guarded_read_that_is_gone(self):
        """An entry that outlasts the code it describes is a guard that has
        stopped guarding. This caught two of its own: the first draft named
        `_location_field`'s two field names and the parser never found
        them, because they are loop variables rather than literals."""
        live = {(f, fn, var, field)
                for f, fn, var, field, _line in _scan_controllers()}
        stale = sorted(k for k in _GUARDED_READS if k not in live)
        self.assertFalse(
            stale, "`_GUARDED_READS` names reads the controllers no longer "
            "make — either the code went away, or the parser cannot see it "
            "any more, which is worse: %s" % (stale,))

    def test_every_guarded_read_names_a_field_that_exists(self):
        """The assertion the shrugs were hiding.

        On a database carrying our modules, every field a controller guards
        against is either there — in which case the guard is about an
        optional module, as it was written to be — or it has been renamed,
        which is the defect.
        """
        broken = []
        for f, fn, var, field, line in _scan_controllers():
            model = _GUARDED_READS.get((f, fn, var, field))
            if not model:
                continue
            if (model, field) in _MUST_NOT_RESOLVE:
                continue
            if field not in self.env[model]._fields:
                broken.append(
                    "%s:%s guards `%s` on %s, which has no such field — so "
                    "everything reading it publishes null and nothing fails."
                    % (f, line, field, model))
        self.assertFalse(broken, "\n".join(broken))

    def test_the_name_this_deployment_does_not_have_is_still_the_one_missing(self):
        """`_location_field` tries `location_id` and falls through to
        `generic_location_id`. The fallback is only correct while the first
        name is absent — the day `request.request` gains a `location_id`
        again, that helper starts writing the wrong column, silently."""
        fields = self.env["request.request"]._fields
        for model, name in sorted(_MUST_NOT_RESOLVE):
            self.assertNotIn(
                name, self.env[model]._fields,
                "%s has a `%s` again. `v1_requests._location_field` prefers "
                "it over `generic_location_id`, so requests would start "
                "being written to whichever of the two is now wrong."
                % (model, name))
        self.assertIn("generic_location_id", fields)

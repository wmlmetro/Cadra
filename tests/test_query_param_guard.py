"""Every published query parameter reaches a validator, or is waived by name.

The static half of `tests/test_query_params.py`. That file asserts what a
caller receives today; this one asserts that the parameter somebody adds next
year cannot quietly rejoin the family it closed.

The family: a filter whose value the parser did not recognise appended NO
domain term, so the caller received the list they would have received with no
filter at all. **An empty list reads as "no matches". A full list reads as an
answer.** Seven booleans, thirteen enums and nineteen foreign keys failed that
way across five controllers, and every one of them was written by somebody
following the shape of the parameter next to it.

So the shape next to it is what this guards. `INVENTORY` below names every
query parameter every route declares, and says how it is validated — or why
it is not. Adding a parameter without an entry fails. Deleting the validation
of one that has an entry fails. A stale entry for a parameter nobody declares
any more fails too, because a waiver list that nobody prunes is how a waiver
list stops meaning anything.

It is a pinned inventory rather than a pure inference, and that is deliberate:
the reader below can see the route decorator, the parameter list and the
`parse_*` call, but it cannot see whether a free-text `q` SHOULD have a closed
set. That judgement is a person's, so it is written down where a person can
disagree with it.
"""
import ast
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTROLLERS = REPO_ROOT / "myservice_api" / "controllers"

#: The door. Pure by construction, and `test_the_door_does_no_database_work`
#: is what keeps it that way.
DOOR = CONTROLLERS / "query_params.py"

#: The parse functions that count as validating a parameter.
VALIDATORS = frozenset({"parse_bool", "parse_enum", "parse_int"})

#: `int_filter_terms(qs, (...))` validates every name in its second argument.
BULK_VALIDATOR = "int_filter_terms"

#: `*PAGINATION_QUERY_PARAMS` in a `query_params` list expands to these.
#: Written out rather than imported because the test venv cannot import
#: `odoo`, which `v1.py` does at module scope.
PAGINATION_PARAMS = ("limit", "cursor")

#: `*_PERIOD_QUERY_PARAMS` in `v1_audit.py` expands to these — the inclusive
#: `from`/`to` pair the two §13.4 log reports share. Same reason as above for
#: writing it out, and the same rule applies: a splat this file cannot expand
#: fails `test_the_reader_understands_every_route` rather than being skipped.
PERIOD_PARAMS = ("from", "to")

#: Every starred name this reader can expand, and what it expands to. A list
#: rather than an `if/elif` chain so that adding one is a data change; the
#: guard that a NEW splat must not pass silently is unaffected either way.
EXPANDABLE_SPLATS = {
    "PAGINATION_QUERY_PARAMS": PAGINATION_PARAMS,
    "_PERIOD_QUERY_PARAMS": PERIOD_PARAMS,
    # `v1_audit`'s access report re-spells `limit` and `cursor` so it can say
    # a page is a window of ACCOUNTS. Same names, same parsers, different
    # unit — the names are what this reader checks.
    "_ACCOUNT_PAGE_QUERY_PARAMS": PAGINATION_PARAMS,
}


# ─── the inventory ───────────────────────────────────────────────────
#
# `(module, parameter) -> (kind, why)`.
#
# Kinds that MUST reach a validator:
#   "bool"  parse_bool     "enum"  parse_enum     "int"  parse_int / bulk
#
# Kinds that are waived, each with the reason it is waived. A waiver is a
# claim that there is nothing to validate against, and it has to be a claim
# somebody can check:
#   "text"    free text with no closed set — a substring search, an exact
#             match on a reference another system minted
#   "date"    validated by a date parser that already answers 400
#   "opaque"  the caller does not compose it; we minted it
#   "inline"  validated where it is used rather than through the door,
#             with the reason it could not go through the door

INVENTORY = {
    # ── v1.py — the barcode station's routes ──────────────────────────
    ("v1", "query"): ("text", "a tag, asset code or serial typed into a scan box"),
    ("v1", "q"): ("text", "free-text search across name, asset code, serial"),
    ("v1", "domain_filter"): ("text", "an FM domain name forwarded to the barcode station's own filter, which has no closed set of its own to read"),
    ("v1", "limit"): ("int", ""),
    ("v1", "tag_id"): ("inline", "refused inline by barcode_print_url, which must distinguish malformed from absent BEFORE delegating, so it cannot share the delegate's 404"),
    ("v1", "size"): ("enum", ""),

    # ── v1_assets.py ──────────────────────────────────────────────────
    ("v1_assets", "q"): ("text", "free-text across name, code, tag, serial, GRN and PO"),
    ("v1_assets", "category_id"): ("int", ""),
    ("v1_assets", "subcategory_id"): ("int", ""),
    ("v1_assets", "location_id"): ("int", ""),
    ("v1_assets", "building_id"): ("int", ""),
    ("v1_assets", "floor_id"): ("int", ""),
    ("v1_assets", "room_id"): ("int", ""),
    ("v1_assets", "custodian_id"): ("int", ""),
    ("v1_assets", "parent_id"): ("int", ""),
    ("v1_assets", "state"): ("enum", ""),
    ("v1_assets", "condition"): ("enum", ""),
    ("v1_assets", "domain"): ("enum", ""),
    ("v1_assets", "asset_level"): ("enum", ""),
    ("v1_assets", "is_verified"): ("bool", ""),
    ("v1_assets", "grn_reference"): ("text", "a reference Vendra minted; Cadra has no set of them to check against"),
    ("v1_assets", "purchase_order_reference"): ("text", "a reference SAP minted"),
    ("v1_assets", "purchase_vendor"): ("text", "a supplier name as the receipt recorded it"),
    ("v1_assets", "import_source"): ("enum", ""),
    ("v1_assets", "import_ref"): ("text", "the writing system's own batch reference"),
    ("v1_assets", "is_tagged"): ("bool", ""),
    ("v1_assets", "tag_label_state"): ("enum", ""),
    ("v1_assets", "sap_asset_number"): ("text", "SAP's asset number; Cadra holds no list of the ones SAP has issued"),
    ("v1_assets", "has_sap_code"): ("bool", ""),
    ("v1_assets", "sap_reconciliation_state"): ("enum", ""),
    ("v1_assets", "warranty_status"): ("enum", ""),
    ("v1_assets", "warranty_expires_within_days"): ("int", ""),
    ("v1_assets", "include"): ("enum", ""),
    ("v1_assets", "sort"): ("enum", ""),
    # Handoff 61 §6, the sync filter. A date-time, parsed in `v1_assets`
    # because the door imports nothing and a datetime cannot be read
    # without `datetime`.
    ("v1_assets", "updated_since"): ("date", "_parse_updated_since — 400 for unparseable"),
    ("v1_assets", "as_of"): ("date", "_parse_report_date — 400 for unparseable, absent-but-required, and a future date"),
    ("v1_assets", "from"): ("date", "_parse_report_date"),
    # The two §13.4 log reports. Same parser as the disposal report above —
    # imported from `v1_assets` rather than re-implemented, so `from` and
    # `to` cannot come to mean two different things on two audit reports.
    ("v1_audit", "from"): ("date", "_parse_report_date — 400 for unparseable, absent-but-required, and a reversed period"),
    ("v1_audit", "to"): ("date", "_parse_report_date"),
    # `limit` and `cursor` are in SHARED_PARAMS and are not inventoried per
    # module; `_page` runs them through `parse_limit` and `decode_cursor`.
    ("v1_assets", "to"): ("date", "_parse_report_date"),

    # ── v1_requests.py ────────────────────────────────────────────────
    ("v1_requests", "q"): ("text", "free-text across name, request body and the people on it"),
    ("v1_requests", "type_id"): ("int", ""),
    ("v1_requests", "category_id"): ("int", ""),
    ("v1_requests", "stage_id"): ("int", ""),
    ("v1_requests", "user_id"): ("int", ""),
    ("v1_requests", "author_id"): ("int", ""),
    ("v1_requests", "partner_id"): ("int", ""),
    ("v1_requests", "service_id"): ("int", ""),
    ("v1_requests", "parent_id"): ("int", ""),
    ("v1_requests", "location_id"): ("int", ""),
    ("v1_requests", "asset_id"): ("int", ""),
    ("v1_requests", "nrs_asset_id"): ("int", ""),
    ("v1_requests", "priority"): ("enum", ""),
    ("v1_requests", "kanban_state"): ("enum", ""),
    ("v1_requests", "closed"): ("bool", ""),
    ("v1_requests", "has_deadline"): ("bool", ""),
    ("v1_requests", "include"): ("enum", ""),

    # ── v1_identity.py ────────────────────────────────────────────────
    ("v1_identity", "q"): ("text", "free-text across name and IR number"),
    ("v1_identity", "ir_number"): ("text", "an exact IR number; the set is the staff register itself"),
    ("v1_identity", "grade_level"): ("text", "a Char on the model, not a Selection — 'GL 14' and its neighbours are not a closed set in the schema"),
    ("v1_identity", "sap_status"): ("enum", ""),
    ("v1_identity", "sap_sync_status"): ("enum", ""),
    ("v1_identity", "location_id"): ("int", ""),
    ("v1_identity", "department_id"): ("int", ""),
    ("v1_identity", "active"): ("bool", ""),

    # ── v1_locations.py ───────────────────────────────────────────────
    ("v1_locations", "q"): ("text", "free-text across name, description, zone code and city"),
    ("v1_locations", "type_id"): ("int", ""),
    ("v1_locations", "parent_id"): ("int", ""),
    ("v1_locations", "country_id"): ("int", ""),
    ("v1_locations", "state_id"): ("int", ""),
    ("v1_locations", "location_type"): ("enum", ""),
    ("v1_locations", "active"): ("bool", ""),
    ("v1_locations", "has_coordinates"): ("bool", ""),
    ("v1_locations", "include"): ("enum", ""),

    # ── v1_approvals.py ───────────────────────────────────────────────
    #
    # Handoff 35's queue. `waiting_on_me` and `raised_by_me` are the two that
    # matter most here and for a reason this file already knows: a boolean
    # filter whose value the parser did not recognise used to append no
    # domain term, so `?waiting_on_me=nonsense` would have answered with
    # EVERY approval request in the register and called it the caller's
    # queue. An approver reading that list has no way to tell it from theirs.
    ("v1_approvals", "state"): ("enum", ""),
    ("v1_approvals", "change_type"): ("enum", ""),
    ("v1_approvals", "asset_id"): ("int", ""),
    ("v1_approvals", "waiting_on_me"): ("bool", ""),
    ("v1_approvals", "raised_by_me"): ("bool", ""),
    ("v1_approvals", "q"): ("text", "free-text on an approver candidate's name; the set is the tenant's user list itself"),

    # ── v1_tags.py — handoff 51, the replacements record ──────────────
    #
    # The approvals trio, on the label's own lifecycle. Same stakes:
    # `?waiting_on_me=nonsense` answering with every replacement request on
    # the tenant would read as the caller's queue.
    ("v1_tags", "state"): ("enum", ""),
    ("v1_tags", "waiting_on_me"): ("bool", ""),
    ("v1_tags", "raised_by_me"): ("bool", ""),

    # ── handoff 57 — the receipt gates (kept by 58) ─────────────────
    ("v1_assets", "register_state"): ("inline", "refused inline by _register_state_domain, which must answer a 403 (no `candidates:read`) before it can answer a 400, and accepts `any`, which is not a state"),
    ("v1_gates", "register_state"): ("inline", "refused inline by list_candidates against the model's states minus `registered`, which a candidate never is"),
    ("v1_gates", "waiting_on"): ("inline", "refused inline by list_candidates against asset_gates.WAITING_ON_VALUES, a derived set the model owns"),
    ("v1_gates", "q"): ("text", "free-text across name, code, tag, serial, GRN and PO — `_list_domain`'s own"),
    # ── handoff 60 — seventy a day ──────────────────────────────────
    ("v1_gates", "waiting_on_me"): ("bool", ""),
    ("v1_gates", "sort"): ("enum", ""),

    # ── v1_fleet.py ───────────────────────────────────────────────────
    ("v1_fleet", "q"): ("text", "free-text across plate, VIN, name, driver, model, brand, home location"),
    ("v1_fleet", "state_id"): ("int", ""),
    ("v1_fleet", "fuel_type"): ("enum", ""),
    ("v1_fleet", "is_staff_bus"): ("bool", ""),

    # ── v1_users.py — handoff 41, who has what ────────────────────────
    ("v1_users", "q"): ("text", "free-text across name, login and email; the set is the tenant's user list itself"),
    ("v1_users", "role"): ("enum", ""),
    ("v1_users", "role_direct"): ("enum", ""),
    ("v1_users", "active"): ("bool", ""),
    ("v1_users", "is_api_client"): ("bool", ""),

    # ── v1_sap_links.py — handoff 65, the link ────────────────────────
    ("v1_sap_links", "status"): ("enum", ""),
    ("v1_sap_links", "state"): ("enum", ""),
    ("v1_sap_links", "kind"): ("enum", ""),
    ("v1_sap_links", "flagged"): ("bool", ""),
    ("v1_sap_links", "asset_id"): ("int", ""),
    ("v1_sap_links", "offset"): ("int", ""),
    ("v1_sap_links", "limit"): ("int", ""),
    ("v1_sap_links", "office"): ("text", "SAP's office code, as `v1_sap_mirror`'s `office`: the set is whatever SAP's export carries"),
    ("v1_sap_links", "class"): ("text", "a SAP asset class as SAP writes it, as `v1_sap_mirror`'s `class`"),
    # ── v1_sap_mirror.py — handoff 63, the SAP mirror ─────────────────
    ("v1_sap_mirror", "active"): ("bool", ""),
    ("v1_sap_mirror", "in_latest_export"): ("bool", ""),
    ("v1_sap_mirror", "updated_since"): ("date", "_parse_updated_since, imported from v1_assets — 400 for unparseable"),
    ("v1_sap_mirror", "office"): ("text", "an office code inside a FIRS/<office>/… old tag, or `none`; the set is whatever SAP's export carries (901 on nrs19's October import), not a closed list Cadra owns"),
    ("v1_sap_mirror", "class"): ("text", "a SAP asset class as SAP writes it; the set is SAP's, compared exactly, and a class that matches nothing is an honest empty page"),
    ("v1_sap_mirror", "old_tag"): ("text", "an old FIRS tag read off an item, matched exactly after normalising"),
    ("v1_sap_mirror", "description"): ("text", "what the item is, in words; matched whole-word"),
    ("v1_sap_mirror", "serial"): ("text", "a serial read off an item; a placeholder is said to be one, in `notes`"),
}

#: Pagination is shared by every list route and validated once, in
#: `utils.parse_limit` and `utils.decode_cursor`, rather than per controller.
#: `test_pagination_is_validated_in_one_place` is what asserts that, so the
#: two names are excluded from the per-module inventory rather than repeated
#: in it seven times.
SHARED_PARAMS = {"limit", "cursor"}

VALIDATED_KINDS = {"bool": "parse_bool", "enum": "parse_enum", "int": "parse_int"}


# ─── the reader ──────────────────────────────────────────────────────

def _controller_modules():
    for path in sorted(CONTROLLERS.glob("v1*.py")):
        yield path.stem, path


def _declared_params(tree):
    """Every name in every `query_params=[...]` in the module.

    `*PAGINATION_QUERY_PARAMS` is expanded; any other starred expression is
    returned as its source text so `test_the_reader_understands_every_route`
    fails on it rather than silently skipping a whole list.
    """
    names, unresolved = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "query_params":
                continue
            for element in getattr(kw.value, "elts", []):
                if isinstance(element, ast.Starred):
                    source = ast.unparse(element.value)
                    if source in EXPANDABLE_SPLATS:
                        names.update(EXPANDABLE_SPLATS[source])
                    else:
                        unresolved.add(source)
                    continue
                for key, value in zip(element.keys, element.values):
                    if getattr(key, "value", None) == "name":
                        names.add(value.value)
    return names, unresolved


def _constant_names(node):
    """The string literals a node can evaluate to, as far as a reader can tell."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        # `param = "asset_id" if qs.get("asset_id") else "nrs_asset_id"`.
        # The requests list publishes both spellings of the same filter and
        # refuses whichever one the caller actually sent, so the validated
        # name is a conditional rather than a literal.
        return _constant_names(node.body) | _constant_names(node.orelse)
    return set()


def _loop_bindings(tree):
    """`{loop variable: {literal values it takes}}` for every `for` in the file.

    `v1_assets._list_domain` validates four enums in one loop:

        for fld, fallback in (("state", _ASSET_STATES), ...):
            value = parse_enum(fld, qs.get(fld), ...)

    so `parse_enum`'s first argument is a Name, not a Constant. Without this
    the reader would report `state`, `condition`, `domain` and `asset_level`
    as unvalidated — and a guard that is wrong about correct code is a guard
    somebody deletes.
    """
    bindings = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        targets = ([node.target] if isinstance(node.target, ast.Name)
                   else list(getattr(node.target, "elts", [])))
        for position, target in enumerate(targets):
            if not isinstance(target, ast.Name):
                continue
            for item in getattr(node.iter, "elts", []):
                if isinstance(item, ast.Constant) and len(targets) == 1:
                    bindings.setdefault(target.id, set()).add(item.value)
                elif isinstance(item, (ast.Tuple, ast.List)):
                    if position < len(item.elts):
                        element = item.elts[position]
                        if isinstance(element, ast.Constant):
                            bindings.setdefault(target.id, set()).add(element.value)

    # Plain assignments of a string, or of a conditional between two strings.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        values = _constant_names(node.value)
        if not values:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bindings.setdefault(target.id, set()).update(values)
    return bindings


def _validated_params(tree):
    """`{parameter: {validator names}}` for the module."""
    bindings = _loop_bindings(tree)

    def names_of(node):
        if isinstance(node, ast.Constant):
            return {node.value}
        if isinstance(node, ast.Name):
            return set(bindings.get(node.id, ()))
        if isinstance(node, ast.IfExp):
            # `param = "asset_id" if qs.get("asset_id") else "nrs_asset_id"`.
            # The requests list publishes both spellings of the same filter
            # and refuses whichever one the caller actually sent, so the
            # validated name is a conditional rather than a literal.
            return names_of(node.body) | names_of(node.orelse)
        return set()

    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            function = node.func.id
        elif isinstance(node.func, ast.Attribute):
            function = node.func.attr
        else:
            continue

        if function in VALIDATORS and node.args:
            for name in names_of(node.args[0]):
                found.setdefault(name, set()).add(function)
        elif function == BULK_VALIDATOR and len(node.args) > 1:
            for element in getattr(node.args[1], "elts", []):
                if isinstance(element, ast.Constant):
                    found.setdefault(element.value, set()).add("parse_int")
                elif isinstance(element, ast.Tuple) and element.elts:
                    if isinstance(element.elts[0], ast.Constant):
                        found.setdefault(element.elts[0].value,
                                         set()).add("parse_int")
    return found


def _domain_builder_reads(tree):
    """Every `qs.get("x")` inside a function whose name ends `_domain`.

    The reverse direction: a parameter the domain builder ACTS on but that no
    route declares is invisible to Swagger, invisible to the inventory above,
    and was how `kanban_state` and `has_deadline` stayed undocumented for the
    life of the requests endpoint.
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.endswith("_domain"):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "get"
                    and getattr(inner.func.value, "id", None) == "qs"
                    and inner.args
                    and isinstance(inner.args[0], ast.Constant)):
                names.add(inner.args[0].value)
            elif (isinstance(inner, ast.Subscript)
                  and getattr(inner.value, "id", None) == "qs"
                  and isinstance(inner.slice, ast.Constant)):
                names.add(inner.slice.value)
        names.update(_loop_bindings(node).get("fld", set()))
    return names


def _module_facts():
    facts = {}
    for name, path in _controller_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        declared, unresolved = _declared_params(tree)
        facts[name] = {
            "declared": declared,
            "unresolved": unresolved,
            "validated": _validated_params(tree),
            "domain_reads": _domain_builder_reads(tree),
        }
    return facts


# ─── the guards ──────────────────────────────────────────────────────

def test_the_reader_understands_every_route():
    """A `*SOMETHING` the reader cannot expand is a whole parameter list it
    skipped, and every test below would then pass by not looking."""
    unresolved = {name: sorted(facts["unresolved"])
                  for name, facts in _module_facts().items()
                  if facts["unresolved"]}
    assert not unresolved, (
        "these `query_params` lists splat something this file cannot expand, "
        "so the parameters in them are unchecked: %s" % unresolved)


def test_every_declared_query_parameter_is_in_the_inventory():
    """The one that fires when somebody adds a filter.

    A new parameter with no entry here is a parameter nobody has decided
    about — and the default outcome of not deciding is the silent
    pass-through this whole handoff removed.
    """
    missing = []
    for name, facts in _module_facts().items():
        for param in sorted(facts["declared"] | facts["domain_reads"]):
            if param in SHARED_PARAMS:
                continue
            if (name, param) not in INVENTORY:
                missing.append("%s: %s" % (name, param))
    assert not missing, (
        "these query parameters are declared or acted on but have no "
        "INVENTORY entry in this file:\n  %s\n\n"
        "Add one. If it is a bool, an enum or an int it must reach the door "
        "in myservice_api/controllers/query_params.py; if it genuinely has "
        "no closed set, waive it with the reason." % "\n  ".join(missing))


def test_the_inventory_has_no_stale_entries():
    """A waiver list nobody prunes is a waiver list that stops meaning
    anything. Every entry must still correspond to a live parameter."""
    facts = _module_facts()
    stale = []
    for (module, param) in sorted(INVENTORY):
        known = facts.get(module)
        if known is None:
            stale.append("%s: module is gone" % module)
        elif param not in (known["declared"] | known["domain_reads"]):
            stale.append("%s: %s is no longer declared or read" % (module, param))
    assert not stale, (
        "these INVENTORY entries name parameters that no longer exist:\n  %s"
        % "\n  ".join(stale))


@pytest.mark.parametrize("kind", sorted(VALIDATED_KINDS))
def test_every_parameter_of_a_validated_kind_reaches_the_door(kind):
    """Deleting a `parse_bool` call fails here, which is the point.

    The inventory says what a parameter is; this says the code agrees. A
    parameter recorded as a boolean that no longer reaches `parse_bool` has
    been returned to the state where an unreadable value drops the filter.
    """
    facts = _module_facts()
    expected = VALIDATED_KINDS[kind]
    unvalidated = []
    for (module, param), (declared_kind, _why) in sorted(INVENTORY.items()):
        if declared_kind != kind:
            continue
        seen = facts[module]["validated"].get(param, set())
        if expected not in seen:
            unvalidated.append(
                "%s: %s is inventoried as %s but no %s() call names it "
                "(found: %s)" % (module, param, kind, expected,
                                 sorted(seen) or "nothing"))
    assert not unvalidated, (
        "an unreadable value for these would drop the filter rather than be "
        "refused:\n  %s" % "\n  ".join(unvalidated))


def test_every_waiver_says_why():
    """A waiver with no reason is a parameter somebody skipped, spelled the
    same way as one somebody thought about."""
    silent = [(module, param) for (module, param), (kind, why)
              in sorted(INVENTORY.items())
              if kind not in VALIDATED_KINDS and not why.strip()]
    assert not silent, (
        "these waivers give no reason: %s" % silent)


def test_every_inventory_kind_is_one_this_file_understands():
    known = set(VALIDATED_KINDS) | {"text", "date", "opaque", "inline"}
    unknown = {(module, param): kind
               for (module, param), (kind, _why) in INVENTORY.items()
               if kind not in known}
    assert not unknown, (
        "these entries use a kind nothing in this file checks, so they are "
        "waivers wearing a validator's name: %s" % unknown)


def test_pagination_is_validated_in_one_place():
    """`limit` and `cursor` ride on every list route and are parsed once.

    Asserted rather than left implied, because the alternative to one shared
    parser is seven copies, and six of them drifting is how `is_verified`
    came to differ from `is_tagged` in the first place.
    """
    utils = (CONTROLLERS / "utils.py").read_text(encoding="utf-8")
    tree = ast.parse(utils)
    validated = _validated_params(tree)
    assert "parse_int" in validated.get("limit", set()), (
        "utils.parse_limit no longer sends `limit` through the door, so "
        "`?limit=all` is back to silently serving the default page size")
    assert "def decode_cursor" in utils, (
        "utils.decode_cursor is gone; whatever replaced it needs an entry here")


# ─── the door itself ─────────────────────────────────────────────────

def test_the_door_does_no_database_work():
    """The acceptance criterion, asserted rather than asserted in prose.

    `utils._selection_allowed_values` is the obvious thing to reuse and is
    forbidden here: it calls `cr.rollback()` when it cannot read a field,
    because it was written for the error path after a failed write. A read
    path runs it on the happy path of every list request, so a transient
    failure would roll back a cursor nothing had asked it to touch. That
    ruling is landed (docs/DECISIONS.md, 2026-09-06) and it is the reason
    this module exists rather than that helper being extended.

    The strongest form of "does no database work" available to a static test
    is that the module reaches nothing that could do any: no imports at all,
    and no mention of the request, the environment or the cursor.
    """
    source = DOOR.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = [ast.unparse(node) for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not imports, (
        "the door imports something. It is pure by construction and that is "
        "what makes it safe on a read path: %s" % imports)

    # Read CODE, not prose. The module's docstring says the words "database",
    # "cursor" and "rollback" out loud, because explaining a rule means naming
    # what it forbids — and a guard that flags its own explanation is a guard
    # somebody satisfies by deleting the explanation.
    forbidden = {"request", "env", "cr", "rollback", "search", "sudo",
                 "browse", "_fields", "odoo", "get_values", "http"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            offenders.append("line %d: name `%s`" % (node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            offenders.append("line %d: attribute `.%s`" % (node.lineno, node.attr))
    assert not offenders, (
        "the door reaches for something that could touch the database:\n  %s"
        % "\n  ".join(offenders))


def test_the_door_accepts_no_boolean_spelling_it_did_not_publish():
    """`1`, `yes` and `on` stay refused, and that is deliberate.

    Widening the accepted set would be a second silent reinterpretation of a
    value the caller may have meant as something else — the same family of
    bug, one layer along, and the one place a well-meaning fix could
    reintroduce it.
    """
    namespace = {}
    exec(compile(DOOR.read_text(encoding="utf-8"), str(DOOR), "exec"), namespace)
    parse_bool, BadFilter = namespace["parse_bool"], namespace["BadFilter"]

    assert parse_bool("x", "true") is True
    assert parse_bool("x", "True") is True
    assert parse_bool("x", "false") is False
    assert parse_bool("x", "False") is False
    assert parse_bool("x", None) is None
    assert parse_bool("x", "") is None
    # `"null"` is absent ONLY where a parameter published that leniency.
    assert parse_bool("x", "null", null_is_absent=True) is None

    for value in ("1", "0", "yes", "no", "on", "off", "TRUE", "t", "null"):
        with pytest.raises(BadFilter):
            parse_bool("x", value)


# ─── mutation proofs ─────────────────────────────────────────────────
#
# Each of these makes the change the guard above exists to catch, confirms it
# fails, and confirms the honest version does not. Without them a guard can
# pass because it read nothing.

_FIXTURE_HEADER = (
    "from .query_params import BadFilter, parse_bool, parse_enum, parse_int\n"
    "from .v1 import PAGINATION_QUERY_PARAMS, cadra_route\n\n\n"
)

_HONEST = _FIXTURE_HEADER + '''
def _list_domain(qs):
    domain = []
    closed = parse_bool("closed", qs.get("closed"))
    if closed is not None:
        domain.append(("closed", "=", closed))
    return domain


class C:
    @cadra_route("/api/v1/things", method="GET",
                 query_params=[{"name": "closed", "schema": {"type": "boolean"}}])
    def list_things(self, **kwargs):
        return []
'''

_DROPPED_VALIDATOR = _FIXTURE_HEADER + '''
def _list_domain(qs):
    domain = []
    closed = qs.get("closed")
    if closed in ("true", "True"):
        domain.append(("closed", "=", True))
    elif closed in ("false", "False"):
        domain.append(("closed", "=", False))
    return domain


class C:
    @cadra_route("/api/v1/things", method="GET",
                 query_params=[{"name": "closed", "schema": {"type": "boolean"}}])
    def list_things(self, **kwargs):
        return []
'''

_UNDECLARED_PARAM = _FIXTURE_HEADER + '''
def _list_domain(qs):
    domain = []
    if qs.get("has_deadline") == "true":
        domain.append(("deadline_date", "!=", False))
    return domain


class C:
    @cadra_route("/api/v1/things", method="GET",
                 query_params=[{"name": "closed", "schema": {"type": "boolean"}}])
    def list_things(self, **kwargs):
        return []
'''


def _facts_for(source):
    tree = ast.parse(source)
    declared, unresolved = _declared_params(tree)
    return {
        "declared": declared,
        "unresolved": unresolved,
        "validated": _validated_params(tree),
        "domain_reads": _domain_builder_reads(tree),
    }


def test_the_reader_sees_a_validator_that_has_been_removed():
    """The mutation `test_every_parameter_of_a_validated_kind...` exists for:
    the `parse_bool` call replaced by the membership tests it replaced."""
    honest = _facts_for(_HONEST)
    assert "parse_bool" in honest["validated"].get("closed", set())

    mutant = _facts_for(_DROPPED_VALIDATOR)
    assert "closed" in mutant["declared"]
    assert "parse_bool" not in mutant["validated"].get("closed", set()), (
        "the reader still reports `closed` as validated after the parse_bool "
        "call was deleted, so the guard would pass on the exact regression "
        "it exists to catch")


def test_the_reader_sees_a_parameter_that_is_acted_on_but_not_declared():
    """`kanban_state` and `has_deadline` were accepted by the requests domain
    builder and published by nothing. That is what this catches."""
    mutant = _facts_for(_UNDECLARED_PARAM)
    assert "has_deadline" in mutant["domain_reads"]
    assert "has_deadline" not in mutant["declared"]


def test_the_reader_resolves_the_loop_form():
    """`v1_assets` validates four enums through one loop variable. A reader
    that only understands a string literal would call all four unvalidated,
    and a guard that is wrong about correct code gets deleted."""
    facts = _facts_for(_FIXTURE_HEADER + '''
def _list_domain(qs):
    domain = []
    for fld, fallback in (("state", ()), ("condition", ())):
        value = parse_enum(fld, qs.get(fld), fallback)
        if value is not None:
            domain.append((fld, "=", value))
    return domain
''')
    for param in ("state", "condition"):
        assert "parse_enum" in facts["validated"].get(param, set()), (
            "the reader did not resolve `%s` through the loop variable" % param)
        assert param in facts["domain_reads"]


def test_the_reader_resolves_the_bulk_int_form():
    """`int_filter_terms(qs, (...))` validates a whole tuple at once,
    including the `(query_param, model_field)` pairs the employees and
    locations lists need."""
    facts = _facts_for(_FIXTURE_HEADER + '''
from .query_params import int_filter_terms


def _list_domain(qs):
    return int_filter_terms(qs, (
        "type_id",
        ("location_id", "sap_location_id"),
    ))
''')
    for param in ("type_id", "location_id"):
        assert "parse_int" in facts["validated"].get(param, set()), param

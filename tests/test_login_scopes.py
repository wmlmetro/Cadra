"""Static guards over the group → scope mapping behind `POST /auth/login`.

`/auth/login` used to mint `["*"]` for anybody who could authenticate. That
meant the INT-04/05 separation held for API clients and not for session
users: a storekeeper with an Odoo password carried `tagging:write`, so the
same person could create an asset record and then confirm the label was
affixed to it. An affix record produced that way proves only that one system
said so twice — which is exactly what the Tag-Issuing Unit's own credential
exists to prevent.

The fix is `utils.GROUP_SCOPES` plus `scopes_for_user`. What has to stay true
about it is structural, and none of it is visible in a response: the suite's
token is a client token, so no HTTP call this suite can make exercises the
login path's scope derivation at all. These read the source instead.

    tests/.venv/bin/python -m pytest tests/test_login_scopes.py

The test venv cannot import `odoo`, so `GROUP_SCOPES` is recovered with `ast`
rather than by importing the module. The entries name `SCOPE_*` constants,
not string literals, so the names are resolved against the assignments in the
same file — a regex over the source would read the constant names and never
see the scopes they stand for.
"""
import ast
import re
import pathlib
import xml.etree.ElementTree as ET

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

UTILS_PY = REPO_ROOT / "myservice_api" / "controllers" / "utils.py"
V1_PY = REPO_ROOT / "myservice_api" / "controllers" / "v1.py"
ASSET_SECURITY_XML = (REPO_ROOT / "myservice_asset_register" / "security"
                      / "asset_security.xml")

TAG_ISSUING_UNIT = "myservice_asset_register.group_tag_issuing_unit"
ASSET_MANAGER = "myservice_asset_register.group_asset_manager"
SCOPE_TAGGING_WRITE = "tagging:write"


# ─── recovering module-level values without importing odoo ───────────


def _parse(path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        pytest.fail(f"could not parse {path.relative_to(REPO_ROOT)}: {exc}")


def _string_constants(tree):
    """Every module-level `NAME = "literal"` binding in the file.

    This is what turns `SCOPE_TAGGING_WRITE` back into `"tagging:write"`.
    """
    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


def _module_value(tree, name):
    """The right-hand side of a module-level assignment to `name`."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name
                for t in node.targets):
            return node.value
    return None


def _literal(node, constants, where):
    """Evaluate a literal-ish expression, resolving `SCOPE_*` names.

    Deliberately narrow: constants, names bound to a string literal in the
    same module, the three sequence literals, and a `frozenset(...)`/`set(...)`
    wrapper. Anything else fails the test rather than being skipped — a table
    this guard cannot read is a table it is not guarding.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in constants:
            pytest.fail(
                f"{where}: `{node.id}` is not a module-level string constant "
                f"in {UTILS_PY.name} — this guard resolves scope names there, "
                "so a scope defined some other way is invisible to it."
            )
        return constants[node.id]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [_literal(e, constants, where) for e in node.elts]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set") and node.args):
        return _literal(node.args[0], constants, where)
    pytest.fail(f"{where}: cannot evaluate {ast.dump(node)[:120]}")


def _group_scopes():
    """`GROUP_SCOPES` as [(group xmlid, [scope, ...]), ...]."""
    tree = _parse(UTILS_PY)
    constants = _string_constants(tree)
    value = _module_value(tree, "GROUP_SCOPES")
    assert value is not None, (
        "GROUP_SCOPES has gone from myservice_api/controllers/utils.py. If the "
        "group→scope mapping moved, point this module at its new home — "
        "without it every guard in this file passes vacuously."
    )
    pairs = _literal(value, constants, "GROUP_SCOPES")
    assert pairs, "GROUP_SCOPES is empty — no user would get any scope at all"
    return [(xmlid, list(scopes)) for xmlid, scopes in pairs]



def _implied_by(group_local_id):
    """Group xmlids `group_local_id` implies, per asset_security.xml.

    `has_group` follows `implied_ids`, so a user's effective scopes are the
    union over the groups they hold AND everything those imply. GROUP_SCOPES
    lists only the delta for that reason, and a test that read the table
    literally would understate what Asset Manager actually carries.
    """
    for record_id, model, fields in _security_records():
        if record_id != group_local_id or model != "res.groups":
            continue
        implied = fields.get("implied_ids")
        if implied is None:
            return []
        expr = (implied.get("eval") or "") + (implied.text or "")
        return ["myservice_asset_register.%s" % name
                for name in re.findall(r"ref\(['\"]([\w.]+)['\"]\)", expr)]
    return []


def _scopes_for_group(xmlid):
    """Effective scopes for a user holding exactly `xmlid` — implications included."""
    table = dict(_group_scopes())
    assert xmlid in table, (
        f"`{xmlid}` is no longer in GROUP_SCOPES — a user in that group would "
        "log in with no scopes at all"
    )
    granted = set(table[xmlid])
    local = xmlid.split(".", 1)[1]
    for implied in _implied_by(local):
        # `ref('group_asset_user')` inside asset_security.xml is module-local.
        granted.update(table.get(implied, ()))
    return granted

def _all_scopes():
    tree = _parse(UTILS_PY)
    constants = _string_constants(tree)
    value = _module_value(tree, "ALL_SCOPES")
    assert value is not None, "ALL_SCOPES has gone from utils.py"
    return set(_literal(value, constants, "ALL_SCOPES"))


# ─── the separation the whole change exists to establish ─────────────


def test_tagging_write_is_granted_by_exactly_one_group():
    """One grant, and it is the Tag-Issuing Unit's.

    `tagging:write` reaching a second group is how the control dies quietly:
    the affix endpoint keeps returning 200 and the evidence it records stops
    meaning anything, because the confirming user could also have created the
    asset. `admin` is a separate matter — it is a wildcard in `require_jwt`
    and is granted only to `base.group_system`, whose members can run
    arbitrary server actions anyway.
    """
    granting = [xmlid for xmlid, scopes in _group_scopes()
                if SCOPE_TAGGING_WRITE in scopes]
    assert granting == [TAG_ISSUING_UNIT], (
        f"`{SCOPE_TAGGING_WRITE}` is granted by {granting or 'nothing'}; it "
        f"must be granted by exactly one group, `{TAG_ISSUING_UNIT}`. A "
        "second grant means the team that creates asset records can also "
        "confirm the label went onto the metal."
    )


def test_asset_manager_does_not_get_tagging_write():
    """Asset Manager creating the record AND confirming its tag is the bug.

    Called out separately from the test above because this is the pairing the
    separation is actually about, and because Asset Manager is the group a
    future edit is most likely to widen — it already holds `assets:write`,
    and handing it `tagging:write` "so managers can finish the job" collapses
    INT-04/05 into a single desk.
    """
    scopes = dict(_group_scopes()).get(ASSET_MANAGER)
    assert scopes is not None, (
        f"`{ASSET_MANAGER}` is no longer in GROUP_SCOPES — an Asset Manager "
        "logging in would now get no scopes at all"
    )
    assert SCOPE_TAGGING_WRITE not in scopes, (
        f"`{ASSET_MANAGER}` grants `{SCOPE_TAGGING_WRITE}` ({scopes}). The "
        "group that creates asset records must not be able to confirm their "
        "labels affixed — that is the whole control, not a convenience."
    )


def test_login_does_not_mint_a_wildcard():
    """`scopes = ["*"]` in the login handler undoes all of the above.

    The existing guard in test_source_guards.py catches the *fallback* shape
    (`.scopes or ["*"]`); this one catches the bare assignment that used to
    sit in `login()` behind a TODO. Restoring it would hand `tagging:write` to
    every user who can type an Odoo password, and nothing would go red.
    """
    tree = _parse(V1_PY)

    login = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "login"),
                 None)
    assert login is not None, (
        "no `login` function in myservice_api/controllers/v1.py — if the "
        "handler was renamed, retarget this guard, because it is now checking "
        "nothing."
    )
    assert any(isinstance(n, ast.Name) and n.id == "scopes_for_user"
               for n in ast.walk(login)), (
        "`login` no longer derives its scopes from the user's Odoo groups via "
        "`scopes_for_user` — check what it mints instead."
    )

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "scopes"
                   for t in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            continue
        if any(isinstance(e, ast.Constant) and e.value == "*"
               for e in node.value.elts):
            offenders.append(node.lineno)

    assert not offenders, (
        "myservice_api/controllers/v1.py assigns the wildcard scope list at "
        f"line(s) {offenders}. A session token carrying `*` passes every scope "
        "check including `tagging:write`, so the Tag-Issuing Unit separation "
        "holds for API clients and not for anyone with an Odoo login."
    )


def test_every_mapped_scope_is_a_real_scope():
    """A typo'd scope grants nothing and refuses nothing — it just misleads.

    `require_jwt` compares strings, so `"taging:write"` in the table produces
    a token that looks correctly scoped in `/auth/whoami` and 403s on the one
    endpoint it was meant to open. The 403 is indistinguishable from a real
    permission decision.
    """
    known = _all_scopes()
    unknown = sorted({
        scope
        for _, scopes in _group_scopes()
        for scope in scopes
        if scope not in known
    })
    assert not unknown, (
        f"GROUP_SCOPES names scopes that are not in ALL_SCOPES: {unknown}. "
        "Add them to ALL_SCOPES, or fix the typo — an unknown scope is "
        "granted to nobody and gates nothing."
    )


# ─── the group must stay unattached in the security data ─────────────


def _records_in(path):
    """(id, model, {field name: field element}) for each record in one file."""
    # ElementTree drops comments, so the explanatory block above the record —
    # which names both `implied_ids` and the group — cannot produce a false
    # positive in the scan below.
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        # A non-Odoo XML file somewhere under a module directory. Not our
        # business, and not a reason to fail the security guard.
        return
    for record in root.iter("record"):
        fields = {f.get("name"): f for f in record.findall("field")}
        yield record.get("id"), record.get("model"), fields


def _security_records():
    """The records in the file that declares the Tag-Issuing Unit group."""
    return _records_in(ASSET_SECURITY_XML)


def test_tag_issuing_unit_group_is_implied_by_nothing():
    """`implied_ids` is how this separation would die without a code change.

    Odoo's `has_group` follows `implied_ids`, so hanging the Tag-Issuing Unit
    under Asset Manager — one line in a data file, no Python touched, nothing
    in the API diff — would silently give every Asset Manager `tagging:write`.
    The mapping in utils.py would still read correctly.
    """
    records = list(_security_records())
    assert records, f"{ASSET_SECURITY_XML.name} declares no records — parsed wrong?"

    group = next((r for r in records
                  if r[0] == "group_tag_issuing_unit" and r[1] == "res.groups"),
                 None)
    assert group is not None, (
        "`group_tag_issuing_unit` is not declared in "
        f"{ASSET_SECURITY_XML.relative_to(REPO_ROOT)}. It is the only grant of "
        "`tagging:write`; without it no user can ever confirm a tag affixed."
    )
    assert "implied_ids" not in group[2], (
        "`group_tag_issuing_unit` now carries `implied_ids` — it must imply "
        "nothing and be implied by nothing. Whatever it inherits, its holders "
        "would gain on top of the one scope this group exists to grant."
    )

    # Scan EVERY first-party data file, not just the one that declares the
    # group. Odoo lets any module reopen a group by xmlid --
    # `<record id="myservice_asset_register.group_asset_manager"
    #  model="res.groups"><field name="implied_ids" eval="[(4,
    #  ref('myservice_asset_register.group_tag_issuing_unit'))]"/></record>`
    # -- from a brand module, myservice_identity, or anything added later.
    # A guard that reads only asset_security.xml would pass green while the
    # separation was gone.
    offenders = []
    for xml_path in sorted(REPO_ROOT.glob("myservice_*/**/*.xml")):
        for record_id, _model, fields in _records_in(xml_path):
            implied = fields.get("implied_ids")
            if implied is None:
                continue
            expr = (implied.get("eval") or "") + (implied.text or "")
            if "group_tag_issuing_unit" in expr:
                rel = xml_path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}::{record_id}: {expr.strip()}")

    assert not offenders, (
        "a group implies the Tag-Issuing Unit, so its members hold "
        "`tagging:write` without anyone granting it:\n  "
        + "\n  ".join(offenders)
        + "\n\nThe team that creates asset records must not be the team that "
        "confirms the label went onto the metal. Do not 'tidy' this group "
        "into the Asset Manager hierarchy."
    )


def test_asset_manager_keeps_the_scopes_the_desk_ui_needs():
    """Narrowing the login wildcard must not silently break the SPA.

    The SPA gates nothing on scopes — every menu item and button renders
    whatever the token holds — so a scope an Asset Manager loses does not
    hide a control, it turns one into a 403 toast on click. Bulk Import is
    the sharp case: `integrations:write` is the only thing that page needs
    and the whole of what it does, and it sits in the top-level nav.

    These are the scopes behind SPA screens an Asset Manager uses today.
    Dropping one from GROUP_SCOPES is a one-line edit with no other symptom.
    """
    granted = _scopes_for_group(ASSET_MANAGER)
    needed = {
        "assets:read", "assets:write",
        "locations:read", "locations:write",
        "requests:read", "requests:write",
        "identity:read",
        "dashboards:read",
        "settings:write",       # Categories / Branding / Depreciation
        "integrations:write",   # Bulk Import
    }
    missing = sorted(needed - granted)
    assert not missing, (
        "an Asset Manager session token would no longer carry: "
        + ", ".join(missing)
        + "\n\nEach of these is behind a page the SPA shows them. Losing one "
        "produces a 403 toast on a screen that still looks available, not a "
        "hidden button — which is precisely the 'silently broken' this "
        "handoff's acceptance criterion rules out."
    )


def test_asset_manager_still_has_no_wildcard():
    """The counterweight to the test above.

    The easy way to keep every SPA screen working is to grant `admin`, which
    `require_jwt` treats as a wildcard — and a wildcard passes
    `tagging:write`. That would hand the team that creates asset records the
    power to confirm their own tags, which is the hole this work closes,
    reopened in the name of not breaking the UI.
    """
    granted = _scopes_for_group(ASSET_MANAGER)
    assert "admin" not in granted and "*" not in granted, (
        f"{ASSET_MANAGER} is granted a wildcard ({sorted(granted)}). "
        "`admin` satisfies every scope check in require_jwt, `tagging:write` "
        "included. Use `settings:write` for the Settings screens."
    )


# ─── handoff 47: a role is a job ─────────────────────────────────────

ASSET_USER = "myservice_asset_register.group_asset_user"
ASSET_OFFICER = "myservice_asset_register.group_asset_officer"
AUDITOR = "myservice_api.group_auditor"


def test_asset_officer_is_the_job_between_reading_and_running():
    """Ruling 3: registering, requesting a move, recording a verification —
    and none of running the register.

    The gap handoff 46 measured: Asset User could not register an asset, and
    the only role that could also approved other people's moves and changed
    the branding, the depreciation rules and the SAP integration. The Asset
    Officer closes it by composing scopes that already existed. The pin here
    is both directions: what the role grants, and what it must never pick
    up — `approvals:write` back on this group is handoff 35's two-person
    rule collapsing into one desk.
    """
    granted = _scopes_for_group(ASSET_OFFICER)
    assert granted == _scopes_for_group(ASSET_USER) | {"assets:write"}, (
        f"the Asset Officer's effective scopes are {sorted(granted)}; the "
        "role is Asset User's reads plus `assets:write` and nothing else — "
        "a wider grant is a decision for the Architect, not an edit"
    )
    forbidden = {"approvals:write", "settings:write", "settings:read",
                 "integrations:write", "locations:write", "ingestion:write",
                 "tagging:write", "webhooks:admin", "admin", "*"}
    assert not granted & forbidden, (
        f"the Asset Officer picked up {sorted(granted & forbidden)} — the "
        "role exists precisely so that registering stock does not come with "
        "approving, configuring or importing"
    )


def test_the_register_ladder_is_user_officer_manager():
    """Manager implies Officer implies User, spelled out in the XML.

    Both of Manager's implications are explicit (Officer AND User) so that a
    reader — and `_scopes_for_group`, which resolves one level — sees the
    whole ladder without computing a closure.
    """
    assert ASSET_USER in _implied_by("group_asset_officer"), (
        "the Asset Officer no longer implies Asset User — an officer who "
        "cannot read the register cannot register anything into it"
    )
    manager_implies = _implied_by("group_asset_manager")
    assert ASSET_OFFICER in manager_implies and ASSET_USER in manager_implies, (
        f"Asset Manager implies {manager_implies}; it must imply both the "
        "Officer and the User explicitly (see asset_security.xml)"
    )


def test_access_read_is_granted_by_exactly_the_auditor():
    """Ruling 1, first split: the access record is the Auditor's (and the
    administrator's, via the wildcard) — not every Asset User's.

    `access:read` reaching a second group quietly reopens what the split
    closed: under `identity:read`, every holder of the employee picker could
    read the record of who granted whom which role.
    """
    granting = [xmlid for xmlid, scopes in _group_scopes()
                if "access:read" in scopes]
    assert granting == [AUDITOR], (
        f"`access:read` is granted by {granting or 'nothing'}; it must be "
        f"granted by exactly one group, `{AUDITOR}`"
    )
    assert "access:read" not in _scopes_for_group(ASSET_USER), (
        "Asset User holds `access:read` — the identity:read split is undone"
    )


def test_dashboards_and_operations_are_two_scopes_held_by_different_jobs():
    """Ruling 1, second split: the asset dashboard's figures and the fleet
    are different questions.

    Asset User (and the Auditor) read the register's figures and not the
    fleet; a Security Officer and a Bus User read the operational dashboards
    and not the register's figures. One group holding both halves again is
    the coarse scope coming back under two names.
    """
    for xmlid in (ASSET_USER, AUDITOR):
        granted = _scopes_for_group(xmlid)
        assert "dashboards:read" in granted and "operations:read" not in granted, (
            f"{xmlid} holds {sorted(granted)} — it reads the register's "
            "figures, not the fleet/security/FM dashboards"
        )
    table = dict(_group_scopes())
    for xmlid in ("myservice_security.group_security_officer",
                  "myservice_staff_bus.group_bus_user"):
        scopes = set(table.get(xmlid, ()))
        assert "operations:read" in scopes and "dashboards:read" not in scopes, (
            f"{xmlid} grants {sorted(scopes)} — its job is the operational "
            "dashboards, not the asset register's figures"
        )

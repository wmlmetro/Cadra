"""Static guards over our own source. No running instance required.

These assert things about the code itself rather than about a response, so
they run standalone:

    tests/.venv/bin/python -m pytest tests/test_source_guards.py

The one guard here exists because of a failure that was found by accident.
Odoo 19 removed the `_sql_constraints` model attribute — `orm/model_classes.py`
logs "Model attribute '_sql_constraints' is no longer supported, please define
models.Constraint on the model" and then creates nothing. Every uniqueness and
check constraint declared that way silently stopped existing in every
database, including `unique(asset_code)` on `nrs.asset`, which INT-06/07's
dual-code reconciliation depends on. Nothing failed. No test went red. It
surfaced only because someone happened to read a log line.

A data-integrity guarantee that can disappear without a sound is exactly the
thing to have a test for.
"""
import ast
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Our own modules. Vendored trees (`dist/`, `crnd-19/`, `oca-19/`) are third
# party — they are audited in docs/constraint-audit.md, but we do not control
# their source and patching them carries an upgrade cost, so failing our test
# suite on them would be noise we cannot act on.
FIRST_PARTY_GLOBS = ("myservice_*", "cadra_brand_*")

# The sanctioned pattern is a version guard that declares models.Constraint on
# Odoo >= 19 and keeps the legacy list only for the 15 production stack:
#
#     if _ODOO_MAJOR >= 19:
#         _asset_code_unique = models.Constraint('UNIQUE (asset_code)', '...')
#     else:
#         _sql_constraints = [...]
#
# A `_sql_constraints` reachable ONLY when the major version is below 19 is
# fine. Anything else is the defect — including the same shape written the
# wrong way round, which is a keystroke away and reinstates exactly the bug
# this guard exists to catch:
#
#     if _ODOO_MAJOR >= 19:
#         _sql_constraints = [...]        # dead on 19 — must NOT pass
#
# So it is not enough to notice that some enclosing `if` mentions the version:
# the branch has to be the one that runs on the old major.
_VERSION_NAMES = {"_ODOO_MAJOR", "version_info"}
_ODOO_19 = 19


def _first_party_python_files():
    for glob in FIRST_PARTY_GLOBS:
        for module_dir in sorted(REPO_ROOT.glob(glob)):
            if not (module_dir / "__manifest__.py").exists():
                continue
            for path in sorted(module_dir.rglob("*.py")):
                yield path


def _mentions_odoo_major(expr):
    """True if `expr` reads the running Odoo major version."""
    names = {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(expr) if isinstance(n, ast.Attribute)}
    return bool((names | attrs) & _VERSION_NAMES)


def _branch_runs_below_19(if_node, in_body):
    """Does the taken branch of `if_node` run only on Odoo majors below 19?

    Handles the two spellings that mean the same thing —
    `if _ODOO_MAJOR >= 19: ... else: <here>` and
    `if _ODOO_MAJOR < 19: <here>` — and rejects everything else, including a
    test that merely mentions a variable called `release`.
    """
    test = if_node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not _mentions_odoo_major(test.left):
        return False
    comparator = test.comparators[0]
    if not (isinstance(comparator, ast.Constant)
            and isinstance(comparator.value, int)):
        return False
    op, bound = test.ops[0], comparator.value

    # Which side of the comparison is "old Odoo"?
    if isinstance(op, (ast.GtE, ast.Gt)):          # major >= 19 / > 18
        old_branch_is_body = False
    elif isinstance(op, (ast.Lt, ast.LtE)):        # major < 19 / <= 18
        old_branch_is_body = True
    else:
        return False

    # The bound has to actually separate 18 from 19, or the guard is about
    # some other version boundary and says nothing about this one.
    if isinstance(op, (ast.GtE, ast.Lt)) and bound != _ODOO_19:
        return False
    if isinstance(op, (ast.Gt, ast.LtE)) and bound != _ODOO_19 - 1:
        return False

    return in_body is old_branch_is_body


def _is_version_guarded(node, ancestors_with_branch):
    """True if `node` is reachable only on Odoo majors below 19."""
    return any(
        isinstance(parent, ast.If) and _branch_runs_below_19(parent, in_body)
        for parent, in_body in ancestors_with_branch
    )


def _assigns_sql_constraints(node):
    """True if `node` binds the name `_sql_constraints`.

    Covers the spellings the ORM would still honour on Odoo 15:
    plain assignment, annotated assignment (`_sql_constraints: list = [...]`),
    augmented assignment, and tuple unpacking. `setattr` is out of scope —
    a guard cannot chase arbitrary indirection, and nobody declares model
    constraints that way by accident.
    """
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        return False

    for target in targets:
        for name in ast.walk(target):
            if isinstance(name, ast.Name) and name.id == "_sql_constraints":
                return True
    return False


def _unguarded_sql_constraints(path):
    """Line numbers of every unguarded `_sql_constraints` binding in one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        pytest.fail(f"could not parse {path.relative_to(REPO_ROOT)}: {exc}")

    # ast gives no parent links, so record each node's parent and — for an
    # `if` — which of its two branches the child sits in. The branch is what
    # tells a real guard apart from one written the wrong way round.
    parents = {}
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            for child in (value if isinstance(value, list) else [value]):
                if isinstance(child, ast.AST):
                    parents[child] = (parent, field != "orelse")

    def ancestry(node):
        while node in parents:
            node, in_body = parents[node]
            yield node, in_body

    found = []
    for node in ast.walk(tree):
        if not _assigns_sql_constraints(node):
            continue
        chain = list(ancestry(node))
        # Only a class-body binding declares constraints to the ORM. A local
        # of the same name inside a method is someone's variable, not a model
        # attribute, and flagging it would block legitimate code.
        scope = next((p for p, _ in chain
                      if isinstance(p, (ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef, ast.Module))), None)
        if not isinstance(scope, ast.ClassDef):
            continue
        if not _is_version_guarded(node, chain):
            found.append(node.lineno)
    return sorted(found)


def test_no_unguarded_sql_constraints():
    """`_sql_constraints` must never be declared unguarded in our modules.

    On Odoo 19 it creates nothing, so the constraint it appears to declare
    does not exist. Use `models.Constraint("UNIQUE (a, b)", "message")`,
    keeping the legacy list behind an `_ODOO_MAJOR` check only while the
    Odoo 15 stack is still in production.
    """
    offenders = []
    for path in _first_party_python_files():
        for lineno in _unguarded_sql_constraints(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")

    assert not offenders, (
        "`_sql_constraints` is dead on Odoo 19 — it logs a warning and creates "
        "no constraint, so these declare a database guarantee that does not "
        "exist:\n  " + "\n  ".join(offenders) + "\n\n"
        "Declare it as `models.Constraint(\"UNIQUE (...)\", \"message\")` "
        "instead. If the Odoo 15 stack still needs the old spelling, use the "
        "version-guarded pattern in myservice_asset_register/models/asset.py."
    )


def test_guard_detects_a_reintroduced_declaration(tmp_path):
    """The guard above must actually catch the thing it claims to catch.

    Without this, a bug in the AST walk would make the guard pass forever and
    silently stop guarding — the same failure mode it exists to prevent.
    """
    offending = tmp_path / "offending.py"
    offending.write_text(
        "from odoo import models\n"
        "\n"
        "class Thing(models.Model):\n"
        "    _name = 'thing'\n"
        "    _sql_constraints = [('code_uniq', 'unique(code)', 'msg')]\n"
    )
    assert _unguarded_sql_constraints(offending) == [5]

    guarded = tmp_path / "guarded.py"
    guarded.write_text(
        "from odoo import models, release\n"
        "_ODOO_MAJOR = release.version_info[0]\n"
        "\n"
        "class Thing(models.Model):\n"
        "    _name = 'thing'\n"
        "    if _ODOO_MAJOR >= 19:\n"
        "        _code_uniq = models.Constraint('UNIQUE (code)', 'msg')\n"
        "    else:\n"
        "        _sql_constraints = [('code_uniq', 'unique(code)', 'msg')]\n"
    )
    assert _unguarded_sql_constraints(guarded) == []


# Each case is (label, source, should_be_flagged). Every "True" here was a
# false negative in the guard's first version: it accepted any enclosing `if`
# that merely mentioned the version, and only looked at plain `Assign` with a
# bare `Name` target. The first case is the dangerous one — a keystroke from
# the sanctioned pattern, and it reinstates the exact bug being guarded.
_EVASIONS = [
    ("wrong way round — dead on 19", """
class T(models.Model):
    _name = 't'
    if _ODOO_MAJOR >= 19:
        _sql_constraints = [('c', 'unique(code)', 'm')]
    else:
        _c = models.Constraint('UNIQUE (code)', 'm')
""", True),
    ("an `if` that only mentions a variable named release", """
class T(models.Model):
    _name = 't'
    if release:
        _sql_constraints = [('c', 'unique(code)', 'm')]
""", True),
    ("annotated assignment", """
class T(models.Model):
    _name = 't'
    _sql_constraints: list = [('c', 'unique(code)', 'm')]
""", True),
    ("augmented assignment", """
class T(models.Model):
    _name = 't'
    _sql_constraints = []
    _sql_constraints += [('c', 'unique(code)', 'm')]
""", True),
    ("tuple unpacking", """
class T(models.Model):
    _name = 't'
    _sql_constraints, _other = [('c', 'unique(code)', 'm')], None
""", True),
    ("guarded on an unrelated version boundary", """
class T(models.Model):
    _name = 't'
    if _ODOO_MAJOR < 16:
        _sql_constraints = [('c', 'unique(code)', 'm')]
""", True),
    ("sanctioned: >= 19 with the list in the else", """
class T(models.Model):
    _name = 't'
    if _ODOO_MAJOR >= 19:
        _c = models.Constraint('UNIQUE (code)', 'm')
    else:
        _sql_constraints = [('c', 'unique(code)', 'm')]
""", False),
    ("sanctioned: the < 19 spelling of the same thing", """
class T(models.Model):
    _name = 't'
    if _ODOO_MAJOR < 19:
        _sql_constraints = [('c', 'unique(code)', 'm')]
""", False),
    ("a method-local variable that merely shares the name", """
class T(models.Model):
    _name = 't'
    def build(self):
        _sql_constraints = [('c', 'unique(code)', 'm')]
        return _sql_constraints
""", False),
]


@pytest.mark.parametrize("label,source,should_flag",
                         _EVASIONS, ids=[c[0] for c in _EVASIONS])
def test_guard_is_not_fooled(tmp_path, label, source, should_flag):
    """The guard must judge the branch, not just spot a version-shaped `if`.

    A guard that accepts `if _ODOO_MAJOR >= 19: _sql_constraints = [...]`
    passes green while the constraint it names does not exist — which is the
    original failure wearing the costume of a test.
    """
    path = tmp_path / "case.py"
    path.write_text("from odoo import models, release\n"
                    "_ODOO_MAJOR = release.version_info[0]\n" + source)
    flagged = _unguarded_sql_constraints(path)
    if should_flag:
        assert flagged, f"guard MISSED: {label}"
    else:
        assert not flagged, f"guard wrongly flagged: {label} (lines {flagged})"


def test_guard_covers_the_modules_we_think_it_does():
    """A path typo would make the guard scan nothing and pass vacuously."""
    scanned = list(_first_party_python_files())
    modules = {p.relative_to(REPO_ROOT).parts[0] for p in scanned}
    assert len(scanned) > 100, f"only {len(scanned)} files scanned — glob wrong?"
    for expected in ("myservice_api", "myservice_asset_register",
                     "myservice_staff_bus"):
        assert expected in modules, f"{expected} not covered by the guard"


# ─── empty scopes must never mean "every scope" ──────────────────────
#
# `(client.scopes or "").split() or ["*"]` reads as a harmless default and is
# a privilege escalation: a client saved with an empty scopes field — a typo,
# a half-filled form, an integration provisioned in a hurry — received the
# entire API including `admin`. It is also the exact opposite of what the
# Tag-Issuing Unit's narrowly-scoped client exists to establish.
#
# There is no HTTP test for this, because minting a scopeless client needs ORM
# access the suite does not have. A source guard is what fits: the failure is
# a two-character `or` reappearing in a diff.

_SCOPE_DERIVATION_SITES = (
    "myservice_api/controllers/v1.py",
    "myservice_api/models/api_refresh_token.py",
)


@pytest.mark.parametrize("relpath", _SCOPE_DERIVATION_SITES)
def test_empty_scopes_does_not_fall_back_to_wildcard(relpath):
    source = (REPO_ROOT / relpath).read_text()
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ".scopes or" in stripped and '["*"]' in stripped:
            pytest.fail(
                f"{relpath}:{lineno} restores the empty-scopes wildcard:\n"
                f"    {stripped}\n"
                "An empty scopes field means NO permissions. Grant everything "
                "by writing `admin` on the client, never by leaving it blank."
            )


def test_the_scope_derivation_sites_still_exist():
    """A rename would make the guard above scan the wrong file and pass."""
    for relpath in _SCOPE_DERIVATION_SITES:
        path = REPO_ROOT / relpath
        assert path.exists(), f"{relpath} moved — update _SCOPE_DERIVATION_SITES"
        assert ".scopes or" in path.read_text(), (
            f"{relpath} no longer derives scopes from a client record — "
            "update _SCOPE_DERIVATION_SITES to wherever it moved"
        )


# ─── the Settings screens must not need `admin` ──────────────────────
#
# Six `/api/v1/settings/*` and `/api/v1/asset-categories` routes were gated on
# `admin`, which is a wildcard in `require_jwt`. So the only way to let an
# Asset Manager change a category's useful life or the tenant's branding was
# to hand them every scope on the API, `tagging:write` included — the exact
# thing the Tag-Issuing Unit separation exists to prevent. They now take
# `settings:write`, which `GROUP_SCOPES` grants to Asset Manager alone.
#
# Reverting one decorator is a one-word edit that produces no failure: the
# suite's own token holds `admin`, so every one of those routes keeps
# answering 200. A source guard is the only thing that would notice.

_SETTINGS_CONTROLLER = "myservice_api/controllers/v1_settings.py"


def _route_scopes(relpath):
    """[(route path, [scope constant name, ...]), ...] for one controller."""
    tree = ast.parse((REPO_ROOT / relpath).read_text(encoding="utf-8"))
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "cadra_route":
            continue
        path = (node.args[0].value
                if node.args and isinstance(node.args[0], ast.Constant)
                else f"<line {node.lineno}>")
        scopes = []
        for kw in node.keywords:
            if kw.arg != "scopes" or not isinstance(kw.value, (ast.List, ast.Tuple)):
                continue
            scopes = [e.id for e in kw.value.elts if isinstance(e, ast.Name)]
        routes.append((path, scopes))
    return routes


def test_settings_routes_use_settings_write_and_not_admin():
    """`admin` on a Settings route means an Asset Manager needs a wildcard.

    And a wildcard passes `tagging:write`, so the person who maintains the
    category taxonomy could also confirm labels affixed — the separation
    defeated sideways, by a scope nobody thought of as a tagging permission.
    """
    routes = _route_scopes(_SETTINGS_CONTROLLER)
    assert routes, (
        f"no `cadra_route` calls found in {_SETTINGS_CONTROLLER} — if the "
        "settings endpoints moved, retarget this guard; as written it is now "
        "checking nothing."
    )

    admin_gated = [path for path, scopes in routes if "SCOPE_ADMIN" in scopes]
    assert not admin_gated, (
        f"{_SETTINGS_CONTROLLER} gates these on `admin`, which is a wildcard "
        "in require_jwt:\n  " + "\n  ".join(admin_gated) + "\n\n"
        "Use SCOPE_SETTINGS_WRITE. Granting `admin` to get at the Settings "
        "screens hands out `tagging:write` with it."
    )

    settings_gated = [path for path, scopes in routes
                      if "SCOPE_SETTINGS_WRITE" in scopes]
    assert settings_gated, (
        f"no route in {_SETTINGS_CONTROLLER} uses SCOPE_SETTINGS_WRITE. The "
        "scope exists to carve tenant configuration out of `admin`; a file "
        "with none of it either lost the change or gates configuration on "
        "something looser."
    )


# ─────────────────────────────────────────────────────────────────────
# Manifest load order: a menu's parent must be defined before it is used
# ─────────────────────────────────────────────────────────────────────
#
# Odoo resolves an external ID against what is already in `ir_model_data`, so
# a data file may only reference an xmlid its own module defined EARLIER in
# the manifest's `data` list. Get the order wrong and:
#
#   - a cold install fails with "External ID not found in the system"
#   - an UPGRADE passes, because the row is already there from last time
#
# That asymmetry is the whole problem. Handoff 07 put `asset_sap_views.xml`
# ahead of `asset_menu.xml`, upgraded all eight tenants green, deployed to
# staging green — and broke CI's cold bootstrap, which is the only place that
# installs from nothing. The failure mode it hides is worse than a red build:
# every tenant provisioned from that point on would refuse to install, and
# CLAUDE.md already records that provisioning a new tenant is a path people
# get wrong.

import re
import xml.etree.ElementTree as ET

_MENU_PARENT_RE = re.compile(r'parent\s*=\s*"([^"]+)"')


def _manifest_data_files(module_dir):
    """The `data` list, in load order, from a module manifest."""
    manifest = module_dir / "__manifest__.py"
    if not manifest.exists():
        return []
    try:
        tree = ast.parse(manifest.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant) and key.value == "data"
                    and isinstance(value, ast.List)):
                return [e.value for e in value.elts
                        if isinstance(e, ast.Constant)
                        and isinstance(e.value, str)]
    return []


def _first_party_modules():
    for glob in FIRST_PARTY_GLOBS:
        for path in sorted(REPO_ROOT.glob(glob)):
            if path.is_dir() and (path / "__manifest__.py").exists():
                yield path


def test_menu_parents_are_defined_before_they_are_used():
    """A menuitem's parent must load before the menuitem does.

    Only same-module, unqualified references are checked. A `parent` carrying
    a dot is another module's xmlid, which the dependency graph orders for us
    and which this cannot see.
    """
    problems = []
    for module_dir in _first_party_modules():
        defined = set()
        for relpath in _manifest_data_files(module_dir):
            path = module_dir / relpath
            if path.suffix != ".xml" or not path.exists():
                continue
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError as exc:
                problems.append(f"{module_dir.name}/{relpath}: unparseable ({exc})")
                continue

            # ONE pass, in document order. Odoo processes a data file element
            # by element, so an id defined earlier in the SAME file is already
            # available to what follows it — which is how nearly every menu
            # file in this repo is written, root first and children under it.
            # Checking the whole file against only what previous files defined
            # would flag all of them.
            for element in root.iter():
                if element.tag == "menuitem":
                    parent = element.get("parent")
                    if parent and "." not in parent and parent not in defined:
                        problems.append(
                            f"{module_dir.name}/{relpath}: menu "
                            f"{element.get('id') or '<no id>'!r} hangs off "
                            f"{parent!r}, which this module does not define "
                            f"until later (or not at all). A cold install "
                            f"fails here; an upgrade would not."
                        )
                if element.get("id"):
                    defined.add(element.get("id"))

    assert not problems, "menu parent referenced before it is defined:\n  " + \
        "\n  ".join(problems)


def test_the_menu_order_guard_would_have_caught_handoff_07(tmp_path):
    """The guard is only worth having if it fails on the real mistake."""
    module = tmp_path / "myservice_probe"
    (module / "views").mkdir(parents=True)
    (module / "__manifest__.py").write_text(
        "{'name': 'probe', 'data': ['views/child.xml', 'views/root.xml']}",
        encoding="utf-8")
    (module / "views" / "child.xml").write_text(
        '<odoo><menuitem id="child" parent="menu_root" name="Child"/></odoo>',
        encoding="utf-8")
    (module / "views" / "root.xml").write_text(
        '<odoo><menuitem id="menu_root" name="Root"/></odoo>',
        encoding="utf-8")

    global REPO_ROOT, FIRST_PARTY_GLOBS
    original_root, original_globs = REPO_ROOT, FIRST_PARTY_GLOBS
    REPO_ROOT, FIRST_PARTY_GLOBS = tmp_path, ("myservice_*",)
    try:
        with pytest.raises(AssertionError, match="menu parent referenced"):
            test_menu_parents_are_defined_before_they_are_used()
        # Reversed, the same two files are fine.
        (module / "__manifest__.py").write_text(
            "{'name': 'probe', 'data': ['views/root.xml', 'views/child.xml']}",
            encoding="utf-8")
        test_menu_parents_are_defined_before_they_are_used()
    finally:
        REPO_ROOT, FIRST_PARTY_GLOBS = original_root, original_globs

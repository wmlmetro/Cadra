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
import functools
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


# ─────────────────────────────────────────────────────────────────────
# The scheduler must be able to reach every tenant
# ─────────────────────────────────────────────────────────────────────
#
# `config/odoo.19.conf` set `db_name = odoo`. That looks like it only chooses
# which database HTTP exposes, and it was there for exactly that reason — but
# Odoo's cron worker reads the same option:
#
#     def cron_database_list():
#         return config['db_name'] or list_dbs(True)
#                                     # odoo/service/server.py
#
# So the scheduler served one database. On this stack that one is a leftover
# 15-era database a 19 worker skips as incompatible, which means NO ir.cron
# ran on ANY tenant, ever — INT-05 delivery, depreciation, PM, token GC, the
# mail queue, all of it. Nothing errored and nothing was logged as wrong: an
# event was queued and simply stayed queued.
#
# Exposure is `dbfilter`'s job, and dbfilter does not narrow `list_dbs`. So
# the rule is: a config file a long-running server loads may set `dbfilter`
# and must not set `db_name`.

_DB_NAME_RE = re.compile(r"^\s*db_name\s*=", re.MULTILINE)

# This guard has NO exceptions, and that is deliberate.
#
# It used to carry exactly one: `odoo.conf` at the repo root, a generated
# artefact of the Odoo 15 bare-metal `install.sh` — one host, one database,
# no dbfilter and no tenants, so pinning the scheduler to that database was
# what it meant to do. The file was deleted in handoff 09 and the exception
# went with it. An exception carved for a dead file is a hole waiting for
# someone to drop a live file into it: nothing about `str(rel) == "odoo.conf"`
# checks that the file is still the 15-era artefact, so the day anyone adds a
# repo-root `odoo.conf` for the 19 stack, the guard would wave it through
# silently — which is the precise failure mode the guard exists to catch.
#
# `install.sh` still writes a `db_name` into /etc/odoo/odoo.conf from its own
# heredoc. That is correct for what it is (a single-database bare-metal host
# with no scheduler to starve) and it is not matched here, because the guard
# scans config files this repo SERVES, not shell that generates one elsewhere.


def _server_config_files():
    """Every Odoo config a long-running server could load.

    The k8s ConfigMaps carry their `odoo.conf` inline as YAML, so they are
    matched as text rather than parsed — the guard is a line-level rule and
    an indented `db_name =` inside a block scalar is the same defect.
    """
    for path in sorted(REPO_ROOT.glob("*.conf")):
        yield path
    for path in sorted((REPO_ROOT / "config").glob("*.conf")):
        yield path
    for path in sorted((REPO_ROOT / "k8s").rglob("*configmap*.yaml")):
        yield path


# `db_name` is only one spelling. `-d` / `--database=` on a long-running
# server's argv sets `config['db_name']` identically and pins the cron worker
# in exactly the same way — and that is the keystroke-away reintroduction,
# because the compose files and the k8s Deployment are where the server's
# command line actually lives. Neither does it today; this keeps it that way.
#
# The one-shot invocations are a different thing entirely and must stay: a
# bootstrap, an upgrade or a migration Job SHOULD name its database, because
# it is not a server and has no scheduler. So the rule is scoped to a
# long-running command, which in practice means one without --stop-after-init.
_ARGV_DB_RE = re.compile(r"(?:^|[\s\"'])(?:-d|--database)(?:[=\s]|$)")

# `-d` is not unique to Odoo — `pg_isready -d`, `psql -d` and `pg_dump -d`
# all take one and none of them has a scheduler. Match the Odoo command, not
# the flag.
_PG_TOOLS_RE = re.compile(r"\b(?:pg_isready|psql|pg_dump|pg_restore|createdb|dropdb)\b")
_ODOO_CMD_RE = re.compile(r"(?:^|[\s\"'/])odoo(?:[\s\"']|$)")

_SERVER_ARGV_FILES = (
    "docker-compose.yml",
    "docker-compose.19.yml",
    "docker-compose.prod.yml",
    "k8s/dev/41-odoo-19-deployment.yaml",
)


def test_no_long_running_server_names_its_database_on_the_command_line():
    """`-d`/`--database` on a server pins the cron worker just like db_name.

    A one-shot (`--stop-after-init`) may and should name its database — it
    has no scheduler to starve. A server may not.
    """
    offenders = []
    for relpath in _SERVER_ARGV_FILES:
        path = REPO_ROOT / relpath
        # A named file that is missing used to be skipped. That is the same
        # hole as a waiver that matches nothing: `docker-compose.dev.yml` was
        # deleted with the Odoo 15 stack in handoff 20 and this list would
        # have gone on reciting it, asserting nothing, indistinguishable from
        # a pass. If a file here is genuinely gone, remove its line.
        assert path.exists(), (
            "%s is checked by this guard but does not exist. Delete the "
            "entry, or restore the file — a guard reciting a dead filename "
            "is a guard that checks nothing and says so to nobody." % relpath)
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "--stop-after-init" in stripped:
                continue
            if _PG_TOOLS_RE.search(stripped) or not _ODOO_CMD_RE.search(stripped):
                continue
            if _ARGV_DB_RE.search(stripped):
                offenders.append(f"{relpath}:{lineno}  {stripped}")

    assert not offenders, (
        "a long-running Odoo server names its database on the command line, "
        "which sets config['db_name'] and pins the cron worker to it exactly "
        "as the config option does:\n  " + "\n  ".join(offenders) + "\n\n"
        "Use --db-filter for exposure. One-shot commands carrying "
        "--stop-after-init are exempt and are skipped by this guard."
    )


def test_no_server_config_pins_the_cron_worker_to_one_database():
    """`db_name` in a served config stops every other tenant's cron dead.

    Choose the exposed database with `dbfilter` (`--db-filter`, which
    docker-compose passes from `ODOO_DBFILTER`). It restricts HTTP without
    touching `list_dbs`, so the scheduler keeps seeing every database.
    """
    offenders = []
    for path in _server_config_files():
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8")
        for match in _DB_NAME_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{rel}:{line}")

    assert not offenders, (
        "`db_name` pins Odoo's cron worker to the databases it names — "
        "`cron_database_list()` is `config['db_name'] or list_dbs(True)` — so "
        "every other tenant's ir.cron silently never runs:\n  "
        + "\n  ".join(offenders) + "\n\n"
        "Set the exposed database with `dbfilter` instead (`^%d$` for "
        "host-routed tenants, `^<db>$` for a single one). dbfilter does not "
        "narrow `list_dbs`, so cron still covers every database."
    )


def test_the_db_name_guard_would_have_caught_handoff_08(tmp_path):
    """The guard fails on the exact file that caused this, and passes fixed."""
    global REPO_ROOT
    (tmp_path / "config").mkdir()
    conf = tmp_path / "config" / "odoo.19.conf"
    conf.write_text("[options]\ndb_user = odoo\ndb_name = odoo\n",
                    encoding="utf-8")
    (tmp_path / "k8s").mkdir()

    original_root = REPO_ROOT
    REPO_ROOT = tmp_path
    try:
        with pytest.raises(AssertionError, match="pins Odoo's cron worker"):
            test_no_server_config_pins_the_cron_worker_to_one_database()
        conf.write_text("[options]\ndb_user = odoo\ndbfilter = ^%d$\n",
                        encoding="utf-8")
        test_no_server_config_pins_the_cron_worker_to_one_database()
        # And there is no longer any file it will wave through. The repo-root
        # `odoo.conf` used to be allow-listed by name; handoff 09 deleted the
        # file and the exception, so a NEW repo-root config pinning db_name is
        # now caught like any other.
        (tmp_path / "odoo.conf").write_text("[options]\ndb_name = myservice\n",
                                            encoding="utf-8")
        with pytest.raises(AssertionError, match="pins Odoo's cron worker"):
            test_no_server_config_pins_the_cron_worker_to_one_database()
    finally:
        REPO_ROOT = original_root


def test_the_repo_root_odoo_conf_is_gone():
    """The Odoo 15 bare-metal artefact, and the guard exception it justified.

    Deleted rather than left alone because it was the single named exception
    in the db_name guard above, and an exception matched on a filename cannot
    tell a dead file from a live one that later takes its name.
    """
    assert not (REPO_ROOT / "odoo.conf").exists(), (
        "the repo-root odoo.conf is back. It described an Odoo 15 "
        "single-database bare-metal host that no longer exists, nothing "
        "mounts it (install.sh writes /etc/odoo/odoo.conf from its own "
        "heredoc; every container mounts something under config/), and it "
        "sets db_name — which the guard above no longer excuses. If a "
        "repo-root config is genuinely needed again, name it for the stack it "
        "serves and give it a dbfilter."
    )


# ─── a scheduled method must exist ───────────────────────────────────
#
# The generalised lesson of the same handoff: a test that invokes the thing
# under test cannot see that nothing else invokes it. Every delivery test
# calls `_cron_drain_outbound_events()` directly, which proves the function
# works and says nothing about whether anything calls it.
#
# The mirror-image failure was real in this estate. `nrs19` and `jaizbankplc`
# carried two ir.cron rows — `cron_asset_pm_refresh_overdue` and
# `cron_asset_refresh_verification` — scheduling
# `nrs.asset.pm._cron_refresh_overdue()` and
# `nrs.asset._cron_refresh_verification()`, neither of which existed in the
# code those databases were running. They were dormant only because the
# scheduler was; the first tick after the fix would have raised AttributeError
# on both, every day. Handoff 08 deleted the rows.
#
# Two things about that are worth keeping straight, because both are easy to
# get wrong from memory:
#
#   1. The methods were not fiction. They exist in `c673ed1` on
#      `feat/rfp-phase1-authorisation`, which was never merged — the branch
#      added crons, data file and implementations together and these two
#      databases were upgraded from it. The rows survived the reset; the code
#      did not. Handoff 09 writes the methods properly, so the same two xmlids
#      are live again and legitimate.
#
#   2. THIS GUARD WOULD NOT HAVE CAUGHT THEM. It reads XML we ship, and those
#      crons reached the tenants as database rows whose source was consistent
#      on its own branch. The guard that catches that shape walks `ir.cron` in
#      a live registry and resolves each `state=code` call against the model —
#      `myservice_nrs_base/tests/test_scheduled_actions.py`, which needs a
#      database and so runs in the Odoo-native CI step, not here. This one
#      catches the cheaper mistake: shipping a cron whose method was never
#      written at all.

_CRON_CODE_CALL_RE = re.compile(r"\bmodel\.(_[A-Za-z0-9_]+)\s*\(")


def _scheduled_methods():
    """(file, xmlid, method) for every `state=code` ir.cron we ship."""
    for module_dir in _first_party_modules():
        for path in sorted(module_dir.rglob("*.xml")):
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            for record in root.iter("record"):
                if record.get("model") != "ir.cron":
                    continue
                code = "".join(
                    (field.text or "")
                    for field in record.findall("field")
                    if field.get("name") == "code")
                for method in _CRON_CODE_CALL_RE.findall(code):
                    yield path, record.get("id"), method


def test_every_scheduled_method_exists():
    """An ir.cron may not schedule a method nothing defines.

    The cron record is the production trigger. If it names a method that is
    not there, the guarantee it schedules does not exist — and because the
    row lives in the database rather than in the code, no upgrade removes it
    and no import fails. It surfaces as a daily traceback, or as nothing at
    all while the scheduler happens to be dead.
    """
    defined = set()
    for path in _first_party_python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)

    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {xmlid} schedules model.{method}()"
        for path, xmlid, method in _scheduled_methods()
        if method not in defined
    ]

    assert not offenders, (
        "these ir.cron records schedule a method that does not exist in any "
        "of our modules:\n  " + "\n  ".join(offenders) + "\n\n"
        "A cron whose method is missing fails on every tick — or, if the "
        "scheduler is not running, proves nothing at all."
    )


def test_the_cron_guard_covers_the_crons_we_ship():
    """The guard must actually be looking at something.

    A parser that silently matches nothing passes forever. These are the
    scheduled methods we know we ship; if this list shrinks, either a cron
    was removed deliberately or the parser stopped seeing them.
    """
    found = {method for _, _, method in _scheduled_methods()}
    expected = {
        "_gc",                              # myservice_api refresh tokens
        "_cron_recompute_depreciation",     # myservice_asset_depreciation
        "_cron_create_pm_requests",         # myservice_asset_register
        "_cron_check_preventive_maintenance",   # myservice_fleet_maintenance
        "_cron_drain_outbound_events",      # myservice_workflow (INT-05)
        # ── handoff 09: the stale-stored-compute class ──
        # Each of these pushes a stored compute whose body reads the clock but
        # whose @api.depends contains nothing the clock changes. Without the
        # cron the field is not "slightly behind", it is frozen at whatever it
        # was when something last wrote to the row.
        "_cron_refresh_sla_breached",       # myservice_request_fields
        "_cron_refresh_verification",       # myservice_asset_register
        "_cron_refresh_overdue",            # myservice_asset_register (PM)
        "_cron_refresh_on_duty",            # myservice_security
        "_cron_refresh_maintenance_status",  # myservice_fleet_maintenance
    }
    missing = sorted(expected - found)
    assert not missing, (
        f"the ir.cron parser no longer sees {missing} — either those crons "
        "were removed, or the guard has stopped reading the data files and "
        "is now passing vacuously."
    )


# ─── an API client must not run as Administrator ─────────────────────
#
# `myservice.api.client.user_id` decides which Odoo user a client's writes are
# recorded as, and Odoo 19's `sudo()` does not change `env.uid` — so this
# field, not the sudo, is what the audit trail says. Both provisioning sites
# in scripts/bootstrap.py set it to `base.user_admin`, and every tag affix in
# the estate therefore records:
#
#     "affixed_by": {"id": 2, "name": "Administrator"}
#
# for the Tag-Issuing Unit's client and for the client that created the asset
# alike. The scope separation held; the answer it exists to produce did not.
#
# There is no HTTP test for this half — the suite cannot inspect another
# client's record — so the guard is on the source, where the regression is one
# convenient line.

_CLIENT_PROVISIONING_SITES = ("scripts/bootstrap.py",)


def _admin_user_refs(node):
    """True if `node` is a reference to base.user_admin (or uid 2)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value in (
                "base.user_admin", "base.user_root"):
            return True
        if isinstance(sub, ast.Constant) and sub.value == 2:
            return True
    return False


@pytest.mark.parametrize("relpath", _CLIENT_PROVISIONING_SITES)
def test_no_api_client_is_provisioned_as_admin(relpath):
    """No client may be pointed at Administrator, in either spelling.

    A grep for the string `"user_id"` was the first version of this guard and
    it was wrong twice over: it flagged every ORM domain that happens to
    filter on a user (`search([("user_id", "=", uid)])`), and it MISSED the
    attribute form — `rec.user_id = env.ref("base.user_admin")` — which is the
    spelling this very file already uses elsewhere and therefore the one a
    regression would most naturally take. Parse instead.
    """
    tree = ast.parse((REPO_ROOT / relpath).read_text(encoding="utf-8"))
    offenders = []

    for node in ast.walk(tree):
        # 1. `user_id` as a key in a dict literal that also carries a
        #    `client_id` or `scopes` key — i.e. API-client create vals, not
        #    any old dict.
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "user_id" in keys and keys & {"client_id", "scopes"}:
                offenders.append(
                    f"{relpath}:{node.lineno} API-client create vals set "
                    "`user_id`")

        # 2. `<something>.user_id = <base.user_admin>` — attribute assignment.
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets
                       if isinstance(t, ast.Attribute) and t.attr == "user_id"]
            if targets and _admin_user_refs(node.value):
                offenders.append(
                    f"{relpath}:{node.lineno} assigns Administrator to "
                    "`.user_id`")

    assert not offenders, (
        "an API client is being pointed at Administrator:\n  "
        + "\n  ".join(offenders) + "\n\n"
        "Leave `user_id` out of the create — the model provisions the client "
        "its own res.users. Pointing every client at base.user_admin is what "
        "made `affixed_by` say Administrator for every client in the estate, "
        "so the Tag-Issuing Unit and the client that created the asset were "
        "indistinguishable in the only record that could tell them apart."
    )


def test_the_client_guard_catches_both_spellings(tmp_path):
    """Feed the guard each regression and assert it fails on both."""
    global REPO_ROOT, _CLIENT_PROVISIONING_SITES
    original_root, original_sites = REPO_ROOT, _CLIENT_PROVISIONING_SITES
    probe = tmp_path / "probe.py"
    REPO_ROOT, _CLIENT_PROVISIONING_SITES = tmp_path, ("probe.py",)
    try:
        # The create-vals spelling.
        probe.write_text(
            'Client.create({"client_id": c, "user_id": admin.id})\n',
            encoding="utf-8")
        with pytest.raises(AssertionError, match="pointed at Administrator"):
            test_no_api_client_is_provisioned_as_admin("probe.py")

        # The attribute spelling — the one the grep version missed.
        probe.write_text(
            'rec.user_id = env.ref("base.user_admin")\n', encoding="utf-8")
        with pytest.raises(AssertionError, match="pointed at Administrator"):
            test_no_api_client_is_provisioned_as_admin("probe.py")

        # And an ordinary ORM domain must NOT trip it.
        probe.write_text(
            'Token.search([("user_id", "=", uid), ("revoked", "=", False)])\n',
            encoding="utf-8")
        test_no_api_client_is_provisioned_as_admin("probe.py")
    finally:
        REPO_ROOT, _CLIENT_PROVISIONING_SITES = original_root, original_sites


def test_the_client_provisioning_sites_still_exist():
    """A rename would make the guard above scan nothing and pass."""
    for relpath in _CLIENT_PROVISIONING_SITES:
        path = REPO_ROOT / relpath
        assert path.exists(), (
            f"{relpath} moved — update _CLIENT_PROVISIONING_SITES")
        assert "myservice.api.client" in path.read_text(encoding="utf-8"), (
            f"{relpath} no longer provisions API clients — update "
            "_CLIENT_PROVISIONING_SITES to wherever it moved")


def test_no_scope_grants_an_api_client_system_administrator():
    """`admin` is a token wildcard; it must not mint `base.group_system`.

    `SCOPE_GROUPS` is deliberately not the inverse of `GROUP_SCOPES`, which
    does map `base.group_system` to `admin`. Inverting it would mean a scope
    string typed into a form could provision a system administrator — the
    escalation the empty-scopes guard above exists to stop, arriving by the
    other door.
    """
    source = (REPO_ROOT
              / "myservice_api/controllers/utils.py").read_text(encoding="utf-8")
    start = source.index("SCOPE_GROUPS = {")
    table = source[start:source.index("\n}", start)]
    assert "group_system" not in table, (
        "SCOPE_GROUPS maps a scope to base.group_system. An API client's user "
        "must never be provisioned as a system administrator from its scope "
        "string; the `admin` wildcard lives in the token, where require_jwt "
        "can see it."
    )


# ─── the envelope's error codes must be reachable ────────────────────
#
# Odoo 19's exception hierarchy is a trap the envelope walked into:
#
#     AccessError.__mro__     -> AccessError, UserError, Exception
#     MissingError.__mro__    -> MissingError, UserError, Exception
#     ValidationError.__mro__ -> ValidationError, UserError, Exception
#
# All three are subclasses of `UserError`. So a handler chain that catches
# `UserError` before them never reaches them, and `cadra_route` did exactly
# that — `except (UserError, ValidationError)` sat first and the `AccessError`
# and `MissingError` clauses below it were dead code. Two published error
# codes, `forbidden` and `not_found`, were unreachable through that path.
#
# Rule 1 says the API is a contract and Vendra branches on `error.code`. An
# authorisation failure reporting itself as `validation_failed` tells an
# integrator to fix their payload when the answer is to fix their credentials;
# a missing record reporting the same tells them to fix a field that is fine.
#
# This is a parse, not a grep: the ordering is what matters and only the AST
# knows the order.

_USER_ERROR_SUBCLASSES = ("AccessError", "MissingError", "ValidationError")


def _handler_names(handler):
    """Every exception name a single `except (...)` clause catches."""
    node = handler.type
    if node is None:
        return ["BaseException"]
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    names = []
    for part in parts:
        # `except UserError:` and `except odoo.exceptions.UserError:` are the
        # same clause. Matching only ast.Name would let the dotted spelling
        # both escape the check and fail to register as the shadow.
        if isinstance(part, ast.Name):
            names.append(part.id)
        elif isinstance(part, ast.Attribute):
            names.append(part.attr)
    return names


def test_a_user_error_handler_never_shadows_a_more_specific_one():
    """`except UserError` before `except AccessError` makes the second dead."""
    offenders = []
    for module_dir in _first_party_modules():
        for path in sorted(module_dir.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                seen_user_error_at = None
                for handler in node.handlers:
                    names = _handler_names(handler)
                    specific = [n for n in names if n in _USER_ERROR_SUBCLASSES]
                    if seen_user_error_at is not None and specific:
                        offenders.append(
                            "%s:%d  `except %s` is unreachable — `UserError` "
                            "was already caught on line %d"
                            % (path.relative_to(REPO_ROOT), handler.lineno,
                               "/".join(specific), seen_user_error_at))
                    if "UserError" in names:
                        seen_user_error_at = handler.lineno

    assert not offenders, (
        "an exception handler is shadowed by an earlier `except UserError`. "
        "In Odoo 19 AccessError, MissingError and ValidationError all "
        "subclass UserError, so the broad clause must come LAST or the "
        "specific ones never run:\n  " + "\n  ".join(offenders) + "\n\n"
        "For an API route this silently collapses `forbidden` (403) and "
        "`not_found` (404) into `validation_failed` (400) — three published "
        "error codes becoming one, with no test going red."
    )


# ─── every controller read runs as itself or as sudo, on purpose ─────
#
# The three `myservice.dashboard` routes were the only ones in the API that
# did not `sudo()`. `get_kpis` reads `fleet.vehicle` and `generic.location`
# directly, so a caller holding `dashboards:read` without the matching Odoo
# groups hit an AccessError — which, per the guard above, surfaced as
# `400 validation_failed` naming an Odoo group in the published envelope.
#
# They sudo() now, which makes the declared scope the gate here as it is
# everywhere else. `utils.SCOPE_GROUPS` still derives the groups from the
# scope; that is the belt, this is the braces, and this guard keeps the
# braces on — removing the sudo() would restore the leak without any test
# noticing, because the groups make it work for a client token either way.

def test_the_dashboard_routes_sudo():
    source = (REPO_ROOT
              / "myservice_api/controllers/v1.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    unsudoed = []
    for node in ast.walk(tree):
        # request.env["myservice.dashboard"].<method>()  — the receiver of the
        # call is an Attribute on a Subscript unless `.sudo()` intervenes.
        if not isinstance(node, ast.Attribute):
            continue
        target = node.value
        if not (isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "myservice.dashboard"):
            continue
        if node.attr != "sudo":
            unsudoed.append("v1.py:%d  .%s() on an un-sudoed dashboard env"
                            % (node.lineno, node.attr))

    assert not unsudoed, (
        "a myservice.dashboard route reads without sudo(). The scope is the "
        "gate on these routes; an Odoo group acting as a second, undeclared "
        "gate behind a declared scope is the defect, not the "
        "protection:\n  " + "\n  ".join(unsudoed)
    )


# ─── the cluster-touching workflows queue behind each other ──────────
#
# `upgrade-19` scales `odoo-19` to zero for the duration of a schema upgrade,
# `tenant-cutover-19` does a `rollout restart` on it, and `deploy-dev` /
# `deploy-19` now END by reading the RUNNING `odoo-19` pod to prove the
# ConfigMaps they just applied actually took effect (handoff 10 Part B).
#
# Those two facts do not compose. A deploy whose guard reads the pod while an
# upgrade has scaled it to zero fails with a question about whether the pod is
# up, not an answer about the config — and the answer to a question that shape
# is always "re-run it", which is how a config that never took effect gets
# waved through by the very guard written to catch it.
#
# One queue for everything that takes `odoo-19` down and up. The guard is on
# the *set*: a fifth workflow that rolls the Deployment and quietly gets its
# own group is the failure this exists to catch, so membership is derived from
# what a workflow does to `odoo-19`, never from a hand-kept list of names.

CLUSTER_DEPLOY_GROUP = "cadra-cluster-deploy"

# Anything that takes the shared odoo-19 Deployment down and up, or waits on
# it doing so. `scale` (upgrade-19), `rollout restart` (tenant-cutover-19) and
# `rollout status` (both deploys, which wait for the roll they just applied
# and then exec into the pod it produced) are the three spellings in use.
# Deliberately NOT matched: a plain `kubectl exec` into odoo-19. db-query,
# audit-tenant and set-tenant-company all do that to read a tenant, and
# queueing a 20-second query behind a 40-minute deploy would be a worse
# workflow, not a safer one.
_ROLLS_ODOO_19 = re.compile(
    r"kubectl[^\n]*\b(?:scale|rollout\s+(?:restart|status))\b"
    r"[^\n]*\bdeployment/odoo-19\b"
)

# `concurrency:` at column 0, then its `group:` key. These are our own files
# and PyYAML is not a test dependency; a two-line regex beats adding one.
_CONCURRENCY_GROUP = re.compile(
    r"^concurrency:\s*$\n(?:^\s+#[^\n]*$\n)*^\s+group:\s*(\S+)\s*$",
    re.MULTILINE,
)


def _workflow_concurrency_group(text):
    match = _CONCURRENCY_GROUP.search(text)
    return match.group(1) if match else None


def test_every_workflow_that_rolls_odoo_19_shares_one_concurrency_group():
    workflows = sorted((REPO_ROOT / ".github/workflows").glob("*.yml"))
    assert workflows, "no workflows found — has the path moved?"

    offenders = []
    rollers = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if not _ROLLS_ODOO_19.search(text):
            continue
        rollers.append(path.name)
        group = _workflow_concurrency_group(text)
        if group != CLUSTER_DEPLOY_GROUP:
            offenders.append("%s  group: %s" % (path.name, group))

    assert len(rollers) >= 3, (
        "expected at least the three deploy workflows to roll odoo-19; found "
        "%r. If the kubectl spelling changed, this guard has stopped looking "
        "at anything." % (rollers,)
    )
    assert not offenders, (
        "a workflow takes the odoo-19 Deployment down and up but does not "
        "queue behind the others. Two of these at once and the ConfigMap "
        "guard reads a pod that is being replaced under it:\n  "
        + "\n  ".join(offenders)
    )


def test_the_concurrency_guard_would_have_caught_the_split_groups(tmp_path):
    """The pre-R55 state: each workflow with its own group."""
    before = (
        "on:\n  workflow_dispatch:\n\n"
        "concurrency:\n  group: upgrade-19\n  cancel-in-progress: false\n\n"
        "jobs:\n  upgrade:\n    steps:\n"
        "      - run: kubectl -n cadra-dev scale deployment/odoo-19 --replicas=0\n"
    )
    assert _ROLLS_ODOO_19.search(before), "the detector missed a scale-to-zero"
    assert _workflow_concurrency_group(before) == "upgrade-19"
    assert _workflow_concurrency_group(before) != CLUSTER_DEPLOY_GROUP

    after = before.replace("group: upgrade-19", "group: " + CLUSTER_DEPLOY_GROUP)
    assert _workflow_concurrency_group(after) == CLUSTER_DEPLOY_GROUP

    # A comment block between `concurrency:` and `group:` is what we ship.
    commented = after.replace(
        "concurrency:\n", "# why this queues\nconcurrency:\n  # R55\n", 1)
    assert _workflow_concurrency_group(commented) == CLUSTER_DEPLOY_GROUP


# ─── nothing registers a screen that cannot be opened ────────────────
#
# Handoff 11 R54: "a menu that opens a broken screen is worse than an absent
# one". The two halves of a client action live in different files and nothing
# joined them up:
#
#   * `myservice_security` shipped two JS files registering three tags whose
#     `ir.actions.client` records were deleted in 17aba57 and whose bundle
#     entries went with them. Dead for four months, silently.
#   * `myservice_fleet_maintenance` shipped the opposite defect — the JS WAS
#     bundled and registered `myservice_fleet_dashboard` on every backend page
#     load, and no action record anywhere carries that tag.
#
# So the guard is a two-way join over the pair. A tag registered by a bundled
# file with no action is a screen nobody can open; an action naming a tag no
# bundled file registers is a menu entry that opens an "invalid action" error.
# Both are the same defect seen from opposite ends, and neither is visible in
# a diff of either file alone.
#
# Bundled-ness is the hinge: retiring a screen here means dropping it from the
# manifest and leaving the source in place, so a guard that grepped the JS
# tree would fail on exactly the files we deliberately retired.

_ACTION_REGISTRY_ADD = re.compile(
    r"action_registry\.add\(\s*['\"]([A-Za-z0-9_.]+)['\"]")
# <field name="tag">some_tag</field> inside an ir.actions.client record.
_CLIENT_ACTION_RECORD = re.compile(
    r"<record[^>]*model=[\"']ir\.actions\.client[\"'][^>]*>(.*?)</record>",
    re.DOTALL)
_TAG_FIELD = re.compile(r"<field[^>]*name=[\"']tag[\"'][^>]*>([^<]+)</field>")


def _bundled_asset_paths():
    """Every asset path named by one of our own module manifests."""
    paths = set()
    for manifest in sorted(REPO_ROOT.glob("myservice_*/__manifest__.py")):
        try:
            data = ast.literal_eval(manifest.read_text(encoding="utf-8"))
        except (ValueError, SyntaxError):  # pragma: no cover - a broken manifest
            continue
        for entries in (data.get("assets") or {}).values():
            for entry in entries:
                # ('prepend', 'path') / ('append', 'path') as well as 'path'.
                if isinstance(entry, (tuple, list)):
                    entry = entry[-1]
                if isinstance(entry, str):
                    paths.add(entry)
    return paths


def _registered_client_action_tags():
    """tag -> the bundled JS file that registers it."""
    bundled = _bundled_asset_paths()
    found = {}
    for js in sorted(REPO_ROOT.glob("myservice_*/static/src/js/*.js")):
        rel = js.relative_to(REPO_ROOT).as_posix()
        if rel not in bundled:
            continue  # retired in place, on purpose — see the manifests.
        for tag in _ACTION_REGISTRY_ADD.findall(js.read_text(encoding="utf-8")):
            found[tag] = rel
    return found


def _declared_client_action_tags():
    """tag -> the XML file whose ir.actions.client record declares it."""
    found = {}
    for xml in sorted(REPO_ROOT.glob("myservice_*/**/*.xml")):
        if "/static/" in xml.as_posix():
            continue
        text = xml.read_text(encoding="utf-8", errors="replace")
        if "ir.actions.client" not in text:
            continue
        for body in _CLIENT_ACTION_RECORD.findall(text):
            tag = _TAG_FIELD.search(body)
            if tag:
                found[tag.group(1).strip()] = xml.relative_to(REPO_ROOT).as_posix()
    return found


def test_every_bundled_client_action_has_an_action_record():
    registered = _registered_client_action_tags()
    declared = _declared_client_action_tags()

    assert len(registered) >= 5, (
        "expected at least the five live legacy dashboards to register a "
        "client action; found %r. If the registration spelling changed, this "
        "guard has stopped looking at anything." % (sorted(registered),))

    orphans = ["%s  registered by %s" % (tag, path)
               for tag, path in sorted(registered.items())
               if tag not in declared]
    assert not orphans, (
        "a bundled JS file registers a client action that no "
        "ir.actions.client record dispatches to. It ships to every browser "
        "on every backend page load for a screen nobody can open — retire it "
        "from the manifest (see docs/retired-screens.md) or give it an "
        "action:\n  " + "\n  ".join(orphans))


def test_every_client_action_record_has_a_bundled_registration():
    registered = _registered_client_action_tags()
    declared = _declared_client_action_tags()

    assert len(declared) >= 5, (
        "expected at least five ir.actions.client records; found %r"
        % (sorted(declared),))

    unbacked = ["%s  declared in %s" % (tag, path)
                for tag, path in sorted(declared.items())
                if tag not in registered]
    assert not unbacked, (
        "an ir.actions.client record names a tag that no BUNDLED JS file "
        "registers. Whatever menu points at it opens an 'invalid action' "
        "error — which is the state R54 exists to prevent:\n  "
        + "\n  ".join(unbacked))


@pytest.mark.parametrize("tag", [
    "nrs_security_command_center",
    "nrs_case_management",
    "myservice_security_dashboard",
    "myservice_fleet_dashboard",
])
def test_the_retired_screens_stay_retired(tag):
    """Retired in place: the source is kept, the bundle entry is not.

    Re-adding one of these files to a manifest without also giving it an
    action record puts it straight back to shipping to every browser for a
    screen nobody can open — so this asserts the retirement itself, not just
    the consistency the two guards above check.
    """
    assert tag not in _registered_client_action_tags(), (
        "%s is registered by a bundled file again. If it is genuinely being "
        "revived, it needs an ir.actions.client record and a menu in the same "
        "change, and this case should be deleted — see docs/retired-screens.md"
        % tag)


# ─── the total is never derived from a capped search ─────────────────
#
# `paginate()` used to report `len(search(domain, limit=EXTERNAL_TOTAL_CAP))`
# as `total_estimate`, so an external token asking for 2,363 assets received
# 100 rows, `next_cursor: null`, and `total_estimate: 100`. Nothing about
# that response looks wrong. An auditor who exports 100 rows and is told
# there are 100 has been handed a false statement by a government system,
# and neither they nor we would ever find out.
#
# A behavioural test proves the number is right today. This one is here to
# stop the shape coming back: it reads the STRUCTURE of paginate() and
# insists there is exactly one count, that it is taken on the caller's own
# unclamped domain, and that every return path returns that one value —
# so a future "just cap it here too" cannot pass by adding a branch.

_UTILS = REPO_ROOT / "myservice_api" / "controllers" / "utils.py"


def _paginate_ast():
    tree = ast.parse(_UTILS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "paginate":
            return node
    raise AssertionError(
        "myservice_api/controllers/utils.py no longer defines paginate(). "
        "If it was renamed, this guard has stopped looking at anything — "
        "point it at the new name.")


def test_paginate_counts_exactly_once_and_on_the_uncapped_domain():
    fn = _paginate_ast()
    counts = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute)
              and n.func.attr == "search_count"]

    assert len(counts) == 1, (
        "paginate() makes %d search_count calls; expected exactly 1. Two "
        "counts means two answers, and the caller cannot tell which one the "
        "response carries." % len(counts))

    arg = counts[0].args[0] if counts[0].args else None
    assert isinstance(arg, ast.Name) and arg.id == "domain", (
        "paginate() counts something other than the caller's own `domain` "
        "(got %r). Counting `effective_domain` — which carries the cap's "
        "`('id','in',allowed.ids)` leaf — is exactly the bug: it reports the "
        "size of the window as the size of the register."
        % (ast.dump(arg) if arg is not None else None))


def test_paginate_returns_that_one_count_on_every_path():
    fn = _paginate_ast()

    # The name search_count's result is bound to.
    counts = [n for n in ast.walk(fn)
              if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Attribute)
              and n.value.func.attr == "search_count"]
    assert len(counts) == 1 and len(counts[0].targets) == 1, (
        "expected the single search_count in paginate() to be assigned to "
        "exactly one name")
    total_name = counts[0].targets[0]
    assert isinstance(total_name, ast.Name)
    total_name = total_name.id

    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert len(returns) >= 2, (
        "expected paginate() to keep its early-return path; found %d returns"
        % len(returns))

    for ret in returns:
        assert isinstance(ret.value, ast.Tuple) and len(ret.value.elts) == 3, (
            "every paginate() return must be the 3-tuple "
            "(records, next_cursor, total_estimate)")
        third = ret.value.elts[2]
        assert isinstance(third, ast.Name) and third.id == total_name, (
            "a paginate() return on line %d reports %r as the total instead "
            "of %r. Every path returns the same true count — including the "
            "early return taken when the capped window is empty, which used "
            "to hard-code 0."
            % (ret.lineno,
               ast.unparse(third) if hasattr(ast, "unparse") else "?",
               total_name))


def test_the_record_cap_is_not_read_straight_from_the_aud_claim():
    """The cap must key off the client record, not off `aud`.

    `aud` is stamped only by POST /auth/login, so keying the paywall on it
    alone enforced "browsers are trusted, programs are not" when the rule
    intended was "our own systems are trusted, third parties are not" — and
    it pointed the partner cap at Vendra and at the audit client, both of
    which hold machine credentials. `_request_is_frontend()` survives as a
    second route to uncapped; what must not come back is it being the only
    one.
    """
    source = _UTILS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "record_cap"),
              None)
    assert fn is not None, (
        "utils.record_cap() is gone. It is the single place the cumulative "
        "record cap is decided; if it moved, move this guard with it.")

    body = ast.dump(fn)
    assert "CLAIM_TOTAL_RECORD_CAP" in body, (
        "record_cap() no longer consults the per-client claim, so the cap is "
        "back to being decided by whether the caller looks like a browser.")


# ─── a count derived from a capped window ────────────────────────────
#
# Handoff 12 found six places where a number published to a caller was
# `len()` over a `search(..., limit=N)`. Two were in myservice_api and were
# fixed there; handoff 13 fixed the other four. The interesting part is not
# the four — it is the fifth, which nobody has written yet.
#
# The defect has a shape, and the shape is mechanical: a name bound to a
# LIMITED search, and a COUNT taken from it. It reaches a published payload
# three ways, and all three were live in this repo:
#
#     all_open = Req.search(domain, limit=500)
#     kpis['open'] = len(all_open)                      # direct
#     kpis['overdue'] = len(all_open.filtered(...))     # through a filter
#     for r in all_open: tally[k] = tally.get(k, 0) + 1 # through a tally
#
# What the AST genuinely cannot tell is a "how many are there" from a "how
# many did I just fetch" — `len(records) > limit` inside a paginator is the
# correct code, and it has the identical shape. So the guard does not try:
# it flags the shape and requires the author to say, on the line, that this
# one counts the page on purpose:
#
#     has_more = len(records) > limit   # capped-count-ok: the page size
#
# A waiver that has to be written out is the point. It turns a silent wrong
# number into a sentence somebody chose to write.

_CAPPED_COUNT_WAIVER = "capped-count-ok"


def _limited_search(node):
    """A `.search(...)` / `.search_read(...)` carrying a non-zero limit."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in ("search", "search_read"):
        return False
    for keyword in node.keywords:
        if keyword.arg == "limit" and not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value in (None, 0)):
            return True
    # search(domain, offset, limit, order) positionally.
    return node.func.attr == "search" and len(node.args) >= 3


def _holds_limited_search(node):
    return any(_limited_search(child) for child in ast.walk(node))


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _bound_names(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def _root_name(node):
    """The name at the root of `x`, `x.filtered(...)`, `x[:30]`, `x.ids`."""
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            return None


class _CappedCountScan:
    """Walk one file's functions in SOURCE ORDER, tracking which names hold
    a capped window.

    In order, and with a kill on rebinding, because these controllers reuse
    `v` and `r` across three loops in one function. A flow-insensitive
    version flagged an honest tally forty lines below an unrelated capped
    search, purely because the loop variable had the same name.
    """

    def __init__(self, source):
        self.lines = source.splitlines()
        self.findings = []

    def _waived(self, lineno):
        """The line itself, or the comment block IMMEDIATELY above it.

        Contiguous, so a waiver cannot drift onto a statement it was never
        written for: the moment a line of code lands between the comment
        and the count, the waiver stops applying and the guard speaks up.
        """
        if _CAPPED_COUNT_WAIVER in self.lines[lineno - 1]:
            return True
        index = lineno - 2
        while index >= 0 and self.lines[index].strip().startswith("#"):
            if _CAPPED_COUNT_WAIVER in self.lines[index]:
                return True
            index -= 1
        return False

    def _flag(self, node, why):
        if not self._waived(node.lineno):
            self.findings.append((node.lineno, why))

    def _expressions(self, node, capped):
        for child in ast.walk(node):
            if not (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "len" and child.args):
                continue
            arg = child.args[0]
            if _holds_limited_search(arg):
                self._flag(child, "len() of a limited search")
            elif _root_name(arg) in capped:
                self._flag(child, "len() of %s, a capped window"
                                  % _root_name(arg))
            elif isinstance(arg, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                if any(_holds_limited_search(gen.iter)
                       or (_names_in(gen.iter) & set(capped))
                       for gen in arg.generators):
                    self._flag(child, "len() of a comprehension over a "
                                      "capped window")

    def block(self, body, capped):
        for statement in body:
            self.statement(statement, capped)

    def statement(self, node, capped):
        if isinstance(node, ast.Assign):
            self._expressions(node.value, capped)
            hot = _holds_limited_search(node.value) or bool(
                _names_in(node.value) & set(capped))
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if (_root_name(target) in capped
                            and isinstance(node.value, ast.BinOp)
                            and isinstance(node.value.op, ast.Add)
                            and isinstance(node.value.right, ast.Constant)
                            and node.value.right.value == 1):
                        self._flag(node, "a tally over a capped window")
                    continue
                for name in _bound_names(target):
                    if hot:
                        capped[name] = node.lineno
                    else:
                        capped.pop(name, None)
        elif isinstance(node, ast.AugAssign):
            self._expressions(node.value, capped)
            if (_root_name(node.target) in capped
                    and isinstance(node.op, ast.Add)
                    and isinstance(node.value, ast.Constant)
                    and node.value.value == 1):
                self._flag(node, "a tally over a capped window")
        elif isinstance(node, ast.For):
            self._expressions(node.iter, capped)
            hot = _holds_limited_search(node.iter) or bool(
                _names_in(node.iter) & set(capped))
            for name in _bound_names(node.target):
                if hot:
                    capped[name] = node.lineno
                else:
                    capped.pop(name, None)
            if hot:
                # Anything the loop APPENDS TO or keys into is being built
                # out of the window, so it inherits the window's blindness.
                for child in ast.walk(node):
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and child.func.attr in ("append", "extend", "add",
                                                    "update", "setdefault")):
                        root = _root_name(child.func.value)
                        if root:
                            capped.setdefault(root, child.lineno)
                    if isinstance(child, (ast.Assign, ast.AugAssign)):
                        targets = list(getattr(child, "targets", []))
                        if getattr(child, "target", None) is not None:
                            targets.append(child.target)
                        for target in targets:
                            if isinstance(target, ast.Subscript):
                                root = _root_name(target)
                                if root:
                                    capped.setdefault(root, child.lineno)
            self.block(node.body, capped)
            self.block(node.orelse, capped)
        elif isinstance(node, (ast.If, ast.While)):
            self._expressions(node.test, capped)
            self.block(node.body, capped)
            self.block(node.orelse, capped)
        elif isinstance(node, ast.Try):
            self.block(node.body, capped)
            for handler in node.handlers:
                self.block(handler.body, capped)
            self.block(node.orelse, capped)
            self.block(node.finalbody, capped)
        elif isinstance(node, ast.With):
            self.block(node.body, capped)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.block(node.body, {})
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self._expressions(child, capped)


def _capped_count_findings(source):
    """[(lineno, why)] for one module's source."""
    scan = _CappedCountScan(source)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan.block(node.body, {})
    return sorted(set(scan.findings))


def test_no_published_count_is_taken_from_a_capped_window():
    """The whole first-party tree, by shape rather than by a list of files.

    A pinned list of the four known sites would have closed handoff 13 and
    caught nothing afterwards. This is what stops the fifth one.
    """
    offenders = []
    for path in _first_party_python_files():
        if "/tests/" in str(path):
            continue
        findings = _capped_count_findings(path.read_text(encoding="utf-8"))
        for lineno, why in findings:
            offenders.append("%s:%d — %s"
                             % (path.relative_to(REPO_ROOT), lineno, why))

    assert not offenders, (
        "a number that describes the register is being derived from a "
        "bounded fetch:\n  " + "\n  ".join(offenders)
        + "\n\nCount it with search_count() or _read_group() on the "
          "unclamped domain. If this one genuinely counts the rows just "
          "fetched — a page size, a 'the window was full so ask for another "
          "pass' — say so on the line with a `%s:` comment."
        % _CAPPED_COUNT_WAIVER)


# The four shapes, written as they actually appeared before handoff 13. A
# guard that has never been seen to fail is a decoration.
_HANDOFF_13_SHAPES = [
    ("A2 — the FM KPIs", """
def dashboard_data(self):
    all_open = Req.search([('closed', '=', False)], limit=500)
    overdue = all_open.filtered(lambda r: r.deadline_date < today)
    return {'open': len(all_open), 'overdue': len(overdue)}
""", 2),
    ("A1 — sla_pct", """
def dashboard_data(self):
    all_open = Req.search([('closed', '=', False)], limit=500)
    groups = {}
    for r in all_open:
        groups.setdefault(r.category_id.name, []).append(r)
    for name in groups:
        reqs = groups.get(name, [])
        total = len(reqs)
        ov = len([r for r in reqs if r.deadline_date < today])
""", 2),
    ("A3 — the fleet breakdown", """
def fleet_dashboard_data(self):
    vehicles = Vehicle.search([('active', '=', True)], order='name', limit=100)
    state_counts = {}
    for v in vehicles:
        state = v.state_id.name if v.state_id else 'Unknown'
        state_counts[state] = state_counts.get(state, 0) + 1
""", 1),
    ("A4 — kpis.vendors", """
def get_fleet_command(self):
    vendors = []
    for v in self.env['fleet.service.vendor'].search([], limit=6):
        vendors.append({'id': v.id})
    return {'kpis': {'vendors': len(vendors)}}
""", 1),
]


@pytest.mark.parametrize("label,source,expected",
                         _HANDOFF_13_SHAPES,
                         ids=[s[0] for s in _HANDOFF_13_SHAPES])
def test_the_guard_would_have_caught_handoff_13(label, source, expected):
    findings = _capped_count_findings(source)
    assert len(findings) >= expected, (
        "%s: the guard found %d of the %d counts in this shape — it would "
        "have let the defect through.\n%s"
        % (label, len(findings), expected, findings))


_HONEST_SHAPES = [
    ("the page size, waived", """
def paginate(model, domain):
    records = model.search(domain, limit=limit + 1)
    has_more = len(records) > limit   # capped-count-ok: the page, not the register
"""),
    ("a count over an unclamped domain", """
def kpis(self):
    return {'open': Req.search_count([('closed', '=', False)])}
"""),
    ("a grouped count", """
def sla(self):
    return dict(Req._read_group([('closed', '=', False)], ['category_id'], ['__count']))
"""),
    ("a tally over an unlimited search", """
def by_make(self):
    counts = {}
    for v in Vehicle.search([]):
        counts[v.brand_id.name] = counts.get(v.brand_id.name, 0) + 1
"""),
    ("a loop variable reused after the capped one is done", """
def mixed(self):
    recent = Vehicle.search([], order='name', limit=10)
    for v in recent:
        pass
    counts = {}
    for v in Vehicle.search([]):
        counts[v.id] = counts.get(v.id, 0) + 1
"""),
]


@pytest.mark.parametrize("label,source", _HONEST_SHAPES,
                         ids=[s[0] for s in _HONEST_SHAPES])
def test_the_guard_is_not_fooled_into_flagging_honest_code(label, source):
    findings = _capped_count_findings(source)
    assert not findings, (
        "%s: the guard flagged correct code %s. A guard that cries wolf "
        "gets waived everywhere, which is the same as not having it."
        % (label, findings))


def test_the_waiver_has_to_be_written_out():
    """Remove the comment and the same line fails. Otherwise the waiver is
    decoration and the guard is asserting nothing."""
    waived = """
def paginate(model, domain):
    records = model.search(domain, limit=limit + 1)
    has_more = len(records) > limit   # capped-count-ok: the page, not the register
"""
    assert not _capped_count_findings(waived)
    assert _capped_count_findings(
        waived.replace("   # capped-count-ok: the page, not the register", ""))


# ─── a catch-all that cannot say what it is hiding ───────────────────
#
# `except Exception: pass` and `except Exception: return []` are the worst
# of the family this repo has spent three handoffs on. A capped count is at
# least a number, and somebody might notice it stop moving. This returns
# "there are none" — a complete, confident, wrong answer — and it survives
# forever: `kpis.vendors` told every tenant "No approved vendors yet" for
# three years because a field had been renamed, and nothing anywhere said
# so.
#
# The work is not "remove them". Some are load-bearing for tenants without
# the fleet or asset modules, and turning those into hard failures would
# break working installations. The work is to make every one answer the
# question WHAT IS THIS HIDING, and the answer has to be visible where the
# code is rather than in a document nobody opens beside it.
#
# So this guard is an INVENTORY, pinned by a comment at each site, and every
# entry carries one of three words:
#
#   optional — the failure is expected and benign (a module that may not be
#              installed, a caller's malformed input). Prefer deleting the
#              handler: `env.get('some.model')` answers None and
#              `'some.model' in self.env` works. Where one must stay, narrow
#              the type so it cannot hide a typo.
#   reported — not optional. It raises, or it logs at WARNING and returns
#              something that ADMITS the gap. An empty panel is a lie.
#   unknown  — genuinely nobody knows what can arrive here. Logged at
#              WARNING with the traceback so the next person gets a line
#              instead of silence. The fallback, not the default.
#
# A narrowed handler needs no marker, because it is no longer a catch-all —
# which is the outcome this guard is trying to produce, not to police.
#
# Same convention as `capped-count-ok:` above, deliberately: a second
# mechanism for the same job is a second thing to forget. And the same
# argument for why it is a sentence somebody has to write rather than a
# central list — a list lives away from the code, so it is updated by
# whoever remembers it exists, and the handler it describes is edited by
# whoever does not.

# SCOPE, stated because a guard whose reach nobody knows is worse than one
# that admits its edge — and kept as a COUNT, because the only reading of a
# green run that this guard cannot survive is "there are none".
#
# It walks `_catch_all_python_files()`: the first-party Odoo modules, plus
# `scripts/**/*.py` and the loader scripts at the repo root. `scripts/` is
# inside because `scripts/bootstrap.py` provisions the credentials every
# tenant authenticates with, and a provisioning script that swallows a
# failure hands over a tenant that looks provisioned; the repo-root loaders
# are inside because they write the location, fleet and taxonomy data the
# register is built on, and a load that half-worked and said nothing is the
# same defect as a count that half-worked and said nothing.
#
# `seeds/` is deliberately OUT, and so are `tests/` and `docs/`. A one-shot
# tenant seed's `except: pass` around an `env.ref` is the genuinely optional
# case this convention says to NARROW rather than to annotate, so putting
# them in front of CI buys an annotation exercise and no guarantee.
#
# MEASURED 2026-09-09 (handoff 16 C3), with this file's own
# `_broad_handler_findings()`: **12 broad handlers remain outside the
# boundary and unclassified** — 9 in `seeds/` (nrs_asset_seed 4,
# nrs_fleet_seed 2, nrs_seed 3), 2 in `tests/conftest.py`, 1 in
# `docs/api/smoke_test.py`. A green run of this guard means "every broad
# handler INSIDE the boundary has been judged". It does not mean there are
# none. If that number is stale, re-measure it rather than delete it: the
# sentence is the only thing standing between a green tick and a false one.
_CATCH_ALL_MARKER = "catch-all:"
_CATCH_ALL_CLASSES = ("optional", "reported", "unknown")
_BROAD_EXCEPTIONS = {"Exception", "BaseException"}


# Trees that are somebody else's code or nobody's runtime, excluded wherever
# this guard reaches outside the Odoo modules.
_CATCH_ALL_SKIPPED_PARTS = frozenset({
    "dist", "crnd-19", "oca-19", "_to_delete", "_upgrade",
    ".venv", "node_modules", "__pycache__",
})


def _catch_all_python_files():
    """Everything this guard walks: the first-party Odoo modules, plus
    `scripts/**/*.py` and the loader scripts at the repo root.

    Deliberately its OWN collector rather than a widened
    `_first_party_python_files()`. That one is shared with the
    `_sql_constraints` guard and the capped-count guard, and both of those
    mean by it "code that runs inside a registry and serves requests".
    Widening it in place would silently change what two other guards assert
    — a boundary nobody chose, moved by a third guard's convenience — and
    the capped-count guard in particular would start reporting on one-shot
    loaders whose counts nothing is published from.

    `seeds/` is not here. See the SCOPE note above, which also carries the
    measured count of what that leaves out.
    """
    seen = set()
    for path in _first_party_python_files():
        seen.add(path)
        yield path

    extra = sorted((REPO_ROOT / "scripts").rglob("*.py")) \
        + sorted(REPO_ROOT.glob("*.py"))
    for path in extra:
        if path in seen:
            continue
        if set(path.relative_to(REPO_ROOT).parts) & _CATCH_ALL_SKIPPED_PARTS:
            continue
        seen.add(path)
        yield path


def _is_broad_handler(handler):
    """A handler that catches anything: `except:`, `except Exception:`, or a
    tuple with one of those in it."""
    if handler.type is None:
        return True
    caught = handler.type
    names = set()
    if isinstance(caught, ast.Name):
        names.add(caught.id)
    elif isinstance(caught, ast.Tuple):
        names.update(e.id for e in caught.elts if isinstance(e, ast.Name))
    elif isinstance(caught, ast.Attribute):     # e.g. builtins.Exception
        names.add(caught.attr)
    return bool(names & _BROAD_EXCEPTIONS)


def _marker_class(line):
    """The classification word on a line carrying the marker, or None."""
    index = line.find(_CATCH_ALL_MARKER)
    if index < 0:
        return None
    rest = line[index + len(_CATCH_ALL_MARKER):].strip()
    word = rest.split()[0].strip(".,:;—-") if rest else ""
    return word if word in _CATCH_ALL_CLASSES else ""


def _handler_marker(lines, handler):
    """The classification for `handler`, or None if it carries no marker.

    Three placements, all of which read naturally:

      - on the `except` line itself;
      - in the contiguous comment block IMMEDIATELY above it;
      - in the contiguous comment block that OPENS the handler body.

    Contiguity is what makes it safe. The moment a line of code lands
    between the comment and the `except`, the marker stops applying and the
    guard speaks up — the same rule as the capped-count waiver above, for
    the same reason.

    Contiguity ALONE is not enough, though, and this is the case that got
    past the first version: the comment block above an `except` is the TAIL
    OF THE TRY BODY. A comment written about the last statement inside the
    try would silently classify the handler underneath it —

        try:
            f()
            # a note about f(), indented into the try
        except Exception:
            pass

    — which is the drift this convention exists to prevent, arriving from
    the one direction nobody looks. So the block above must also be at the
    `except` keyword's OWN indentation. A comment inside the try is indented
    deeper and does not count.

    Known limit, stated rather than chased: a handler written as
    `E = Exception` then `except E:` is not seen as broad, here or by any
    other guard in this file. It is not a spelling anybody uses, and a guard
    that tried to follow assignments would be answering a question about
    aliasing rather than about exception handling.
    """
    found = _marker_class(lines[handler.lineno - 1])
    if found is not None:
        return found

    handler_indent = len(lines[handler.lineno - 1]) - len(
        lines[handler.lineno - 1].lstrip())
    index = handler.lineno - 2
    while index >= 0 and lines[index].strip().startswith("#"):
        if len(lines[index]) - len(lines[index].lstrip()) != handler_indent:
            break                       # inside the try body, not about this
        found = _marker_class(lines[index])
        if found is not None:
            return found
        index -= 1

    if handler.body:
        index = handler.lineno            # first line inside the handler
        stop = handler.body[0].lineno - 1
        while index < stop and index < len(lines):
            stripped = lines[index].strip()
            if not stripped:
                break
            if not stripped.startswith("#"):
                break
            found = _marker_class(lines[index])
            if found is not None:
                return found
            index += 1
    return None


def _broad_handler_findings(source):
    """(lineno, problem) for every broad handler without a valid marker."""
    lines = source.splitlines()
    findings = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler) or not _is_broad_handler(node):
            continue
        marker = _handler_marker(lines, node)
        if marker is None:
            findings.append((node.lineno, "no `catch-all:` classification"))
        elif marker == "":
            findings.append(
                (node.lineno,
                 "`catch-all:` is followed by something that is not one of %s"
                 % (", ".join(_CATCH_ALL_CLASSES))))
    return findings


def test_every_catch_all_says_what_it_is_hiding():
    """Every broad handler in our own code carries a classification.

    A new one that does not fails here. That is the whole mechanism: the
    shape is findable and whether a given one is LEGITIMATE is not, so the
    guard does not try to judge — it requires the author to have judged, in
    a sentence, on the line.
    """
    offenders = []
    for path in _catch_all_python_files():
        source = path.read_text(encoding="utf-8")
        try:
            findings = _broad_handler_findings(source)
        except SyntaxError:
            continue
        for lineno, problem in findings:
            offenders.append("%s:%d — %s"
                             % (path.relative_to(REPO_ROOT), lineno, problem))

    assert not offenders, (
        "%d broad exception handler(s) in the Odoo modules, in `scripts/` or "
        "in the repo-root loaders do not say what they are hiding (see the "
        "SCOPE note above — `seeds/`, `tests/` and `docs/` are not "
        "walked):\n  %s"
        "\n\nAdd one of `# catch-all: optional|reported|unknown — <why>` on "
        "the `except` line, in the comment block immediately above it, or in "
        "the comment block that opens the handler body. Better: narrow the "
        "exception type, or delete the handler — a narrowed one needs no "
        "marker because it is no longer a catch-all."
        % (len(offenders), "\n  ".join(offenders)))


def test_the_catch_all_guard_walks_the_boundary_it_claims():
    """A path typo would make the widened guard scan nothing and pass.

    Same failure mode as `test_guard_covers_the_modules_we_think_it_does`
    above, one boundary wider: this guard's whole value is the sentence in
    the SCOPE note saying where it stops, and a collector that quietly
    stopped somewhere else would make that sentence a lie without ever
    going red.
    """
    walked = {str(p.relative_to(REPO_ROOT)) for p in _catch_all_python_files()}

    # The Odoo modules, unchanged.
    assert any(f.startswith("myservice_api/") for f in walked)

    # `scripts/` — bootstrap.py provisions every tenant's credentials.
    assert "scripts/bootstrap.py" in walked, (
        "scripts/bootstrap.py is not walked. It provisions the credentials "
        "every tenant authenticates with; it is the reason `scripts/` is "
        "inside the boundary at all.")
    assert len([f for f in walked if f.startswith("scripts/")]) >= 15, (
        "only %d files under scripts/ — the rglob is wrong"
        % len([f for f in walked if f.startswith("scripts/")]))

    # The repo-root loaders.
    for loader in ("myservice_master_seed.py", "load_offices_v3.py",
                   "fleet_taxonomy_seed.py", "geocode_locations.py"):
        assert loader in walked, "%s is not walked" % loader

    # And `seeds/` is OUT, on purpose. If this ever starts failing because
    # somebody widened the collector, the SCOPE note's measured count above
    # is now wrong and has to move with it.
    assert not [f for f in walked if f.startswith("seeds/")], (
        "seeds/ is being walked. That is a real decision, not a tidy-up — "
        "update the SCOPE note's measured count and its reasoning before "
        "relaxing this.")
    # The repo-level `tests/` directory is out too — this file included.
    # (Module tests live at `myservice_*/tests/` and stay in scope.)
    assert not [f for f in walked if f.startswith("tests/")], (
        "the repo-level tests/ directory is being walked; the SCOPE note "
        "says it is not.")

    # Nothing vendored.
    for tree in ("dist/", "crnd-19/", "oca-19/"):
        assert not [f for f in walked if f.startswith(tree)], tree


def test_the_widened_guard_would_have_caught_the_loaders(tmp_path):
    """Proof by construction that the shape the widening exists to catch is
    the shape it catches — a repo-root loader that swallows a data write.

    Modelled on `load_offices.py`, which counts a failed create into the
    same tally as a row that already existed.
    """
    source = ("for row in rows:\n"
              "    try:\n"
              "        env['generic.location'].create(row)\n"
              "    except Exception:\n"
              "        skipped += 1\n")
    assert _broad_handler_findings(source)
    marked = source.replace(
        "    except Exception:",
        "    # catch-all: reported — printed and counted\n"
        "    except Exception:")
    assert not _broad_handler_findings(marked)


_CATCH_ALL_SHAPES = [
    ("a bare except", "try:\n    f()\nexcept:\n    pass\n"),
    ("except Exception", "try:\n    f()\nexcept Exception:\n    pass\n"),
    ("except BaseException", "try:\n    f()\nexcept BaseException:\n    pass\n"),
    ("Exception inside a tuple",
     "try:\n    f()\nexcept (ValueError, Exception):\n    pass\n"),
]


@pytest.mark.parametrize("label,source", _CATCH_ALL_SHAPES,
                         ids=[s[0] for s in _CATCH_ALL_SHAPES])
def test_the_catch_all_guard_finds_every_broad_spelling(label, source):
    assert _broad_handler_findings(source), (
        "%s went unnoticed. A guard that misses a spelling is an inventory "
        "with a hole in it, and the hole is where the next one lands."
        % label)


def test_a_narrowed_handler_needs_no_marker():
    """Because it is no longer a catch-all, which is the point."""
    assert not _broad_handler_findings(
        "try:\n    f()\nexcept (ValueError, KeyError):\n    pass\n")


def test_the_classification_has_to_be_one_of_the_three_words():
    """`# catch-all: probably fine` is a sentence, not a judgement."""
    assert _broad_handler_findings(
        "try:\n    f()\nexcept Exception:  # catch-all: probably fine\n"
        "    pass\n")


_MARKER_PLACEMENTS = [
    ("on the except line",
     "try:\n    f()\nexcept Exception:  # catch-all: unknown — why\n    pass\n"),
    ("in the block above",
     "try:\n    f()\n# catch-all: optional — why\nexcept Exception:\n    pass\n"),
    ("opening the handler body",
     "try:\n    f()\nexcept Exception:\n"
     "    # catch-all: reported — why\n    _logger.warning('x')\n"),
]


@pytest.mark.parametrize("label,source", _MARKER_PLACEMENTS,
                         ids=[s[0] for s in _MARKER_PLACEMENTS])
def test_the_three_placements_all_count(label, source):
    assert not _broad_handler_findings(source), label


def test_the_marker_cannot_drift_onto_a_handler_it_was_not_written_for():
    """Contiguity, same rule as the capped-count waiver.

    A comment separated from its `except` by a line of code is a comment
    about that line of code. Letting it waive the handler below would mean a
    marker keeps applying to whatever ends up under it after the next edit.
    """
    contiguous = ("try:\n    f()\n# catch-all: optional — why\n"
                  "except Exception:\n    pass\n")
    assert not _broad_handler_findings(contiguous)
    drifted = ("# catch-all: optional — why\nx = 1\ntry:\n    f()\n"
               "except Exception:\n    pass\n")
    assert _broad_handler_findings(drifted)


def test_a_comment_inside_the_try_body_does_not_classify_the_handler():
    """The block above an `except` IS the tail of the try body.

    A note written about the last statement inside the try is contiguous
    with the `except` below it, so contiguity alone let it classify a
    handler nobody had thought about. Indentation settles it: a comment
    inside the try is indented deeper than the `except` keyword.
    """
    inside = ("try:\n    f()\n    # catch-all: optional — about f(), not "
              "about the handler\nexcept Exception:\n    pass\n")
    assert _broad_handler_findings(inside), (
        "a comment indented into the try body classified the handler below "
        "it. That is the drift this convention exists to prevent, arriving "
        "from the one direction nobody looks.")


def test_a_starred_except_group_is_still_broad():
    """`except* Exception:` catches everything in the group."""
    assert _broad_handler_findings(
        "try:\n    f()\nexcept* Exception:\n    pass\n")


# ─── the retry layers Odoo owns above cadra_route ────────────────────
#
# Odoo recovers from two conditions by seeing an exception come OUT of the
# dispatch and replaying the request:
#
#   * `http.py` catches `ReadOnlySqlTransaction` and re-dispatches on a
#     read/write cursor, which is how a route that turns out to write on a
#     read-only cursor still succeeds;
#   * `service/model.retrying` catches `OperationalError` and
#     `ConcurrencyError` and replays up to five times on a serialization
#     failure, which is how two callers writing the same row both succeed.
#
# `cadra_route`'s `except Exception` sits INSIDE both, so swallowing either
# turns something Odoo fixes transparently into a `500 internal_error` the
# caller has to handle — and there is no way for the caller to tell it from
# a real fault.
#
# Found live: `POST /assets/<id>/transfer-custody` answered 500 in a run
# where `/auth/token`, which is NOT wrapped by this decorator, hit the same
# condition on the same cursor and retried into a 200. The unwrapped route
# was the one that worked, which is the wrong way round for a decorator
# whose job is to make the contract better.
#
# `IntegrityError` is deliberately absent: `retrying` re-raises it at once
# unless it is a serialization failure, and the envelope publishes 409 and
# 400 for unique and foreign-key violations.

_MUST_REACH_ODOO = ("ReadOnlySqlTransaction", "OperationalError",
                    "ConcurrencyError")


def _cadra_route_wrapper():
    tree = ast.parse(_UTILS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cadra_endpoint":
            return node
    raise AssertionError(
        "myservice_api/controllers/utils.py no longer defines "
        "cadra_endpoint(). It is where every route's exceptions are turned "
        "into the envelope; if it was renamed, move this guard with it.")


def test_the_envelope_lets_odoos_own_retries_through():
    """A clause that re-raises them, and it comes first."""
    fn = _cadra_route_wrapper()

    reraising = []
    for handler in (n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)):
        names = set(_handler_names(handler))
        if not names & set(_MUST_REACH_ODOO):
            continue
        body = handler.body
        assert len(body) == 1 and isinstance(body[0], ast.Raise) \
            and body[0].exc is None, (
            "the clause on line %d catches %s and then does something other "
            "than re-raise. These have to leave the decorator untouched: "
            "Odoo replays the request on them, and a bare `raise` is the "
            "only body that lets it."
            % (handler.lineno, sorted(names & set(_MUST_REACH_ODOO))))
        reraising.append((handler.lineno, names))

    covered = set()
    for _, names in reraising:
        covered |= names & set(_MUST_REACH_ODOO)
    missing = set(_MUST_REACH_ODOO) - covered
    assert not missing, (
        "cadra_endpoint() swallows %s. Odoo's own retry layers sit ABOVE "
        "this decorator and work by seeing the exception; enveloping it as "
        "a 500 removes a recovery the caller cannot perform itself."
        % ", ".join(sorted(missing)))

    # And it has to be FIRST, for the same reason the AccessError guard
    # above exists: `except psycopg2.OperationalError` under a broad clause
    # is a comment, not a handler.
    first_reraise = min(lineno for lineno, _ in reraising)
    for handler in (n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)):
        if handler.lineno >= first_reraise:
            continue
        names = set(_handler_names(handler))
        assert not (names & {"Exception", "BaseException"}), (
            "a broad handler on line %d sits ABOVE the re-raise clause on "
            "line %d, so the re-raise is dead code and Odoo never sees the "
            "exception." % (handler.lineno, first_reraise))



# ─────────────────────────────────────────────────────────────────────
# A credential may default to NOTHING. It may never default to SOMETHING.
# ─────────────────────────────────────────────────────────────────────
#
# Handoff 17 item B. Two routes that dump or write the whole employee and
# asset register resolved their credential like this:
#
#     get_param('myservice_identity.redhubs_api_key', 'NRS_REDHUBS_KEY_2025')
#     get_param('myservice_identity.sap_webhook_secret', 'NRS_SAP_..._2025')
#
# The second argument is the default. Measured on this machine before the
# fix: that parameter was set on ZERO of the eight local tenants, so the
# string standing between an anonymous caller and a full dump of the asset
# register was a literal committed to this repository — present in every
# clone, every fork and every CI log since it was written.
#
# **The guard is on the LOOKUP, not on the literal.** The handoff asked for
# a guard that spots "a literal that looks like a key", and that is the
# wrong axis: `get_param('web.base.url', 'http://localhost:8069')` is a
# perfectly good default that any entropy heuristic flags, while
# `get_param('...api_key', 'changeme')` is exactly as dangerous as the
# literal above and any entropy heuristic misses it. What makes a string
# dangerous is not how it looks. It is that a credential resolution falls
# back to it.
#
# So the rule is: when the thing being resolved is NAMED as a credential,
# a non-empty literal default fails. An empty default is fine and is what
# the rest of the codebase already does — `get_param("myservice_api.
# jwt_secret", "")` then refuses on the falsy value, which is the shape
# every credential should have.
#
# ── the first version of this guard was defeated six ways ──
#
# A verification pass wrote each of these against the guard and measured it
# accepting them. Every one is a spelling a person would reach for without
# meaning to evade anything, which is the point: a guard that only catches
# the exact keystrokes of the defect it was written for is a record of that
# defect, not a rule.
#
#   1. `get_param('x.api_key', default='NRS_KEY')` — the default passed by
#      keyword. Odoo's own signature is `get_param(self, key, default=False)`,
#      so this is the documented spelling and the guard read positional
#      arguments only.
#   2. `FALLBACK = 'NRS_KEY'` one line above, then passed by name. Module
#      constants were already resolved for the KEY and not for the default.
#   3. `get_param('x.api_key') or 'NRS_KEY'` — not a two-argument call at
#      all, and arguably the most natural way to write the defect. Note the
#      production code this guard exists for now uses the `value or None`
#      shape itself, so the pattern is live in this codebase.
#   4. `f'NRS_KEY_{2025}'` and `'NRS_' + 'KEY'` — a JoinedStr and a BinOp,
#      neither of which is an ast.Constant. An f-string with no literal text
#      at all (`f'{token}'`) bakes nothing in and is correctly ignored.
#   5. `read_config('x.api_key', 'NRS_KEY')` — the resolver name was a closed
#      list of three. See `_RESOLVER_RE` below for what replaced it and why
#      the check was not simply dropped.
#   6. `get_param(self.PARAM_NAME, ...)` and `get_param(PARAMS['api_key'],
#      ...)` — an Attribute or a Subscript where the guard expected a Name.
#      Both carry the credential's name in plain sight; read it off them the
#      same way a bare Name already was.

# ── what counts as a credential ──
#
# Matched case-insensitively against the NAME of the thing being resolved,
# never against the value. Three words are matched only as a whole segment,
# because as bare substrings they are wrong far more often than right:
#
#   `auth`  collides with `author_id`, `authority`, `authored`. Segmented it
#           still catches `x_auth_key`, `AUTH`, `auth-token`; `oauth` and
#           `authorization` are listed separately because they are single
#           words that unambiguously name a credential.
#   `pass`  collides with `bypass`, `compass`, `passenger`, `passive` — and
#           this is a facilities and fleet register, so those are words that
#           genuinely occur here.
#   `salt`  has no real collisions (`asphalt` and `assault` do not contain
#           it) but costs nothing to segment and removes the question.
#   `pw`    added in handoff 18, and it is the reason this list is a list and
#           not a finished thing. `ODOO_ADMIN_PW` — the exact name of the
#           credential baked into `Dockerfile.nrs-import` — matched NOTHING
#           here: `pwd` is listed, `pw` was not, and `password` does not
#           contain it. The guard read the Dockerfile correctly and called
#           the credential an ordinary variable. Segmented, because as a bare
#           substring it is inside `pwd` (already covered) and would fire on
#           any word containing those two letters.
#
# Deliberately absent, both from the verification pass's suggested list:
#
#   `webhook` alone. A webhook URL is not a credential and
#           `get_param('x.webhook_url', 'https://…')` is an ordinary
#           default; it is `webhook_secret` that matters, and `secret`
#           already catches that.
#   `-key` with a hyphen. `_key` is kept, but the hyphenated spelling is how
#           HTTP headers are written and adding it flagged
#           `headers.get('X-Idempotency-Key')` in docs/api/mock_sap.py.
#           An idempotency key is a de-duplication token, not a secret.
#           `X-API-Key` is still caught, by `api[_-]?key`.
#
# The bias is deliberate: a false positive costs a developer one waiver and
# a sentence; a false negative costs a credential. But only just — a guard
# that cries wolf is a guard somebody deletes, so `_key` is as broad as this
# goes and each of the three segmented words was measured against the tree
# before it was added.
_CREDENTIAL_RE = re.compile(
    r"api[_-]?key|secret|token|password|passwd|passphrase|credential"
    r"|private[_-]?key|_key|bearer|signature|pwd|jwt|oauth"
    r"|authorization|authorisation"
    r"|(?:^|[^a-z])(?:auth|pass|salt|pw)(?:[^a-z]|$)",
    re.IGNORECASE,
)

# ── what counts as a resolver ──
#
# This was `("get_param", "getenv", "get")`, which is not a rule but a list
# of the three resolvers that happened to be in front of whoever wrote it.
# `read_config`, `get_setting`, `fetch_secret` and `env()` all walk past it.
#
# The alternative the verification pass raised — drop the resolver check
# entirely and key purely on "a credential-named first argument with a
# non-empty literal default" — was tried and MEASURED against this tree
# before being rejected. It produces two false positives immediately:
#
#     _logger.warning("… the webhook secret is not configured. Set the "
#                     "ir.config_parameter %r …", SAP_SECRET_PARAM, db)
#     fields.Integer(string="token_ttl_seconds", …, "max_page_limit")
#
# — a log line about a missing credential, and a field declaration. Neither
# resolves anything. With the shape rule below, the same walk over every
# Python file in the repository returns ZERO findings, which is the honest
# state of the tree after handoff 17's fix.
#
# So the check stays, expressed as a SHAPE rather than a roster: a callee
# whose name reads as a lookup. `set_param` is in scope on purpose —
# writing a credential to a literal is the same defect pointed the other
# way — and so are `pop`/`setdefault`, which are how a dict-shaped config
# is read.
_RESOLVER_RE = re.compile(
    r"^(?:get|getenv|read|load|fetch|resolve|lookup|pop|setdefault|set)(?:_|$)"
    r"|(?:^|_)(?:param|params|config|conf|setting|settings|env|environ"
    r"|secret|option|options)$",
    re.IGNORECASE,
)

# The keyword spellings of the two arguments that matter. Odoo's own
# signature is `get_param(self, key, default=False)`, so `default=` is not
# an evasion — it is the documented call.
_KEY_KEYWORDS = ("key", "name")
_DEFAULT_KEYWORDS = ("default", "fallback")


def _looks_like_a_credential(text):
    return bool(text) and bool(_CREDENTIAL_RE.search(str(text)))


def _module_string_constants(tree):
    """Module-level `NAME = "literal"` bindings, so a resolver called with a
    constant instead of an inline string can still be judged."""
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _resolver_name(call):
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _key_text(node, constants):
    """The name of the thing being resolved, however it is written.

    A literal, a module constant, or — failing both — the NAME the code uses
    for it. `self.PARAM_NAME`, `PARAMS['api_key']` and a bare `SAP_SECRET`
    all say what they hold in plain sight; refusing to read them because the
    node type is an Attribute or a Subscript was bypass 6.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        index = node.slice
        if isinstance(index, ast.Constant) and isinstance(index.value, str):
            return index.value
        base = node.value
        return base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
    return None


def _baked_in_text(node, constants):
    """The literal text a default expression carries, or None.

    Constant, module constant, f-string and `+` concatenation, because all
    four put a fixed string in the source and the ORM cannot tell them
    apart. An f-string whose parts are ALL placeholders (`f'{token}'`) bakes
    nothing in and correctly returns None — the rule is about what ships in
    the file, not about the node type.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value for part in node.values
                       if isinstance(part, ast.Constant)
                       and isinstance(part.value, str)) or None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _baked_in_text(node.left, constants)
        right = _baked_in_text(node.right, constants)
        if left is None and right is None:
            return None
        return (left or "") + (right or "")
    return None


def _resolved_credential(call, constants):
    """The credential name this call resolves, or None if it resolves none."""
    name = _resolver_name(call)
    if name is None or not _RESOLVER_RE.search(name):
        return None
    keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    key = call.args[0] if call.args else next(
        (keywords[k] for k in _KEY_KEYWORDS if k in keywords), None)
    if key is None:
        return None
    text = _key_text(key, constants)
    return text if _looks_like_a_credential(text) else None


def _credential_defaults(path):
    """Every place one file resolves a credential and falls back to a value.

    Two shapes, because there are two ways to spell a fallback and only one
    of them is an argument:

        get_param('x.api_key', 'NRS_KEY')      # the default argument
        get_param('x.api_key') or 'NRS_KEY'    # the `or` tail

    The second is not a two-argument call and the first version of this
    guard could not see it at all.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _module_string_constants(tree)
    findings = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            key_text = _resolved_credential(node, constants)
            if key_text:
                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                default = node.args[1] if len(node.args) > 1 else next(
                    (keywords[k] for k in _DEFAULT_KEYWORDS if k in keywords), None)
                # A credential is ALLOWED to default to nothing — that is the
                # sanctioned shape, and every falsy default in this codebase
                # refuses on the falsy value a line later.
                baked = _baked_in_text(default, constants)
                if baked:
                    findings.append((node.lineno, key_text, baked))

        # `<credential lookup> or <literal>`. Only values to the RIGHT of the
        # lookup are fallbacks; `'x' or get_param(...)` is a different (and
        # nonsensical) expression and is not this defect.
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            resolved = None
            for value in node.values:
                if resolved is not None:
                    baked = _baked_in_text(value, constants)
                    if baked:
                        findings.append((value.lineno, resolved, baked))
                if isinstance(value, ast.Call):
                    resolved = _resolved_credential(value, constants) or resolved

    return sorted(findings)


# ─────────────────────────────────────────────────────────────────────
# …and it must be looked for everywhere, not only inside an Odoo module
# ─────────────────────────────────────────────────────────────────────
#
# `_first_party_python_files()` walks `myservice_*` / `cadra_brand_*`
# directories carrying a `__manifest__.py`. That is exactly right for the
# `_sql_constraints` guard, which is about what the ORM loads — and it is
# wrong for these two, which are about what is committed. It leaves
# `scripts/`, `seeds/`, the eleven repo-root Python files, `k8s/`, the
# compose files, `.env.example` and `docs/` outside BOTH of them.
#
# A credential literal in a seed script or a ConfigMap is exactly as
# compromised as one in a controller: it is in the same clone, the same
# fork and the same CI log. So these two guards get their own walker.
# `_first_party_python_files()` is left alone deliberately — it is shared
# with the `_sql_constraints` guard and widening it there would start
# failing on trees whose constraints are correct for the Odoo 15 stack.
#
# What that walker covers is what git tracks, minus the vendored trees —
# see `_tracked_paths()` for why "tracked" and not "on disk". Measured at
# 713 text files and 9 MB, well under a second, so scope is not a thing to
# economise on here.
import fnmatch
import subprocess

# Vendored source. `dist/` is the Odoo 15 tree (182 MB), `crnd-19/` and
# `oca-19/` are CRND and OCA. They are tracked, they are not ours, and a
# credential of theirs is not a credential of ours.
_VENDORED_PREFIXES = ("dist/", "crnd-19/", "oca-19/", "_upgrade/")

# Everything a credential can be written into and still be read back by a
# machine or a person. `Dockerfile*` and `.env*` are matched by prefix
# because that is how they are spelled, not by suffix.
_TEXT_SUFFIXES = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".xml",
    ".md", ".sh", ".conf", ".cfg", ".ini", ".toml", ".txt", ".env", ".sql",
    ".html", ".css", ".service", ".sample", ".example",
})
_TEXT_NAMES = frozenset({"Caddyfile", "Makefile"})
_MAX_TEXT_BYTES = 2_000_000


def _tracked_paths():
    """Every path git tracks, repo-relative.

    Tracked rather than "present on disk", and that is the rule rather than
    a convenience: these two guards are about what is IN EVERY CLONE, and a
    generated artefact is not. The first version of this walk read the
    filesystem and proved the point on its first run — it picked up
    `docs/api/test-report.md`, this suite's own gitignored output, found a
    burnt literal inside the failure message the PREVIOUS run had written
    there, and failed on its own report. Nothing was wrong with the repo.

    Scoping to tracked files removes that loop and takes the machine-output
    prune list with it: node_modules, the virtualenvs, __pycache__ and the
    built frontend bundle are all already ignored, so none of them has to be
    named here and none of them can be forgotten.

    If git is absent or this is not a checkout this returns nothing — which
    would make both guards below pass over an empty tree. That failure is
    caught loudly one test further down, by the coverage assertion, rather
    than quietly here.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True, check=True)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return []
    listing = completed.stdout.decode("utf-8", "replace")
    return [rel for rel in listing.split("\0")
            if rel and not rel.startswith(_VENDORED_PREFIXES)]


def _repo_files(suffixes=None):
    """Every tracked file of ours that is text (or, given `suffixes`, those)."""
    for rel in _tracked_paths():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue  # a submodule, or a path removed but not yet committed
        if suffixes is not None:
            if path.suffix in suffixes:
                yield path
            continue
        if (path.suffix in _TEXT_SUFFIXES
                or path.name in _TEXT_NAMES
                or path.name.startswith("Dockerfile")
                or path.name.startswith(".env")):
            yield path


def test_no_credential_has_a_default_baked_into_the_source():
    """No Python in this repository may fall back to a credential literal.

    Not only the Odoo modules: a seed script that authenticates against a
    baked-in key publishes it just as completely as a controller does.
    Files under a `tests/` directory are exempt — a fixture that constructs
    the defect is how the guard below proves it still works.
    """
    offenders = []
    for path in _repo_files({".py"}):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in "/" + rel or path.name == "test_source_guards.py":
            continue
        try:
            found = _credential_defaults(path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            # Loud rather than skipped. A file this walk cannot parse is a
            # file the guard is not covering, and a silent skip is a hiding
            # place that grows one file at a time.
            offenders.append("%s could not be parsed: %s" % (rel, exc))
            continue
        for lineno, key, default in found:
            offenders.append(
                "%s:%d resolves %r with the literal default %r"
                % (rel, lineno, key, default))

    assert not offenders, (
        "A credential must not have a fallback value in source. A tenant "
        "that never set the parameter then authenticates against a string "
        "that is in every clone of this repository and in git history "
        "forever. Resolve it with no default and refuse on the falsy "
        "value.\n  " + "\n  ".join(offenders))


# The pinned half, and it is deliberately only a pin. The guard above is the
# rule; these two strings are the specific credentials handoff 17 found and
# the owner has to rotate on the box. They are in git history and cannot be
# taken out of it, so the only thing a test can still do is make sure nobody
# pastes them back in — including into a comment, a doc string, a seed
# script or a k8s manifest, which is why this reads the raw text rather than
# the AST, and why it reads the WHOLE repository rather than the addon
# directories. Until this handoff that claim was false: the walker it used
# reached none of those three.
_COMPROMISED_LITERALS = ("NRS_REDHUBS_KEY_2025", "NRS_SAP_WEBHOOK_SECRET_2025")

# Two files quote these literals on purpose, and a guard with no way to say
# so would be a guard somebody switches off.
#
# The waiver is a written sentence per entry rather than a bare path list,
# for the reason CLAUDE.md records about the `db_name` guard: an exception
# matched on a filename cannot tell a dead file from a live one that later
# takes its name. Three things keep this one from rotting the same way:
#
#   1. **Only Markdown under `docs/`, plus this file, may ever be waived.**
#      Enforced below, not merely intended. Documentation cannot
#      authenticate anything — a doc quoting a burnt key inside a fenced
#      block is a rotation notice, which is the opposite of a resolution.
#      A `.py`, `.yaml`, `.conf`, `.sh` or `.env` can never take a waived
#      name, and those are the whole reason the walk was widened.
#   2. **A waiver that matches no file fails the test.** A dead entry
#      cannot sit here as a hole waiting for something to drop into it.
#   3. The reason is next to the entry, so removing it is a decision
#      somebody writes out — the same discipline as the `capped-count-ok:`
#      waiver on the register-count guard.
_BURNT_LITERAL_WAIVERS = {
    "docs/api/EXTERNAL-SURFACES.md":
        "quotes both lines verbatim as the defect report that got them "
        "rotated; the finding is unreadable without the string it found",
    "docs/handoffs/*.md":
        "a handoff instruction or report may have to name the credential "
        "it is telling a Builder to remove",
    "tests/test_source_guards.py":
        "this file — the fixtures below feed the guard the real literals "
        "to prove it still catches them",
}


def _burnt_literal_waiver(rel):
    for pattern in _BURNT_LITERAL_WAIVERS:
        if fnmatch.fnmatch(rel, pattern):
            return pattern
    return None


def test_the_compromised_literals_are_gone_from_first_party_source():
    offenders = []
    for path in _repo_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _burnt_literal_waiver(rel):
            continue
        try:
            if path.stat().st_size > _MAX_TEXT_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - not text
            continue
        for literal in _COMPROMISED_LITERALS:
            if literal in text:
                offenders.append("%s contains %s" % (rel, literal))

    assert not offenders, (
        "These are burnt. They guarded the Redhubs asset export and the SAP "
        "employee webhook with a value published in this repository, and "
        "they are being rotated. Nothing may resolve to them again.\n  "
        + "\n  ".join(offenders))


def test_the_burnt_literal_waivers_are_narrow_and_still_earned():
    """A waiver may only cover documentation, and must cover something.

    Both halves matter. The type limit is what stops the waiver becoming a
    door into the executable half of the repo, which is the half this guard
    was widened to reach. The "must match a file" half is what stops a dead
    entry sitting here until a live file inherits its name — the failure
    CLAUDE.md records against the old `odoo.conf` exception, arriving by the
    same route one guard later.
    """
    for pattern, reason in _BURNT_LITERAL_WAIVERS.items():
        assert reason and len(reason) > 20, (
            "%s is waived without a reason anybody can weigh" % pattern)
        assert pattern == "tests/test_source_guards.py" or (
            pattern.startswith("docs/") and pattern.endswith(".md")), (
            "%s is not documentation. Only Markdown under docs/ may quote a "
            "burnt credential; anything a machine reads must not contain one "
            "at all." % pattern)
        matched = [p for p in _repo_files()
                   if fnmatch.fnmatch(p.relative_to(REPO_ROOT).as_posix(), pattern)]
        assert matched, (
            "the waiver %r matches no file. Delete it: an exception kept "
            "past the thing it excused is a hole with a name on it." % pattern)


def test_the_credential_guards_reach_the_files_the_comment_claims():
    """A walker typo would make both guards above pass over an empty tree.

    The named directories are the ones the OLD walker missed and the ones
    the comment on the literal guard already claimed to cover — a seed
    script, a k8s manifest, the deployment shell, the repo-root Python and
    the docs. The exclusions are asserted too, because a walk that reached
    `dist/` would spend its time on 182 MB of vendored Odoo and would start
    failing on source we do not control.
    """
    text_files = {p.relative_to(REPO_ROOT).as_posix() for p in _repo_files()}
    python_files = {p.relative_to(REPO_ROOT).as_posix()
                    for p in _repo_files({".py"})}

    assert len(python_files) > 200, (
        "only %d Python files walked — the prune list is eating the repo"
        % len(python_files))
    for expected in ("scripts/bootstrap.py", "seeds/nrs_seed.py",
                     "geocode_locations.py",
                     "myservice_api/controllers/v1.py"):
        assert expected in python_files, "%s is not walked" % expected
    for expected in ("k8s/dev/10-configmap-odoo-19.yaml",
                     "docker-compose.19.yml", "Dockerfile.nrs-import",
                     "docs/api/EXTERNAL-SURFACES.md", "config/odoo.19.conf"):
        assert expected in text_files, "%s is not walked" % expected

    for excluded in ("dist", "crnd-19", "oca-19", "_upgrade"):
        assert not any(p.startswith(excluded + "/") for p in text_files), (
            "%s/ is vendored and must stay out of the walk" % excluded)
    assert not any("node_modules/" in p or "/.venv/" in p for p in text_files), (
        "the walk reached a dependency tree")
    assert "docs/api/test-report.md" not in text_files, (
        "the walk reached this suite's own generated report — which quotes "
        "its own failure messages, so it will contain any literal the guard "
        "has just complained about. A guard that reads its own output has "
        "one failure that never clears.")


# Each case is (label, source, should_flag). Every True below was MEASURED
# passing the first version of this guard, one bypass at a time; every False
# is a default somebody legitimately writes and must keep being able to
# write. Both directions matter equally — a guard nobody can satisfy is a
# guard that gets its assertion inverted six months later.
_CREDENTIAL_EVASIONS = [
    # ── the two defects handoff 17 actually found ──
    ("the redhubs defect itself",
     "get_param('myservice_identity.redhubs_api_key', 'NRS_REDHUBS_KEY_2025')",
     True),
    ("the sap defect itself",
     "get_param('myservice_identity.sap_webhook_secret', 'NRS_SAP_X_2025')",
     True),
    ("a low-entropy default is exactly as bad",
     "get_param('some.module.api_key', 'changeme')",
     True),
    ("an environment variable is the same defect",
     "os.getenv('SERVICE_SECRET', 'hunter2')",
     True),
    ("a module constant naming a credential parameter",
     "SAP_SECRET_PARAM = 'a.b.sap_webhook_secret'\n"
     "x = get_param(SAP_SECRET_PARAM, 'fallback')",
     True),

    # ── bypass 1: the default passed by keyword ──
    ("the default passed as default= — Odoo's own signature",
     "get_param('x.api_key', default='NRS_KEY')",
     True),
    ("both arguments passed by keyword",
     "get_param(key='x.api_key', default='NRS_KEY')",
     True),

    # ── bypass 2: the literal moved one line up ──
    ("a module constant holding the DEFAULT rather than the key",
     "FALLBACK = 'NRS_KEY'\n"
     "get_param('x.api_key', FALLBACK)",
     True),
    ("the same, by keyword",
     "FALLBACK = 'NRS_KEY'\n"
     "get_param('x.api_key', default=FALLBACK)",
     True),

    # ── bypass 3: not a two-argument call at all ──
    ("an `or` tail is a default with different punctuation",
     "get_param('x.api_key') or 'NRS_KEY'",
     True),
    ("an `or` tail after the sanctioned empty default",
     "get_param('x.api_key', '') or 'NRS_KEY'",
     True),
    ("an `or` tail holding a module constant",
     "FALLBACK = 'NRS_KEY'\n"
     "get_param('x.api_key') or FALLBACK",
     True),

    # ── bypass 4: a string that is not an ast.Constant ──
    ("an f-string default",
     "get_param('x.api_key', f'NRS_KEY_{2025}')",
     True),
    ("a concatenated default",
     "get_param('x.api_key', 'NRS_' + 'KEY')",
     True),

    # ── bypass 5: a resolver nobody listed ──
    ("a resolver outside the original three",
     "read_config('x.api_key', 'NRS_KEY')",
     True),
    ("writing a credential to a literal is the same defect reversed",
     "set_param('x.api_key', 'NRS_KEY')",
     True),
    ("a dict-shaped config read",
     "conf.setdefault('sap_webhook_secret', 'NRS_KEY')",
     True),

    # ── bypass 6: the key is not a Name ──
    ("the key held on an attribute",
     "get_param(self.PARAM_NAME_API_KEY, 'NRS_KEY')",
     True),
    ("the key held in a dict",
     "get_param(PARAMS['api_key'], 'NRS_KEY')",
     True),

    # ── bypass 7: words the first version did not think were credentials ──
    ("an auth segment",
     "get_param('x.x_auth_token_value', 'NRS_KEY')",
     True),
    ("a password by its short name",
     "os.getenv('ODOO_ADMIN_PWD', 'admin')",
     True),
    ("a webhook signing secret under `signature`",
     "get_param('x.hmac_signature', 'NRS_KEY')",
     True),

    # ── the shapes that must keep working ──
    ("an empty default is the SANCTIONED shape",
     "get_param('myservice_api.jwt_secret', '')",
     False),
    ("an empty default by keyword is equally sanctioned",
     "get_param('myservice_api.jwt_secret', default='')",
     False),
    ("an empty `or` tail is not a fallback value",
     "get_param('myservice_api.jwt_secret') or ''",
     False),
    ("a non-credential default is nobody's business",
     "get_param('web.base.url', 'http://localhost:8069')",
     False),
    ("a high-entropy default for a non-credential is still fine",
     "get_param('cadra.brand_primary', '#0B3D2E')",
     False),
    ("no default at all is the fix",
     "get_param('myservice_identity.redhubs_api_key')",
     False),
    ("a credential defaulting to a COMPUTED value bakes in nothing",
     "get_param('x.api_key') or secrets.token_hex(32)",
     False),
    ("an f-string with no literal text bakes in nothing",
     "get_param('x.api_key', f'{generated}')",
     False),
    ("an idempotency key is a de-duplication token, not a secret",
     "request.httprequest.headers.get('X-Idempotency-Key') or '-'",
     False),
    ("`author` is not `auth`",
     "get_param('x.author_name', 'Unknown')",
     False),
    ("`bypass` is not `pass`",
     "get_param('x.bypass_reason', 'none')",
     False),
    ("a webhook URL is not a webhook secret",
     "get_param('x.webhook_url', 'https://vendra.network/hook')",
     False),
    ("a log line about a credential resolves nothing",
     "_logger.warning('the api_key is not set on %s', 'this database')",
     False),
    ("a field declaration naming a credential is not a lookup",
     "fields.Char(string='api_key', default='')",
     False),
]


# ─────────────────────────────────────────────────────────────────────
# `request.jsonrequest` does not exist on Odoo 19
# ─────────────────────────────────────────────────────────────────────
#
# Handoff 18 item D. `jsonrequest` is an attribute of the DISPATCHER
# (`odoo/http.py`, `JsonRPCDispatcher.__init__`), never of `request`, so
# `request.jsonrequest` raises `AttributeError`. `myservice_identity/
# controllers/sap_webhook.py` read it on the branch taken when `kwargs` is
# empty — which is precisely the branch whose intended answer is
# `{'success': False, 'error': 'Empty payload'}`. An empty or non-JSON-RPC
# body to the unauthenticated inbound employee endpoint got a 500.
#
# It is a guard rather than a fix note because the attribute is real on Odoo
# 15 in `dist/`, and anyone reading a 15 controller for a pattern will copy a
# line that works there and 500s here. The reason used to read "the 15 stack
# is still production" — handoff 20 deleted that stack and every profile now
# resolves to 19, so `dist/` being readable source in the tree is the whole of
# what keeps this guard earning its place. Corrected in handoff 24.
# `request.get_json_data()` is the replacement.
_DEAD_REQUEST_ATTRS = {
    "jsonrequest": "an attribute of the JSON-RPC dispatcher, not of request; "
                   "use request.get_json_data()",
}


def test_no_controller_reads_an_attribute_odoo_19_removed_from_request():
    offenders = []
    for path in _repo_files({".py"}):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in "/" + rel or path.name == "test_source_guards.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
            offenders.append("%s could not be parsed: %s" % (rel, exc))
            continue
        for node in ast.walk(tree):
            # `request.<attr>` and `http.request.<attr>` alike: the guard
            # keys on the attribute chain ending in `request`, so an alias
            # (`req = request`) escapes it and a rename does not.
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in _DEAD_REQUEST_ATTRS:
                continue
            base = node.value
            base_name = (base.id if isinstance(base, ast.Name)
                         else getattr(base, "attr", None))
            if base_name != "request":
                continue
            offenders.append("%s:%d reads request.%s — %s"
                             % (rel, node.lineno, node.attr,
                                _DEAD_REQUEST_ATTRS[node.attr]))

    assert not offenders, (
        "These attributes do not exist on Odoo 19's `request`. Reading one "
        "is an AttributeError at runtime, which on a public webhook is a 500 "
        "where the code below it was written to answer a refusal.\n  "
        + "\n  ".join(offenders))


# ─────────────────────────────────────────────────────────────────────
# …and the same rule where there is no Python to parse
# ─────────────────────────────────────────────────────────────────────
#
# Handoff 18 item C. `Dockerfile.nrs-import` carried
#
#     ENV ODOO_URL=... ODOO_ADMIN_PW=admin PACK=...
#
# and `scripts/nrs_import_entrypoint.sh` passed that straight to XML-RPC as
# the tenant's admin. The guard above walks `.py` only, so it could not see
# it — and this one is WORSE than the two `get_param` defaults it was written
# for, in one specific way the handoff named: **images get pulled**. A literal
# in a source file stays where it was written. A literal in an `ENV` layer
# ships to every host that runs the image, is printed by `docker history`, and
# is readable by anyone with access to the registry.
#
# The rule is unchanged — a credential may default to nothing and never to
# something. What changes is the file format, so the reader changes with it:
# an AST for Python, an instruction parser for a Dockerfile, an indentation
# walk for a k8s manifest, a fallback-operator match for TypeScript. Three
# small readers rather than one clever one, because each format spells "this
# is the default" differently and a regex that tried to cover all three would
# be wrong about all three.
#
# **The compose files and `.env.example` ARE covered now**, and the four
# defaults they ship are a written exception rather than a gap. Report 18
# named them and declined to rule; handoff 20 §C rules: the values stay, the
# exception is written, and it is a waiver that fails when it stops matching.
# See `_ENV_DEFAULT_WAIVERS` below for the reasoning and the enforcement.
#
# The distinction the waiver rests on is worth stating once. An image layer is
# PULLED onto every host that runs it and printed by `docker history`; a k8s
# manifest is APPLIED. Neither is a thing anybody edits per deployment. A
# compose default and a `.env.example` line are the opposite: they exist to be
# overridden, the override is a documented step, and — since handoff 20 — the
# prod bring-up REFUSES TO START while they have not been. That last clause is
# what turns the argument from "a template ought to be edited" into something
# a guard can stand on, and it is asserted in tests/test_deployment_profile.py.

#: Values that are not a baked-in credential even though they are non-empty.
#: A Dockerfile `ENV X=$Y` or a manifest `value: "$(FOO)"` defers to something
#: outside the file, which is the fix, not the defect.
_INDIRECTION_RE = re.compile(r"^\$[({]?[A-Za-z_][A-Za-z0-9_]*[)}]?$")


def _is_baked_value(value):
    """True when `value` is a literal a machine would authenticate with."""
    value = (value or "").strip().strip('"').strip("'").strip()
    if not value:
        return False            # the sanctioned shape: default to nothing
    return not _INDIRECTION_RE.match(value)


def _dockerfile_credential_defaults(path):
    """Credential-named `ENV`/`ARG` assignments carrying a literal value.

    Handles what Docker actually accepts: line continuations, several
    assignments on one instruction, quoted values, and the legacy
    space-separated `ENV KEY value` form (one pair per instruction).
    """
    # Join continuations — the defect was on the FOURTH line of a five-line
    # ENV, so a per-line reader misses it entirely. But the join has to keep
    # the original line number with it: collapsing first and numbering the
    # result reported `Dockerfile.nrs-import:34` for a defect on line 39,
    # pointing five lines up at a comment. A finding that names the wrong
    # line sends whoever reads it to the wrong place, which is most of what
    # a guard's output is for.
    source_lines = path.read_text(encoding="utf-8").splitlines()

    def physical_line(start, name, value):
        """The line the ASSIGNMENT is on, not the line the instruction is on.

        Reporting the instruction's first line was already better than the
        collapsed-text number it replaced, but on the five-line `ENV` this
        guard exists for it still pointed four lines above the credential.
        """
        needle = "%s=" % name
        for offset, text in enumerate(source_lines[start - 1:], start=start):
            if needle in text:
                return offset
        return start

    instructions = []          # (original lineno, joined text)
    pending, start = None, None
    for lineno, raw in enumerate(source_lines, start=1):
        line = raw.rstrip()
        if pending is None:
            pending, start = line.strip(), lineno
        else:
            pending += " " + line.strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        instructions.append((start, pending))
        pending = None
    if pending is not None:
        instructions.append((start, pending))

    findings = []
    for lineno, stripped in instructions:
        if not re.match(r"^(ENV|ARG)\s", stripped, re.IGNORECASE):
            continue
        body = stripped.split(None, 1)[1] if len(stripped.split(None, 1)) > 1 else ""
        pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|\S*)", body)
        if not pairs:
            # Legacy `ENV KEY value ...` — everything after the name is the
            # value, spaces included. `ARG KEY` alone has no value at all.
            parts = body.split(None, 1)
            if len(parts) == 2:
                pairs = [(parts[0], parts[1])]
        for name, value in pairs:
            if _looks_like_a_credential(name) and _is_baked_value(value):
                findings.append((physical_line(lineno, name, value), name,
                                 value.strip('"').strip("'")))
    return sorted(findings)


#: How deep a k8s `value:` may sit below its `- name:` and still belong to the
#: same list item. Two covers `value:` and a comment line between them; a
#: deeper one is a different structure and is not guessed at.
_MANIFEST_VALUE_WINDOW = 4


def _manifest_credential_defaults(path):
    """Credential-named container env vars carrying a literal `value:`.

    Text rather than YAML: the pytest venv has no pyyaml and a guard that
    silently skips every manifest when an import fails is worse than one that
    reads them with an indentation walk. The shape is fixed by k8s itself —

        - name: ODOO_ADMIN_PW
          value: "admin"          # flagged
        - name: DB_PASSWORD
          valueFrom:              # the fix — not flagged
            secretKeyRef: ...
    """
    findings = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        # A trailing comment on the `- name:` line defeated the first version
        # of this — `- name: ODOO_ADMIN_PW  # the admin pw` matched nothing,
        # and the manifests in this repo are heavily commented, so that is
        # the spelling a person here actually writes.
        flow = re.match(
            r"^\s*-\s*\{\s*name:\s*([^,}]+),\s*value:\s*([^}]+)\}", line)
        if flow:
            fname = flow.group(1).strip().strip('"').strip("'")
            fvalue = flow.group(2).strip()
            if _looks_like_a_credential(fname) and _is_baked_value(fvalue):
                findings.append((i + 1, fname,
                                 fvalue.strip().strip('"').strip("'")))
            continue
        m = re.match(r"^(\s*)-\s+name:\s*([^#]+?)\s*(?:#.*)?$", line)
        if not m:
            continue
        indent, name = m.group(1), m.group(2).strip().strip('"').strip("'")
        if not _looks_like_a_credential(name):
            continue
        for follow in lines[i + 1:i + 1 + _MANIFEST_VALUE_WINDOW]:
            if re.match(r"^\s*-\s", follow) or (
                    follow.strip() and len(follow) - len(follow.lstrip()) <= len(indent)):
                break               # next list item, or out of this block
            v = re.match(r"^\s*value:\s*(.*)$", follow)
            if v and _is_baked_value(v.group(1).split("#")[0]):
                findings.append((i + 1, name,
                                 v.group(1).split("#")[0].strip().strip('"').strip("'")))
                break
    return sorted(findings)


#: `process.env.X ?? "lit"` / `|| "lit"`, which is JavaScript for
#: `os.getenv('X', 'lit')`. Only the UNCONDITIONAL fallback — `e2e/config.ts`
#: keeps an `admin` default behind an "is this origin local?" test, which is
#: the exception handoff 18 allowed, and a conditional default is not this
#: shape. That is by construction rather than by waiver: gating the default
#: is exactly what takes it out of the guard's reach, so the guard rewards
#: the fix instead of needing an exception written for it.
#: `process.env.X` and Vite's `import.meta.env.X`, dotted or bracketed. The
#: second matters here: `Frontend/` is a Vite app and that is the spelling it
#: uses, so a reader that knew only `process.env` covered the e2e harness and
#: none of the product.
_JS_ENV_ACCESS = (
    r"(?:process\.env|import\.meta\.env)"
    r"(?:\.([A-Za-z_$][\w$]*)|\[\s*[\"'`]([^\"'`]+)[\"'`]\s*\])"
)

#: `<env access> ?? "lit"`, `|| "lit"`, and the ternary spelling of the same
#: thing. `\s*` spans newlines under DOTALL-free matching because it includes
#: `\n`, which is what a formatter breaking a long line produces.
_JS_ENV_FALLBACK_RE = re.compile(
    _JS_ENV_ACCESS + r"\s*(?:\?\?|\|\|)\s*[\"'`]([^\"'`]+)[\"'`]")

#: `x ? x : "lit"` — the pre-`??` spelling, still written.
_JS_ENV_TERNARY_RE = re.compile(
    _JS_ENV_ACCESS + r"\s*\?[^?:]{0,200}?:\s*[\"'`]([^\"'`]+)[\"'`]")

#: `const { E2E_PASS = "admin" } = process.env;` — the ordinary JS idiom, and
#: the one the first version of this reader missed entirely. The destructuring
#: pattern is matched first and each defaulted binding inside it is judged.
_JS_DESTRUCTURE_RE = re.compile(
    r"\{([^{}]*=[^{}]*)\}\s*=\s*(?:process\.env|import\.meta\.env)")
_JS_DESTRUCTURE_BINDING_RE = re.compile(
    r"([A-Za-z_$][\w$]*)\s*(?::\s*[A-Za-z_$][\w$]*\s*)?=\s*[\"'`]([^\"'`]+)[\"'`]")


def _js_credential_defaults(path):
    """Whole-file rather than line-by-line.

    A prettier run that breaks `process.env.E2E_PASS ?? "admin"` across two
    lines is not an evasion anybody intends, and a per-line reader cannot see
    it. Line numbers come from counting newlines up to the match instead.
    """
    text = path.read_text(encoding="utf-8")

    def lineno_at(offset):
        return text.count("\n", 0, offset) + 1

    findings = []
    for regex in (_JS_ENV_FALLBACK_RE, _JS_ENV_TERNARY_RE):
        for m in regex.finditer(text):
            name = m.group(1) or m.group(2)
            default = m.group(3)
            if _looks_like_a_credential(name) and _is_baked_value(default):
                findings.append((lineno_at(m.start()), name, default))
    for m in _JS_DESTRUCTURE_RE.finditer(text):
        for name, default in _JS_DESTRUCTURE_BINDING_RE.findall(m.group(1)):
            if _looks_like_a_credential(name) and _is_baked_value(default):
                findings.append((lineno_at(m.start()), name, default))
    return sorted(findings)


#: `${NAME:-literal}` and `${NAME:?message}` — compose's own way of writing
#: "read this from the environment, and here is what to use if it is absent".
#: The `:?` form supplies no default at all, which is the sanctioned shape and
#: must not be flagged; only `:-` and `:=` bake a value in.
_COMPOSE_DEFAULT_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\s*:?[-=]\s*([^}]*)\}")


def _compose_credential_defaults(path):
    """Credential defaults in a compose file, in every spelling it accepts.

    A compose file is where a deployment's environment is actually assembled,
    and it can bake a credential in several ways that look nothing alike:

        PASSWORD: ${POSTGRES_PASSWORD:-odoo}     # a default for a lookup
        ODOO_MASTER_PASSWORD: admin              # a flat literal
        - POSTGRES_PASSWORD=odoo                 # the list form
        environment: {PASSWORD: odoo}            # a flow mapping

    The interpolation form is judged on the ENVIRONMENT VARIABLE's name, not
    the key's, because that is the thing being defaulted — `PASSWORD:
    ${FOO:-odoo}` defaults FOO. The others are judged on the key.

    The first version of this read only the first two, and a verification pass
    measured it walking past the list form when quoted, the flow mapping, and
    a literal on a line that also carried an unrelated `${...}`. Those are the
    same spellings `docs/DECISIONS.md` records defeating the k8s reader one
    handoff earlier — a guard that only catches the keystrokes of the defect
    it was written for is a record of that defect, not a rule.
    """
    findings = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        code = _strip_yaml_comment(line)
        if not code.strip():
            continue

        # 1. `${NAME:-literal}` / `${NAME:=literal}`, anywhere on the line,
        #    including inside a longer string. `${NAME:?message}` supplies no
        #    default at all — it REFUSES when the variable is unset, which is
        #    the fix — and is deliberately not matched.
        seen_here = set()
        for m in _COMPOSE_DEFAULT_RE.finditer(code):
            name, default = m.group(1), m.group(2).strip()
            seen_here.add(name)
            if _looks_like_a_credential(name) and _is_baked_value(default):
                findings.append((i + 1, name, default.strip('"').strip("'")))

        # 2. Every `key: value` and `- KEY=value` pair on the line, whether it
        #    is a block mapping, a list item or inside `{...}`. A pair whose
        #    VALUE still contains an interpolation defers to the environment
        #    and is not a baked literal — but that is decided per PAIR, not
        #    per line, so one unrelated `${...}` no longer hides a literal
        #    sitting beside it.
        for name, value in _compose_pairs(code):
            if name in seen_here or not _looks_like_a_credential(name):
                continue
            if "${" in value or "$(" in value:
                continue
            if _is_baked_value(value):
                findings.append((i + 1, name, value.strip('"').strip("'")))
    return sorted(set(findings))


#: A pair is read from TOKENS, not from one regex over the line. The regex
#: version could not tell `environment: {PASSWORD: odoo}` apart from a value
#: — `PASSWORD:` is a perfectly good scalar as far as a pattern is concerned
#: — so the outer key swallowed the inner pair and the credential vanished.
#: Tokenising says the obvious thing instead: a token ending in `:` is a key,
#: never a value.
_INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _compose_pairs(code):
    """Every `key: value` and `KEY=value` on one line, flow form included.

    Flow punctuation is replaced with spaces first, which turns
    `environment: {PASSWORD: odoo}` into the block form and lets one rule read
    both — smaller than the regex that failed to read either.

    `${DB_PASSWORD:-a#b}` must survive that flattening intact: its brace
    closes a DEFAULT, not a mapping. Interpolations are lifted out before and
    put back after.
    """
    kept = []

    def _stash(m):
        kept.append(m.group(0))
        return "\x00%d\x00" % (len(kept) - 1)

    def _restore(text):
        for i, original in enumerate(kept):
            text = text.replace("\x00%d\x00" % i, original)
        return text

    flat = _INTERPOLATION_RE.sub(_stash, code)
    flat = flat.translate({ord(c): " " for c in "{},"})
    tokens = flat.split()

    for i, token in enumerate(tokens):
        raw = token.strip('"').strip("'")
        if "=" in raw and not raw.endswith(":"):
            name, _, value = raw.partition("=")
            name = name.strip('"').strip("'")
            if _NAME_RE.match(name):
                yield name, _restore(value).strip('"').strip("'")
            continue
        if not token.endswith(":"):
            continue
        name = token[:-1].strip('"').strip("'")
        if not _NAME_RE.match(name):
            continue
        if i + 1 >= len(tokens):
            continue
        nxt = tokens[i + 1]
        # The next token is itself a key, so this one has no scalar value.
        if nxt.endswith(":") and _NAME_RE.match(nxt[:-1].strip('"').strip("'")):
            continue
        yield name, _restore(nxt).strip('"').strip("'")


def _strip_yaml_comment(line):
    """Remove a trailing YAML comment, and only a real one.

    `#` opens a comment in YAML only at the start of a token — after
    whitespace — so `${PW:-a#b}` and `#004080` are not comments. Splitting on
    a bare `#` truncated the line before the credential could be seen, which
    is a false PASS. `_dotenv_credential_defaults` already got this right with
    `split(" #")`; the two readers now agree.
    """
    out, prev, quote = [], " ", None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and prev in " \t":
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def _dotenv_credential_defaults(path):
    """`NAME=value` in a committed env template.

    `.env` itself is gitignored and never walked; `.env.example` is the file
    an operator copies, so whatever it ships is what a deployment starts with
    until somebody edits it.
    """
    findings = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$",
                     stripped)
        if not m:
            continue
        name, value = m.group(1), m.group(2).split(" #")[0].strip()
        if _looks_like_a_credential(name) and _is_baked_value(value):
            findings.append((i + 1, name, value.strip('"').strip("'")))
    return sorted(findings)


# ── the written exception, and what stops it rotting ────────────────────
#
# Handoff 20 §C. Four credential defaults stay exactly as they are:
# `docker-compose.yml` resolves `${POSTGRES_PASSWORD:-odoo}` twice, and
# `.env.example` ships `POSTGRES_PASSWORD=odoo` and `ODOO_MASTER_PASSWORD=admin`.
#
# Why they stay: changing them changes the local bring-up for every checkout
# and buys nothing, because the values are not what protects a deployment —
# the prod container's refusal to start on them is, and that landed in the
# same change (see docker-compose.prod.yml's `command:`, asserted by
# tests/test_deployment_profile.py). `.env.example` is a template whose own
# header says every value must be overridden, and now says the server enforces
# it.
#
# Three things keep this waiver honest, the same three that keep
# `_BURNT_LITERAL_WAIVERS` honest, plus a fourth this shape allows:
#
#   1. It is keyed on (path, VARIABLE NAME), not on a path. Waiving a FILE
#      would mean a fifth credential default dropped into `.env.example`
#      tomorrow inherits the exception silently. These two names are waived
#      in these two files and nothing else is.
#   2. **An entry that matches no finding fails the test.** Fix one of these
#      four and its waiver becomes a hole with a name on it; the suite says
#      so on the next run rather than in a year.
#   3. The reason is next to the entry, so removing it is a decision somebody
#      has to write out.
#   4. The waived VALUES must be values the prod bring-up refuses. That is
#      checked in tests/test_deployment_profile.py, from the other side: the
#      exception is only defensible while the assertion behind it holds, so
#      the two are wired together rather than merely agreeing today.
_ENV_DEFAULT_WAIVERS = {
    ("docker-compose.yml", "POSTGRES_PASSWORD"):
        "the local Postgres password. Compose needs a default here or a bare "
        "`docker compose up` fails on a fresh clone, which is the developer "
        "onboarding path and CI's. The prod overlay refuses this value.",
    (".env.example", "POSTGRES_PASSWORD"):
        "the template an operator copies. Shipping it blank moves the failure "
        "from a named refusal at prod start-up to a confusing connection "
        "error on every dev bring-up. The prod overlay refuses this value.",
    (".env.example", "ODOO_MASTER_PASSWORD"):
        "the Odoo database-manager password, `admin` for dev. Same reasoning; "
        "the prod overlay refuses this value and says so in this file's own "
        "header.",
}


def _env_default_waiver(rel, name):
    return _ENV_DEFAULT_WAIVERS.get((rel, name))


_NON_PYTHON_CREDENTIAL_READERS = (
    ("Dockerfile", _dockerfile_credential_defaults,
     lambda rel: pathlib.Path(rel).name.startswith("Dockerfile")),
    ("k8s manifest", _manifest_credential_defaults,
     lambda rel: rel.startswith("k8s/") and rel.endswith((".yaml", ".yml"))),
    ("JS/TS", _js_credential_defaults,
     lambda rel: rel.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))),
    ("compose file", _compose_credential_defaults,
     lambda rel: pathlib.Path(rel).name.startswith("docker-compose")
     and rel.endswith((".yml", ".yaml"))),
    ("env template", _dotenv_credential_defaults,
     lambda rel: pathlib.Path(rel).name.startswith(".env")),
)


def _non_python_credential_findings():
    """Walk once, and return (unwaived offenders, waiver keys that matched).

    Shared so the guard and the waiver audit below cannot disagree about what
    was found — the failure mode a second, near-identical walk invites.
    """
    offenders, hit = [], set()
    for path in _repo_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in "/" + rel or "/node_modules/" in "/" + rel:
            continue
        for label, reader, applies in _NON_PYTHON_CREDENTIAL_READERS:
            if not applies(rel):
                continue
            try:
                found = reader(path)
            except (OSError, UnicodeDecodeError):  # pragma: no cover
                continue
            for lineno, name, value in found:
                if _env_default_waiver(rel, name):
                    hit.add((rel, name))
                    continue
                offenders.append(
                    "%s:%d (%s) assigns %s the literal %r"
                    % (rel, lineno, label, name, value))
    return offenders, hit


def test_no_credential_defaults_in_an_image_layer_or_a_manifest():
    """The Python rule, applied where there is no Python.

    An `ENV ODOO_ADMIN_PW=admin` is not a worse-looking literal than a
    `get_param` default — it is a worse-PLACED one. Source sits in a clone;
    an image layer is pulled onto every host that runs it and is printed by
    `docker history`.
    """
    offenders, _ = _non_python_credential_findings()
    assert not offenders, (
        "A credential must not default to a value, and an image layer or a "
        "cluster manifest is the worst place for one — the image is pulled "
        "and the manifest is applied. Read it from a Secret or an "
        "environment variable and REFUSE when it is unset, naming what is "
        "missing.\n  " + "\n  ".join(offenders))


def test_no_compose_service_pulls_its_environment_from_an_unwalked_file():
    """`env_file:` is the hole neither credential reader can see.

    The env-template reader keys on a filename starting with `.env`, because
    that is what the walk can recognise as a committed template. A service
    that says `env_file: ./config/service.env` gets its whole environment —
    credentials included — from a file the guard never opens, and the guard
    stays green.

    Following the reference is the wrong fix: the path can be a list, can be
    relative to a different directory, and can point outside the repository.
    Refusing the construct is the right one. No compose file here uses it,
    and if one needs to, the reader has to learn about it in the same change.
    """
    offenders = []
    for path in sorted(REPO_ROOT.glob("docker-compose*.yml")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if re.match(r"^\s*env_file\s*:", line.split("#")[0]):
                offenders.append("%s:%d" % (path.name, i + 1))
    assert not offenders, (
        "these services load an environment from a file the credential "
        "guards do not walk, so a credential default in it would pass "
        "unseen: %s\nTeach `_NON_PYTHON_CREDENTIAL_READERS` to open the "
        "referenced file in the same change that introduces it."
        % ", ".join(offenders))


def test_the_env_default_waivers_are_narrow_and_still_earned():
    """A waiver that has stopped excusing anything is a hole with a name on it.

    This is the failure CLAUDE.md records against the old `odoo.conf`
    exception and that `_BURNT_LITERAL_WAIVERS` was shaped to avoid: an
    exception matched by name cannot tell a dead entry from a live one, so a
    file or a variable that later takes a waived name inherits the excuse.
    Requiring every entry to have actually matched something this run is what
    closes it.
    """
    # Scope FIRST. A waiver on a Dockerfile also fails the "matched nothing"
    # check below, and would be reported as a dead entry — which is a true
    # sentence about the less serious of the two faults, and the one somebody
    # fixes by making it match.
    scope = {rel for rel, _name in _ENV_DEFAULT_WAIVERS}
    assert scope <= {"docker-compose.yml", ".env.example"}, (
        "this waiver covers the two files handoff 20 ruled on and nothing "
        "else. A Dockerfile, a k8s manifest or a shell script must never "
        "take one: those are pulled and applied, not edited per deployment, "
        "and the prod refusal that makes this exception defensible does not "
        "reach them. Found: %s" % sorted(scope))

    _, hit = _non_python_credential_findings()
    for (rel, name), reason in _ENV_DEFAULT_WAIVERS.items():
        assert reason and len(reason) > 40, (
            "%s:%s is waived without a reason anybody can weigh" % (rel, name))
        assert (rel, name) in hit, (
            "the waiver for %s in %s matched nothing. Either the default was "
            "fixed — in which case delete the waiver — or the reader stopped "
            "seeing it, which is worse, because the guard is now silent about "
            "a file it reports on." % (name, rel))


def test_the_non_python_credential_guard_reaches_its_file_types():
    """A reader whose predicate matches nothing is a guard that passes."""
    seen = {label: 0 for label, _, _ in _NON_PYTHON_CREDENTIAL_READERS}
    for path in _repo_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for label, _reader, applies in _NON_PYTHON_CREDENTIAL_READERS:
            if applies(rel):
                seen[label] += 1
    for label, count in seen.items():
        assert count, "the %s reader matched no tracked file" % label


# Each case is (label, filename, source, should_flag). The first entry is the
# defect handoff 18 found, byte for byte including its position on the fourth
# continuation line — a per-line reader passes it, which is why the reader
# joins continuations before it looks at anything.
_NON_PYTHON_EVASIONS = [
    ("the baked image credential itself", "Dockerfile.x",
     "ENV ODOO_URL=http://odoo-19:8069 \\\n"
     "    SOURCE_DB=staging \\\n"
     "    DB_HOST=db \\\n"
     "    ODOO_ADMIN_PW=admin \\\n"
     "    PACK=/opt/pack\n", True),
    ("a single-line ENV credential", "Dockerfile",
     "ENV API_KEY=NRS_KEY_2025\n", True),
    ("the legacy space-separated ENV form", "Dockerfile",
     "ENV ADMIN_PASSWORD hunter2\n", True),
    ("a quoted value", "Dockerfile",
     'ENV SERVICE_TOKEN="changeme"\n', True),
    ("a lowercase instruction", "Dockerfile",
     "env admin_password=admin\n", True),
    ("an ARG default is pulled too — it is in the build history", "Dockerfile",
     "ARG JWT_SECRET=dev-secret\n", True),
    ("a non-credential ENV is nobody's business", "Dockerfile",
     "ENV ODOO_URL=http://odoo-19:8069 SOURCE_DB=staging\n", False),
    ("an ENV deferring to a build arg bakes nothing in", "Dockerfile",
     "ENV ODOO_ADMIN_PW=$ADMIN_PW\n", False),
    ("the braced spelling of the same", "Dockerfile",
     "ENV ODOO_ADMIN_PW=${ADMIN_PW}\n", False),
    ("an empty default is the sanctioned shape here too", "Dockerfile",
     'ENV ODOO_ADMIN_PW=""\n', False),
    ("an ARG with no value at all", "Dockerfile",
     "ARG ODOO_ADMIN_PW\n", False),
    ("a bare PATH-ish name that merely contains 'pass'", "Dockerfile",
     "ENV BYPASS_CACHE=1\n", False),

    ("a literal manifest env credential", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: ODOO_ADMIN_PW\n"
     '              value: "admin"\n', True),
    ("the same with a comment between", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: DB_PASSWORD\n"
     "              # set by hand for now\n"
     '              value: "odoo"\n', True),
    ("secretKeyRef is the fix and must not be flagged", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: DB_PASSWORD\n"
     "              valueFrom:\n"
     "                secretKeyRef:\n"
     "                  name: cadra-db\n"
     "                  key: POSTGRES_PASSWORD\n", False),
    ("a non-credential literal value", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: TARGET_DB\n"
     '              value: "staging19"\n', False),
    ("a credential name whose value is the NEXT item's", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: DB_PASSWORD\n"
     "              valueFrom:\n"
     "                secretKeyRef:\n"
     "                  name: cadra-db\n"
     "                  key: POSTGRES_PASSWORD\n"
     "            - name: TARGET_DB\n"
     '              value: "staging19"\n', False),
    ("a downward field reference is not a literal", "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: API_KEY\n"
     '              value: "$(SOME_OTHER_VAR)"\n', False),

    ("the JS spelling of a credential default", "e2e/x.ts",
     'export const PASS = process.env.E2E_PASS ?? "admin";\n', True),
    ("the `||` spelling", "e2e/x.ts",
     'const token = process.env.API_TOKEN || "NRS_KEY";\n', True),
    ("the bracket spelling", "e2e/x.ts",
     'const s = process.env["SERVICE_SECRET"] || "hunter2";\n', True),
    ("a non-credential env default", "e2e/x.ts",
     'export const ORIGIN = process.env.E2E_ORIGIN ?? "http://localhost:8069";\n',
     False),
    ("a default GATED on something is not an unconditional default",
     "e2e/x.ts",
     'function pw() { if (isLocal()) return "admin";\n'
     '  throw new Error("E2E_PASS is not set"); }\n', False),
    ("no default at all", "e2e/x.ts",
     'export const PASS = process.env.E2E_PASS;\n', False),

    # ── what a verification pass wrote against the FIRST version of these
    #    three readers and measured them accepting. Every one is a spelling
    #    somebody reaches for without meaning to evade anything, which is the
    #    point: a guard that only catches the keystrokes of the defect it was
    #    written for is a record of that defect, not a rule. Same discipline
    #    as the six bypasses of the Python guard above.
    ("a trailing comment on the name line — and this repo comments heavily",
     "k8s/dev/x.yaml",
     "          env:\n"
     "            - name: ODOO_ADMIN_PW  # the admin pw\n"
     '              value: "admin"\n', True),
    ("a YAML flow mapping on one line", "k8s/dev/x.yaml",
     "          env:\n"
     '            - {name: ODOO_ADMIN_PW, value: "admin"}\n', True),
    ("a quoted name with a trailing comment", "k8s/dev/x.yaml",
     "          env:\n"
     '            - name: "DB_PASSWORD"   # from the secret one day\n'
     '              value: "odoo"\n', True),
    ("a flow mapping using secretKeyRef is still the fix", "k8s/dev/x.yaml",
     "          env:\n"
     "            - {name: DB_PASSWORD, valueFrom: x}\n", False),

    ("the ordinary destructuring idiom", "e2e/x.ts",
     'const { E2E_PASS = "admin" } = process.env;\n', True),
    ("destructuring with a rename", "e2e/x.ts",
     'const { API_TOKEN: tok = "NRS_KEY" } = process.env;\n', True),
    ("destructuring a non-credential", "e2e/x.ts",
     'const { E2E_ORIGIN = "http://localhost:8069" } = process.env;\n', False),
    ("a fallback a formatter broke across two lines", "e2e/x.ts",
     'export const PASS =\n  process.env.E2E_PASS ??\n  "admin";\n', True),
    ("Vite's import.meta.env — the spelling the Frontend/ app uses",
     "e2e/x.ts",
     'const s = import.meta.env.VITE_API_SECRET ?? "abc";\n', True),
    ("the pre-`??` ternary spelling", "e2e/x.ts",
     'const p = process.env.E2E_PASS ? process.env.E2E_PASS : "admin";\n',
     True),
    ("a ternary on a non-credential", "e2e/x.ts",
     'const o = process.env.E2E_ORIGIN ? process.env.E2E_ORIGIN : "http://x";\n',
     False),

    # ── compose files and env templates, added in handoff 20 §C ──
    #
    # The negative half is the whole reason these two readers can be turned on
    # at all. `${VAR:?message}` is the shape that REFUSES when a variable is
    # unset — the fix — and the first version of this reader read the refusal
    # MESSAGE as a baked password. A guard that flags the correction is worse
    # than no guard, because the fix is what somebody stops making.
    ("the compose default spelling — the shape being waived",
     "docker-compose.x.yml",
     "    environment:\n"
     "      PASSWORD: ${POSTGRES_PASSWORD:-odoo}\n", True),
    ("the `:=` spelling of the same thing", "docker-compose.x.yml",
     "      PASSWORD: ${POSTGRES_PASSWORD:=odoo}\n", True),
    ("a flat literal, which is what somebody writes when interpolation "
     "gets in the way", "docker-compose.x.yml",
     "      ODOO_MASTER_PASSWORD: admin\n", True),
    ("a quoted flat literal", "docker-compose.x.yml",
     '      CADRA_JWT_SECRET: "dev-secret"\n', True),
    ("`:?` supplies NO default — it refuses, which is the fix",
     "docker-compose.x.yml",
     "      ODOO_MASTER_PASSWORD: ${ODOO_MASTER_PASSWORD:?must be set in .env}\n",
     False),
    ("an empty default is the sanctioned shape here too",
     "docker-compose.x.yml",
     "      CADRA_JWT_SECRET: ${CADRA_JWT_SECRET:-}\n", False),
    ("plain interpolation with no default at all", "docker-compose.x.yml",
     "      PASSWORD: ${POSTGRES_PASSWORD}\n", False),
    ("a non-credential default is nobody's business", "docker-compose.x.yml",
     "      POSTGRES_DB: ${POSTGRES_DB:-odoo}\n", False),
    ("a commented-out default is not in effect", "docker-compose.x.yml",
     "      # PASSWORD: ${POSTGRES_PASSWORD:-odoo}\n", False),
    ("the credential is the VARIABLE being defaulted, not the key",
     "docker-compose.x.yml",
     "      HOST: ${DB_PASSWORD:-odoo}\n", True),

    ("an env template shipping a password", ".env.example",
     "POSTGRES_PASSWORD=odoo\n", True),
    ("an env template shipping a master password", ".env.example",
     "ODOO_MASTER_PASSWORD=admin\n", True),
    ("the `export` spelling", ".env.example",
     "export CADRA_JWT_SECRET=dev-secret\n", True),
    ("a blank value is the sanctioned shape", ".env.example",
     "CADRA_JWT_SECRET=\n", False),
    ("a commented example is documentation, not a value", ".env.example",
     "# CADRA_TURNSTILE_SECRET=abc123\n", False),
    ("a non-credential setting", ".env.example",
     "POSTGRES_DB=odoo\n", False),
    ("a value that defers to the environment", ".env.example",
     "CADRA_JWT_SECRET=$JWT_FROM_VAULT\n", False),

    # ── what a verification pass measured the FIRST compose reader walking
    #    past. Each is a spelling somebody writes without meaning to evade
    #    anything, and every one of them is a FALSE PASS — the dangerous
    #    direction. Three are the same spellings docs/DECISIONS.md records
    #    defeating the k8s reader one handoff earlier.
    ("a YAML flow mapping — the spelling that defeated the k8s reader too",
     "docker-compose.x.yml",
     "    environment: {PASSWORD: odoo}\n", True),
    ("a QUOTED list item (the unquoted one was already caught)",
     "docker-compose.x.yml",
     '      - "POSTGRES_PASSWORD=odoo"\n', True),
    ("the unquoted list item", "docker-compose.x.yml",
     "      - POSTGRES_PASSWORD=odoo\n", True),
    ("an unrelated interpolation on the same line must not hide a literal",
     "docker-compose.x.yml",
     "      ODOO_MASTER_PASSWORD: admin   # next to ${FOO}\n", True),
    ("a `#` INSIDE a value is not a comment in YAML",
     "docker-compose.x.yml",
     "      PASSWORD: ${DB_PASSWORD:-a#b}\n", True),
    ("a default inside a longer string", "docker-compose.x.yml",
     '      DSN: "user:${DB_PASSWORD:-odoo}@db/x"\n', True),
    ("a credential at column 0, in an x- extension block",
     "docker-compose.x.yml",
     "x-shared: &shared\n"
     "ADMIN_PASSWORD: admin\n", True),
    ("a real trailing comment is still a comment", "docker-compose.x.yml",
     "      POSTGRES_DB: odoo   # not a credential, and PASSWORD: admin here\n",
     False),
    ("a pair whose value defers to the environment", "docker-compose.x.yml",
     "      PASSWORD: ${POSTGRES_PASSWORD}\n", False),
    ("the refusal form, inside a flow mapping", "docker-compose.x.yml",
     "    environment: {ODOO_MASTER_PASSWORD: ${ODOO_MASTER_PASSWORD:?set it}}\n",
     False),
]


@pytest.mark.parametrize(
    "label,filename,source,should_flag", _NON_PYTHON_EVASIONS,
    ids=[c[0] for c in _NON_PYTHON_EVASIONS])
def test_the_non_python_credential_guard_is_not_fooled(
        tmp_path, label, filename, source, should_flag):
    """Proven to fail before it passes, in both directions and per format.

    The negative half carries the weight again. `secretKeyRef` and
    `ENV X=$ARG` are the two shapes the fix takes, so a guard that flagged
    either would be a guard that punishes the correction — and the gated
    TypeScript default is the exception handoff 18 granted, passing because
    of how it is written rather than because it is named in a waiver list.
    """
    rel = pathlib.Path(filename)
    path = tmp_path / rel.name
    path.write_text(source, encoding="utf-8")

    reader = next(r for _l, r, applies in _NON_PYTHON_CREDENTIAL_READERS
                  if applies(filename))
    flagged = bool(reader(path))
    assert flagged is should_flag, (
        "%s: expected flagged=%s, got %s (%r)"
        % (label, should_flag, flagged, reader(path)))


@pytest.mark.parametrize("label,source,should_flag", _CREDENTIAL_EVASIONS,
                         ids=[c[0] for c in _CREDENTIAL_EVASIONS])
def test_the_credential_guard_is_not_fooled(tmp_path, label, source, should_flag):
    """Proven to fail before it passes, both directions.

    The negative half is the half that matters most. A guard keyed on how a
    string LOOKS flags the brand colour and the localhost URL and misses
    `changeme`; keying it on the NAME of the thing being resolved gets every
    case here right, and the six bypasses above are what it costs to read
    that name in all the ways a person writes it.
    """
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    flagged = bool(_credential_defaults(path))
    assert flagged is should_flag, (
        "%s: expected flagged=%s, got %s" % (label, should_flag, flagged))


# ─── every Odoo test class asks which database it is in ──────────────
#
# Handoff 25. The in-registry suites write, and until now nothing stopped one
# from writing into a client-derived register: report 24 §B measured 88% of
# `jaizbankplc`'s assets as `pytest-*` fixtures. The fix is a guarded base
# class whose `setUpClass` refuses unless `cadra.database_class = test` is set
# in the target database — see `myservice_nrs_base/tests/common.py`.
#
# A guard that lives in a base class is only as good as the discipline of
# using it, and that discipline is exactly the thing that erodes. So the
# discipline is a test: a class deriving straight from a core base escapes the
# refusal, and this fails on it.

#: The core bases that carry no guard. `SingleTransactionCase` is unused in
#: first-party code today and is listed anyway — the point of a drift guard is
#: to be right about the file somebody adds next year.
_UNGUARDED_TEST_BASES = frozenset({
    "TransactionCase", "HttpCase", "SingleTransactionCase",
    # `odoo.addons.base.tests.common`. Real, env-carrying, and unguarded —
    # listed because the point of a drift guard is to be right about the file
    # somebody adds next year, not only about the ones here today.
    "TransactionCaseWithUserDemo", "HttpCaseWithUserDemo",
})

#: Ours. Every one wraps a core base with the database-class assertion.
_GUARDED_TEST_BASES = frozenset({
    "CadraTransactionCase", "CadraHttpCase", "CadraSingleTransactionCase",
})


def _base_name(node):
    """The trailing name of a base expression, however it is spelled.

    `TransactionCase`, `common.TransactionCase` and
    `odoo.tests.common.TransactionCase` are the same base reached three ways,
    and a guard that only knows the bare spelling is a guard with two holes.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _unguarded_test_classes(path):
    """Test classes in `path` that derive from a core base directly.

    Also resolves `from odoo.tests import TransactionCase as Base`: an alias
    is a rename, not an exemption, and a matcher comparing three literal
    strings is blind to it.
    """
    try:
        source = path.read_text(encoding="utf-8") if hasattr(path, "read_text") else path
        tree = ast.parse(source)
    except SyntaxError:
        return []

    aliases = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or "odoo" not in (node.module or ""):
            continue
        for alias in node.names:
            if alias.name in _UNGUARDED_TEST_BASES and alias.asname:
                aliases[alias.asname] = alias.name

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = _base_name(base)
            name = aliases.get(name, name)
            if name in _UNGUARDED_TEST_BASES:
                found.append((node.lineno, node.name, name))
    return found


def _first_party_odoo_test_files():
    """`<module>/tests/*.py` for our own modules only.

    `myservice_nrs_base/tests/common.py` is where the guarded bases are
    DEFINED, so it is the one file that must name the core bases.
    """
    for glob in FIRST_PARTY_GLOBS:
        for module_dir in sorted(REPO_ROOT.glob(glob)):
            if not (module_dir / "__manifest__.py").exists():
                continue
            tests_dir = module_dir / "tests"
            if not tests_dir.is_dir():
                continue
            # rglob, not glob: `tests/sub/test_x.py` is reachable through
            # `tests/__init__.py` and a top-level-only scan never sees it.
            for path in sorted(tests_dir.rglob("*.py")):
                if path.name == "common.py" and module_dir.name == "myservice_nrs_base":
                    continue
                yield path


def test_every_odoo_test_class_derives_from_a_guarded_base():
    """No in-registry test class may skip the database-class refusal."""
    offenders = []
    for path in _first_party_odoo_test_files():
        for lineno, cls, base in _unguarded_test_classes(path):
            offenders.append(
                "%s:%d  class %s(%s)"
                % (path.relative_to(REPO_ROOT), lineno, cls, base))
    assert not offenders, (
        "These test classes derive from a core Odoo base and therefore never "
        "ask which database they are about to write to:\n  "
        + "\n  ".join(offenders)
        + "\n\nDerive from the guarded base instead:\n"
          "  from odoo.addons.myservice_nrs_base.tests.common import "
          "CadraTransactionCase, CadraHttpCase\n"
          "See myservice_nrs_base/database_class.py for why there is no "
          "opt-out.")


def test_the_test_base_guard_would_have_caught_an_unguarded_class(tmp_path):
    """Proved to fail first, in both directions.

    CLAUDE.md's standing rule: a guard nobody has watched fail is a guard that
    passes. Report 22 shipped one whose mutation proof asserted on a name that
    never existed, so it was green against a file it could not read.
    """
    guarded = tmp_path / "test_guarded.py"
    guarded.write_text(
        "from odoo.addons.myservice_nrs_base.tests.common import "
        "CadraTransactionCase\n"
        "class TestFine(CadraTransactionCase):\n"
        "    pass\n", encoding="utf-8")
    assert _unguarded_test_classes(guarded) == []

    for label, source in (
        ("bare name",
         "from odoo.tests import TransactionCase\n"
         "class TestBad(TransactionCase):\n    pass\n"),
        ("module-qualified",
         "from odoo.tests import common\n"
         "class TestBad(common.HttpCase):\n    pass\n"),
        ("fully qualified",
         "import odoo\n"
         "class TestBad(odoo.tests.common.TransactionCase):\n    pass\n"),
        ("a core base sitting SECOND, behind a guarded one",
         # The shape the first pass of handoff 25 actually missed, on two real
         # classes in myservice_workflow/tests/test_callback_replay.py. The
         # first version of this proof wrote `class TestBad(HttpCase, Mixin)`
         # — core base FIRST — which the matcher caught for the wrong reason
         # and which proved nothing about the case it was labelled for. Same
         # failure mode as report 22's guard asserting on a variable name that
         # never existed.
         "class TestBad(CadraHttpCase, TransactionCase):\n    pass\n"),
        ("a core base second, module-qualified",
         "class TestBad(CadraHttpCase, common.HttpCase):\n    pass\n"),
        ("aliased on import",
         "from odoo.tests import TransactionCase as Base\n"
         "class TestBad(Base):\n    pass\n"),
    ):
        path = tmp_path / "test_bad.py"
        path.write_text(source, encoding="utf-8")
        assert _unguarded_test_classes(path), "missed the %s case" % label


def test_the_test_base_guard_covers_the_modules_we_think_it_does():
    """The guard reads real files, and enough of them.

    A scan whose file list quietly went empty passes every assertion in it.
    The numbers are floors, not equalities — adding a test module must not
    fail this.
    """
    files = list(_first_party_odoo_test_files())
    modules = {p.parent.parent.name for p in files}
    assert len(modules) >= 13, (
        "expected in-registry tests in at least 13 first-party modules, found "
        "%d: %s" % (len(modules), sorted(modules)))
    assert len(files) >= 36, (
        "expected at least 36 first-party Odoo test files, found %d"
        % len(files))
    guarded = sum(
        1 for p in files
        if any(b in p.read_text(encoding="utf-8") for b in _GUARDED_TEST_BASES))
    assert guarded >= 36, (
        "only %d of %d first-party Odoo test files name a guarded base"
        % (guarded, len(files)))


# ─── a fixture may not mint a credential that lies about itself ──────
#
# Handoff 25 §A. `is_test_credential` is what makes a fixture identifiable
# after the fact: it drives `nrs.asset.custody.source = 'test'`, which is why
# 352 custody rows in `jaizbankplc` self-label without anyone curating them.
#
# Handoff 23 minted `Handoff23 Approver` with a direct `create()` and the flag
# defaulted off. The six disposals it approved are the ONE class of artefact in
# that register a reader cannot identify from the record itself — they had to
# be found by name pattern and marked by hand afterwards. One unset boolean is
# the whole difference between a fixture that discloses itself and a fabricated
# approval sitting unlabelled in an auditor-facing report.
#
# So there is one way to mint a credential in a test — `create_api_client`,
# which forces the flag — and this fails on any other.

_API_CLIENT_MODEL = "myservice.api.client"


def _direct_credential_creations(path):
    """Calls that `create()` an API client other than through the fixture.

    Matched on the AST rather than on text: the model name and the `.create`
    can sit on different lines, `.sudo()` may or may not be in between, and a
    regex over the source gets both wrong.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    # Names bound to this model anywhere in the file:
    #     Client = cls.env["myservice.api.client"]
    #     Client = self.env["myservice.api.client"].sudo()
    handles = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        cur = node.value
        while True:
            if isinstance(cur, ast.Call):
                cur = cur.func
            elif isinstance(cur, ast.Attribute):
                cur = cur.value
            else:
                break
        if (isinstance(cur, ast.Subscript)
                and isinstance(cur.slice, ast.Constant)
                and cur.slice.value == _API_CLIENT_MODEL):
            handles.add(target.id)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "create":
            continue
        # Walk back down the chain to whatever the call hangs off, stepping
        # over `.sudo()`, `.with_context(...)` and friends.
        cur = func.value
        while True:
            if isinstance(cur, ast.Call):
                cur = cur.func
            elif isinstance(cur, ast.Attribute):
                cur = cur.value
            else:
                break
        if isinstance(cur, ast.Subscript):
            key = cur.slice
            if isinstance(key, ast.Constant) and key.value == _API_CLIENT_MODEL:
                found.append((node.lineno, _API_CLIENT_MODEL))
        elif isinstance(cur, ast.Name) and cur.id in handles:
            # `Client = cls.env["myservice.api.client"]` on one line and
            # `Client.create({...})` on another. This is not hypothetical: it
            # is VERBATIM the shape that stood in test_auth_failure_causes.py,
            # test_pagination_cap.py, test_custody_is_not_capped.py and
            # test_limit_change_revokes.py until handoff 25 rewrote them, and
            # the first cut of this guard could not see the very spelling it
            # had just finished removing.
            found.append((node.lineno, _API_CLIENT_MODEL))
    return found


def test_no_test_mints_a_credential_outside_the_fixture():
    """Every test credential says it is one."""
    offenders = []
    for path in _first_party_odoo_test_files():
        for lineno, model in _direct_credential_creations(path):
            offenders.append(
                "%s:%d  create() on %s"
                % (path.relative_to(REPO_ROOT), lineno, model))
    assert not offenders, (
        "These tests mint an API credential directly, so `is_test_credential` "
        "takes its default and anything written under the credential cannot "
        "be identified as a fixture afterwards:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse the fixture instead, which forces the flag:\n"
          "  cls.create_api_client({...})\n"
          "(myservice_nrs_base/tests/common.py). A test that needs an "
          "UNFLAGGED credential to prove the flag's own behaviour should "
          "toggle it on a record it already holds — "
          "test_custody_is_not_capped.py does exactly that.")


def test_the_credential_minting_guard_would_have_caught_handoff_23(tmp_path):
    """Proved against the real shape that got through, and against its cousins.

    The first case below is `test_approve_disposal_route.py:72` as handoff 23
    actually wrote it. A guard that cannot flag the line it was written for is
    report 22's CI-series guard again.
    """
    for label, source, should_flag in (
        ("handoff 23, verbatim",
         'cls.client_rec = cls.env["myservice.api.client"].sudo().create({\n'
         '    "name": "Approver probe", "scopes": "approvals:write"})\n', True),
        ("no sudo",
         'x = self.env["myservice.api.client"].create({"name": "p"})\n', True),
        ("via with_context",
         'x = self.env["myservice.api.client"].with_context(a=1).create({})\n', True),
        ("through the fixture",
         'x = cls.create_api_client({"name": "p"})\n', False),
        ("bound to a local first — the shape handoff 25 removed",
         'Client = cls.env["myservice.api.client"]\n'
         'cls.live = Client.create({"name": "auth probe live"})\n', True),
        ("bound to a local with .sudo() in the chain",
         'C = self.env["myservice.api.client"].sudo()\n'
         'C.create({"name": "p"})\n', True),
        ("a different model entirely",
         'x = self.env["nrs.asset"].sudo().create({"name": "a"})\n', False),
        ("a local bound to a different model",
         'Asset = self.env["nrs.asset"]\nAsset.create({"name": "a"})\n', False),
        ("writing the flag on a record already held",
         'self.client_test.is_test_credential = False\n', False),
    ):
        path = tmp_path / "sample.py"
        path.write_text(source, encoding="utf-8")
        flagged = bool(_direct_credential_creations(path))
        assert flagged is should_flag, (
            "%s: expected flagged=%s, got %s" % (label, should_flag, flagged))


# ─── the database-class guard may not read through a cache ───────────
#
# Handoff 25. The first cut of `database_class()` used
# `ir.config_parameter.get_param`, which is `@ormcache`d PER WORKER. During
# its own proof run the route reported `database_class = "client"` for a
# database whose parameter row had been deleted, while the suite — pointed at
# a database carrying no mark at all — ran 24 writing tests to a green pass.
#
# A guard served from a stale cache says yes about a state that has stopped
# being true. This fails if the cached reader comes back.

_DATABASE_CLASS_MODULE = REPO_ROOT / "myservice_nrs_base" / "database_class.py"


def _reads_through_a_cache(source):
    """True if `database_class()` resolves the mark through `get_param`.

    Returns None if the function is absent — a caller asserting on the live
    module should notice that rather than read it as a pass.
    """
    tree = ast.parse(source)
    func = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "database_class"),
                None)
    if func is None:
        return None
    # The docstring EXPLAINS why `get_param` is wrong, so scanning the whole
    # function would flag the explanation. Read the statements only.
    statements = [n for n in func.body
                  if not (isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))]
    body = "\n".join(ast.get_source_segment(source, n) or "" for n in statements)
    return "get_param" in body or not ("ir_config_parameter" in body
                                       and "execute" in body)


def test_the_database_class_is_read_from_the_database_not_a_cache():
    verdict = _reads_through_a_cache(
        _DATABASE_CLASS_MODULE.read_text(encoding="utf-8"))
    assert verdict is not None, (
        "database_class() is gone from %s — the guard is asserting on nothing."
        % _DATABASE_CLASS_MODULE)
    assert verdict is False, (
        "database_class() resolves the mark through `get_param`, which is "
        "ormcached per worker and can answer with a mark the database no "
        "longer holds. Read the row with SQL — see that module's docstring "
        "for the run where this leaked 24 writing tests onto an unmarked "
        "database.")


def test_the_cache_guard_would_have_caught_the_first_cut(tmp_path):
    """Proved against the exact code that leaked, and against its cousins."""
    for label, source, should_flag in (
        ("the first cut, verbatim",
         'def database_class(env):\n'
         '    raw = env["ir.config_parameter"].sudo().get_param(PARAM)\n'
         '    return raw\n', True),
        ("get_param hidden behind a local",
         'def database_class(env):\n'
         '    icp = env["ir.config_parameter"].sudo()\n'
         '    return icp.get_param(PARAM)\n', True),
        ("neither cached nor a direct read — a third way in",
         'def database_class(env):\n'
         '    return SOME_MODULE.lookup(PARAM)\n', True),
        ("the SQL read that replaced it",
         'def database_class(env):\n'
         '    env.cr.execute("SELECT value FROM ir_config_parameter '
         'WHERE key = %s", (PARAM,))\n'
         '    return env.cr.fetchone()\n', False),
        ("prose about get_param is not a use of it",
         'def database_class(env):\n'
         '    """Not get_param, deliberately."""\n'
         '    env.cr.execute("SELECT value FROM ir_config_parameter '
         'WHERE key = %s", (PARAM,))\n'
         '    return env.cr.fetchone()\n', False),
    ):
        assert _reads_through_a_cache(source) is should_flag, (
            "%s: expected flagged=%s" % (label, should_flag))

    assert _reads_through_a_cache("def something_else():\n    pass\n") is None


# ─── the guarded base only runs if the subclass lets it ──────────────
#
# Handoff 25. `CadraTransactionCase.setUpClass` is where the database-class
# refusal happens, so a subclass that defines `setUpClass` and does not call
# `super().setUpClass()` silently skips it.
#
# `myservice_nrs_base/tests/common.py` claimed this was "enforced by
# tests/test_source_guards.py" before anything enforced it. A docstring
# asserting a protection the repository does not have is the exact class of
# claim CLAUDE.md's standard is about, so the claim is made true here rather
# than softened.


def _setupclass_without_super(path):
    """Test classes overriding `setUpClass` without calling super()."""
    try:
        source = path.read_text(encoding="utf-8") if hasattr(path, "read_text") else path
        tree = ast.parse(source)
    except SyntaxError:
        return []
    offenders = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef) or fn.name != "setUpClass":
                continue
            calls_super = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "setUpClass"
                and isinstance(c.func.value, ast.Call)
                and isinstance(c.func.value.func, ast.Name)
                and c.func.value.func.id == "super"
                for c in ast.walk(fn)
            )
            if not calls_super:
                offenders.append((fn.lineno, cls.name))
    return offenders


def test_every_setupclass_calls_super():
    """Otherwise the class skips the database-class refusal entirely."""
    offenders = []
    for path in _first_party_odoo_test_files():
        for lineno, cls in _setupclass_without_super(path):
            offenders.append("%s:%d  %s.setUpClass"
                             % (path.relative_to(REPO_ROOT), lineno, cls))
    assert not offenders, (
        "These classes override setUpClass without calling "
        "super().setUpClass(), so the database-class guard in "
        "CadraTransactionCase never runs for them:\n  "
        + "\n  ".join(offenders))


def test_the_setupclass_guard_would_have_caught_a_skipped_super(tmp_path):
    """Proved in both directions."""
    for label, source, should_flag in (
        ("no super() at all",
         "class T(CadraTransactionCase):\n"
         "    @classmethod\n"
         "    def setUpClass(cls):\n"
         "        cls.x = 1\n", True),
        ("calls a DIFFERENT super method",
         "class T(CadraTransactionCase):\n"
         "    @classmethod\n"
         "    def setUpClass(cls):\n"
         "        super().setUp()\n", True),
        ("calls super().setUpClass()",
         "class T(CadraTransactionCase):\n"
         "    @classmethod\n"
         "    def setUpClass(cls):\n"
         "        super().setUpClass()\n"
         "        cls.x = 1\n", False),
        ("does not override setUpClass at all",
         "class T(CadraTransactionCase):\n    pass\n", False),
    ):
        assert bool(_setupclass_without_super(source)) is should_flag, label


# ─── nothing but the guard may read the raw credentials ──────────────
#
# Handoff 25. `tests/conftest.py` hands out `creds` only after
# `database_accepts_test_writes` has cleared the target database;
# `_creds_unchecked` exists solely so the guard can read the file without
# depending on its own output.
#
# This guard exists because gating `token` alone was NOT enough: four tests
# took `api_base` + `creds` and POSTed to `/auth/token` with bare `requests`,
# so `pytest tests/test_auth.py` against a client-derived register ran green
# without the guard ever being instantiated. Gating the credentials closed
# that by construction — this stops the private fixture becoming the new door.

def test_only_conftest_reads_the_unchecked_credentials():
    offenders = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        if path.name == "conftest.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        # AST, not text: this very file NAMES the fixture in its own comments
        # and assertion messages, and a substring scan flags the explanation —
        # the same trap the cache guard fell into one section above. A comment
        # is not a use; a parameter or a reference is.
        used = any(
            (isinstance(n, ast.Name) and n.id == "_creds_unchecked")
            or (isinstance(n, ast.arg) and n.arg == "_creds_unchecked")
            for n in ast.walk(tree)
        )
        if used:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "These test modules reach for `_creds_unchecked`, which bypasses the "
        "database-class guard:\n  " + "\n  ".join(offenders)
        + "\n\nUse the `creds` fixture, which is the same value handed out "
          "only after the target database has been cleared.")


def test_the_credentials_gate_is_actually_wired():
    """`creds` must depend on the guard, or the gate is decorative.

    Asserted on the signature rather than trusted: this is a fixture
    dependency, and a fixture dependency that gets dropped in a refactor
    fails nothing and reopens the second door silently.
    """
    source = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "creds"), None)
    assert fn is not None, "the `creds` fixture is gone from tests/conftest.py"
    args = [a.arg for a in fn.args.args]
    assert "database_accepts_test_writes" in args, (
        "`creds` no longer depends on `database_accepts_test_writes`, so "
        "any test taking `creds` can authenticate against an unmarked "
        "database. Its arguments are: %s" % args)


# ═════════════════════════════════════════════════════════════════════════
# Handoff 26 §A — every model the API can create labels itself
#
# `nrs.asset.custody` has carried a derived `source = 'test'` since handoff
# 24, which is why 352 of its rows self-identify with nobody curating
# anything. Every other model relied on a NAME PREFIX, which is a convention
# — a thing somebody remembers to type — and `request.request` never had one
# at all, so the 460 requests on `jaizbankplc` can never be found again.
#
# `cadra.test.fixture.mixin` (`myservice_api/models/test_fixture.py`) makes
# the derivation general. THIS guard closes the class rather than the
# instance: it enumerates every model any first-party code path can create
# and fails on one that is neither labelled, nor labelled by its own older
# mechanism, nor classified as unreachable-from-a-credential WITH A REASON.
#
# A model added next year turns the suite red on the day it is added.
# ═════════════════════════════════════════════════════════════════════════

#: Receiver methods whose presence in an attribute chain does not change
#: which MODEL is being addressed. `Client.sudo().with_context(...).create()`
#: still creates a `myservice.api.client`.
_TRANSPARENT_CHAIN = frozenset({
    "sudo", "with_context", "with_user", "with_company", "with_env",
    "browse", "search", "exists", "filtered", "sorted", "ensure_one",
})

#: `message_post` is a `mail.message` create wearing a different name. It is
#: resolved explicitly because the whole point of this guard is that a create
#: spelled unusually is exactly the one that gets missed — report 25's
#: credential guard could not see `Client = env[MODEL]` followed by
#: `Client.create(...)`, which was verbatim the spelling it had just removed
#: from four files.
#: `set_param` writes an `ir.config_parameter` row, creating it when absent.
#: It was invisible to the first version of this guard, so that model
#: appeared in NO classification while the guard's own docstring claimed to
#: enumerate every model any first-party path can create. Found by the
#: verification pass.
_CREATE_ALIASES = {"create": None, "copy": None,
                   "message_post": "mail.message",
                   "set_param": "ir.config_parameter"}

#: Sentinel for a helper that returns `self` rather than a named model.
_SELF = object()

#: Sentinel for a name bound to more than one model in the same file. Any
#: create through such a name is reported UNRESOLVED, which fails the guard,
#: rather than silently resolved to whichever binding came last.
_AMBIGUOUS = object()


def _strip_chain(node):
    """Peel `.sudo()`, `.with_context(...)` and friends off a receiver."""
    while True:
        if isinstance(node, ast.Call):
            node = node.func
            continue
        if isinstance(node, ast.Attribute) and node.attr in _TRANSPARENT_CHAIN:
            node = node.value
            continue
        return node


def _env_subscript_model(node, consts):
    """`self.env['x']`, `env['x']`, `self.env[CONST]` → `'x'`, else None."""
    inner = _strip_chain(node)
    if not isinstance(inner, ast.Subscript):
        return None
    base = _strip_chain(inner.value)
    is_env = ((isinstance(base, ast.Attribute) and base.attr == "env")
              or (isinstance(base, ast.Name) and base.id == "env"))
    if not is_env:
        return None
    key = inner.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    if isinstance(key, ast.Name):
        return consts.get(key.id)
    return None


def _model_of_class(node):
    """The model a `class` addresses: `_name` wins, else the first `_inherit`."""
    name = inherit = None
    for stmt in node.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name) or target.id not in ("_name", "_inherit"):
            continue
        value = stmt.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            resolved = value.value
        elif (isinstance(value, (ast.List, ast.Tuple)) and value.elts
              and isinstance(value.elts[0], ast.Constant)):
            resolved = value.elts[0].value
        else:
            resolved = None
        if target.id == "_name":
            name = resolved
        else:
            inherit = resolved
    return name or inherit


def _created_models(path):
    """Every model a `create`-shaped call in `path` addresses.

    Resolves four spellings, because the fifth one is always the one that
    bites: a string literal subscript, a module-level string CONSTANT used as
    a subscript, a NAME bound earlier to `env['x']`, and bare `self` inside a
    model class. `super().create(...)` is skipped — it is the same model.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))

    # These maps are flow- and scope-INSENSITIVE: `ast.walk` flattens the
    # whole module, so a name bound in two functions collapses to one entry.
    # Last-write-wins would make the resolver answer CONFIDENTLY WRONG and
    # report nothing unresolved — a model silently invisible to the guard,
    # which is the failure this whole file exists to stop.
    #
    # So a name bound to two DIFFERENT models is marked ambiguous, and any
    # create through it is reported as unresolved, which FAILS the guard.
    # Loud and over-strict beats quiet and wrong: the remedy is to spell the
    # model at the create site.
    consts, env_names = {}, {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        target = node.targets[0].id
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if target in consts and consts[target] != node.value.value:
                consts[target] = _AMBIGUOUS
            elif consts.get(target) is not _AMBIGUOUS:
                consts[target] = node.value.value
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        model = _env_subscript_model(node.value, consts)
        if not model or model is _AMBIGUOUS:
            continue
        target = node.targets[0].id
        if target in env_names and env_names[target] != model:
            env_names[target] = _AMBIGUOUS
        elif env_names.get(target) is not _AMBIGUOUS:
            env_names[target] = model

    # Single-`return` helpers that hand back a recordset, e.g.
    # `def _dispatch(self): return self.sudo().with_context(...)`. Odoo code
    # is full of these, and `self._dispatch().create(...)` is a create the
    # resolver would otherwise have to give up on — and a create it gives up
    # on is a model nobody has to classify, which is the hole.
    #: name -> model string, or the sentinel `_SELF` meaning "the enclosing
    #: class's own model".
    aliases = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [st for st in node.body if not (isinstance(st, ast.Expr)
                and isinstance(st.value, ast.Constant))]
        if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
            continue
        model = _env_subscript_model(body[0].value, consts)
        resolved = None
        if model and model is not _AMBIGUOUS:
            resolved = model
        else:
            inner = _strip_chain(body[0].value)
            if isinstance(inner, ast.Name) and inner.id == "self":
                resolved = _SELF
        if resolved is None:
            continue
        # Two classes in one file each defining `_target` would otherwise
        # collapse to whichever came last. Same rule as above.
        if node.name in aliases and aliases[node.name] is not resolved:
            aliases[node.name] = _AMBIGUOUS
        elif aliases.get(node.name) is not _AMBIGUOUS:
            aliases[node.name] = resolved

    enclosing = {}

    def _descend(parent, current):
        for child in ast.iter_child_nodes(parent):
            here = child if isinstance(child, ast.ClassDef) else current
            enclosing[child] = here
            _descend(child, here)

    _descend(tree, None)

    found, unresolved = set(), []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _CREATE_ALIASES:
            continue
        fixed = _CREATE_ALIASES[node.func.attr]
        if fixed:
            found.add(fixed)
            continue
        receiver = node.func.value
        # Checked BEFORE stripping: `_strip_chain` unwraps any Call to its
        # func, so `super().create(...)` arrives here as a bare Name and the
        # obvious `isinstance(inner, ast.Call)` test never fires.
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) \
                and receiver.func.id == "super":
            continue
        model = _env_subscript_model(receiver, consts)
        if model is None:
            inner = _strip_chain(receiver)
            owner = (_model_of_class(enclosing.get(node))
                     if isinstance(enclosing.get(node), ast.ClassDef) else None)
            if isinstance(inner, ast.Name) and inner.id in env_names:
                model = env_names[inner.id]
            elif isinstance(inner, ast.Name) and inner.id == "self":
                model = owner
            else:
                # `self._helper().create(...)` / `_helper().create(...)`
                called = receiver.func if isinstance(receiver, ast.Call) else None
                helper = None
                if isinstance(called, ast.Attribute):
                    helper = called.attr
                elif isinstance(called, ast.Name):
                    helper = called.id
                if helper in aliases:
                    resolved = aliases[helper]
                    if resolved is _AMBIGUOUS:
                        model = None
                    elif resolved is _SELF:
                        model = owner
                    else:
                        model = resolved
        # A sentinel is not a model name. `_AMBIGUOUS` must land in
        # `unresolved` (which fails the guard), never in `found` (which would
        # put an object() in the classification set and pass).
        if isinstance(model, str) and model:
            found.add(model)
        else:
            unresolved.append((path.name, node.lineno))
    return found, unresolved


#: Where the labelled set comes from: the mixin module itself, parsed. Not a
#: list copied into this file — a copied list is a convention, and a
#: convention is the thing this whole handoff is about.
_MIXIN_FILE = REPO_ROOT / "myservice_api" / "models" / "test_fixture.py"
_MIXIN = "cadra.test.fixture.mixin"


def _models_carrying_the_mixin():
    tree = ast.parse(_MIXIN_FILE.read_text(encoding="utf-8"), str(_MIXIN_FILE))
    carrying = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        name = inherits = None
        for stmt in node.body:
            if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)):
                continue
            if stmt.targets[0].id == "_name" and isinstance(stmt.value, ast.Constant):
                name = stmt.value.value
            if stmt.targets[0].id == "_inherit" and isinstance(stmt.value, (ast.List, ast.Tuple)):
                inherits = [e.value for e in stmt.value.elts
                            if isinstance(e, ast.Constant)]
        if name and inherits and _MIXIN in inherits:
            carrying.add(name)
    return carrying


#: Labelled by an OLDER mechanism that predates the mixin and is not worth
#: migrating: the value is a Selection, not a boolean, and three reports and
#: a script cite it by name.
ALREADY_LABELLED = {
    "nrs.asset.custody":
        "`source = 'test'`, derived in myservice_api/models/append_only.py "
        "from the same credential flag. 352 rows on jaizbankplc self-label "
        "because of it — this is the mechanism the mixin generalises. Until "
        "handoff 31 the derivation was an override on THIS model, in "
        "myservice_api/models/asset_custody.py; it is now the one on "
        "`nrs.asset.append.only.mixin`, which custody inherits, and "
        "`test_the_three_records_inherit_the_label_they_are_listed_for` "
        "holds every link of that.",
    "nrs.asset.movement":
        "`source = 'test'`, derived in myservice_api/models/append_only.py "
        "from the same credential flag and by the same one derivation on "
        "`myservice.api.client` — custody's mechanism, for the append-only "
        "record of where an asset has been (handoff 28; its own override in "
        "myservice_api/models/asset_movement.py until handoff 31, the "
        "mixin's since). Measured on test19 the day it landed: 63 of 63 "
        "rows written under the test credential say `test`, and the one "
        "written by a person logged in says `api_move`. "
        "tests/test_asset_history.py holds it over HTTP.",
    "nrs.asset.event":
        "`source = 'test'`, derived in myservice_api/models/append_only.py "
        "from the same credential flag — on the abstract "
        "`nrs.asset.append.only.mixin` rather than on the model, so that a "
        "fourth append-only record cannot be written without the derivation "
        "(handoff 30). The mixin is abstract and creates nothing itself; "
        "what this entry rests on is that `nrs.asset.event` INHERITS it, "
        "which `test_the_three_records_inherit_the_label_they_are_listed_for` "
        "holds. tests/test_asset_events_api.py holds the label over HTTP.",
    "res.users":
        "Labelled through its partner. `res.users` `_inherits` `res.partner` "
        "(`partner_id`), and `res.partner` carries "
        "`cadra.test.fixture.mixin` (myservice_api/models/test_fixture.py), "
        "so creating a user creates a partner whose `is_test_fixture` is "
        "stamped from the acting credential and is readable as "
        "`user.is_test_fixture`. Reachable since handoff 43: "
        "`POST /api/v1/users` creates a person; until then the only writer "
        "was `myservice.api.client._provision_client_user`, which has no "
        "route. myservice_api/tests/test_user_lifecycle.py reads the label back "
        "on the partner after a create under a test credential.",
}

#: Models a create-shaped call addresses that an API CREDENTIAL cannot cause
#: to be created, each with the reason. Not a convenience list: adding an
#: entry here is a claim somebody can check, and the test below fails if a
#: model is in two classifications at once.
NOT_CREDENTIAL_REACHABLE = {
    "myservice.api.refresh_token":
        "Operational. One row per token mint, GC'd by its own cron. It is "
        "the row report 25 could not avoid writing before its refusal — "
        "authenticating is a write — and it carries no register data.",
    "myservice.api.idempotency":
        "Operational. One row per idempotent request, autovacuumed after "
        "24h. Keyed on (key, path); holds a response body, not a record.",
    "myservice.api.access.change":
        "Written only by the res.users / res.groups recorders "
        "(models/access_recorder.py), which no /api/v1 route reaches — no "
        "route creates or re-groups a user. It is itself an append-only "
        "audit record; labelling an audit record from the credential that "
        "triggered it would put a derived claim inside evidence.",
    "mail.mail":
        "The outgoing-email queue row, not register data. It is a delivery "
        "attempt; the message it delivers IS labelled (mail.message).",
    "nrs.asset.import.line":
        "A line of the asset-import wizard (nrs.asset.import), which is an "
        "Odoo form flow with no route. The ASSETS it produces are labelled.",
    "ir.config_parameter":
        "Tenant CONFIGURATION, not register data — a key/value row, written "
        "through `set_param` by the settings routes and the depreciation "
        "recompute. Labelling one would be labelling a setting, and the "
        "configuration-change report (handoff 23) is what identifies who "
        "wrote a parameter and when.",
    "security.incident":
        "Created by the PUBLIC incident portal "
        "(myservice_security/controllers/portal.py), which authenticates "
        "nobody — there is no credential to derive a label from. A member of "
        "the public filing an incident is not a test fixture.",
    "hr.department":
        None,   # placeholder — replaced below if the mixin carries it
}
# `hr.department` is labelled by the mixin; drop the placeholder rather than
# let a stale entry claim an exemption the code does not take.
NOT_CREDENTIAL_REACHABLE.pop("hr.department", None)


def _first_party_module_python():
    for pattern in FIRST_PARTY_GLOBS:
        for module in sorted(REPO_ROOT.glob(pattern)):
            if not module.is_dir():
                continue
            for path in sorted(module.rglob("*.py")):
                if "/tests/" in str(path) or "__pycache__" in str(path):
                    continue
                yield path


def test_every_model_a_first_party_path_creates_is_classified():
    """The class, not the instance.

    Fails when first-party code gains a create of a model that nobody has
    said whether a test credential should be able to mint. The remedy is one
    of three deliberate acts — add it to the mixin, note that it is labelled
    another way, or write down why a credential cannot reach it — and all
    three are cheaper than finding out from a register two years later.
    """
    created = set()
    unresolved = []
    for path in _first_party_module_python():
        models, misses = _created_models(path)
        created |= models
        unresolved += misses

    labelled = _models_carrying_the_mixin()
    classified = labelled | set(ALREADY_LABELLED) | set(NOT_CREDENTIAL_REACHABLE)
    unclassified = sorted(created - classified)

    assert not unclassified, (
        "these models are created by first-party code and carry no "
        "self-label:\n  %s\n\n"
        "Every record a test credential creates must say so on its face — a "
        "name prefix is a convention and conventions are what left 460 "
        "unidentifiable service requests on a client's register.\n"
        "Do one of three things, deliberately:\n"
        "  1. add the model to myservice_api/models/test_fixture.py so it "
        "carries `cadra.test.fixture.mixin` (and upgrade EVERY tenant — a "
        "stored field is a multi-tenant migration);\n"
        "  2. record it in ALREADY_LABELLED here if it labels itself some "
        "other way, naming the field;\n"
        "  3. record it in NOT_CREDENTIAL_REACHABLE here WITH THE REASON a "
        "credential cannot create it."
        % "\n  ".join(unclassified))

    assert not unresolved, (
        "the resolver could not work out which model these create-shaped "
        "calls address, so the enumeration above is incomplete and this "
        "guard is weaker than it reads:\n  %s"
        % "\n  ".join("%s:%d" % u for u in unresolved))


def test_every_exemption_names_a_reason():
    """An exemption with no reason is a list entry, not a decision."""
    for mapping, label in ((ALREADY_LABELLED, "ALREADY_LABELLED"),
                           (NOT_CREDENTIAL_REACHABLE,
                            "NOT_CREDENTIAL_REACHABLE")):
        for model, reason in mapping.items():
            assert reason and len(reason.strip()) > 30, (
                "%s[%r] carries no usable reason. Say why a credential "
                "cannot create it, or why it labels itself another way."
                % (label, model))


def test_no_model_is_classified_twice():
    """Labelled AND exempt is a contradiction somebody must resolve."""
    labelled = _models_carrying_the_mixin()
    for mapping, label in ((ALREADY_LABELLED, "ALREADY_LABELLED"),
                           (NOT_CREDENTIAL_REACHABLE,
                            "NOT_CREDENTIAL_REACHABLE")):
        clash = sorted(labelled & set(mapping))
        assert not clash, (
            "%s claims %s, but test_fixture.py gives them the mixin. One of "
            "the two is a leftover." % (label, ", ".join(clash)))
    both = sorted(set(ALREADY_LABELLED) & set(NOT_CREDENTIAL_REACHABLE))
    assert not both, "classified twice: %s" % ", ".join(both)


def test_the_mixin_still_declares_models():
    """Report 22 and 25's lesson: assert the subject exists first."""
    assert _MIXIN_FILE.exists(), (
        "myservice_api/models/test_fixture.py is gone — this guard and the "
        "label it enforces are both asserting on nothing.")
    carrying = _models_carrying_the_mixin()
    assert len(carrying) >= 10, (
        "only %d model(s) carry %s. Handoff 26 gave it to fourteen; a "
        "collapse to nearly none is how a label silently stops existing "
        "while its guard goes on passing. Found: %s"
        % (len(carrying), _MIXIN, sorted(carrying)))
    assert "request.request" in carrying, (
        "`request.request` lost the mixin. It is THE measured hole — its "
        "name is a sequence, so without a derived label a test-created "
        "request is indistinguishable from a real one forever.")


_APPEND_ONLY_MIXIN = "nrs.asset.append.only.mixin"
_REGISTER_MODELS = REPO_ROOT / "myservice_asset_register" / "models"
_EVENT_MODEL_FILE = _REGISTER_MODELS / "asset_event.py"
#: The three records the ONE derivation labels, and the file that declares
#: each. Until handoff 31 only the event record reached the label through
#: the mixin; custody and movement each had an override of their own.
_APPEND_ONLY_MODEL_FILES = {
    "nrs.asset.custody": _REGISTER_MODELS / "asset_custody.py",
    "nrs.asset.movement": _REGISTER_MODELS / "asset_movement.py",
    "nrs.asset.event": _EVENT_MODEL_FILE,
}
_APPEND_ONLY_GUARD_FILE = _REGISTER_MODELS / "append_only.py"
_EVENT_LABEL_FILE = REPO_ROOT / "myservice_api" / "models" / "append_only.py"
#: The three per-model overrides handoff 31 deleted. One of them coming back
#: is a second answer to the question the mixin answers.
_RETIRED_LABEL_FILES = tuple(
    REPO_ROOT / "myservice_api" / "models" / name
    for name in ("asset_custody.py", "asset_movement.py", "asset_event.py"))
_GUARD_METHODS = ("create", "write", "unlink", "_resolve_source")


def _class_model_attrs(node):
    """`(_name, [_inherit…])` of a class body; a bare string is a list of one."""
    name, inherits = None, []
    for stmt in node.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            continue
        value = stmt.value
        if stmt.targets[0].id == "_name" and isinstance(value, ast.Constant):
            name = value.value
        if stmt.targets[0].id == "_inherit":
            if isinstance(value, ast.Constant):
                inherits = [value.value]
            elif isinstance(value, (ast.List, ast.Tuple)):
                inherits = [e.value for e in value.elts
                            if isinstance(e, ast.Constant)]
    return name, inherits


def _own_guard_methods(class_node):
    """Which of the append-only guard's four methods a class body defines."""
    return sorted(
        fn.name for fn in class_node.body
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and fn.name in _GUARD_METHODS)


def test_the_three_records_inherit_the_label_they_are_listed_for():
    """Three entries in `ALREADY_LABELLED` are claims. This checks them.

    Until handoff 31 custody and movement each carried their own
    `_resolve_source` override, on the model, so each entry named a file and
    the file named the model; only the event record's derivation was a step
    further away. All three are now: the derivation sits on an ABSTRACT mixin
    in `myservice_api`, and reaches a record only because that record
    inherits the mixin in a different module. Three links, any of which can
    be dropped without anything going red — and then every custody change,
    move, verification and status change this suite writes lands on a
    client-shaped register as `api_write`, permanently, because the records
    are append-only and nobody can relabel them afterwards.

    And ONE derivation means one. A model that grows a `_resolve_source` of
    its own again sits IN FRONT of the mixin's, and that is exactly how
    custody came to honour a `source` any caller could claim for twelve days
    after movement, copied from it, was written without the hole. The same
    for the three override files handoff 31 deleted. The registry has the
    acting half of this (`test_append_only_mixin.py`); this is the half that
    runs with no server.

    And the mixin itself must NOT appear as a created model: it is abstract,
    its `create` is a `super()` call, and a guard that started listing it
    would be asking somebody to classify a table that does not exist.
    """
    for path in (*_APPEND_ONLY_MODEL_FILES.values(), _APPEND_ONLY_GUARD_FILE,
                 _EVENT_LABEL_FILE):
        assert path.exists(), (
            "%s is gone — an entry in ALREADY_LABELLED is citing a file that "
            "does not exist" % path.relative_to(REPO_ROOT))
    assert sorted(_APPEND_ONLY_MODEL_FILES) == sorted(
        m for m in ALREADY_LABELLED if m.startswith("nrs.asset.")), (
        "ALREADY_LABELLED and this guard disagree about which records the "
        "mixin's derivation labels")

    # 1. each model inherits the guard, and defines none of it again…
    for model, path in _APPEND_ONLY_MODEL_FILES.items():
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = {name: (node, inherits)
                   for node in tree.body if isinstance(node, ast.ClassDef)
                   for name, inherits in [_class_model_attrs(node)] if name}
        assert model in classes, (
            "`%s` is no longer declared in %s" % (model, rel))
        model_class, inherits = classes[model]
        assert _APPEND_ONLY_MIXIN in inherits, (
            "`%s` does not inherit `%s` (it inherits %s), so the `test` "
            "derivation in myservice_api never reaches it and its rows are "
            "labelled by route." % (model, _APPEND_ONLY_MIXIN, inherits))
        own = _own_guard_methods(model_class)
        assert not own, (
            "`%s` defines %s itself, in %s. That sits in front of the "
            "mixin's: a second copy of the append-only guard, and the last "
            "time there were two, one of them let a caller file a real "
            "change of custody under `test`." % (model, own, rel))
        assert ("myservice_api/models/append_only.py"
                in ALREADY_LABELLED[model]), (
            "the `%s` entry in ALREADY_LABELLED does not name the file the "
            "derivation lives in" % model)

        # …and can HOLD the label: a Selection without `test` makes the
        # derivation a ValueError inside every write the suite makes.
        source_values = {
            literal.value
            for stmt in model_class.body
            if isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "source"
                    for t in stmt.targets)
            for literal in ast.walk(stmt.value)
            if isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)}
        assert "test" in source_values, (
            "`%s.source` no longer offers `test`" % model)

    # …the guard they inherit is declared, and declares all four.
    tree = ast.parse(_APPEND_ONLY_GUARD_FILE.read_text(encoding="utf-8"))
    declared = [node for node in tree.body if isinstance(node, ast.ClassDef)
                and _class_model_attrs(node)[0] == _APPEND_ONLY_MIXIN]
    assert len(declared) == 1, (
        "%s declares `%s` %d time(s)" % (
            _APPEND_ONLY_GUARD_FILE.relative_to(REPO_ROOT),
            _APPEND_ONLY_MIXIN, len(declared)))
    assert _own_guard_methods(declared[0]) == sorted(_GUARD_METHODS), (
        "the mixin no longer defines the whole guard: %s"
        % _own_guard_methods(declared[0]))
    register_init = (_REGISTER_MODELS / "__init__.py").read_text(
        encoding="utf-8")
    imports = re.findall(r"^from \. import (\w+)", register_init, re.MULTILINE)
    assert "append_only" in imports, (
        "myservice_asset_register/models/__init__.py does not import "
        "`append_only`")
    for later in ("asset_custody", "asset_movement", "asset_event"):
        assert imports.index("append_only") < imports.index(later), (
            "`append_only` is imported after `%s`, which names it in "
            "`_inherit` — a model cannot be built before the mixin it names"
            % later)

    # 2. the derivation is on the MIXIN, ONCE, and says `test`.
    tree = ast.parse(_EVENT_LABEL_FILE.read_text(encoding="utf-8"))
    overrides = [
        fn for node in tree.body if isinstance(node, ast.ClassDef)
        and _APPEND_ONLY_MIXIN in _class_model_attrs(node)[1]
        and _class_model_attrs(node)[0] in (None, _APPEND_ONLY_MIXIN)
        for fn in node.body
        if isinstance(fn, ast.FunctionDef) and fn.name == "_resolve_source"]
    assert overrides, (
        "%s no longer extends `%s._resolve_source`"
        % (_EVENT_LABEL_FILE.relative_to(REPO_ROOT), _APPEND_ONLY_MIXIN))
    returns_test = [
        ret for fn in overrides for ret in ast.walk(fn)
        if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Constant)
        and ret.value.value == "test"]
    assert returns_test, (
        "the `_resolve_source` override never returns `test`")
    assert "_is_test_credential_user" in _EVENT_LABEL_FILE.read_text(
        encoding="utf-8"), (
        "the label is no longer derived from the ONE statement of what a "
        "test credential is, `myservice.api.client._is_test_credential_user`")
    back = [path.relative_to(REPO_ROOT).as_posix()
            for path in _RETIRED_LABEL_FILES if path.exists()]
    assert not back, (
        "%s is back. Handoff 31 replaced three per-model overrides with the "
        "one on the mixin; a per-model file is a second derivation, and "
        "three were 'supposed to be the same rule and were not the same "
        "code'." % ", ".join(back))
    elsewhere = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "myservice_api" / "models").glob("*.py")
        if path != _EVENT_LABEL_FILE
        and re.search(r"def _resolve_source\b",
                      path.read_text(encoding="utf-8")))
    assert not elsewhere, (
        "`_resolve_source` is also defined in %s" % ", ".join(elsewhere))

    # 3. the override is actually loaded.
    init = (REPO_ROOT / "myservice_api" / "models" / "__init__.py").read_text(
        encoding="utf-8")
    assert re.search(r"^from \. import append_only\b", init, re.MULTILINE), (
        "myservice_api/models/__init__.py does not import `append_only`; the "
        "override exists and nothing loads it")
    stale = re.findall(
        r"^from \. import (asset_custody|asset_movement|asset_event)\b",
        init, re.MULTILINE)
    assert not stale, (
        "myservice_api/models/__init__.py still imports %s, which handoff 31 "
        "deleted — the module would not load" % stale)

    # 4. the abstract mixin is not mistaken for a model somebody can create.
    created, unresolved = _created_models(_EVENT_MODEL_FILE)
    assert created == {"nrs.asset.event"}, (
        "expected the one create in this file to resolve to the event "
        "record; got %s" % sorted(created))
    assert not unresolved, unresolved


def test_the_second_copy_guard_sees_a_second_copy():
    """The guard above passes today because no model defines the guard
    again. That is also what it would say if `_own_guard_methods` could not
    see a method at all — so it is shown the shape custody had until
    handoff 31, and must name every one of the four."""
    sample = (
        "class NRSAssetCustody(models.Model):\n"
        "    _name = 'nrs.asset.custody'\n"
        "    _inherit = ['nrs.asset.append.only.mixin']\n"
        "    @api.model_create_multi\n"
        "    def create(self, vals_list):\n"
        "        return super().create(vals_list)\n"
        "    def write(self, vals):\n"
        "        raise UserError('no')\n"
        "    def unlink(self):\n"
        "        raise UserError('no')\n"
        "    @api.model\n"
        "    def _resolve_source(self, declared, user):\n"
        "        return declared or self.env.context.get('src') or 'direct'\n"
        "    def _record(self, asset):\n"
        "        return self.sudo().create({})\n")
    node = ast.parse(sample).body[0]
    assert _class_model_attrs(node) == (
        "nrs.asset.custody", [_APPEND_ONLY_MIXIN])
    assert _own_guard_methods(node) == sorted(_GUARD_METHODS)
    clean = ast.parse(
        "class NRSAssetCustody(models.Model):\n"
        "    _name = 'nrs.asset.custody'\n"
        "    def _record(self, asset):\n"
        "        return self.sudo().create({})\n").body[0]
    assert _own_guard_methods(clean) == []


@pytest.mark.parametrize("label,source,expected", [
    (
        "literal subscript",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        self.env['some.model'].create({})\n",
        {"some.model"},
    ),
    (
        # VERBATIM the spelling report 25's credential guard could not see.
        "name bound to env[...] then .create()",
        "MODEL = 'some.model'\n"
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        Thing = self.env[MODEL]\n"
        "        Thing.create({})\n",
        {"some.model"},
    ),
    (
        "sudo/with_context in the chain",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        self.env['some.model'].sudo().with_context(x=1).create({})\n",
        {"some.model"},
    ),
    (
        "bare self.create inside the model class",
        "class A(models.Model):\n"
        "    _name = 'some.model'\n"
        "    def f(self):\n"
        "        self.create({})\n",
        {"some.model"},
    ),
    (
        "message_post is a mail.message create",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        self.message_post(body='x')\n",
        {"mail.message"},
    ),
    (
        "super().create is the SAME model, not a new one",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def create(self, vals):\n"
        "        return super().create(vals)\n",
        set(),
    ),
])
def test_the_resolver_sees_every_spelling(tmp_path, label, source, expected):
    """Mutation proof, against the spellings that blinded the last guard.

    Report 25 found that the guard written to stop direct credential creates
    could not see `Client = env[MODEL]` then `Client.create(...)` — verbatim
    the spelling it had just removed from four files. A guard is only worth
    what its hardest case proves, so each case here is one that a regex or a
    naive AST walk gets wrong.
    """
    path = tmp_path / "probe.py"
    path.write_text(source, encoding="utf-8")
    found, unresolved = _created_models(path)
    assert found == expected, (
        "%s: resolver returned %s, expected %s" % (label, sorted(found),
                                                   sorted(expected)))
    assert not unresolved, "%s: resolver could not resolve %s" % (label, unresolved)



def _is_allow_list_name(name):
    """Does this module-level name look like a writable-field allow-list?

    NOT `endswith("_WRITABLE_FIELDS")`, which is what the first version of
    this guard tested and which was blind to the two that do not use that
    spelling: `_CATEGORY_WRITABLE` and `_SETTINGS_WRITABLE`
    (`myservice_api/controllers/v1_settings.py:49` and `:57`).
    `_CATEGORY_WRITABLE` gates `nrs.asset.category` — a model that CARRIES the
    mixin — on both the create and the write path, so `is_test_fixture`
    landing there would have left this guard green while the write path
    raised `UserError` out of a route.

    A guard that matches one spelling of the thing it protects is the exact
    defect report 25 found in the credential guard, reproduced in the guard
    written to close it. Matched on the shape of the name instead.
    """
    return "WRITABLE" in name or "ALLOWED_FIELDS" in name


@pytest.mark.parametrize("label,source", [
    (
        "one name bound to two different models in one file",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        Rec = self.env['brand.new.unlabelled']\n"
        "        Rec.create({})\n"
        "    def g(self):\n"
        "        Rec = self.env['nrs.asset']\n"
        "        Rec.create({})\n",
    ),
    (
        "a module constant rebound to a second model",
        "MODEL = 'brand.new.unlabelled'\n"
        "MODEL = 'nrs.asset'\n"
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def f(self):\n"
        "        self.env[MODEL].create({})\n",
    ),
    (
        "two classes in one file each defining the same helper name",
        "class A(models.Model):\n"
        "    _name = 'a.b'\n"
        "    def _target(self):\n"
        "        return self.env['brand.new.unlabelled']\n"
        "    def f(self):\n"
        "        self._target().create({})\n"
        "class B(models.Model):\n"
        "    _name = 'c.d'\n"
        "    def _target(self):\n"
        "        return self.sudo()\n",
    ),
])
def test_an_ambiguous_binding_fails_rather_than_resolving_wrongly(
        tmp_path, label, source):
    """The dangerous half of a flow-insensitive resolver.

    `ast.walk` flattens the module, so a name bound twice would otherwise
    collapse to whichever binding came last — and the resolver would answer
    CONFIDENTLY WRONG with nothing in `unresolved`, hiding a model from the
    guard entirely. Found by the verification pass, which built exactly these
    three shapes and watched `brand.new.unlabelled` disappear.

    The fix is not to resolve them correctly — that needs real scope
    analysis — but to refuse to guess. An ambiguous binding is reported
    unresolved, and an unresolved create FAILS
    `test_every_model_a_first_party_path_creates_is_classified`.
    """
    path = tmp_path / "probe.py"
    path.write_text(source, encoding="utf-8")
    found, unresolved = _created_models(path)
    assert unresolved, (
        "%s: the resolver reported nothing unresolved, so it guessed. "
        "found=%s" % (label, sorted(found)))
    assert all(isinstance(m, str) for m in found), (
        "%s: a sentinel leaked into the resolved set: %r" % (label, found))
    assert "brand.new.unlabelled" not in found or unresolved, (
        "%s: resolved the shadowed model without flagging ambiguity" % label)


def test_the_derived_label_is_not_writable_over_the_api():
    """`is_test_fixture` in a `_WRITABLE_FIELDS` would make it a convention.

    The mixin's `create` derives the value and its `write` refuses to move
    it, so the ORM is closed. This closes the allow-list: a field that
    reaches `_filter_writable` is one an integration can send, and a label a
    caller can send is a label that says whatever the caller wants.
    """
    offenders = []
    for path in _first_party_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                continue
            if not _is_allow_list_name(node.targets[0].id):
                continue
            for literal in ast.walk(node.value):
                if isinstance(literal, ast.Constant) \
                        and literal.value == "is_test_fixture":
                    offenders.append("%s:%d"
                                     % (path.relative_to(REPO_ROOT), node.lineno))
    assert not offenders, (
        "`is_test_fixture` was added to a writable-field allow-list at %s. "
        "It is DERIVED from the acting credential; a caller able to send it "
        "can mint a real-looking record by omitting it, or slander a real "
        "one by sending it." % ", ".join(offenders))


def test_the_allow_list_guard_sees_the_two_it_used_to_miss():
    """Mutation proof, on the two REAL names the first version was blind to.

    Not a synthetic case: `_CATEGORY_WRITABLE` and `_SETTINGS_WRITABLE` are
    in `v1_settings.py` today, neither ends in `_WRITABLE_FIELDS`, and
    `_CATEGORY_WRITABLE` gates a model that carries the mixin.
    """
    for name in ("_CATEGORY_WRITABLE", "_SETTINGS_WRITABLE", "_WRITABLE_FIELDS"):
        assert _is_allow_list_name(name), "%s is not recognised" % name
    for name in ("_FM_DOMAINS", "_PRIORITY_VALUES", "ALL_SCOPES"):
        assert not _is_allow_list_name(name), (
            "%s is matched as an allow-list; the name test is too broad and "
            "the guard will flag things that are not allow-lists" % name)

    # And the scan must actually REACH the file those two live in.
    settings = REPO_ROOT / "myservice_api" / "controllers" / "v1_settings.py"
    assert settings in set(_first_party_python_files()), (
        "v1_settings.py is outside the scanned set, so widening the NAME "
        "test bought nothing")
    found = set()
    tree = ast.parse(settings.read_text(encoding="utf-8"), str(settings))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and _is_allow_list_name(node.targets[0].id)):
            found.add(node.targets[0].id)
    assert {"_CATEGORY_WRITABLE", "_SETTINGS_WRITABLE"} <= found, (
        "the guard does not find the two allow-lists in v1_settings.py; it "
        "found %s" % sorted(found))


# ═════════════════════════════════════════════════════════════════════════
# Handoff 30 §C — three fields that accepted a value and moved nothing
# ═════════════════════════════════════════════════════════════════════════

_V1_ASSETS = REPO_ROOT / "myservice_api" / "controllers" / "v1_assets.py"

#: On the Odoo form these drive `location_id` through an `@api.onchange`. An
#: onchange is a form behaviour and never runs for the API.
_ONCHANGE_ONLY_LOCATION_FIELDS = ("building_id", "floor_id", "room_id")


def _string_literals_of(source, name):
    """The string constants in the module-level assignment to `name`, or None.

    Constants, not text: the allow-list carries a comment explaining why the
    three fields are ABSENT, which names all three, and a guard that grepped
    the file would fail on the explanation of its own rule.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            return {c.value for c in ast.walk(node.value)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    return None


def test_the_location_hierarchy_is_not_writable_over_the_api():
    """`building_id`, `floor_id` and `room_id` stay OUT of `_WRITABLE_FIELDS`.

    Until handoff 30 they were in it, and `PATCH {"building_id": …}` answered
    200, rewrote the building — and with it the published address and the
    coordinates, which are computed from the building — and MOVED NOTHING:
    `location_id` follows them only through a form onchange the API never
    runs. The asset then contradicted itself, and the append-only movement
    record correctly said no move had happened (report 28 §1).

    They were removed rather than made to work, because making them work
    means re-implementing the onchange inside `write`: a second copy of a
    rule, in a programme that has been bitten three times by two things that
    should agree and do not. `location_id` is the one writable statement of
    where an asset is and `POST /assets/<id>/move` is the act.

    Putting one back looks like restoring a feature. It restores the bug.
    `tests/test_asset_events_api.py` holds the behaviour over HTTP — the
    three land in `_warnings.rejected_fields` and the hierarchy is unchanged.
    """
    assert _V1_ASSETS.exists(), "v1_assets.py is gone; this guards nothing"
    writable = _string_literals_of(
        _V1_ASSETS.read_text(encoding="utf-8"), "_WRITABLE_FIELDS")
    assert writable is not None, (
        "`_WRITABLE_FIELDS` is no longer a module-level assignment in "
        "v1_assets.py, so this guard is asserting on nothing")
    # Assert the subject first (reports 22 and 25): an allow-list parsed to
    # an empty set would pass the check below for ever.
    assert {"name", "location_id", "custodian_id", "state"} <= writable, (
        "the allow-list parsed to %d names and lacks fields it is known to "
        "carry — the parser is reading the wrong thing" % len(writable))
    back = sorted(set(_ONCHANGE_ONLY_LOCATION_FIELDS) & writable)
    assert not back, (
        "%s %s back in `v1_assets._WRITABLE_FIELDS`. Over the API a write to "
        "it changes the hierarchy and the published address and does NOT "
        "move the asset, because the derivation is a form onchange. Write "
        "`location_id`, or call POST /assets/<id>/move."
        % (", ".join("`%s`" % f for f in back),
           "is" if len(back) == 1 else "are"))


def test_the_hierarchy_guard_reads_literals_and_not_comments():
    """Mutation proof, both ways, on the shape the real file has."""
    clean = ('_WRITABLE_FIELDS = {\n'
             '    "name",\n'
             '    # `building_id` was here until handoff 30.\n'
             '    "location_id",\n'
             '}\n')
    assert _string_literals_of(clean, "_WRITABLE_FIELDS") == {
        "name", "location_id"}, (
        "a COMMENT naming the field was read as the field being writable")
    reverted = clean.replace('"location_id",', '"building_id", "location_id",')
    assert "building_id" in _string_literals_of(reverted, "_WRITABLE_FIELDS")
    assert _string_literals_of(clean, "_NO_SUCH_LIST") is None


# ═════════════════════════════════════════════════════════════════════════
# A comment that names a test must name one that exists
#
# Handoff 26 wrote, in the mixin's own header, that the enumeration guard in
# this file was named `test_every_api_creatable_model_self_labels`. No such
# function was ever written — the guard is
# `test_every_model_a_first_party_path_creates_is_classified`. The sentence
# was wrong the moment it was typed, and nothing would have caught it.
#
# (That claim is deliberately NOT written here in the `<file>.py::<name>`
# form this guard matches on, or the guard would flag its own explanation.
# The mutation proof below exercises the real form on a temporary string.)
#
# That is report 25 finding 9 again ("a docstring asserting a protection the
# repo did not have") and it is the §B shape in prose: a reference that names
# a thing, the thing does not exist, and nobody hears about it. A reader who
# goes looking for the named test and cannot find it has to work out whether
# the guard was renamed, moved, or never existed.
#
# Only FIRST-PARTY references are checked. `odoo/modules/migration.py::
# VALID_MIGRATE_PARAMS` points into Odoo core, which is not in this repo.
# ═════════════════════════════════════════════════════════════════════════

#: `::` may be followed by a line break and a comment/docstring continuation
#: before the name — which is how the very reference that prompted this guard
#: was written, after it was wrapped to fit the column width:
#:
#:     # `tests/test_source_guards.py::
#:     # test_every_model_a_first_party_path_creates_is_classified`
#:
#: The first version required the name to follow `::` immediately, so it
#: found ZERO references in the one file whose broken reference prompted it,
#: and passed. A guard blind to its own headline case is the defect, not a
#: detail of it.
_PY_REF = re.compile(
    r"([A-Za-z0-9_/]+\.py)::"          # the file
    r"(?:\s*\n\s*[#*]?\s*)?"           # an optional wrap: newline, indent,
                                       # and a leading `#` or `*` if the
                                       # continuation line carries one
    r"([A-Za-z0-9_]+)")                # the name


def _python_files_to_scan():
    yield from _first_party_python_files()
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        yield path
    for path in sorted((REPO_ROOT / "scripts").glob("*.py")):
        yield path


@functools.lru_cache(maxsize=1)
def _files_a_bare_name_may_resolve_to():
    """basename → the governed files carrying it.

    The universe is `_python_files_to_scan()` — the first-party modules plus
    `tests/` and `scripts/` — and NOT the whole working tree. That is the
    difference between a guard that says the same thing everywhere and one
    that does not.

    **It used to `rglob` the repository**, excluding `__pycache__`, `/dist/`,
    `node_modules` and `.venv`, and resolve when exactly one file survived.
    Two things were wrong with that, and the second is the one that bit:

    1. It could resolve a bare name onto a VENDORED tree — `crnd-19/`,
       `oca-19/` — which this guard does not govern and whose contents we do
       not control. A reference is then checked against a file nobody here
       wrote.
    2. The answer depended on files that are not in the repository. The
       working tree carries `_upgrade/`, which is untracked scratch, and it
       holds a second `ir_actions.py`. Locally that made TWO matches, so the
       reference resolved to None and was skipped; in a clean CI checkout
       `_upgrade/` does not exist, ONE match survived, and the same commit
       failed on a name that file does not define. **The test passed on
       every developer's machine and failed in CI, because an untracked
       directory was load-bearing in a guard about references.**

    Restricting the universe fixes both at once and restores the documented
    intent: `ir_actions.py::IrActionsServer` is Odoo core, it is not
    vendored here, so nothing governed carries that basename, it resolves to
    None, and a BARE unresolved name is skipped rather than failed — exactly
    what the comment in the caller has always said should happen.
    """
    index = {}
    for path in _python_files_to_scan():
        index.setdefault(path.name, []).append(path)
    return index


def _resolve_referenced_file(relpath, source_path):
    """Find the file a `<path>.py::<name>` reference means, or None.

    An explicit path — one carrying directories — is still resolved wherever
    it points, vendored trees included. That is deliberate: it is a statement
    about a specific file rather than a guess, and a miss there is a real
    breakage the caller reports. Only the BARE-name fallback is restricted.
    """
    candidates = [REPO_ROOT / relpath, source_path.parent / relpath]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # A bare or partial path — match on the tail, but only if it is unique
    # among the files this guard governs.
    tail = relpath.split("/")[-1]
    matches = _files_a_bare_name_may_resolve_to().get(tail, ())
    return matches[0] if len(matches) == 1 else None


def _defined_names(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_a_comment_that_names_a_test_names_one_that_exists():
    broken = []
    for path in _python_files_to_scan():
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for relpath, name in _PY_REF.findall(source):
            if relpath.startswith("odoo/") or "/dist-packages/" in relpath:
                continue          # Odoo core, not in this repository
            target = _resolve_referenced_file(relpath, path)
            if target is None:
                # A BARE filename that resolves to nothing points outside
                # this repository — `ir_actions.py::IrActionsServer` is Odoo
                # core, which is not vendored here and cannot be checked. A
                # reference carrying DIRECTORIES is ours, and a miss there is
                # a real breakage.
                if "/" in relpath:
                    broken.append("%s → %s::%s (no such file in this repo)"
                                  % (path.relative_to(REPO_ROOT), relpath, name))
                continue
            defined = _defined_names(target)
            if defined is None:
                continue
            if name not in defined:
                broken.append(
                    "%s → %s::%s (file exists; that name is not defined in it)"
                    % (path.relative_to(REPO_ROOT), relpath, name))
    assert not broken, (
        "these comments name something that does not exist:\n  %s\n\n"
        "A reference that names a thing which is not there is the §B shape in "
        "prose — the reader cannot tell a rename from a guard that was never "
        "written. Fix the reference, or write the thing."
        % "\n  ".join(broken))


def test_the_reference_guard_catches_the_sentence_that_prompted_it(tmp_path):
    """Mutation proof, on the exact sentence handoff 26 shipped and corrected.

    Not a synthetic example: this is verbatim what
    `myservice_api/models/test_fixture.py` said before the verification pass,
    naming a function that was never written.
    """
    real = REPO_ROOT / "tests" / "test_source_guards.py"
    defined = _defined_names(real)
    assert defined is not None

    wrong = "test_every_api_creatable_model_self_labels"
    right = "test_every_model_a_first_party_path_creates_is_classified"
    assert wrong not in defined, (
        "the name this proof calls WRONG now exists, so the proof no longer "
        "distinguishes anything — pick another")
    assert right in defined, (
        "the guard this proof calls RIGHT is gone from %s, so the guard it "
        "protects is asserting on nothing" % real.name)

    # And the matcher must actually pull the name out of a prose sentence —
    # on ONE line, and WRAPPED across two, which is how the reference that
    # prompted this guard is really written.
    one_line = ("# `tests/test_source_guards.py::%s`\n"
                "# walks every route and fails if a model has no label.\n" % wrong)
    assert _PY_REF.findall(one_line) == [("tests/test_source_guards.py", wrong)], (
        "the matcher did not extract the name from a single-line reference")

    wrapped = ("# `tests/test_source_guards.py::\n"
               "# %s`\n" % wrong)
    assert _PY_REF.findall(wrapped) == [("tests/test_source_guards.py", wrong)], (
        "the matcher cannot see a reference wrapped across two comment lines "
        "— which is exactly how the reference in "
        "myservice_api/models/test_fixture.py is written, so the guard would "
        "find nothing in the one file that prompted it")

    # Not a hypothetical: assert it on the real file.
    mixin = REPO_ROOT / "myservice_api" / "models" / "test_fixture.py"
    refs = _PY_REF.findall(mixin.read_text(encoding="utf-8"))
    assert refs, (
        "the guard finds NO `<file>.py::<name>` reference in %s, which "
        "carries one. It is passing by seeing nothing." % mixin.name)
    assert (real.relative_to(REPO_ROOT).as_posix(), right) in refs, (
        "the reference in %s no longer resolves to the guard it names; "
        "found %r" % (mixin.name, refs))


def test_a_bare_reference_resolves_only_against_files_this_guard_governs():
    """The resolver, proved in both directions.

    `test_a_comment_that_names_a_test_names_one_that_exists` passed on every
    developer's machine and failed in CI on the same commit, because the
    resolver used to `rglob` the WORKING TREE: locally the untracked
    `_upgrade/` scratch directory held a second `ir_actions.py`, two matches
    meant "ambiguous, skip", and a clean checkout had only the `crnd-19/` one
    — which resolved, and does not define `IrActionsServer`. An untracked
    directory was load-bearing in a guard about references.

    So this asserts the property that makes the answer the same everywhere:
    a BARE name resolves only against the files this guard governs.
    """
    index = _files_a_bare_name_may_resolve_to()

    # 1. Nothing vendored or scratch is in the universe. These are the trees
    #    whose contents we do not control, and `dist/` is off every addons
    #    path entirely.
    for tail, paths in index.items():
        for path in paths:
            rel = path.relative_to(REPO_ROOT).as_posix()
            assert not rel.startswith(("dist/", "crnd-19/", "oca-19/",
                                       "_upgrade/", "Frontend/")), (
                "%s is resolvable by bare name but is not a file this guard "
                "governs" % rel)

    # 2. The reference that started this: `ir_actions.py` is Odoo core. It is
    #    not vendored in anything we govern, so it must resolve to nothing —
    #    which is what makes the caller skip it, exactly as its comment says.
    assert "ir_actions.py" not in index, (
        "`ir_actions.py` is resolvable again, so `ir_actions.py::"
        "IrActionsServer` — an Odoo core reference — will be checked against "
        "a file that is not Odoo core. That is the CI failure this fixed.")
    assert _resolve_referenced_file("ir_actions.py", REPO_ROOT / "x.py") is None

    # 3. The guard has NOT been turned off: a bare name that names a governed
    #    file still resolves to it.
    real = REPO_ROOT / "myservice_api" / "models" / "test_fixture.py"
    assert index.get(real.name) == [real], (
        "expected `%s` to be uniquely resolvable among governed files; got %r"
        % (real.name, index.get(real.name)))
    assert _resolve_referenced_file(real.name, REPO_ROOT / "x.py") == real

    # 4. And it still FAILS on a reference that names something absent — the
    #    mutation proof. Without this, 1-3 are satisfied by a resolver that
    #    returns None for everything.
    defined = _defined_names(real)
    missing = "IrActionsServer"          # real class name, wrong file
    assert missing not in defined, (
        "pick another absent name: %r now exists in %s" % (missing, real.name))
    target = _resolve_referenced_file(real.name, REPO_ROOT / "x.py")
    assert target is not None and missing not in _defined_names(target), (
        "the resolver no longer reaches a governed file, so the guard that "
        "reports broken references is asserting on nothing")


# ─── a refused field is a 400, not a warning beside a 2xx (handoff 31) ──
#
# Until handoff 31 ten write routes answered a body naming a field they do
# not accept with a 2xx: they wrote the rest and named the dropped keys in
# `data._warnings.rejected_fields`. They answer 400 now, through ONE helper
# (`refuse_unwritable` in `myservice_api/controllers/utils.py`), and the old
# shape is gone. `tests/test_rejected_fields_are_refused.py` holds the ten
# over HTTP. What it cannot hold is the ELEVENTH — a route written next month
# by copying a controller from before the change. This does, with no server.
#
# `_warnings` itself is not retired: `truncated` on a capped list and
# `discarded_fields` on a replayed workflow callback are warnings about a
# request that SUCCEEDED, and stay. And `details={"rejected_fields": …}` on
# an `err(...)` is the new shape, not the old one. So the guard is an AST
# walk for the one construction, not a grep for either word.

def _warned_rejections(source):
    """Line numbers where `rejected_fields` is put under `_warnings`.

    Three spellings, because a route can build the block three ways:

        out["_warnings"] = {"rejected_fields": rejected}
        return {"id": 1, "_warnings": {"rejected_fields": rejected}}
        out["_warnings"]["rejected_fields"] = rejected
    """
    def const(node, value):
        return isinstance(node, ast.Constant) and node.value == value

    def names_rejections(node):
        return isinstance(node, ast.Dict) and any(
            const(key, "rejected_fields") for key in node.keys)

    def is_warnings_slot(node):
        return isinstance(node, ast.Subscript) and const(node.slice, "_warnings")

    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            for target in targets:
                if is_warnings_slot(target) and names_rejections(node.value):
                    found.add(node.lineno)
                if (isinstance(target, ast.Subscript)
                        and const(target.slice, "rejected_fields")
                        and is_warnings_slot(target.value)):
                    found.add(node.lineno)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if const(key, "_warnings") and names_rejections(value):
                    found.add(value.lineno)
    return sorted(found)


@pytest.mark.parametrize("label,source,expected", [
    (
        # VERBATIM what all ten routes did until handoff 31.
        "the block assigned onto the response",
        "def create_asset(self):\n"
        "    out = serialize_asset(rec)\n"
        "    if rejected:\n"
        "        out[\"_warnings\"] = {\"rejected_fields\": rejected}\n"
        "    return out\n",
        [4],
    ),
    (
        "PATCH /requests' spelling, with the hint beside it",
        "out['_warnings'] = {'rejected_fields': rejected,\n"
        "                    'hint': 'Use POST .../transition'}\n",
        [1],
    ),
    (
        "built inline in the returned dict",
        "def f(self):\n"
        "    return {'id': 1,\n"
        "            '_warnings': {'rejected_fields': rejected}}\n",
        [3],
    ),
    (
        "written into an existing block",
        "out.setdefault('_warnings', {})\n"
        "out['_warnings']['rejected_fields'] = rejected\n",
        [2],
    ),
    (
        # The NEW shape. A guard that flagged this would be asking somebody
        # to delete the fix.
        "the refusal itself",
        "return err(ERR_INVALID_REQUEST, 'no',\n"
        "           details={'rejected_fields': rejected,\n"
        "                    'writable': sorted(writable)})\n",
        [],
    ),
    (
        "the two warnings that are about a request that succeeded",
        "data['_warnings'] = {'discarded_fields': discarded}\n"
        "body['_warnings'] = {'truncated': {'returned': 100}}\n",
        [],
    ),
    (
        "the words in a comment and a docstring",
        "def f(self):\n"
        "    \"\"\"Used to set out['_warnings'] = {'rejected_fields': x}.\"\"\"\n"
        "    # out['_warnings'] = {'rejected_fields': rejected}\n"
        "    return 1\n",
        [],
    ),
])
def test_the_warned_rejection_finder_sees_each_spelling(label, source,
                                                        expected):
    """Fail-first, as every guard in this file is: shown the construction
    the ten routes used, it must find it; shown the refusal that replaced
    it, and the two `_warnings` that stay, it must not."""
    assert _warned_rejections(source) == expected, label


def test_no_controller_reports_a_refused_field_beside_a_success():
    """`data._warnings.rejected_fields` is not set anywhere, by any route.

    Rule 3: never let an integration guess. A dropped field beside a 2xx is
    a guess the integration does not know it is making — Vendra dead-letters
    the receipt AFTER Cadra has created the asset without the field, under an
    idempotency key that replays the same 201 for ever. A route that needs
    to refuse a key calls `refuse_unwritable(...)` BEFORE it writes.
    """
    controllers = sorted(
        path for path in REPO_ROOT.glob("myservice_*/controllers/*.py")
        if path.name != "__init__.py")
    assert len(controllers) >= 10, (
        "only %d controller file(s) found — the glob has stopped matching "
        "and this guard is asserting on nothing" % len(controllers))
    names = {path.relative_to(REPO_ROOT).as_posix() for path in controllers}
    for owed in ("myservice_api/controllers/v1_assets.py",
                 "myservice_api/controllers/v1_locations.py",
                 "myservice_api/controllers/v1_requests.py",
                 "myservice_api/controllers/v1_settings.py"):
        assert owed in names, "%s is not among the files scanned" % owed

    sites = [
        "%s:%d" % (path.relative_to(REPO_ROOT).as_posix(), line)
        for path in controllers
        for line in _warned_rejections(path.read_text(encoding="utf-8"))]
    assert not sites, (
        "`_warnings.rejected_fields` is set at %s. Since handoff 31 a field "
        "a route does not accept is a 400 through `refuse_unwritable`, "
        "BEFORE anything is written — not a 2xx that dropped it."
        % ", ".join(sites))

    # And the helper the ten routes call is still there to be called.
    utils = (REPO_ROOT / "myservice_api" / "controllers"
             / "utils.py").read_text(encoding="utf-8")
    assert re.search(r"^def refuse_unwritable\(", utils, re.MULTILINE), (
        "myservice_api/controllers/utils.py no longer defines "
        "`refuse_unwritable`")
    callers = [name for name in sorted(names)
               if re.search(r"\brefuse_unwritable\(",
                            (REPO_ROOT / name).read_text(encoding="utf-8"))
               and not name.endswith("/utils.py")]
    assert len(callers) >= 4, (
        "only %s call `refuse_unwritable`; the four controllers that hold "
        "the ten routes all did" % callers)

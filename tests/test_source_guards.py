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
    "docker-compose.dev.yml",
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
        if not path.exists():
            continue
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

_CATCH_ALL_MARKER = "catch-all:"
_CATCH_ALL_CLASSES = ("optional", "reported", "unknown")
_BROAD_EXCEPTIONS = {"Exception", "BaseException"}


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

    Three placements, all of which read naturally and none of which can
    drift onto a handler it was not written for:

      - on the `except` line itself;
      - in the contiguous comment block IMMEDIATELY above it;
      - in the contiguous comment block that OPENS the handler body.

    Contiguity is what makes it safe. The moment a line of code lands
    between the comment and the `except`, the marker stops applying and the
    guard speaks up — the same rule as the capped-count waiver above, for
    the same reason.
    """
    found = _marker_class(lines[handler.lineno - 1])
    if found is not None:
        return found

    index = handler.lineno - 2
    while index >= 0 and lines[index].strip().startswith("#"):
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
    for path in _first_party_python_files():
        source = path.read_text(encoding="utf-8")
        try:
            findings = _broad_handler_findings(source)
        except SyntaxError:
            continue
        for lineno, problem in findings:
            offenders.append("%s:%d — %s"
                             % (path.relative_to(REPO_ROOT), lineno, problem))

    assert not offenders, (
        "%d broad exception handler(s) do not say what they are hiding:\n  %s"
        "\n\nAdd one of `# catch-all: optional|reported|unknown — <why>` on "
        "the `except` line, in the comment block immediately above it, or in "
        "the comment block that opens the handler body. Better: narrow the "
        "exception type, or delete the handler — a narrowed one needs no "
        "marker because it is no longer a catch-all."
        % (len(offenders), "\n  ".join(offenders)))


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

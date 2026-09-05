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

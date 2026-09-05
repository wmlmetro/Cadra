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
# A `_sql_constraints` inside such a branch is fine. One in a bare class body
# is the defect.
_VERSION_GUARD_NAMES = {"_ODOO_MAJOR", "version_info", "release"}


def _first_party_python_files():
    for glob in FIRST_PARTY_GLOBS:
        for module_dir in sorted(REPO_ROOT.glob(glob)):
            if not (module_dir / "__manifest__.py").exists():
                continue
            for path in sorted(module_dir.rglob("*.py")):
                yield path


def _is_version_guarded(node, ancestors):
    """True if `node` sits inside an `if` that tests the Odoo version."""
    for parent in ancestors:
        if not isinstance(parent, ast.If):
            continue
        names = {
            n.id for n in ast.walk(parent.test) if isinstance(n, ast.Name)
        } | {
            n.attr for n in ast.walk(parent.test) if isinstance(n, ast.Attribute)
        }
        if names & _VERSION_GUARD_NAMES:
            return True
    return False


def _unguarded_sql_constraints(path):
    """Every unguarded `_sql_constraints = ...` in one file, as (line, source)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        pytest.fail(f"could not parse {path.relative_to(REPO_ROOT)}: {exc}")

    # ast gives no parent links; build them once so we can walk upwards.
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def ancestry(node):
        while node in parents:
            node = parents[node]
            yield node

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_sql_constraints":
                if not _is_version_guarded(node, ancestry(node)):
                    found.append(node.lineno)
    return found


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


def test_guard_covers_the_modules_we_think_it_does():
    """A path typo would make the guard scan nothing and pass vacuously."""
    scanned = list(_first_party_python_files())
    modules = {p.relative_to(REPO_ROOT).parts[0] for p in scanned}
    assert len(scanned) > 100, f"only {len(scanned)} files scanned — glob wrong?"
    for expected in ("myservice_api", "myservice_asset_register",
                     "myservice_staff_bus"):
        assert expected in modules, f"{expected} not covered by the guard"

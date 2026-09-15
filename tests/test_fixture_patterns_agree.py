"""The two fixture scripts must agree about what a fixture looks like.

`scripts/mark_test_fixtures.py` MARKS the fixtures that cannot be removed;
`scripts/remove_test_residue.py` REMOVES the ones that can. Both decide what
is a fixture by matching the record's name against a tuple of patterns, and
the two tuples are declared separately because each script is executed by
`odoo shell < script` — there is no import to share between them.

Two copies of a rule is how the two answers start disagreeing, and the
failure here is not symmetric. If the removal script's patterns grow wider
than the marking script's, it deletes a record the marking script never
disclosed. If they grow narrower, the marking script marks a record that is
then left in the register with a name saying it is a fixture while nothing
ever removes it.

The anchoring matters as much as the patterns. **Odoo wraps a `like` value in
`%...%`**, so `('name', 'like', 'H23 %')` compiles to `name LIKE '%H23 %%'` —
a substring match that would claim a real `PUMP-H23-4` as a fixture. Only
`=like` passes the pattern through as written. `mark_test_fixtures.py`
carried the `like` spelling from handoff 24 until handoff 26, three months
after its sibling had documented the trap as rule 2.

Static: no Odoo instance, no database.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

#: Both scripts, and the tuple names they must both declare.
PEERS = ("mark_test_fixtures.py", "remove_test_residue.py")
TUPLES = ("ASSET_PATTERNS", "LOCATION_PATTERNS")


def _declared_tuples(path):
    """Module-level `NAME = (...)` string tuples, by name."""
    tree = ast.parse(path.read_text(), str(path))
    out = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in TUPLES:
            continue
        value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        if not all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                   for e in value.elts):
            continue
        out[target.id] = tuple(e.value for e in value.elts)
    return out


@pytest.mark.parametrize("script", PEERS)
def test_the_script_still_declares_its_patterns(script):
    """Fail if the declaration this guard reads has moved or been renamed.

    Report 22's lesson, and report 25's: a guard whose subject has quietly
    gone away passes for the wrong reason. This asserts the thing being
    compared still exists before anything compares it.
    """
    path = SCRIPTS / script
    assert path.exists(), "%s is gone — this guard is asserting on nothing" % script
    declared = _declared_tuples(path)
    missing = [name for name in TUPLES if name not in declared]
    assert not missing, (
        "%s no longer declares %s as a module-level tuple of string literals. "
        "Either it moved (update this guard) or the two scripts have stopped "
        "sharing a definition of what a fixture name looks like."
        % (script, ", ".join(missing)))
    for name, patterns in declared.items():
        assert patterns, "%s.%s is empty — it would match nothing" % (script, name)


@pytest.mark.parametrize("tuple_name", TUPLES)
def test_both_scripts_agree_on_what_a_fixture_name_looks_like(tuple_name):
    marking = _declared_tuples(SCRIPTS / "mark_test_fixtures.py")[tuple_name]
    removal = _declared_tuples(SCRIPTS / "remove_test_residue.py")[tuple_name]
    assert marking == removal, (
        "scripts/mark_test_fixtures.py and scripts/remove_test_residue.py "
        "disagree about %s.\n"
        "  marking : %r\n"
        "  removal : %r\n"
        "Whichever is right, they must both say it. A removal pattern wider "
        "than the marking pattern deletes a record that was never disclosed; "
        "a narrower one leaves a record marked as a fixture that nothing "
        "will ever remove." % (tuple_name, marking, removal))


@pytest.mark.parametrize("script", PEERS)
def test_a_fixture_name_is_matched_with_anchored_like(script):
    """`=like`, never `like`, on a name domain in either script.

    Odoo's `like` is a SUBSTRING match — it wraps the value in `%...%` — so
    `('name', 'like', 'H23 %')` would claim `PUMP-H23-4`. Every name match in
    these two scripts deletes or relabels a record in somebody's register,
    and a substring match is the difference between a fixture and a pump.
    """
    path = SCRIPTS / script
    tree = ast.parse(path.read_text(), str(path))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 3:
            continue
        field, operator, _value = node.elts
        if not (isinstance(field, ast.Constant) and field.value == "name"):
            continue
        if not isinstance(operator, ast.Constant):
            continue
        if operator.value in ("like", "ilike", "not like", "not ilike"):
            offenders.append((node.lineno, operator.value))
    assert not offenders, (
        "%s matches a record NAME with an unanchored operator at %s.\n"
        "Odoo wraps a `like` value in `%%...%%`, so the pattern is a "
        "SUBSTRING match: `H23 %%` claims a real `PUMP-H23-4`. Use `=like`, "
        "which passes the pattern through as written.\n"
        "A substring match that is DELIBERATE is still written with `=like` "
        "and its own explicit `%%` wildcards, so that the intent is in the "
        "code rather than in the reader's memory of Odoo's defaults."
        % (script, ", ".join("line %d (`%s`)" % o for o in offenders)))


def test_the_anchoring_guard_catches_the_spelling_it_was_written_for(tmp_path):
    """Mutation proof, on the code handoff 24 ACTUALLY shipped.

    Report 22's failure mode was a mutation proof that asserted on a variable
    name which never existed, and report 25's was one whose "core base second"
    case put the base first. So this feeds the guard the real line — the
    disposal search from `mark_test_fixtures.py` as handoff 24 wrote it — and
    fails if the guard does not flag it.
    """
    shipped = (
        "fixtures = Asset.search([\n"
        "    ('disposal_approved_by', '!=', False),\n"
        "    '|', ('name', 'like', 'pytest-%'), ('name', 'like', 'H23%'),\n"
        "])\n"
    )
    fixed = (
        "fixtures = Asset.search([\n"
        "    ('disposal_approved_by', '!=', False),\n"
        "    '|', ('name', '=like', 'pytest-%'), ('name', '=like', 'H23 %'),\n"
        "])\n"
    )

    def offenders(source):
        tree = ast.parse(source)
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 3:
                continue
            field, operator, _ = node.elts
            if (isinstance(field, ast.Constant) and field.value == "name"
                    and isinstance(operator, ast.Constant)
                    and operator.value in ("like", "ilike",
                                           "not like", "not ilike")):
                found.append(node.lineno)
        return found

    assert offenders(shipped) == [3, 3], (
        "the guard does not flag the two unanchored matches in the code "
        "handoff 24 shipped — it would have passed over the real bug")
    assert offenders(fixed) == [], (
        "the guard flags the CORRECTED spelling, so it cannot be satisfied")

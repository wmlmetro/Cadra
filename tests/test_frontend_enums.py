"""The front end may not declare a set the model owns.

WHY THIS FILE IS THE DELIVERABLE
--------------------------------
Handoff 22 corrected five enum sets in the Cadra SPA. Correcting them was the
easy half and the worthless half: every one of those five had been correct
once, and every one had drifted without anybody noticing, because a `<select>`
populated from a stale list is indistinguishable from a `<select>` populated
from a fresh one. Fixing the five copies without removing the mechanism that
produced them would have bought a year.

So the front end now READS the sets — `GET /api/v1/meta/enums` derives them
from the live Odoo Selection at request time. `src/lib/enums.ts` keeps a SEED
of the same sets, because a form has to render something before that request
resolves and has to render something correct if it never does.

**A seed is a copy, and this file is what stops the copy rotting.** It parses
the Odoo model source and the TypeScript seed and fails when they disagree —
on values, on order, and on labels. Adding a value to the model without
touching the seed fails. Editing the seed without touching the model fails.

What the five defects actually were, so nobody relaxes this later:

  * `priority` was shifted a whole step. The form displayed "Normal" and
    wrote `"2"`, which the model calls **High**, so every request created
    without touching the dropdown was filed one level above what the user
    saw. 35 records across three tenants carry it.
  * `location_type` offered `state` and `office`, which the model has never
    had — saving either raised — and omitted `wing`, which it has, so a wing
    opened for edit rendered a blank select and could not be saved back
    unchanged.
  * `asset_level` was missing `group`; a group-level asset silently demoted.
  * `fuel_type` mapped nine model values onto three labels with a regex,
    rendering `electric` and both plug-in hybrids as **CNG**.
  * `domain` was a free-text box advertising `nrs.fcs`, a value not in the
    set and not even the right shape.

ORDER IS CHECKED, NOT JUST MEMBERSHIP
-------------------------------------
Deliberately. `priority`'s keys are the strings `"0"`–`"4"` and they read like
a scale, so a set that is right as a bag and wrong as a sequence is exactly
the failure that shipped. Comparing sets would have passed the bug this file
was written for.

RUNS WITHOUT ODOO
-----------------
The test venv cannot import `odoo` (see `tests/test_query_param_guard.py`,
same constraint), so both sides are read as SOURCE — Python via `ast`,
TypeScript via a small deliberate parser. That is a weaker oracle than the
registry and it is the honest one available here; the values it reads were
additionally verified against a live registry on `jaizbankplc` when this file
was written.
"""
import ast
import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPA = REPO_ROOT / "Frontend" / "artifacts" / "nrs-asset-register" / "src"
SEED_TS = SPA / "lib" / "enums.ts"
META_PY = REPO_ROOT / "myservice_api" / "controllers" / "v1_meta.py"
FLEET_PY = REPO_ROOT / "myservice_api" / "controllers" / "v1_fleet.py"

#: published name -> (source file, model _name, field name)
#:
#: `asset_state` is published under that name rather than `state` because
#: `state` is the most reused field name in this schema — `nrs.asset.tag.
#: label`, `nrs.asset.transfer` and `nrs.asset.import` each have one — and a
#: client keying a cache on the bare name would collide the first time a
#: second `state` were published.
MODEL_SOURCED = {
    "priority": (
        REPO_ROOT / "myservice_request_core" / "models" / "request_request.py",
        "request.request", "priority"),
    "location_type": (
        REPO_ROOT / "crnd-19" / "generic_location" / "models" / "generic_location.py",
        "generic.location", "location_type"),
    "asset_level": (
        REPO_ROOT / "myservice_asset_register" / "models" / "asset.py",
        "nrs.asset", "asset_level"),
    "condition": (
        REPO_ROOT / "myservice_asset_register" / "models" / "asset.py",
        "nrs.asset", "condition"),
    "asset_state": (
        REPO_ROOT / "myservice_asset_register" / "models" / "asset.py",
        "nrs.asset", "state"),
    # `nrs.asset.domain` is `related='category_id.domain'`, so the Selection
    # it carries is the one declared on the category. Reading the related
    # field's own declaration would find no list at all.
    "domain": (
        REPO_ROOT / "myservice_asset_register" / "models" / "asset.py",
        "nrs.asset.category", "domain"),
}

#: `fuel_type` is Odoo CORE (`fleet.vehicle`), which is not in this checkout —
#: neither `oca-19/` nor `crnd-19/` carries it and no module here extends it.
#: Its in-repo authority is the published fallback tuple in the fleet
#: controller, which is keys only: the LABELS live in Odoo's own source and
#: cannot be asserted from here. So this one is checked on values and order,
#: and its labels are checked by nothing. Said out loud because an unstated
#: gap in a guard is worth less than no guard.
FLEET_FUEL_FALLBACK = "_FUEL_TYPES"

#: Model defaults, by VALUE. The front end's blank forms must start on these.
#: `priority` is here because starting a form on the middle of a five-item
#: list instead of on `default='1'` is precisely what filed 35 requests as
#: High. A default is a value, not an index.
DEFAULTS_EXPECTED = {
    "priority": "1",
    "asset_level": "asset",
    "condition": "good",
    "asset_state": "active",
}


# ─── reading the Odoo side ───────────────────────────────────────────

def _class_for_model(tree, model_name):
    """The ClassDef whose `_name` is `model_name`."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign)
                    and any(getattr(t, "id", None) == "_name" for t in stmt.targets)
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value == model_name):
                return node
    return None


def _selection_call(cls, field_name):
    """The `fields.Selection(...)` Call assigned to `field_name` in `cls`."""
    for stmt in cls.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == field_name for t in stmt.targets):
            continue
        call = stmt.value
        if (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "Selection"):
            return call
    return None


def model_selection(path, model_name, field_name):
    """`([(value, label)], default_or_None)` read from the model's source."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = _class_for_model(tree, model_name)
    assert cls is not None, "no class declaring _name = %r in %s" % (
        model_name, path.relative_to(REPO_ROOT))
    call = _selection_call(cls, field_name)
    assert call is not None, "no fields.Selection assigned to %s.%s in %s" % (
        model_name, field_name, path.relative_to(REPO_ROOT))

    assert call.args and isinstance(call.args[0], ast.List), (
        "%s.%s is a Selection whose values this guard cannot read statically "
        "(a callable or a `related=`?). It needs a hand-written entry here "
        "rather than a silently skipped check." % (model_name, field_name))

    pairs = []
    for elt in call.args[0].elts:
        assert isinstance(elt, ast.Tuple) and len(elt.elts) == 2, (
            "%s.%s has a Selection entry that is not a 2-tuple" % (
                model_name, field_name))
        key, label = elt.elts
        assert isinstance(key, ast.Constant) and isinstance(label, ast.Constant)
        pairs.append((key.value, label.value))

    default = None
    for kw in call.keywords:
        if kw.arg == "default" and isinstance(kw.value, ast.Constant):
            default = kw.value.value
    return pairs, default


def py_tuple_of_strings(path, name):
    """A module-level `NAME = ("a", "b", ...)` read from source."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == name for t in node.targets)
                and isinstance(node.value, (ast.Tuple, ast.List))):
            return [e.value for e in node.value.elts
                    if isinstance(e, ast.Constant)]
    raise AssertionError("no module-level %s in %s" % (
        name, path.relative_to(REPO_ROOT)))


# ─── reading the TypeScript side ─────────────────────────────────────

_BLOCK_RE = r"\n  (%s):\s*\[(.*?)\n  \],"
_OPTION_RE = re.compile(
    r"""\{\s*value:\s*"([^"]*)"\s*,\s*label:\s*"([^"]*)"\s*,?\s*\}""")


def seed_sets():
    """`{name: [(value, label), ...]}` parsed out of `ENUM_SEED` in enums.ts.

    A deliberate parser rather than a general one: it reads only the shape
    this file is required to be written in, and FAILS on anything else. A
    regex that quietly matched less than it should would make this whole
    guard pass on a file it had not really read — which is the collapsed
    denominator, one layer up.
    """
    source = SEED_TS.read_text(encoding="utf-8")
    start = source.find("export const ENUM_SEED")
    assert start != -1, "no `export const ENUM_SEED` in %s" % SEED_TS.name
    body = source[start:]

    sets = {}
    for name in list(MODEL_SOURCED) + ["fuel_type"]:
        m = re.search(_BLOCK_RE % re.escape(name), body, re.S)
        assert m, (
            "`%s` is not a key of ENUM_SEED, or is not written in the "
            "`  name: [ ... \\n  ],` shape this guard reads. Both are "
            "failures: the second means the guard stopped reading the file "
            "it claims to check." % name)
        options = _OPTION_RE.findall(m.group(2))
        assert options, "ENUM_SEED.%s parsed to zero options" % name
        # Every `{`-opening object in the block must have matched, or the
        # parser skipped an entry and the comparison below is over a subset.
        assert m.group(2).count("{ value:") == len(options), (
            "ENUM_SEED.%s has %d entries but only %d parsed — the guard is "
            "reading less than the file contains" % (
                name, m.group(2).count("{ value:"), len(options)))
        sets[name] = options
    return sets


def seed_defaults():
    """`ENUM_DEFAULT` from enums.ts.

    Tolerates both `= {...};` and `= {...} satisfies T;` — the second is what
    the file uses, so that `ENUM_DEFAULT.priority` types as a string rather
    than `string | undefined` and a form cannot fall back to `""`. A select
    whose value matches no option displays the FIRST one, so an empty default
    would have shown "Low" while an untouched form recorded "Normal": the same
    defect one value along.
    """
    source = SEED_TS.read_text(encoding="utf-8")
    m = re.search(
        r"export const ENUM_DEFAULT[^=]*=\s*\{(.*?)\n\}\s*(?:satisfies[^;]*)?;",
        source, re.S)
    assert m, "no `export const ENUM_DEFAULT` in %s" % SEED_TS.name
    found = dict(re.findall(r"(\w+):\s*\"([^\"]*)\"", m.group(1)))
    assert found, "ENUM_DEFAULT parsed to zero entries — the guard is reading "\
                  "less than the file contains"
    return found


# ─── the guard ───────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(MODEL_SOURCED))
def test_seed_matches_the_model(name):
    """The front end's seed set IS the model's, in the model's order."""
    path, model_name, field_name = MODEL_SOURCED[name]
    expected, _ = model_selection(path, model_name, field_name)
    actual = seed_sets()[name]

    assert actual == expected, (
        "`ENUM_SEED.%s` in Frontend/.../src/lib/enums.ts has drifted from "
        "`%s.%s` in %s.\n"
        "  model: %r\n"
        "  seed:  %r\n"
        "This is the defect handoff 22 closed, reopening. If you added a "
        "value to the model, add it to the seed. If you changed the seed, "
        "the model is the source of truth (CLAUDE.md architecture rule 4) "
        "and the seed is what is wrong." % (
            name, model_name, field_name, path.relative_to(REPO_ROOT),
            expected, actual))


def test_seed_fuel_type_matches_the_published_fallback():
    """`fuel_type` is Odoo core; the fleet controller's tuple is its authority.

    Values and order only — the labels are Odoo's and are not in this
    checkout, so nothing here can assert them.
    """
    expected = py_tuple_of_strings(FLEET_PY, FLEET_FUEL_FALLBACK)
    actual = [v for v, _ in seed_sets()["fuel_type"]]
    assert actual == expected, (
        "`ENUM_SEED.fuel_type` has drifted from `%s` in %s.\n"
        "  controller: %r\n"
        "  seed:       %r\n"
        "The old front end collapsed these nine onto three labels and showed "
        "`electric` as CNG." % (
            FLEET_FUEL_FALLBACK, FLEET_PY.relative_to(REPO_ROOT),
            expected, actual))


@pytest.mark.parametrize("name", sorted(DEFAULTS_EXPECTED))
def test_blank_form_defaults_are_the_model_defaults(name):
    """A blank form starts on the model's `default=`, by value.

    `priority` is why this test exists: the form defaulted to `"2"` believing
    it was the middle of five. `"2"` is High.
    """
    path, model_name, field_name = MODEL_SOURCED[name]
    _, model_default = model_selection(path, model_name, field_name)
    assert model_default == DEFAULTS_EXPECTED[name], (
        "%s.%s declares default=%r; this guard expects %r. The model moved — "
        "update DEFAULTS_EXPECTED and the front end together." % (
            model_name, field_name, model_default, DEFAULTS_EXPECTED[name]))
    assert seed_defaults().get(name) == model_default, (
        "`ENUM_DEFAULT.%s` is %r but `%s.%s` defaults to %r. A blank form "
        "would record something other than what the model considers "
        "unset — which is how 35 requests were filed as High while their "
        "form displayed Normal." % (
            name, seed_defaults().get(name), model_name, field_name,
            model_default))


@pytest.mark.parametrize("name", sorted(MODEL_SOURCED))
def test_the_endpoint_publishes_the_same_fallback(name):
    """`v1_meta._PUBLISHED_ENUMS` fallbacks match the model too.

    The endpoint reads the registry, so these fire only when the registry
    read fails — which is exactly when nobody is watching. A fallback nobody
    checks is a stale list with a longer fuse.
    """
    source = META_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    published = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "_PUBLISHED_ENUMS"
                        for t in node.targets)):
            continue
        for entry in node.value.elts:
            key = entry.elts[0].value
            published[key] = [e.value for e in entry.elts[3].elts]
    assert published, "no `_PUBLISHED_ENUMS` tuple parsed out of v1_meta.py"

    path, model_name, field_name = MODEL_SOURCED[name]
    expected = [v for v, _ in model_selection(path, model_name, field_name)[0]]
    assert published.get(name) == expected, (
        "`v1_meta._PUBLISHED_ENUMS[%r]`'s fallback is %r; `%s.%s` is %r." % (
            name, published.get(name), model_name, field_name, expected))


#: Files allowed to key a map on a model-owned set, and why.
#:
#: A waiver is a claim, so each one has to be a claim somebody can disagree
#: with. The claim here is always the same: **this is a STYLING lookup, and
#: colour is not a set the back end owns.** A missing key in one of these
#: yields a documented neutral fallback — not a wrong value, not a missing
#: option, not a record retyped by being opened. That is a different failure
#: from the one this file exists to prevent, and a smaller one.
#:
#: Each waived file MUST have a fallback for an unrecognised key; the test
#: below checks for one rather than taking the waiver's word for it.
STYLING_WAIVERS = {
    "components/ConditionBadge.tsx":
        "colour and dot per condition; `?? UNKNOWN_CONDITION` covers a value "
        "the model gains before this build knows its colour",
    "pages/ITAssetsCommand.tsx":
        "the same per-condition colour chain inline, plus the ConditionBars "
        "row labels, whose counts come from the API keyed on model values",
    "pages/RequestsList.tsx":
        "PRIORITY_COLOR — severity colour, deliberately kept when the label "
        "map was deleted, with PRIORITY_COLOR_UNKNOWN as the fallback",
    "components/LifecyclePill.tsx":
        "colour and dot per lifecycle state (handoff 29). The LABEL is read "
        "from `useEnumLabel('asset_state')`, never declared; `?? "
        "UNKNOWN_STATE` covers a state the model gains before this build "
        "knows its colour. It exists because the register rendered a missing "
        "or disposed asset as a green `Cleared`: the only status pill knew "
        "about data quality and nothing about lifecycle",
}


def _strip_comments(text):
    """Source with `//` and `/* */` removed.

    Read CODE, not prose. Every one of these files explains the defect it
    used to carry, and explaining a rule means naming what it forbids — so a
    guard that matched its own explanation would be one somebody satisfies by
    deleting the explanation. `tests/test_query_param_guard.py` makes the same
    point about the same trap; this is that lesson, applied a second time
    after this very test tripped over it.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def test_no_page_declares_a_model_owned_set():
    """No `.ts`/`.tsx` re-introduces a local copy of one of these sets.

    The corrections would have been worth nothing if the next copy could be
    added by somebody following the shape of the file they were editing —
    which is exactly how all of them got there. Two of the copies this closed
    were in wire TYPES (`ApiAsset.condition`, `Asset.lifecycleState`): the
    layer furthest from anyone who would notice it going stale.

    Matches on the model's own KEYS, not on variable names, because the thing
    that must not recur is the list, whatever it gets called. It requires the
    keys to appear CLOSE TOGETHER, which is what distinguishes a declared set
    — a union, an array, an option list — from a file that legitimately names
    two of the values in two unrelated calls. `dataProvider.fetchCategoryDashboard`
    is the case that matters: it issues one `countAssets({condition: ...})` per
    value, which enumerates the set across 60 lines without declaring it.
    """
    #: Two keys per set, chosen to be ones nothing else would say.
    fingerprints = {
        "location_type": ('"wing"', '"floor"'),
        "asset_level": ('"sub_asset"', '"component"'),
        "condition": ('"decommissioned"', '"fair"'),
        "asset_state": ('"in_repair"', '"transferred"'),
        "fuel_type": ('"plug_in_hybrid_diesel"', '"full_hybrid"'),
        "domain": ('"plumbing"', '"furniture"'),
    }
    #: How near two keys must be to count as one declaration. A union or an
    #: array literal puts them within a line or two of each other; separate
    #: call sites do not.
    SPAN = 240

    offenders = []
    for path in sorted(SPA.rglob("*.ts*")):
        rel = path.relative_to(SPA).as_posix()
        if path == SEED_TS or rel.startswith("mock/"):
            # The seed is the one permitted copy and is guarded above. The
            # mock fixtures are demo rows, not a set offered to a user.
            continue
        code = _strip_comments(path.read_text(encoding="utf-8"))
        for name, (a, b) in fingerprints.items():
            ia, ib = code.find(a), code.find(b)
            if ia == -1 or ib == -1 or abs(ia - ib) > SPAN:
                continue
            if rel in STYLING_WAIVERS:
                continue
            offenders.append("%s declares the `%s` set (%s, %s)" % (rel, name, a, b))

    assert not offenders, (
        "a front-end file declares a set the model owns:\n  %s\n"
        "Read it from `useEnum(...)` (hooks/useEnums.ts) instead. The seed in "
        "lib/enums.ts is the only copy, and it is guarded. If this really is "
        "a styling lookup rather than a set offered to a user, add it to "
        "STYLING_WAIVERS with its reason and give it a fallback." % (
            "\n  ".join(offenders)))


@pytest.mark.parametrize("rel", sorted(STYLING_WAIVERS))
def test_a_waived_styling_map_has_a_fallback(rel):
    """A waiver is only sound if the map degrades instead of breaking.

    `conditionConfig[condition]` was an unguarded index: the first value the
    model gained would have thrown inside render and white-screened the asset
    register from a Python change. A styling map is waived because a missing
    key is harmless — so the harmlessness has to be real.
    """
    path = SPA / rel
    assert path.exists(), (
        "STYLING_WAIVERS names %s, which does not exist. A waiver list nobody "
        "prunes is how a waiver list stops meaning anything." % rel)
    code = _strip_comments(path.read_text(encoding="utf-8"))
    assert "??" in code, (
        "%s is waived as a styling lookup but has no `??` fallback for a key "
        "it does not recognise. Reason on file: %s" % (rel, STYLING_WAIVERS[rel]))

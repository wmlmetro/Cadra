"""The endpoint reference is held to the route census — handoff 52 §6b.

`docs/api/cadra_api_endpoint_reference.md` presents itself as the endpoint
index, and until handoff 52 nothing held it to the code: it carried none of
the five tag-replacement routes from handoff 38 until 51 noticed, and when
this guard was first run it was missing 51 of the 115 first-party `/api/v1`
routes. A reference complete except where it isn't is how an integrator
builds against half an API; after this, it cannot be complete except where
it isn't without a red test naming where.

Static, like `tests/test_sidebar_catalog.py`: the census side is an AST walk
over every `myservice_*/controllers/*.py` and `cadra_brand_*/controllers/*.py`
reading `@cadra_route(...)` and `@http.route(...)` declarations — the same
sources the in-registry census (`test_published_names_resolve.py`) reads off
the live routing attribute, re-derived here without an Odoo so the diff runs
in CI's pytest step and on any laptop. Scope: routes under `/api/v1` only.
The first-party routes outside it are `docs/api/EXTERNAL-SURFACES.md`'s, by
that file's own charter, and holding one document to its own surface is the
point — a guard that swept both would make every outside route a documented
API route, which handoff 17 spent a cycle proving they are not.

Paths are compared with every `<...>` placeholder collapsed to `<>`, because
the code spells converters (`<int:id>`) and the reference spells names
(`<id>`, `<reference>`), and the name of a placeholder is not the identity
of a route.
"""

import ast
import glob
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "docs" / "api" / "cadra_api_endpoint_reference.md"
CONTROLLER_GLOBS = ("myservice_*", "cadra_brand_*")

_PLACEHOLDER = re.compile(r"<[^>]+>")

# Routes the reference legitimately omits, one sentence each. EMPTY is the
# healthy state; an entry here is a debt with its reason attached, not a
# convenience. (At the time of writing the index carries every route, so
# nothing is excluded.)
EXCLUSIONS = {
    # ("METHOD", "/api/v1/<>-normalised path"): "why the reference omits it",
}


def _norm(path):
    return _PLACEHOLDER.sub("<>", path.strip())


def _census():
    """Every (METHOD, normalised path) under /api/v1, from the source.

    `cadra_route` declares one `method` (default GET); `http.route` declares
    `methods` (a list) or nothing, which Odoo serves as any method — those
    are returned separately so a documented method can satisfy them.
    """
    exact = {}
    any_method = {}
    files = []
    for pattern in CONTROLLER_GLOBS:
        files += sorted(glob.glob(str(REPO_ROOT / pattern / "controllers" / "*.py")))
    assert files, "no controller files found — the census glob is broken"
    for fp in files:
        rel = str(pathlib.Path(fp).relative_to(REPO_ROOT))
        tree = ast.parse(pathlib.Path(fp).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                elif isinstance(dec.func, ast.Attribute):
                    dec_name = dec.func.attr
                else:
                    continue
                if dec_name not in ("cadra_route", "route"):
                    continue
                paths = []
                if dec.args:
                    arg = dec.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        paths = [arg.value]
                    elif isinstance(arg, (ast.List, ast.Tuple)):
                        paths = [e.value for e in arg.elts
                                 if isinstance(e, ast.Constant)]
                methods = None
                for kw in dec.keywords:
                    if kw.arg == "method" and isinstance(kw.value, ast.Constant):
                        methods = [kw.value.value]
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        methods = [e.value for e in kw.value.elts
                                   if isinstance(e, ast.Constant)]
                if dec_name == "cadra_route" and methods is None:
                    methods = ["GET"]
                where = "%s:%s" % (rel, node.name)
                for p in paths:
                    if not p.startswith("/api/v1"):
                        continue
                    if methods is None:
                        any_method[_norm(p)] = where
                    else:
                        for m in methods:
                            exact[(m.upper(), _norm(p))] = where
    return exact, any_method


# A row of the index table: "| 26 | POST   | `/api/v1/assets/<id>/tag-affixed` | ... |"
_ROW = re.compile(
    r"^\|\s*[0-9a-z]+\s*\|\s*(GET|POST|PATCH|PUT|DELETE)\s*\|\s*`([^`]+)`\s*\|")


def _reference_rows():
    rows = {}
    for n, line in enumerate(REFERENCE.read_text().splitlines(), 1):
        m = _ROW.match(line)
        if m:
            rows[(m.group(1), _norm(m.group(2).split("?")[0]))] = n
    return rows


def test_every_census_route_has_a_row():
    exact, any_method = _census()
    rows = _reference_rows()
    total = len(exact) + len(any_method)
    assert total >= 100, (
        "the census parsed only %d /api/v1 routes — the parser is broken, "
        "not the API small" % total)
    documented_paths = {p for (_m, p) in rows}
    missing = sorted(
        "%s %s  (%s)" % (m, p, where)
        for (m, p), where in exact.items()
        if (m, p) not in rows and (m, p) not in EXCLUSIONS)
    missing += sorted(
        "ANY %s  (%s)" % (p, where)
        for p, where in any_method.items()
        if p not in documented_paths and ("ANY", p) not in EXCLUSIONS)
    assert not missing, (
        "%d of %d first-party /api/v1 routes have no row in the endpoint "
        "index of %s. Either add the row or add an exclusion WITH ITS "
        "SENTENCE:\n  %s"
        % (len(missing), total, REFERENCE.name, "\n  ".join(missing)))


def test_every_row_names_a_census_route():
    exact, any_method = _census()
    rows = _reference_rows()
    assert len(rows) >= 100, (
        "the index parsed only %d rows — the row regex is broken, not the "
        "table short" % len(rows))
    ghosts = sorted(
        "%s %s  (line %d)" % (m, p, line)
        for (m, p), line in rows.items()
        if (m, p) not in exact and p not in any_method)
    assert not ghosts, (
        "%d of %d endpoint-index rows name a route no first-party "
        "controller declares — the reference is describing an API that "
        "does not exist:\n  %s"
        % (len(ghosts), len(rows), "\n  ".join(ghosts)))


def test_every_exclusion_still_excludes_something():
    """An exclusion whose route gained a row (or died) is stale — delete it."""
    exact, any_method = _census()
    rows = _reference_rows()
    stale = []
    for (m, p), why in EXCLUSIONS.items():
        exists = ((m, p) in exact) or (m == "ANY" and p in any_method)
        documented = (m, p) in rows or (
            m == "ANY" and any(rp == p for (_rm, rp) in rows))
        if not exists or documented:
            stale.append("%s %s — %s" % (m, p, why))
    assert not stale, (
        "stale exclusions (route gone, or now documented):\n  %s"
        % "\n  ".join(stale))


# ─── handoff 58, D6: the `waiting_on` values the reference publishes ────

def _served_waiting_on():
    """`WAITING_ON_VALUES` read off the model's source — the tuple the
    route's `?waiting_on=` filter and its OpenAPI enum are built from."""
    src = (REPO_ROOT / "myservice_asset_register" / "models"
           / "asset_gates.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "WAITING_ON_VALUES"
                for t in node.targets):
            return [e.value for e in node.value.elts]
    raise AssertionError("WAITING_ON_VALUES not found in asset_gates.py")


def test_the_reference_lists_every_waiting_on_value_it_serves():
    """Report 57 D6: `iad_approver` was served and not published. §14.2's
    list must name exactly the values `GET /candidates?waiting_on=` accepts —
    no more, no fewer."""
    text = REFERENCE.read_text(encoding="utf-8")
    start = text.index("`waiting_on`: `store`")
    block = text[start:text.index("\n\n", start)]
    # `null` is the absence of a value (registered, rejected), not a filter.
    documented = [v for v in re.findall(r"`([a-z_]+)`\s+\(", block)
                  if v != "null"]
    assert sorted(documented) == sorted(_served_waiting_on()), (
        "the endpoint reference's `waiting_on` list (§14.2) and the served "
        "values disagree: documented %s, served %s"
        % (documented, _served_waiting_on()))

"""The SPA's two scope maps cannot drift from the server's — handoff 52 §6a.

`myservice_api/controllers/utils.py` owns the scope names: the `SCOPE_*`
constants, gathered into `ALL_SCOPES`. The SPA restates them twice — the
`SCOPE` map in `hooks/use-scopes.ts`, which is what every page and sidebar
gate reads, and `SCOPE_WORDS` in `pages/admin/Users.tsx`, which is how a
scope is explained to the administrator granting it. A scope renamed
server-side used to fail in the one place that decides what a person sees,
and fail silently (report 50 §J.10): `use-scopes.ts` was carrying 17 of the
server's 19 when this guard was written.

Static, the `tests/test_sidebar_catalog.py` pattern: regex the three files,
assert set equality in both directions, print the denominator. Every parse
asserts it found a plausible count first, so a reformat that silently
matches nothing fails as itself rather than as a vacuous pass.
"""

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
UTILS = REPO_ROOT / "myservice_api" / "controllers" / "utils.py"
SPA = REPO_ROOT / "Frontend" / "artifacts" / "nrs-asset-register" / "src"
USE_SCOPES = SPA / "hooks" / "use-scopes.ts"
USERS_PAGE = SPA / "pages" / "admin" / "Users.tsx"


def _server_scopes():
    """The SCOPE_* constants, and ALL_SCOPES checked against them."""
    text = UTILS.read_text()
    constants = dict(re.findall(
        r'^(SCOPE_[A-Z_]+)\s*=\s*"([^"]+)"', text, re.M))
    assert len(constants) >= 15, (
        "parsed only %d SCOPE_* constants out of utils.py — the regex is "
        "broken, not the scope list short" % len(constants))
    # ALL_SCOPES must gather every constant: a scope declared but left out
    # of the census is exactly the drift this file exists to refuse.
    tree = ast.parse(text)
    gathered = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "ALL_SCOPES":
            call = node.value
            assert isinstance(call, ast.Call), "ALL_SCOPES is not a frozenset(...) call"
            names = {e.id for e in ast.walk(call) if isinstance(e, ast.Name)
                     and e.id.startswith("SCOPE_")}
            gathered = {constants[n] for n in names if n in constants}
    assert gathered is not None, "ALL_SCOPES not found in utils.py"
    assert gathered == set(constants.values()), (
        "ALL_SCOPES and the SCOPE_* constants disagree:\n"
        "  constants only: %s\n  ALL_SCOPES only: %s"
        % (sorted(set(constants.values()) - gathered),
           sorted(gathered - set(constants.values()))))
    return set(constants.values())


def _block(path, start_re, end_marker):
    """The lines of one `export const X = {...}` block, exclusive."""
    lines = path.read_text().splitlines()
    out, inside = [], False
    for line in lines:
        if not inside and re.search(start_re, line):
            inside = True
            continue
        if inside:
            if line.strip().startswith(end_marker):
                return out
            out.append(line)
    raise AssertionError("could not find the block %s in %s" % (start_re, path.name))


def _spa_scope_map():
    """The values of `export const SCOPE = {...}` in use-scopes.ts."""
    values = []
    for line in _block(USE_SCOPES, r"^export const SCOPE = \{", "} as const"):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        m = re.match(r'^\s*\w+:\s*"([^"]+)",?\s*$', line)
        if m:
            values.append(m.group(1))
    assert len(values) >= 15, (
        "parsed only %d entries out of the SCOPE map — the regex is broken, "
        "not the map short" % len(values))
    assert len(values) == len(set(values)), "duplicate values in the SCOPE map"
    return set(values)


def _scope_words():
    """The keys of `export const SCOPE_WORDS = {...}` in Users.tsx."""
    keys = []
    for line in _block(USERS_PAGE, r"^export const SCOPE_WORDS", "};"):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        m = re.match(r'^\s*"([^"]+)":\s*$|^\s*"([^"]+)":\s*"', line)
        if m:
            keys.append(m.group(1) or m.group(2))
    assert len(keys) >= 15, (
        "parsed only %d keys out of SCOPE_WORDS — the regex is broken, not "
        "the map short" % len(keys))
    assert len(keys) == len(set(keys)), "duplicate keys in SCOPE_WORDS"
    return set(keys)


def test_the_scope_map_is_the_servers_list():
    server, spa = _server_scopes(), _spa_scope_map()
    assert spa == server, (
        "use-scopes.ts SCOPE and the server's %d scopes disagree "
        "(SPA carries %d):\n  server only: %s\n  SPA only: %s"
        % (len(server), len(spa),
           sorted(server - spa), sorted(spa - server)))


def test_scope_words_is_the_servers_list():
    server, words = _server_scopes(), _scope_words()
    assert words == server, (
        "SCOPE_WORDS and the server's %d scopes disagree (the page "
        "carries %d):\n  server only: %s\n  page only: %s"
        % (len(server), len(words),
           sorted(server - words), sorted(words - server)))

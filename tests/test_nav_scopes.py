"""Every sidebar item declares the scope the server requires for it.

Handoff 46. Until then only the two Administration items carried a `scope`
and the filter read *no scope means everybody*, so a Tag-Issuing Unit was
drawn Fleet, Staff Bus and every report, and every one refused it. The table
now lives in `lib/navigation.ts`, `scope` is REQUIRED on every item, and the
landing page is computed from the same table.

What a type checker cannot hold, this does:

* every item carries a scope, and every scope it names is one the server
  knows (`utils.ALL_SCOPES`) — a typo hides an item from everybody, and an
  invented scope is a finding about the role model dressed up as a fix;
* every path the landing rule tries is an item in the table, so the rule
  and the sidebar cannot drift apart;
* every item's path is a route `App.tsx` serves.

Whether the scopes are RIGHT — drawn ⇔ answered, hidden ⇔ refused — is
proved by signing in as each persona: `e2e/tests/46-everyone-sees-their-own-job.spec.ts`.

Static: no Odoo instance, no database.
"""
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPA = REPO_ROOT / "Frontend" / "artifacts" / "nrs-asset-register" / "src"
NAV = SPA / "lib" / "navigation.ts"
APP = SPA / "App.tsx"
UTILS = REPO_ROOT / "myservice_api" / "controllers" / "utils.py"

_ITEM = re.compile(r"^\s*\{\s*name:\s*\"(?P<name>[^\"]+)\",\s*path:\s*\"(?P<path>[^\"]+)\"(?P<rest>.*)\},?\s*$")


def _server_scopes():
    return set(re.findall(r'^SCOPE_[A-Z_]+\s*=\s*"([^"]+)"', UTILS.read_text(), re.M))


def _items():
    """Live (uncommented) items of ALL_NAV_GROUPS."""
    items = []
    for line in NAV.read_text().splitlines():
        if line.lstrip().startswith("//"):
            continue
        m = _ITEM.match(line)
        if m:
            items.append(m.groupdict())
    return items


def _scopes_of(rest):
    m = re.search(r"scope:\s*(\[[^\]]*\]|\"[^\"]*\")", rest)
    return None if not m else re.findall(r"\"([^\"]+)\"", m.group(1))


def test_the_table_is_where_the_test_reads_it():
    """Every live `path:` in the file is an item the parse saw.

    Counted independently of the item regex, so an item reformatted onto
    several lines fails here instead of silently dropping out of every
    assertion below (verification pass, N5)."""
    live_paths = [l for l in NAV.read_text().splitlines()
                  if re.search(r'\bpath:\s*"', l) and not l.lstrip().startswith("//")]
    assert live_paths and len(_items()) == len(live_paths), (
        "parsed %d nav items but the file has %d live `path:` lines — the "
        "parse no longer matches the file" % (len(_items()), len(live_paths)))


def test_every_item_declares_a_scope_the_server_knows():
    known = _server_scopes()
    assert "assets:read" in known and "admin" in known, "scope parse failed"
    bad = []
    for item in _items():
        scopes = _scopes_of(item["rest"])
        if not scopes:
            bad.append("%s (%s): no scope" % (item["name"], item["path"]))
        else:
            unknown = set(scopes) - known
            if unknown:
                bad.append("%s (%s): %s" % (item["name"], item["path"], sorted(unknown)))
    assert not bad, (
        "nav items with no scope, or a scope the server does not know — an "
        "item with none is drawn for everybody, and a scope that does not "
        "exist is a role-model question to raise, not a string to add:\n  "
        + "\n  ".join(bad))


def test_the_landing_rule_only_tries_pages_in_the_table():
    order = re.search(r"LANDING_ORDER\s*=\s*\[([^\]]*)\]", NAV.read_text())
    assert order, "LANDING_ORDER not found in lib/navigation.ts"
    paths = {i["path"] for i in _items()}
    tried = re.findall(r"\"([^\"]+)\"", order.group(1))
    assert tried, "LANDING_ORDER is empty — everybody would land on /no-access"
    missing = [p for p in tried if p not in paths]
    assert not missing, (
        "the landing rule tries %s, which the nav table does not carry — the "
        "rule would judge a page by scopes nobody declared" % missing)


def test_every_item_is_a_route_the_app_serves():
    app = APP.read_text()
    served = set(re.findall(r"<Route\s+path=\"([^\"]+)\"", app))
    missing = [i["path"] for i in _items() if i["path"] not in served]
    assert not missing, "nav items with no route in App.tsx: %s" % missing

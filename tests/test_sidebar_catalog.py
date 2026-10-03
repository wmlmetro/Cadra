"""The sidebar's switch keys: one table in the app, one on the server, agreed.

Handoff 48. A tenant switches an item off by its KEY
(`cadra.sidebar.item.<key>`), and the key has to outlive every other fact
about the item — the label is reworded, the path re-routed, the scope
re-ruled (handoff 47 is about to change several). So:

* every item and group in `lib/navigation.ts` carries a `key`, and the
  app's keys, their grouping and their order are exactly the server's
  `SIDEBAR_GROUPS` (`myservice_api/controllers/v1_sidebar.py`) — a key the
  server does not know is refused by the PATCH, and one the app does not
  carry is a switch with nothing to switch;
* **no key that was ever published disappears.** `PUBLISHED` below is every
  key as of the day this shipped; one that leaves the table must be moved to
  `SIDEBAR_RETIRED`, and a retired key is never reused — a tenant's row for
  the old item would otherwise switch the new one off;
* the locked key is the item whose page IS the Sidebar screen — so the
  lockout guards the screen it claims to, wherever it is moved;
* **presentation, not permission, held statically**: nothing on the server
  but `v1_sidebar.py` reads a `cadra.sidebar.` row, and the app's route table
  does not consult the tenant's switches. If either ever does, the two axes
  have blended.

Static: no Odoo instance, no database.
"""
import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPA = REPO_ROOT / "Frontend" / "artifacts" / "nrs-asset-register" / "src"
NAV = SPA / "lib" / "navigation.ts"
APP = SPA / "App.tsx"
SERVER = REPO_ROOT / "myservice_api" / "controllers" / "v1_sidebar.py"

#: Every key ever published, groups then items — 2026-10-03 (handoff 48)
#: onwards. A new item's key is ADDED here in the same commit (the test fails
#: until it is). Never edit or remove a line to make the test pass: a key
#: that leaves the table goes to SIDEBAR_RETIRED, and stays listed here.
PUBLISHED_GROUPS = {
    "dashboards", "asset_register", "operations", "hr_staff",
    "fleet_transport", "reports", "settings", "audit", "administration",
    "tools",
}
PUBLISHED_ITEMS = {
    "facility_command_center", "fleet_command", "it_assets_command",
    "asset_dashboard", "all_assets", "approvals", "new_asset",
    "locations", "new_location",
    "employees", "sap_sync", "bulk_import", "identity_clearance",
    "fleet", "staff_bus",
    "fleet_roster", "asset_inventory", "maintenance_readiness",
    "location_coverage", "tag_adoption", "depreciation_report",
    "asset_categories", "branding", "depreciation_settings",
    "sidebar_settings",
    "access_changes", "users", "barcode_station",
    # The auditor's own screens (handoff 49).
    "configuration_changes", "disposals_report", "register_snapshot",
    "register_export",
}

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def _server():
    """SIDEBAR_GROUPS, SIDEBAR_RETIRED and LOCKED_ITEMS, read as literals."""
    tree = ast.parse(SERVER.read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == "SIDEBAR_GROUPS":
                out[name] = ast.literal_eval(node.value)
            elif name in ("SIDEBAR_RETIRED", "LOCKED_ITEMS"):
                call = node.value
                assert isinstance(call, ast.Call) and call.func.id == "frozenset"
                out[name] = (frozenset(ast.literal_eval(call.args[0]))
                             if call.args else frozenset())
    assert set(out) == {"SIDEBAR_GROUPS", "SIDEBAR_RETIRED", "LOCKED_ITEMS"}, (
        "could not read the catalog out of v1_sidebar.py: %s" % sorted(out))
    return out


def _app():
    """[(group key, [(item key, path)])] from the live lines of navigation.ts."""
    groups = []
    for line in NAV.read_text().splitlines():
        if line.lstrip().startswith("//"):
            continue
        g = re.match(r'^\s*\{\s*key:\s*"([^"]+)",\s*label:\s*"[^"]+",\s*items:', line)
        if g:
            groups.append((g.group(1), []))
            continue
        if re.search(r'\bpath:\s*"', line):
            m = re.match(r'^\s*\{\s*key:\s*"([^"]+)",\s*name:\s*"[^"]+",\s*path:\s*"([^"]+)"', line)
            assert m, "a live nav item with no leading `key:` — %s" % line.strip()
            assert groups, "a nav item before any group: %s" % line.strip()
            groups[-1][1].append((m.group(1), m.group(2)))
    assert groups, "no groups parsed from lib/navigation.ts"
    return groups


def test_every_key_is_well_formed_and_unique():
    app = _app()
    gkeys = [g for g, _ in app]
    ikeys = [k for _, items in app for k, _ in items]
    for k in gkeys + ikeys:
        assert _KEY.match(k), "%r is not a lower_snake_case key" % k
    assert len(set(gkeys)) == len(gkeys), "a group key is used twice"
    assert len(set(ikeys)) == len(ikeys), "an item key is used twice"


def test_the_app_and_the_server_carry_the_same_table():
    server = [(g, list(items)) for g, items in _server()["SIDEBAR_GROUPS"]]
    app = [(g, [k for k, _ in items]) for g, items in _app()]
    assert app == server, (
        "lib/navigation.ts and SIDEBAR_GROUPS disagree — keys, grouping or "
        "order.\n  app:    %s\n  server: %s" % (app, server))


def test_no_published_key_disappears_and_none_is_reused():
    s = _server()
    live_groups = {g for g, _ in s["SIDEBAR_GROUPS"]}
    live_items = {k for _, items in s["SIDEBAR_GROUPS"] for k in items}
    retired = s["SIDEBAR_RETIRED"]
    gone = (PUBLISHED_GROUPS - live_groups) | (PUBLISHED_ITEMS - live_items)
    assert not gone - retired, (
        "published keys left the table without being retired: %s. A tenant "
        "may hold a row for each; retire the key (SIDEBAR_RETIRED) so it is "
        "never reused, and give the item a new one."
        % sorted(gone - retired))
    reused = retired & (live_groups | live_items)
    assert not reused, "retired keys are back in the table: %s" % sorted(reused)
    # A key added later is protected only once it is listed, so a live key
    # that is not listed fails here: adding an item means adding its key
    # to PUBLISHED_* in the same commit (verification pass, R4).
    unlisted = (live_groups - PUBLISHED_GROUPS) | (live_items - PUBLISHED_ITEMS)
    assert not unlisted, (
        "keys in the table that PUBLISHED_GROUPS / PUBLISHED_ITEMS do not "
        "list: %s — add them, so the day one is renamed this test notices"
        % sorted(unlisted))


def test_the_locked_key_is_the_screen_the_switches_live_on():
    s = _server()
    paths = {k: p for _, items in _app() for k, p in items}
    assert s["LOCKED_ITEMS"], "nothing is locked — the Sidebar screen can be switched off"
    for k in s["LOCKED_ITEMS"]:
        assert paths.get(k) == "/settings/sidebar", (
            "LOCKED_ITEMS names %r, whose path is %r — the lockout guards a "
            "screen that is not where the switches are changed"
            % (k, paths.get(k)))
    app = APP.read_text()
    assert re.search(r'<Route\s+path="/settings/sidebar"\s+component=\{SidebarSettings\}', app), (
        "/settings/sidebar is not routed to the Sidebar settings page")


def test_nothing_on_the_server_reads_the_switches_but_their_own_route():
    """Presentation, not permission: no other module may consult a switch."""
    readers = []
    for path in REPO_ROOT.glob("myservice*/**/*.py"):
        if path == SERVER or "/tests/" in str(path):
            continue
        text = path.read_text(errors="replace")
        # The one line that loads the route is not a reader.
        text = re.sub(r"^from \. import v1_sidebar$", "", text, flags=re.M)
        if "cadra.sidebar." in text or "v1_sidebar" in text:
            readers.append(str(path.relative_to(REPO_ROOT)))
    assert not readers, (
        "the sidebar's switches are read outside their own route: %s. They "
        "are presentation; a route that refused on one would turn a menu "
        "setting into a permission nobody granted." % readers)


def test_the_app_never_routes_on_the_tenants_switches():
    app = APP.read_text()
    for name in ("useTenantHidden", "tenantShows", "hidden_items", "fetchSidebarSettings"):
        assert name not in app, (
            "App.tsx consults the tenant's sidebar switches (%s) — a hidden "
            "item's address must still render its page" % name)

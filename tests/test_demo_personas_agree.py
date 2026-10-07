"""The three demo-persona scripts must agree about what a persona is.

Handoff 46. `seed_demo_personas.py` CREATES the personas,
`list_demo_personas.py` says which accounts are personas, and
`remove_demo_personas.py` deletes them. Each is run by `odoo shell < script`,
so there is no import to share, and each declares the marks it relies on.
Two copies of a rule is how the answers start disagreeing — the same reason
`test_fixture_patterns_agree.py` exists — and here the cost is not symmetric:
a remover with a wider idea of "ours" than the seed deletes a real account,
and a narrower one leaves invented officers on a client's register after
go-live while reporting a clean removal.

Also held here, because each is a property the safety of the personas rests
on and none is visible from a test run:

* the email domain is under `.example` (RFC 2606 — can never be delegated,
  so can never be a person's address);
* the external-id namespace is not a valid module name, so no module
  upgrade can adopt or delete those rows;
* every login the seed would create is on that domain;
* the persona roles are the ones the API grants (`API_GRANTABLE_XMLIDS`)
  plus `base.group_system` for the administrator, and nothing else;
* the sentinel lines the seed prints are the ones the wrapper strips — a
  mismatch would put passwords on the terminal;
* the passwords file is gitignored.

Static: no Odoo instance, no database.
"""
import ast
import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
SEED = SCRIPTS / "seed_demo_personas.py"
LIST = SCRIPTS / "list_demo_personas.py"
REMOVE = SCRIPTS / "remove_demo_personas.py"
WRAPPER = SCRIPTS / "demo_personas.sh"

SHARED = ("XMLID_MODULE", "EMAIL_DOMAIN", "SEEDER_CLIENT_ID")

#: The roles `POST /users` may grant (`access_guard.API_GRANTABLE_XMLIDS`)
#: and the administrator's system group. A persona holding anything else is a
#: role the system does not have.
ALLOWED_GROUPS = {
    "myservice_asset_register.group_asset_user",
    # Handoff 47's fifth grantable role; the Store Officer holds it since 57.
    "myservice_asset_register.group_asset_officer",
    "myservice_asset_register.group_asset_manager",
    # Handoff 57's five gate roles, all API-grantable.
    "myservice_asset_register.group_iad_vfm_officer",
    "myservice_asset_register.group_iad_vfm_approver",
    "myservice_asset_register.group_asset_controller",
    "myservice_asset_register.group_register_maker",
    "myservice_asset_register.group_register_checker",
    "myservice_asset_register.group_tag_issuing_unit",
    "myservice_api.group_auditor",
    "base.group_system",
}


def _constants(path):
    """Module-level `NAME = <literal>` assignments, evaluated."""
    found = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                # A non-literal (PERSONAS refers to names) — resolved below.
                continue
    return found


def _personas():
    """PERSONAS with the group-name constants substituted."""
    tree = ast.parse(SEED.read_text())
    consts = _constants(SEED)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PERSONAS":
            src = ast.unparse(node.value)
            return eval(src, {}, dict(consts))  # noqa: S307 — our own literal
    raise AssertionError("seed_demo_personas.py declares no PERSONAS")


@pytest.mark.parametrize("name", SHARED)
def test_the_three_scripts_declare_the_same_marks(name):
    values = {p.name: _constants(p).get(name) for p in (SEED, LIST, REMOVE)}
    assert None not in values.values(), (
        "%s is missing from: %s" % (name, [k for k, v in values.items() if v is None]))
    assert len(set(values.values())) == 1, (
        "the persona scripts disagree about %s: %s — the remover's idea of "
        "'ours' must be exactly the seed's" % (name, values))


def test_the_domain_can_never_be_a_persons():
    domain = _constants(SEED)["EMAIL_DOMAIN"]
    assert domain == "example" or domain.endswith(".example"), (
        "%r is not under the RFC 2606 `.example` TLD — a real organisation "
        "could own it, and a persona's login could be somebody's address" % domain)


def test_the_namespace_is_no_modules():
    module = _constants(SEED)["XMLID_MODULE"]
    assert module.startswith("__") and module.endswith("__"), (
        "%r could be a module name — a module of that name, upgraded, would "
        "delete or adopt the personas' external ids" % module)


def test_every_persona_login_is_on_the_domain_and_every_role_exists():
    consts = _constants(SEED)
    personas = _personas()
    keys = [p[0] for p in personas]
    assert len(keys) == len(set(keys)), "two personas share a key: %s" % keys
    names = [p[1] for p in personas]
    assert len(names) == len(set(names)), "two personas share a name"
    for key, name, title, groups in personas:
        login = "%s@%s" % (".".join(name.lower().split()), consts["EMAIL_DOMAIN"])
        assert login.endswith("@" + consts["EMAIL_DOMAIN"])
        assert title, "%s has no job title" % key
        unknown = set(groups) - ALLOWED_GROUPS
        assert not unknown, "%s holds %s, which is not a role this system has" % (key, unknown)


def test_the_wrapper_strips_exactly_the_seeds_sentinels():
    consts = _constants(SEED)
    wrapper = WRAPPER.read_text()
    for name in ("SENTINEL_BEGIN", "SENTINEL_END"):
        value = consts[name]
        # As whole lines, the way both the sed range and the Python reader
        # match them — a substring count passed `CADRA_PERSONAS_BEGIN_X`.
        exact = len(re.findall(r"\^%s\$" % re.escape(value), wrapper)) + \
            len(re.findall(r'== "%s"' % re.escape(value), wrapper))
        assert exact >= 2, (
            "demo_personas.sh does not strip %s=%r in both places — the "
            "passwords would reach the terminal" % (name, value))


def test_the_passwords_file_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "docs/api/.personas.anytenant"],
        cwd=REPO_ROOT, check=False)
    assert result.returncode == 0, (
        "docs/api/.personas.* is not gitignored — the next `git add -A` "
        "commits every persona's password")


def test_the_seed_refuses_an_unclassified_or_production_database():
    """Absent refuses, as everywhere; production refuses because at go-live
    these come OFF. Read from the guard's own tuple, not from a comment."""
    src = SEED.read_text()
    guard = re.search(r"if db_class not in \(([^)]*)\):", src)
    assert guard, "seed_demo_personas.py has no class guard"
    assert set(x.strip() for x in guard.group(1).split(",")) == {"TEST", "CLIENT"}


def test_the_remover_accepts_production_and_refuses_absent():
    """Removal is exactly what a live tenant needs at go-live."""
    src = REMOVE.read_text()
    guard = re.search(r"if db_class not in \(([^)]*)\):", src)
    assert guard, "remove_demo_personas.py has no class guard"
    assert set(x.strip() for x in guard.group(1).split(",")) == {
        "TEST", "CLIENT", "PRODUCTION"}


CI = SCRIPTS / "demo_personas_ci.sh"
RECIPIENT = SCRIPTS / "demo_personas_recipient.pem"


def test_the_cluster_path_strips_exactly_the_seeds_sentinels():
    """`.github/workflows/demo-personas.yml` prints the seed's output through
    `demo_personas_ci.sh`; if its markers drift from the seed's, every
    password on a live tenant is printed into a GitHub log."""
    consts = _constants(SEED)
    ci = CI.read_text()
    for name in ("SENTINEL_BEGIN", "SENTINEL_END"):
        value = consts[name]
        assert len(re.findall(r"\^%s\$" % re.escape(value), ci)) >= 2, (
            "demo_personas_ci.sh does not match %s=%r as a whole line in both "
            "the extract and the strip" % (name, value))


def test_the_committed_key_is_public_and_no_private_key_is_tracked():
    """The cluster's passwords are encrypted to this key; its private half
    lives only on the owner's machine (docs/api/.personas.key.pem)."""
    text = RECIPIENT.read_text()
    assert "BEGIN PUBLIC KEY" in text and "PRIVATE" not in text, (
        "scripts/demo_personas_recipient.pem is not a bare public key")
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    leaked = [p for p in tracked if p.endswith((".pem", ".key"))
              and "PRIVATE KEY" in (REPO_ROOT / p).read_text(errors="ignore")]
    assert not leaked, "a private key is tracked: %s" % leaked
    result = subprocess.run(["git", "check-ignore", "-q", "docs/api/.personas.key.pem"],
                            cwd=REPO_ROOT, check=False)
    assert result.returncode == 0, "the private key's path is not gitignored"

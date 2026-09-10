"""The prod start-up script, executed — not read.

`config/prod-entrypoint.sh` runs at container start on a CLIENT's server. A
bug in it is a deployment that does not come up, and two bugs got past careful
reading in this file's short history:

  1. The first draft lived inline in `docker-compose.prod.yml` and used
     `check … && flag=1` under `set -e`. That kills the script when the check
     PASSES, so a correct configuration refused to start and an incorrect one
     printed nothing at all. It was found by rendering the block through
     `docker compose config` and running it, not by reading it.
  2. The block copied the config template and appended `admin_passwd` — and
     not `db_user`/`db_password`. A compose `command:` replaces CMD and not
     ENTRYPOINT, so the Odoo image's entrypoint falls through its `*) exec
     "$@"` branch and its HOST/USER/PASSWORD injection never runs. The prod
     profile had never been able to reach its own database, and nothing
     caught it because CI runs `docker compose config`, which parses YAML and
     starts nothing.

Both are the same lesson: **the shell was not executable by anything.** So it
is a file now, and this runs it — with a stubbed `odoo` on PATH, so the script
needs no test hook of its own and the thing under test is the shipped file
byte for byte.
"""
import os
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "config" / "prod-entrypoint.sh"

#: A password no rule should object to. Deliberately awkward: a space, a
#: quote, a `$` and a backslash, because those are what break a shell that
#: quotes carelessly, and a generated password can contain any of them.
STRONG = 'Xf9$k "a\\b/2+Qz'


def _run(tmp_path, **env):
    """Run the real script with a stub `odoo` and a stub config template."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "odoo"
    # Records its argv and the config it was handed, so the test can assert
    # on what the server would actually have been started with.
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "$CADRA_TEST_ARGV"\n'
        'cp "$2" "$CADRA_TEST_CONF_OUT"\n'
        "echo REACHED_SERVER_START\n")
    stub.chmod(0o755)

    template = tmp_path / "odoo.conf.template"
    if not template.exists():
        template.write_text("[options]\ndb_host = db\ndb_port = 5432\n")

    argv_out = tmp_path / "argv.txt"
    conf_out = tmp_path / "conf.out"

    full = dict(os.environ)
    full.pop("USER", None)          # the host's own USER is not the container's
    full.update({
        "PATH": "%s:%s" % (bindir, os.environ.get("PATH", "")),
        "CADRA_CONF_TEMPLATE": str(template),
        "CADRA_CONF": str(tmp_path / "odoo.conf"),
        "CADRA_TEST_ARGV": str(argv_out),
        "CADRA_TEST_CONF_OUT": str(conf_out),
    })
    for k, v in env.items():
        if v is None:
            full.pop(k, None)
        else:
            full[k] = v

    proc = subprocess.run(["bash", str(SCRIPT)], env=full,
                          capture_output=True, text=True, timeout=30)
    return proc, (conf_out.read_text() if conf_out.exists() else ""), \
        (argv_out.read_text().splitlines() if argv_out.exists() else [])


def test_the_script_is_syntactically_valid():
    """Cheap, and it is the failure that produces the least helpful symptom:
    a container that exits 2 with one line of bash noise."""
    proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_the_script_is_executable_and_committed_as_such():
    """It is bind-mounted into the container. A mode that loses the execute
    bit is a start-up failure that only appears on the client's server."""
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK), (
        "config/prod-entrypoint.sh is not executable. `git update-index "
        "--chmod=+x` it — the compose command invokes it through `bash`, so "
        "this is belt and braces, but a script somebody runs directly should "
        "not need to be told how.")


# ── the refusal ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,env,expected_named", [
    ("both credentials are repo defaults — both named on the first attempt",
     {"PASSWORD": "odoo", "ODOO_MASTER_PASSWORD": "admin"},
     ["POSTGRES_PASSWORD", "ODOO_MASTER_PASSWORD"]),
    ("a strong postgres password and a default master password",
     {"PASSWORD": STRONG, "ODOO_MASTER_PASSWORD": "admin"},
     ["ODOO_MASTER_PASSWORD"]),
    ("a placeholder jwt secret",
     {"PASSWORD": STRONG, "ODOO_MASTER_PASSWORD": STRONG,
      "CADRA_JWT_SECRET": "changeme"},
     ["CADRA_JWT_SECRET"]),
    ("`test`, which is a placeholder somebody genuinely types",
     {"PASSWORD": "test", "ODOO_MASTER_PASSWORD": STRONG},
     ["POSTGRES_PASSWORD"]),
])
def test_a_default_valued_credential_refuses_the_bring_up(
        tmp_path, label, env, expected_named):
    proc, _conf, _argv = _run(tmp_path, **env)
    assert proc.returncode == 1, "%s: expected a refusal\n%s" % (label, proc.stdout)
    assert "REACHED_SERVER_START" not in proc.stdout, (
        "%s: odoo was started anyway" % label)
    for name in expected_named:
        assert name in proc.stderr, (
            "%s: the refusal does not name %s. An operator with two to fix "
            "must learn about both on the first attempt, not one per "
            "bring-up.\n%s" % (label, name, proc.stderr))
    for name in ("POSTGRES_PASSWORD", "ODOO_MASTER_PASSWORD", "CADRA_JWT_SECRET"):
        if name not in expected_named:
            assert name not in proc.stderr, (
                "%s: %s was named but is not a default" % (label, name))


@pytest.mark.parametrize("label,env", [
    ("strong credentials, empty jwt secret — bootstrap generates that one",
     {"PASSWORD": STRONG, "ODOO_MASTER_PASSWORD": STRONG,
      "CADRA_JWT_SECRET": ""}),
    ("strong credentials throughout",
     {"PASSWORD": STRONG, "ODOO_MASTER_PASSWORD": STRONG,
      "CADRA_JWT_SECRET": "s3cret-long-enough-value"}),
    ("a password that merely CONTAINS a refused word",
     {"PASSWORD": "administrator-9f2", "ODOO_MASTER_PASSWORD": "odoo-9f2x"}),
    ("a password that looks like a glob — the case patterns have no "
     "metacharacters, so this must not match",
     {"PASSWORD": "admi?", "ODOO_MASTER_PASSWORD": "od*o"}),
])
def test_a_real_credential_starts_the_server(tmp_path, label, env):
    """The half that matters most. A guard that refuses a correct
    configuration is a guard somebody deletes, and the inline first draft did
    exactly this: `set -e` killed it on the check that PASSED."""
    proc, _conf, _argv = _run(tmp_path, **env)
    assert proc.returncode == 0, (
        "%s: refused a legitimate configuration\nstderr: %s" % (label, proc.stderr))
    assert "REACHED_SERVER_START" in proc.stdout, label
    assert "FATAL" not in proc.stderr, label


# ── the config it builds ────────────────────────────────────────────────

def test_the_database_credentials_reach_the_config(tmp_path):
    """The defect that made the prod profile unable to start at all.

    A compose `command:` replaces CMD, not ENTRYPOINT, so the Odoo image's
    entrypoint runs with `$1` = `bash`, falls to `*) exec "$@"` and appends no
    `--db_user` / `--db_password`. `config/odoo.prod.conf` deliberately commits
    no database password. Without these two lines Odoo connects as the
    container user with no password and Postgres refuses it.
    """
    proc, conf, argv = _run(
        tmp_path, PASSWORD=STRONG, ODOO_MASTER_PASSWORD="Master-9f2x",
        POSTGRES_USER="odoo")
    assert proc.returncode == 0, proc.stderr

    assert "db_user = " in conf, (
        "no db_user in the generated config — the prod profile cannot "
        "authenticate to Postgres. See k8s/dev/41-odoo-19-deployment.yaml, "
        "which appends both.")
    assert "db_password = %s" % STRONG in conf, (
        "no db_password, or it was mangled. The value under test contains a "
        "space, a quote, a `$` and a backslash on purpose.")
    assert "admin_passwd = Master-9f2x" in conf

    # The template is preserved, not replaced.
    assert "db_host = db" in conf

    assert argv[:2] == ["-c", str(tmp_path / "odoo.conf")], argv
    assert any(a.startswith("--workers=") for a in argv), argv


def test_the_template_is_copied_not_edited_in_place(tmp_path):
    """The template is mounted READ-ONLY at `/etc/odoo/odoo.conf.template`.
    A script that appended to it directly would fail on the mount, and worse,
    would succeed on a developer's writable copy."""
    template = tmp_path / "odoo.conf.template"
    template.write_text("[options]\ndb_host = db\n")
    before = template.read_text()
    proc, _conf, _argv = _run(tmp_path, PASSWORD=STRONG,
                              ODOO_MASTER_PASSWORD=STRONG)
    assert proc.returncode == 0, proc.stderr
    assert template.read_text() == before, (
        "the script wrote to the config TEMPLATE, which is a read-only bind "
        "mount in the container")


def test_a_missing_template_fails_loudly_rather_than_starting_odoo(tmp_path):
    """`set -e` earns its place here: a `cp` that fails must not be followed
    by an `exec odoo` against a config that does not exist."""
    proc, _conf, _argv = _run(
        tmp_path, PASSWORD=STRONG, ODOO_MASTER_PASSWORD=STRONG,
        CADRA_CONF_TEMPLATE=str(tmp_path / "does-not-exist.conf"))
    assert proc.returncode != 0
    assert "REACHED_SERVER_START" not in proc.stdout


def test_the_master_password_never_reaches_stdout(tmp_path):
    """It goes into a file inside the container. `docker compose logs` is not
    a place to publish it, and a refusal message that echoed a GOOD password
    would be worse than the defect the refusal exists to prevent."""
    secret = "Zq7-not-in-any-log-4413"
    proc, _conf, _argv = _run(tmp_path, PASSWORD=STRONG,
                              ODOO_MASTER_PASSWORD=secret)
    assert proc.returncode == 0, proc.stderr
    assert secret not in proc.stdout
    assert secret not in proc.stderr


def test_the_compose_file_actually_invokes_this_script():
    """A script nothing runs is a test suite testing itself.

    The compose `command:` and the volume that puts the file in the container
    are both checked, because either one silently reverting to the inline
    block would leave every test above passing against a file the deployment
    no longer uses.
    """
    text = (REPO_ROOT / "docker-compose.prod.yml").read_text()
    assert "./config/prod-entrypoint.sh:" in text, (
        "docker-compose.prod.yml does not mount config/prod-entrypoint.sh")
    assert "cadra-prod-entrypoint" in text, (
        "docker-compose.prod.yml does not invoke the script it mounts")
    # Match the CODE, not the word: the `Prod-specific behavior` header
    # legitimately mentions admin_passwd in prose, and a guard that cannot
    # tell a comment from a command is a guard somebody edits around.
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    for shape in ("printf", "cp /etc/odoo", "set -e"):
        assert shape not in code, (
            "the start-up shell has crept back into the compose YAML (%r), "
            "where no test can execute it. That is how both of the bugs in "
            "this file's docstring shipped." % shape)

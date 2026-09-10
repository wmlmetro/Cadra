"""The bootstrap's wait for postgres, executed against a simulated blip.

CI failed on `fix/query-params-validate` with two lines a hundred
milliseconds apart:

    postgres ready after 2s
    FATAL: postgres did not become ready

The same commit passed on the next run, which is the signature of a race
rather than a defect in what was being tested — and a build that fails at
random is a build people re-run instead of read.

The race is in the postgres image, not in ours. `initdb` starts a TEMPORARY
server to create the database and run any init scripts, then shuts it down
before starting the real one. `pg_isready` answers yes to that temporary
server. `scripts/bootstrap.sh` broke its wait loop on the first yes, then
ran a second, independent confirmation probe — which landed during the
shutdown.

**A check that passes, followed by the same check failing.** This repository
has been here before: the first prod start-up shell refused every correct
configuration because `set -e` killed it on the check that PASSED, and
`tests/test_prod_entrypoint.py` exists because that shell was not runnable by
anything. Same lesson here, so the same treatment — the wait block is
extracted from the shipped file between two markers and RUN, with a stubbed
`docker` that reproduces the blip. Nothing here needs docker or a database.
"""
import pathlib
import re
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "bootstrap.sh"

_BEGIN = "# cadra-pg-wait: begin"
_END = "# cadra-pg-wait: end"


def _wait_block():
    """The shipped wait, byte for byte, between its markers."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert _BEGIN in text and _END in text, (
        "the `cadra-pg-wait` markers are gone from scripts/bootstrap.sh, so "
        "this file is testing nothing. They bracket the wait loop; if the "
        "loop moved, move them with it.")
    body = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    # The begin marker's own comment continuation lines run to end of line.
    return body.split("\n", 1)[1]


def _run(probe_results, streak=None, wait_seconds=12):
    """Execute the shipped block with `docker` answering from a script.

    `probe_results` is one character per second: `y` for a `pg_isready` that
    succeeds, `n` for one that refuses. The stub walks it in order, so a
    sequence like "nynnyyy" is initdb's temporary server appearing at second
    two and the real server arriving at second five.
    """
    harness = [
        "set -euo pipefail",
        "COMPOSE_FILES=(-f docker-compose.yml)",
        'ODOO_DB=odoo; ODOO_USER_DB=odoo',
        "PROBES='%s'" % probe_results,
        "probe_n=0",
        # Stubs. `sleep` is a no-op so the test runs in milliseconds rather
        # than in the wall-clock seconds the real loop waits.
        "sleep() { :; }",
        "docker() {",
        '  if [ "${2:-}" = "logs" ]; then return 0; fi',
        "  probe_n=$((probe_n + 1))",
        '  local c="${PROBES:$((probe_n - 1)):1}"',
        '  if [ "$c" = "y" ]; then return 0; else return 1; fi',
        "}",
        "CADRA_PG_WAIT_SECONDS=%d" % wait_seconds,
        "export CADRA_PG_WAIT_SECONDS",
    ]
    if streak is not None:
        harness.append("CADRA_PG_READY_STREAK=%d" % streak)
        harness.append("export CADRA_PG_READY_STREAK")
    source = "\n".join(harness) + "\n" + _wait_block()
    return subprocess.run(["bash", "-c", source],
                          capture_output=True, text=True, timeout=30)


def test_the_script_is_syntactically_valid():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_the_initdb_blip_no_longer_fails_the_build():
    """The regression, reproduced.

    `n y n n y y y` — refused, then initdb's temporary server for one second,
    then the shutdown, then the real server. The old loop broke on second 2
    and its confirmation probe ran on second 3.
    """
    proc = _run("nynnyyyyyyyy")
    assert proc.returncode == 0, (
        "the wait failed on a server that came up after a normal initdb "
        "blip\nstdout: %s\nstderr: %s" % (proc.stdout, proc.stderr))
    assert "FATAL" not in proc.stderr, proc.stderr
    assert "postgres ready after 7s" in proc.stdout, (
        "expected the wait to hold out for the REAL server at second 7, not "
        "to latch onto the blip at second 2: %r" % proc.stdout)


def test_a_single_probe_is_not_enough():
    """The heart of it: one yes, surrounded by noes, is not readiness."""
    proc = _run("nnynnnnnnnnn")
    assert proc.returncode == 1, (
        "a single successful probe was accepted as readiness: %s" % proc.stdout)
    assert "FATAL" in proc.stderr


def test_a_server_that_is_simply_up_is_accepted_promptly():
    """The counterweight. A guard that makes a healthy bring-up slow or
    flaky in the other direction is a guard somebody deletes."""
    proc = _run("yyyyyyyyyyyy")
    assert proc.returncode == 0, proc.stderr
    assert "postgres ready after 3s" in proc.stdout, (
        "a postgres that is up from the first probe should be accepted as "
        "soon as the streak is satisfied: %r" % proc.stdout)


def test_a_postgres_that_never_comes_up_still_fails():
    """The half that must not be lost. Making the wait tolerant of a blip
    must not make it tolerant of a database that is not there."""
    proc = _run("nnnnnnnnnnnn")
    assert proc.returncode == 1
    assert "did not become ready" in proc.stderr
    assert "the last streak reached 0" in proc.stderr, (
        "the failure does not say how close it got, which is the one number "
        "that tells an operator whether they are watching a slow start or a "
        "dead container: %r" % proc.stderr)


def test_a_flapping_server_is_never_accepted():
    """Up, down, up, down. Whatever that is, it is not a database to install
    into, and accepting it would move the failure to a later step where it
    reads as something else."""
    proc = _run("ynynynynynyn")
    assert proc.returncode == 1, (
        "a server alternating up and down was accepted: %s" % proc.stdout)


@pytest.mark.parametrize("probes,expected_second", [
    ("nnnnnyyyyyyy", 8),
    ("yynyyyyyyyyy", 6),
])
def test_the_reported_second_is_when_readiness_was_CONFIRMED(
        probes, expected_second):
    """The number in the log is the second the streak completed, not the
    second of the first hopeful answer. An operator reading "ready after 2s"
    on a build that then failed was reading a number about the wrong server.
    """
    proc = _run(probes)
    assert proc.returncode == 0, proc.stderr
    assert "postgres ready after %ds" % expected_second in proc.stdout, proc.stdout


def test_the_wait_does_not_probe_again_after_the_loop():
    """The specific shape that broke, guarded directly.

    Re-probing is what turned a race into a failed build: the loop had
    already established readiness and the script asked a second time,
    independently, with no retry. The loop's own outcome is the answer.
    """
    block = _wait_block()
    after_loop = block.split("done", 1)[1]
    # An INVOCATION, not the word. The failure message below quite
    # reasonably names `pg_isready` in prose, and a reader that cannot tell
    # a probe from a sentence about probes would flag its own diagnostics.
    probes = [line.strip() for line in after_loop.splitlines()
              if "pg_isready" in line and not line.lstrip().startswith(("#", "echo"))]
    assert not probes, (
        "scripts/bootstrap.sh probes pg_isready again after the wait loop. "
        "That is the exact defect this file exists for — the loop already "
        "knows, and a second independent probe can land during a restart.\n"
        "  %s" % "\n  ".join(probes))


def test_the_streak_is_not_written_as_the_form_that_kills_the_script():
    """`check && ready=1` under `set -e` kills the script when the check
    PASSES. That is not a hypothetical here: it is why the first prod
    start-up shell refused every correct configuration, and it is one
    keystroke from this loop."""
    block = _wait_block()
    offenders = [line.strip() for line in block.splitlines()
                 if re.search(r"&&\s*pg_\w+=", line)]
    assert not offenders, (
        "this assignment form exits a `set -e` script on the branch that "
        "succeeds: %s" % offenders)

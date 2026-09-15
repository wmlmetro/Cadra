"""What runtime a deployment actually gets, asserted rather than documented.

`docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
resolved the `odoo` service to `cadra-odoo:15.0-dev`, built `FROM odoo:15.0`,
for the whole of the Odoo 19 migration. `prod` is the profile a CLIENT is
deployed with, CI builds and tests only the 19 stack, and `myservice_request_core`
is 19-only — so the documented production path built a runtime that CI cannot
test and that cannot load this application's own modules.

Nothing had been deployed that way, which is the only reason it survived. It
survived TWO handoffs and a report, and report 19's own verification pass had
to find it twice, because **no test asserted which image a profile resolves
to**. Every reader who looked saw the 19 overlay, which is the one place the
override was, and concluded the stack was on 19.

This file is that test. It is deliberately static — it parses the compose
files and the Dockerfiles itself rather than shelling out to `docker compose
config` — for two reasons:

  1. The pytest suite runs on the host with `pytest` and `requests` and
     nothing else (tests/requirements.txt). A guard that needs the docker CLI
     is a guard that SKIPS where the CLI is missing, and a skip is a guard
     that passes. CLAUDE.md is explicit that a green run which executed
     nothing is the failure mode to design against.
  2. The real resolver is checked too, but in CI, where docker genuinely
     exists — see the `prod-compose-lint` job in .github/workflows/ci.yml,
     which asserts the same thing against `docker compose config` output.
     Two independent readers of the same fact, neither able to skip quietly.

The merge model below is the one compose actually uses for these keys: for a
scalar under a service, the LAST file on the command line wins. That is all
these files need — no `!reset`, no merge tags, no anchors — and
`test_the_merge_model_matches_what_docker_compose_resolves` states the
limitation rather than leaving it implied.
"""
import contextlib
import pathlib
import re
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The one runtime. Not "the runtime the overlay you happened to read uses".
EXPECTED_ODOO_MAJOR = 19

#: Every way this repository can be brought up, as the compose file list you
#: would actually type. A profile missing from here is a profile nothing
#: checks, so `test_every_compose_overlay_is_covered` fails if a
#: `docker-compose*.yml` exists that no entry below names.
PROFILES = {
    "dev": ("docker-compose.yml", "docker-compose.19.yml"),
    "prod": ("docker-compose.yml", "docker-compose.prod.yml"),
}

#: The base alone. It is not a profile — bringing it up on its own gives the
#: wrong odoo.conf and no proxy, which CLAUDE.md warns about — but it is what
#: an overlay INHERITS, and pinning the version there rather than in one
#: overlay is the fix. Checked separately so the reason stays visible.
BASE_ONLY = ("docker-compose.yml",)


def _service_scalars(compose_files, service, keys):
    """Resolve `keys` for `service` across an ordered list of compose files.

    Hand-rolled rather than PyYAML because tests/requirements.txt is `pytest`
    and `requests`, and adding a dependency to the host suite to read four
    files of flat two-space YAML is a worse trade than thirty lines here.

    Handles exactly what these files contain: a top-level `services:` map,
    two-space-indented service names, four-space-indented scalar keys, and
    one level of nesting for `build:`. A key is addressed as `build.dockerfile`
    or `image`. Anything it cannot parse it does not report, and the
    fixture-driven tests below are what stop that becoming a silent pass.
    """
    resolved = {}
    for name in compose_files:
        path = REPO_ROOT / name
        assert path.exists(), (
            "%s is named by PROFILES but does not exist. A profile pointing "
            "at a missing file resolves to nothing and asserts nothing."
            % name)
        found = _parse_one(path.read_text(encoding="utf-8"), service)
        for key in keys:
            if key in found:
                resolved[key] = found[key]      # last file on the CLI wins
    return resolved


#: A service key: two-or-more-space indented, optionally quoted, ending the
#: line with `:` once any trailing comment is removed. `  odoo:  # the app`
#: is ordinary YAML and the first version of this required the raw line to
#: end in a colon, so a single trailing comment made the whole service
#: invisible — and an invisible service in an OVERLAY reads as "overrides
#: nothing", which is a silent PASS on exactly the drift this file exists to
#: catch.
_SERVICE_KEY_RE = re.compile(r'^(\s+)["\']?([A-Za-z_][\w.-]*)["\']?:\s*(.*)$')


def _strip_comment(rest):
    """Remove a trailing YAML comment.

    `#` only opens a comment after whitespace or at the start, so a `#` inside
    a value (`${PW:-a#b}`, a colour, a URL fragment) is not one. Splitting on
    a bare `#` truncates those and can hide the very thing being looked for.
    """
    out, prev = [], " "
    in_quote = None
    for ch in rest:
        if in_quote:
            out.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in "\"'":
            in_quote = ch
            out.append(ch)
        elif ch == "#" and prev in " \t":
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).strip()


def _parse_one(text, service):
    """A deliberately small YAML reader, and its limits are asserted.

    It understands the shape these four files actually have. What it does NOT
    understand — anchors, merge keys, `!reset`, `extends`, and a service whose
    body is an inline flow mapping — is checked for separately by
    `test_the_compose_files_stay_inside_the_modelled_subset`, so an
    unsupported spelling FAILS rather than being silently misread. That
    distinction is the whole design: a parser that guesses is worse than one
    that says it cannot.
    """
    out = {}
    in_services = False
    in_this_service = False
    service_indent = None
    nested = None
    nested_indent = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            in_services = raw.split(":")[0].strip().strip("\"'") == "services"
            in_this_service = False
            service_indent = None
            continue
        if not in_services:
            continue
        m = _SERVICE_KEY_RE.match(raw)
        if not m:
            continue
        indent = len(m.group(1))
        key = m.group(2)
        rest = _strip_comment(m.group(3))

        # A service key sits at the shallowest indent inside `services:`.
        # Taking the FIRST one seen rather than assuming two spaces is what
        # makes a four-space-indented file readable instead of invisible.
        if service_indent is None:
            service_indent = indent
        if indent == service_indent:
            in_this_service = key == service
            nested = nested_indent = None
            continue
        if not in_this_service:
            continue

        if nested_indent is not None and indent > nested_indent:
            if rest:
                out["%s.%s" % (nested, key)] = rest.strip("\"").strip("'")
            continue
        nested = nested_indent = None
        if rest:
            out[key] = rest.strip("\"").strip("'")
        else:
            nested, nested_indent = key, indent
    return out


def value_of(rest):
    rest = rest.split("#")[0].strip()
    if not rest:
        return None
    return rest.strip('"').strip("'")


_FROM_RE = re.compile(r"^\s*FROM\s+odoo:(\d+)", re.IGNORECASE | re.MULTILINE)


def _dockerfile_major(rel):
    path = REPO_ROOT / rel
    assert path.exists(), "%s is referenced by a compose file but is gone" % rel
    m = _FROM_RE.search(path.read_text(encoding="utf-8"))
    assert m, "%s has no `FROM odoo:<major>` — cannot tell what it builds" % rel
    return int(m.group(1))


_IMAGE_TAG_RE = re.compile(r":(\d+)\.")


# ── the guard itself ────────────────────────────────────────────────────

@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_every_profile_resolves_to_the_one_supported_odoo_major(profile):
    """Both halves — the tag somebody reads and the base image it builds.

    They are checked separately on purpose. The drift this replaces was NOT a
    wrong `FROM`: `Dockerfile.odoo.dev` said `FROM odoo:15.0` and the image
    said `cadra-odoo:15.0-dev` and the two agreed perfectly with each other.
    Agreeing with each other is not the property that matters.
    """
    resolved = _service_scalars(PROFILES[profile], "odoo",
                                ("image", "build.dockerfile"))

    image = resolved.get("image")
    assert image, "profile %r resolves the odoo service to no image at all" % profile
    m = _IMAGE_TAG_RE.search(image)
    assert m, ("profile %r resolves to image %r, whose tag does not carry a "
               "major version. The tag is what a person reads when they ask "
               "what is running." % (profile, image))
    assert int(m.group(1)) == EXPECTED_ODOO_MAJOR, (
        "profile %r resolves the odoo service to %r — Odoo %s, not %d.\n"
        "A client deployed by this profile gets that runtime. CI builds and "
        "tests %d only, and myservice_request_core cannot load on anything "
        "else. If the supported major has genuinely changed, change "
        "EXPECTED_ODOO_MAJOR here and say so in docs/DECISIONS.md; if it has "
        "not, this is the drift that cost handoffs 19 and 20."
        % (profile, image, m.group(1), EXPECTED_ODOO_MAJOR, EXPECTED_ODOO_MAJOR))

    dockerfile = resolved.get("build.dockerfile")
    assert dockerfile, (
        "profile %r resolves to no build.dockerfile. It may be pulling a "
        "prebuilt image, which is fine for a release — but then this guard "
        "can no longer see what is inside it, and something else must."
        % profile)
    major = _dockerfile_major(dockerfile)
    assert major == EXPECTED_ODOO_MAJOR, (
        "profile %r builds from %s, which is `FROM odoo:%d`. The image TAG "
        "says %s. A tag that disagrees with its own base image is worse than "
        "either being wrong: every reader believes the tag."
        % (profile, dockerfile, major, image))


def test_the_base_compose_is_what_pins_the_version():
    """The overlay must not be the only thing that knows.

    `prod` overrode the command and the volumes and NOT the image, so it
    inherited whatever the base happened to build — and the base built 15
    while the single overlay that did override it built 19. Any overlay
    written from here inherits the right runtime by default instead of
    having to remember to ask for it.
    """
    resolved = _service_scalars(BASE_ONLY, "odoo", ("image", "build.dockerfile"))
    assert _dockerfile_major(resolved["build.dockerfile"]) == EXPECTED_ODOO_MAJOR, (
        "docker-compose.yml itself builds the wrong major. Every overlay that "
        "does not override `image` inherits this, which is exactly how the "
        "prod profile came to be on 15.")


def test_no_odoo_15_image_can_be_built_from_this_repository():
    """The retirement, not just the repointing.

    Repointing the compose files leaves `FROM odoo:15.0` sitting in the tree
    for the next `dockerfile:` line to find. There is one runtime; there
    should be no way to build another. `dist/` is excluded because it is the
    vendored Odoo 15 source tree and is not ours.
    """
    offenders = []
    for path in sorted(REPO_ROOT.glob("Dockerfile*")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _FROM_RE.finditer(text):
            if int(m.group(1)) != EXPECTED_ODOO_MAJOR:
                offenders.append("%s: FROM odoo:%s" % (path.name, m.group(1)))
    assert not offenders, (
        "These build an Odoo major this repository no longer supports. A "
        "Dockerfile nothing currently references is not harmless — it is the "
        "thing the next compose overlay points at.\n  " + "\n  ".join(offenders))


#: A first-party CI configuration. `crnd-19/.gitlab-ci.yml` is inside the
#: vendored CRND tree and is theirs; anything at the repository root is ours,
#: whoever wrote it originally.
_FIRST_PARTY_CI_GLOBS = (".gitlab-ci.yml", ".gitlab-ci.yaml",
                         ".github/workflows/*.yml",
                         ".github/workflows/*.yaml")

_SERIES_RE = re.compile(r"(?<![\d.])(\d+)\.0(?![\d])")

#: A YAML comment, which is prose and not a pin. `.github/workflows/ci.yml`
#: explains in a comment why `prod` used to resolve to `cadra-odoo:15.0-dev`,
#: and a guard that reads the explanation as the defect is a guard somebody
#: deletes the explanation to satisfy.
_YAML_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")

#: The two shapes a `<major>.0` takes in a first-party CI file when it is NOT
#: an Odoo series, both of them GitHub Actions conventions:
#:
#:     - uses: actions/setup-python@v5.0      a marketplace action, tag-pinned
#:       with: {node-version: '20.0'}         a runtime for the runner itself
#:
#: Everything else in these files that reads `<major>.0` is a series pin.
#:
#: That the exemptions are an ALLOW-list is the whole of the fix. This guard
#: used to demand the word `odoo` somewhere on the line before it would look
#: at the version — and the pin it was written to catch, `SERIES_BRANCH:
#: '15.0'`, does not carry it. Neither do the two bare `- "15.0"` refs beside
#: it. The guard read the real file, found nothing, and reported success;
#: only the proof's invented `ODOO_SERIES_BRANCH` ever tripped it.
#:
#: A deny-list of other people's version keys would be a list of guesses that
#: grows every time somebody adds a tool. These two exemptions are fixed
#: conventions, and the mutation proof below exercises both of them in the
#: same run that it rejects the real file.
_ACTION_TAG_PREFIX_RE = re.compile(r"@v?$")

#: A runtime-version key, matched ONLY where it sits immediately before the
#: number. `[\w-]*[-_]version\s*:` searched line-wide was the first attempt
#: and it was a hole in the same shape as the one this guard was written to
#: close: `ODOO_VERSION: '15.0'` — the single most likely spelling of the pin
#: — was exempted BECAUSE IT CONTAINS THE WORD `version`. So was
#: `ODOO_SERIES_VERSION`, and so was every `N.0` on any inline-flow line that
#: happened to carry a `python-version:` key somewhere else along it.
#:
#: Anchored with `$` against the text before the match, so only the key this
#: number is the value OF can exempt it — the discipline
#: `_ACTION_TAG_PREFIX_RE` already had.
_TOOL_VERSION_KEY_RE = re.compile(
    r"[\w-]*[-_]version\s*:\s*[\'\"]?$", re.I)

#: A line naming the runtime THIS repository ships is never exempt, whatever
#: key the number hangs off. `odoo` for the obvious reason; `cadra` because
#: our own modules are versioned `19.0.x` against the same major, so a
#: `CADRA_VERSION: 16.0` in a pipeline is the same finding wearing our name.
_OUR_OWN_RUNTIME_RE = re.compile(r"odoo|cadra", re.I)


def _versions_a_tool_and_not_odoo(line, match):
    """True when this `<major>.0` pins something that is not an Odoo series.

    `line` is the comment-stripped line; `match` is the `_SERIES_RE` hit
    inside it. Both tests read only what sits immediately BEFORE the number,
    so `odoo:15.0` — prefix `:` — is never exempted by either.

    And a line that mentions Odoo at all is exempted by NEITHER. That is the
    belt to the anchor's braces: a key called `odoo_version` is a runtime
    version by name and an Odoo series pin in fact, and there is no spelling
    of this rule that gets that case right by pattern alone. A CI file
    naming Odoo and a retired series on one line is the thing being looked
    for, whatever the key is called.
    """
    before = line[:match.start()]
    if _OUR_OWN_RUNTIME_RE.search(line):
        return False
    if _ACTION_TAG_PREFIX_RE.search(before):
        return True
    return bool(_TOOL_VERSION_KEY_RE.search(before))


def test_no_first_party_ci_config_pins_a_retired_odoo_series():
    """The same argument as the Dockerfile above, one file type along.

    The root `.gitlab-ci.yml` was a CRND assembly artifact — `SERIES_BRANCH:
    '15.0'`, a `registry.crnd.pro` image, a GitLab that is not a remote of
    this repository, last touched by an assembly bot in March 2023. It was
    left in place at handoff 20 on the grounds that it was inert, and inert
    is exactly the state the Dockerfile above was in when it was the thing
    the prod overlay pointed at. A pipeline definition nobody runs is what
    somebody wires up when they next want a pipeline.

    So the file is gone, and this is what stops it, or a successor, coming
    back carrying a version this repository cannot run.
    """
    offenders = []
    for glob in _FIRST_PARTY_CI_GLOBS:
        for path in sorted(REPO_ROOT.glob(glob)):
            text = path.read_text(encoding="utf-8", errors="replace")
            for raw_line in text.splitlines():
                line = _YAML_COMMENT_RE.sub("", raw_line)
                for m in _SERIES_RE.finditer(line):
                    if int(m.group(1)) == EXPECTED_ODOO_MAJOR:
                        continue
                    if _versions_a_tool_and_not_odoo(line, m):
                        continue
                    offenders.append("%s: %s" % (
                        path.relative_to(REPO_ROOT), line.strip()))
    assert not offenders, (
        "These CI configurations name an Odoo series this repository no "
        "longer supports:\n  " + "\n  ".join(offenders))


#: `.gitlab-ci.yml` as it stood the moment before `d8e6d98` deleted it, byte
#: for byte. Evidence, not a sketch — see the two tests below.
RETIRED_CI_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "retired-gitlab-ci.yml"


def test_the_ci_series_guard_reads_the_file_it_was_written_for(tmp_path):
    """Mutation proof against THE REAL FILE, not one this test invented.

    The previous version of this proof wrote `ODOO_SERIES_BRANCH: '15.0'` and
    passed. The deleted file actually said `SERIES_BRANCH: '15.0'` — no
    `odoo` anywhere on the line — so the guard, which required that word
    before it would look, read the real file and found nothing. Restoring it
    here would have been a green run either way. Report 22 counted four
    guards that pass without testing anything; this was one of them, and the
    proof is the part that was wrong.

    So the input is now `tests/fixtures/retired-gitlab-ci.yml`, which is the
    file git deleted and is asserted to be exactly that by
    `test_the_retired_ci_fixture_is_the_file_git_deleted`.
    """
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".gitlab-ci.yml").write_bytes(RETIRED_CI_FIXTURE.read_bytes())
    # And the three shapes that must NOT trip it: an action pinned by tag, a
    # runtime for the runner, and a comment explaining the history this guard
    # exists because of. Both exemptions get exercised on every run.
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  build:\n    steps:\n"
        "      # `prod` used to resolve to cadra-odoo:15.0-dev\n"
        "      - uses: actions/setup-python@v5.0\n"
        "        with:\n"
        "          python-version: '3.11.0'\n"
        "          node-version: '20.0'\n")

    with _repo_root_at(tmp_path):
        with pytest.raises(AssertionError) as exc:
            test_no_first_party_ci_config_pins_a_retired_odoo_series()
    message = str(exc.value)
    # The pin itself, named in the words the file uses.
    assert "SERIES_BRANCH: '15.0'" in message, message
    # And the branch refs beside it, which carry the series and no `odoo`
    # either. Three offenders, not one.
    assert message.count("15.0") >= 3, message
    # None of the exempt shapes.
    assert "setup-python" not in message, message
    assert "node-version" not in message, message
    assert "used to resolve" not in message, message


#: Lines that MUST be flagged, and lines that must not. Every entry in the
#: first list was exempted by the first version of this fix, which searched
#: for a `*_version:` key anywhere on the line: `ODOO_VERSION: '15.0'` — the
#: most natural spelling of the very pin this guard exists to catch — was
#: waved through BECAUSE IT CONTAINS THE WORD `version`. A fix that reopens
#: the hole it closed in a new shape is why these are a table and not a
#: paragraph.
_MUST_FLAG = (
    "    ODOO_VERSION: '15.0'",
    "    odoo_version: 15.0",
    '    ODOO-VERSION: "15.0"',
    "    ODOO_SERIES_VERSION: '15.0'",
    "  odoo_addons_version: 15.0",
    "    CADRA_VERSION: 16.0",
    "  image: odoo:15.0",
    "    SERIES_BRANCH: '15.0'",
    '        - "15.0"',
    # One `python-version:` elsewhere on an inline-flow line used to exempt
    # every number on it, including the Odoo image beside it.
    "  with: {python-version: '3.11.0', odoo-image: 'odoo:15.0'}",
)

_MUST_NOT_FLAG = (
    "      - uses: actions/setup-python@v5.0",
    "          node-version: '20.0'",
    "        with: {python-version: '3.0'}",
    "      - uses: docker/build-push-action@v6.0",
    "    go-version: 21.0",
)


@pytest.mark.parametrize("line", _MUST_FLAG)
def test_a_retired_series_cannot_hide_behind_a_version_key(line):
    """Each of these is a way the pin has been, or could be, spelled."""
    stripped = _YAML_COMMENT_RE.sub("", line)
    flagged = [m for m in _SERIES_RE.finditer(stripped)
               if int(m.group(1)) != EXPECTED_ODOO_MAJOR
               and not _versions_a_tool_and_not_odoo(stripped, m)]
    assert flagged, (
        "this line pins a retired series and the guard exempts it: %r" % line)


@pytest.mark.parametrize("line", _MUST_NOT_FLAG)
def test_a_tool_version_is_not_read_as_an_odoo_series(line):
    """The other direction. A guard that flags `setup-python@v5.0` is a
    guard somebody switches off, and the real pins go with it."""
    stripped = _YAML_COMMENT_RE.sub("", line)
    flagged = [m for m in _SERIES_RE.finditer(stripped)
               if int(m.group(1)) != EXPECTED_ODOO_MAJOR
               and not _versions_a_tool_and_not_odoo(stripped, m)]
    assert not flagged, (
        "this line versions a tool and the guard reads it as an Odoo "
        "series: %r" % line)


def test_the_retired_ci_fixture_is_the_file_git_deleted():
    """The fixture is evidence, so it has to be the bytes git is holding.

    A fixture that drifts from the file it claims to be is how the proof
    above goes hollow a second time. This re-derives it from history rather
    than trusting the copy.

    It is the one test here allowed to skip, and only where history is not
    present to check against: `actions/checkout@v4` clones at depth 1, so in
    CI the deleting commit's parent simply is not in the object store. The
    skip is safe because nothing else depends on it — the mutation proof
    reads the committed bytes and fails on them, shallow clone or not.
    """
    import subprocess

    def git(*args):
        return subprocess.run(("git",) + args, cwd=str(REPO_ROOT),
                              capture_output=True)

    probe = git("rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0:
        pytest.skip("not a git work tree")

    deleted_in = git("log", "--diff-filter=D", "--format=%H", "-1",
                     "--", ".gitlab-ci.yml")
    commit = deleted_in.stdout.decode().strip()
    if deleted_in.returncode != 0 or not commit:
        pytest.skip("the deleting commit is not in this clone (shallow)")

    blob = git("show", commit + "^:.gitlab-ci.yml")
    if blob.returncode != 0:
        pytest.skip("the deleting commit's parent is not in this clone")

    assert blob.stdout == RETIRED_CI_FIXTURE.read_bytes(), (
        "tests/fixtures/retired-gitlab-ci.yml is no longer the file deleted "
        "in %s. Restore it with:\n"
        "  git show %s^:.gitlab-ci.yml > tests/fixtures/"
        "retired-gitlab-ci.yml" % (commit[:12], commit[:12]))


def test_every_compose_overlay_is_covered_by_a_profile():
    """A guard that names its own inputs cannot see a new one.

    PROFILES is a hand-written list, which is the same shape of mistake as a
    waiver list: add `docker-compose.staging.yml` and nothing here fails,
    because nothing here looks. This is what looks.
    """
    on_disk = {p.name for p in REPO_ROOT.glob("docker-compose*.yml")}
    covered = {name for files in PROFILES.values() for name in files}
    covered |= set(BASE_ONLY)
    unchecked = on_disk - covered
    assert not unchecked, (
        "these compose files are not part of any profile this file checks, "
        "so nothing asserts which runtime they resolve to: %s\n"
        "Add them to PROFILES." % ", ".join(sorted(unchecked)))


def test_the_deployment_runbook_names_the_runtime():
    """docs/DEPLOYMENT.md did not contain the string "19" ANYWHERE.

    CLAUDE.md calls that document the real shape of a client deployment, and
    it described a runtime two majors old without ever naming a version — so
    a reader could not even tell it was out of date. Naming the version is
    what makes the next drift visible to a person as well as to this file.
    """
    text = (REPO_ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert re.search(r"Odoo\s+%d" % EXPECTED_ODOO_MAJOR, text), (
        "docs/DEPLOYMENT.md never says 'Odoo %d'. It is the document a client "
        "deployment is performed from; it has to say what it deploys."
        % EXPECTED_ODOO_MAJOR)
    for dead in ("docker-compose.dev.yml", "Dockerfile.odoo.dev",
                 "config/odoo.dev.conf", "Dockerfile.odoo.k8s"):
        assert dead not in text, (
            "docs/DEPLOYMENT.md still tells an operator to use %s, which was "
            "removed with the Odoo 15 stack." % dead)


# ── the same fact, checked the other way: the prod credential refusal ────
#
# §C of handoff 20: `docs/DEPLOYMENT.md` told a prod operator to generate
# strong values with `openssl rand`. That is ADVICE, so the security position
# rested on somebody having read it — the exact promise a rule exists to stop
# relying on. The prod bring-up refuses to start on a default-valued
# credential now, and this is what stops that list quietly emptying out.

#: Kept identical to the `case` list in docker-compose.prod.yml's command.
#: Duplicated deliberately: the shell needs it as a glob alternation and the
#: test needs it as data, and asserting the two agree is cheaper and louder
#: than generating one from the other at container start.
REFUSED_CREDENTIAL_VALUES = (
    "admin", "odoo", "postgres", "password", "passwd", "secret",
    "changeme", "change-me", "CHANGEME", "test", "cadra", "example",
)

_MARKER = "# cadra-refusable-defaults:"


#: The start-up shell lives in a FILE, not inline in the compose YAML, so
#: that tests/test_prod_entrypoint.py can execute it. This reads the same
#: file for its value list.
PROD_ENTRYPOINT = REPO_ROOT / "config" / "prod-entrypoint.sh"


def _prod_refusal_list():
    text = PROD_ENTRYPOINT.read_text(encoding="utf-8")
    marker = [ln for ln in text.splitlines() if _MARKER in ln]
    assert len(marker) == 1, (
        "expected exactly one `%s` marker in config/prod-entrypoint.sh, "
        "found %d. The marker is how this test reads the shell's own list."
        % (_MARKER, len(marker)))
    declared = tuple(marker[0].split(_MARKER, 1)[1].split())

    case = re.search(r"^\s*(\S*\|\S*)\)\s*$", text, re.MULTILINE)
    assert case, "no `a|b|c)` case alternation found in the refusal block"
    return declared, tuple(case.group(1).split("|"))


def test_the_prod_bring_up_refuses_every_default_this_repo_ships():
    """The list, the shell and this file all say the same thing.

    Three copies is two too many unless they are asserted equal, which they
    are — so widening the shell's `case` without widening the marker, or
    either without this constant, fails here rather than in six months on a
    client server.
    """
    declared, in_case = _prod_refusal_list()
    assert declared == in_case, (
        "the `cadra-refusable-defaults:` marker and the shell `case` in "
        "config/prod-entrypoint.sh disagree.\n  marker: %s\n  case:   %s"
        % (list(declared), list(in_case)))
    assert set(declared) == set(REFUSED_CREDENTIAL_VALUES), (
        "config/prod-entrypoint.sh refuses %s; this test expects %s"
        % (sorted(declared), sorted(REFUSED_CREDENTIAL_VALUES)))


def test_the_committed_credential_defaults_are_all_actually_refused():
    """The point of the list is these four values, so read them, don't recite.

    `.env.example` is the file a prod operator copies. Whatever credential
    defaults it ships must be values the prod container refuses, or the
    waiver in tests/test_source_guards.py is excusing a default that can
    still reach a client server.
    """
    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    cred = re.compile(r"password|passwd|secret|token|_key", re.IGNORECASE)
    shipped = {}
    for line in env.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
        if m and cred.search(m.group(1)) and m.group(2).strip():
            shipped[m.group(1)] = m.group(2).strip()

    assert shipped, (
        ".env.example ships no non-empty credential default at all. If that "
        "is genuinely true now, delete this test and the waiver in "
        "tests/test_source_guards.py with it — an exception kept past the "
        "thing it excused is a hole with a name on it.")

    unrefused = {k: v for k, v in shipped.items()
                 if v not in REFUSED_CREDENTIAL_VALUES}
    assert not unrefused, (
        ".env.example ships these credential defaults and the prod bring-up "
        "would start with them: %s\nEither add the value to the refusal list "
        "in config/prod-entrypoint.sh (and to REFUSED_CREDENTIAL_VALUES "
        "here), or stop shipping it." % unrefused)


# ── proving the guards fail before they pass ────────────────────────────
#
# CLAUDE.md: a guard that has never been seen to fail is a guard nobody
# knows works. These feed the readers above the exact drift they exist to
# catch, as fixtures, so the failure is demonstrated on every run rather
# than remembered from the day it was written.

@contextlib.contextmanager
def _repo_root_at(path):
    """Point the readers at a fixture tree, and always put REPO_ROOT back.

    `sys.modules[__name__]` rather than `import tests.test_deployment_profile`:
    the readers close over the module-level `REPO_ROOT`, so the object patched
    has to be the one they read. An `import` by name relies on pytest having
    put this file in `sys.modules` under exactly that dotted path — true today
    because `tests/` is a package, and a silent no-op the day it is not, which
    would leave these two tests asserting things about the REAL repository
    while claiming to test a fixture.

    `finally` matters as much: REPO_ROOT is module state, so an assertion
    failing inside the block would otherwise leave every later test in this
    file pointed at a deleted tmp_path, and they would fail with a missing
    file rather than with the real reason.
    """
    module = sys.modules[__name__]
    original = module.REPO_ROOT
    module.REPO_ROOT = path
    try:
        yield module
    finally:
        module.REPO_ROOT = original


_BASE_FIXTURE = """\
services:
  db:
    image: postgres:13
  odoo:
    build:
      context: .
      dockerfile: Dockerfile.odoo.19.dev
    image: cadra-odoo:19.0-dev
"""

_OVERLAY_OVERRIDES_IMAGE = """\
services:
  odoo:
    build:
      dockerfile: Dockerfile.odoo.15.dev
    image: cadra-odoo:15.0-dev
"""

_OVERLAY_OVERRIDES_NOTHING = """\
services:
  odoo:
    command:
      - odoo
    restart: unless-stopped
"""


@pytest.mark.parametrize("label,overlay,expected_image", [
    ("an overlay that overrides the image wins",
     _OVERLAY_OVERRIDES_IMAGE, "cadra-odoo:15.0-dev"),
    ("an overlay that overrides neither inherits the base — the prod defect",
     _OVERLAY_OVERRIDES_NOTHING, "cadra-odoo:19.0-dev"),
])
def test_the_merge_model_is_last_file_wins(label, overlay, expected_image, tmp_path):
    files = []
    for name, body in (("a.yml", _BASE_FIXTURE), ("b.yml", overlay)):
        (tmp_path / name).write_text(body)
        files.append(name)
    with _repo_root_at(tmp_path) as mod:
        resolved = mod._service_scalars(files, "odoo", ("image", "build.dockerfile"))
    assert resolved["image"] == expected_image, label


def test_the_reader_catches_the_drift_it_was_written_for(tmp_path):
    """The literal defect: base on 15, one overlay on 19, prod overriding
    neither. That resolved to 15 and no test anywhere said so."""
    (tmp_path / "base.yml").write_text(
        _BASE_FIXTURE.replace("19.0-dev", "15.0-dev")
                     .replace("Dockerfile.odoo.19.dev", "Dockerfile.odoo.dev"))
    (tmp_path / "prod.yml").write_text(_OVERLAY_OVERRIDES_NOTHING)
    (tmp_path / "Dockerfile.odoo.dev").write_text("FROM odoo:15.0\n")
    with _repo_root_at(tmp_path) as mod:
        resolved = mod._service_scalars(("base.yml", "prod.yml"), "odoo",
                                        ("image", "build.dockerfile"))
        assert resolved["image"] == "cadra-odoo:15.0-dev"
        assert mod._dockerfile_major(resolved["build.dockerfile"]) == 15


#: Spellings a verification pass measured the FIRST version of `_parse_one`
#: getting wrong. Every one returned `{}` for the odoo service — and `{}` in
#: an OVERLAY reads as "overrides nothing, inherits the base", which is a
#: silent PASS on precisely the drift this file exists to catch. A parser that
#: cannot see a service is more dangerous than one that cannot see a key.
_PARSER_SPELLINGS = [
    ("a trailing comment on the service key — ordinary YAML, and this repo "
     "comments heavily",
     "services:\n"
     "  odoo:   # the application container\n"
     "    image: cadra-odoo:19.0-dev\n"),
    ("four-space indentation",
     "services:\n"
     "    odoo:\n"
     "        image: cadra-odoo:19.0-dev\n"),
    ("a quoted service key",
     "services:\n"
     '  "odoo":\n'
     "    image: cadra-odoo:19.0-dev\n"),
    ("a quoted mapping key",
     "services:\n"
     "  odoo:\n"
     '    "image": cadra-odoo:19.0-dev\n'),
    ("a trailing comment on the value",
     "services:\n"
     "  odoo:\n"
     "    image: cadra-odoo:19.0-dev   # pinned, see DECISIONS\n"),
    ("a quoted value",
     "services:\n"
     "  odoo:\n"
     '    image: "cadra-odoo:19.0-dev"\n'),
]


@pytest.mark.parametrize("label,source", _PARSER_SPELLINGS,
                         ids=[c[0][:40] for c in _PARSER_SPELLINGS])
def test_the_reader_sees_the_service_however_it_is_written(label, source):
    found = _parse_one(source, "odoo")
    assert found.get("image") == "cadra-odoo:19.0-dev", (
        "%s: the reader returned %r. An unreadable service in an overlay "
        "resolves as 'inherits the base', which is a silent pass."
        % (label, found))


@pytest.mark.parametrize("label,source,expected", [
    ("a service named `odoo` nested under another service's depends_on",
     "services:\n"
     "  proxy:\n"
     "    depends_on:\n"
     "      odoo:\n"
     "        condition: service_started\n"
     "    image: nginx:alpine\n", {}),
    ("`image:` inside a multi-line command block is not a key",
     "services:\n"
     "  odoo:\n"
     "    command:\n"
     "      - bash\n"
     "      - -c\n"
     "      - |\n"
     "        echo image: cadra-odoo:15.0-dev\n"
     "    restart: unless-stopped\n", {}),
], ids=["nested-service-name", "image-inside-a-command-block"])
def test_the_reader_does_not_invent_an_image(label, source, expected):
    """The other direction, and the one that would be loudest if wrong: a
    false FAIL on a correct file teaches people to delete the guard."""
    found = _parse_one(source, "odoo")
    assert "image" not in found, "%s: read %r as the odoo image" % (label, found)


def test_the_compose_files_stay_inside_the_modelled_subset():

    """States the limitation instead of leaving it implied.

    The reader above understands flat scalars and one level of `build:`
    nesting. It does NOT understand anchors, merge keys, `!reset`, `!override`
    or `extends`, and if one of those ever appears under a compose service
    here, its answer stops matching docker's. Rather than skip when the CLI is
    absent — a skip is a guard that passes — this asserts the PRECONDITION:
    the compose files stay within the subset the reader models.
    """
    unsupported = ("<<:", "!reset", "!override", "extends:")
    offenders = []
    for path in sorted(REPO_ROOT.glob("docker-compose*.yml")):
        text = path.read_text(encoding="utf-8")
        for token in unsupported:
            if token in text:
                offenders.append("%s uses %s" % (path.name, token))
        # A service whose whole body is an inline flow mapping
        # (`odoo: {image: …}`). The reader skips the body and returns {},
        # which in an overlay reads as "inherits the base" — a silent pass.
        # It is not worth parsing for four files that do not use it; it IS
        # worth failing on.
        for m in re.finditer(r"^\s+[\"']?[A-Za-z_][\w.-]*[\"']?:\s*\{",
                             text, re.MULTILINE):
            offenders.append("%s uses an inline flow mapping at %r"
                             % (path.name, m.group(0).strip()))
    assert not offenders, (
        "the static merge model in this file no longer describes these "
        "files, so its answer may differ from `docker compose config`:\n  "
        + "\n  ".join(offenders) +
        "\nEither keep the compose files within the modelled subset, or "
        "replace this reader with one that shells out to the real resolver.")

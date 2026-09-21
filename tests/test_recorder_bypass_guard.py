"""Nothing first-party may change who holds an asset, where it is, or what has
happened to it, by a route that goes round `nrs.asset.write`.

`nrs.asset.custody`, `nrs.asset.movement` and — since handoff 30 —
`nrs.asset.event` are written by `nrs.asset.write` (the first two by
`nrs.asset.create` as well). Their whole value is that EVERY writer passes
through there — and a guarantee that lives in Python says nothing to a writer
that does not. There are exactly three ways to be one: raw SQL against
`nrs_asset`, the ORM's low-level `_write()`, and the database acting by
itself (a foreign key's `SET NULL`, which `generic.location.unlink` covers
and `myservice_asset_register/tests/test_movement_record.py` holds).

This holds the first two. It is a source scan, in the manner of
`test_source_guards.py`, because the failure it prevents cannot be seen by
running anything: a script that does `UPDATE nrs_asset SET location_id = …`
works perfectly, and leaves a register that says an asset never moved. One
that does `UPDATE nrs_asset SET state = 'active'` un-disposes an asset with
no event, no actor and no reason — and also walks straight past the rule that
disposal is terminal, which lives in the same `write`.

Tests are exempt, on purpose. Fixtures backdate and remove rows with SQL
because the models refuse to let them — that is the models working.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Where first-party code that can reach a database lives.
ROOTS = ("scripts", "seeds", "docs/api")
SKIP_PARTS = {"tests", "__pycache__", "node_modules", "dist", "_upgrade",
              "_to_delete", ".venv"}

# Custody and movement. Matched as a WORD anywhere in the SET clause, as they
# have been since handoff 28: neither name turns up on the right-hand side of
# anything, so a mention is a write.
RECORDED = ("location_id", "custodian_id")

# `nrs.asset.event` (handoff 30): a change of status, a verification date, and
# the three references an auditor reconciles against Vendra and SAP. Matched
# as an ASSIGNMENT TARGET, not as a word, because `state` is a word: a
# perfectly innocent `SET disposal_date = CASE WHEN state = 'disposed' …`
# reads it and changes nothing, and a guard that cries at that is a guard
# somebody learns to silence. `last_verified_by` is not here: the recorder
# keys on the DATE, and a verifier written without one is not an event.
EVENT_RECORDED = ("state", "last_verified_date", "grn_reference",
                  "purchase_order_reference", "sap_asset_number")

# `UPDATE nrs_asset SET`, `UPDATE nrs_asset a SET`, `UPDATE nrs_asset AS a
# SET`. The alias forms were invisible until handoff 30 — nothing in the tree
# used one, which is luck and not a guarantee. `nrs_asset_custody` and the
# other `nrs_asset_*` tables are not matched: `\s+` has to follow the name.
_UPDATE = re.compile(
    r"UPDATE\s+(?:ONLY\s+)?nrs_asset(?:\s+(?:AS\s+)?(?!SET\b)\w+)?\s+SET\b"
    r"(?P<set>.*?)(?:\bWHERE\b|;|\"\"\"|'''|$)",
    re.IGNORECASE | re.DOTALL)
_LOW_LEVEL_WRITE = re.compile(r"\._write\(")


def _assigns(field, set_clause):
    """Whether the SET clause ASSIGNS `field` — `state = …`, `a.state = …`,
    `"state" = …`, or inside a row assignment `(state, condition) = (…)`."""
    single = r"(?:^|,)\s*(?:\w+\.)?\"?%s\"?\s*=(?!=)" % re.escape(field)
    row = r"\([^()=]*\b%s\b[^()=]*\)\s*=" % re.escape(field)
    return bool(re.search(single, set_clause, re.IGNORECASE)
                or re.search(row, set_clause, re.IGNORECASE))


def _first_party_python():
    roots = [REPO / r for r in ROOTS]
    roots += [p for p in REPO.iterdir()
              if p.is_dir() and p.name.startswith("myservice_")]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if SKIP_PARTS & set(path.relative_to(REPO).parts):
                continue
            yield path


def _raw_sql_offenders(touches):
    """`path:line sets a, b` for every raw UPDATE of `nrs_asset` that
    `touches(set_clause)` says writes a recorded field."""
    offenders = []
    for path in _first_party_python():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _UPDATE.finditer(text):
            touched = touches(match.group("set"))
            if touched:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append("%s:%d sets %s" % (
                    path.relative_to(REPO), line, ", ".join(touched)))
    return offenders


def test_no_raw_sql_moves_an_asset_or_changes_its_custodian():
    offenders = _raw_sql_offenders(
        lambda clause: [f for f in RECORDED
                        if re.search(r"\b%s\b" % f, clause)])
    assert not offenders, (
        "raw SQL that changes a recorded field goes round `nrs.asset.write`, "
        "so the append-only record never hears of it and the register says "
        "nothing happened:\n  " + "\n  ".join(offenders) +
        "\nWrite through the ORM. If the change genuinely must not be "
        "recorded, that is a decision for docs/DECISIONS.md, not a query.")


def test_no_raw_sql_changes_a_status_a_verification_or_a_reference():
    """The event recorder's five columns, for the movement recorder's reason.

    And one reason of its own: `nrs.asset.write` is also where a disposed
    asset is refused a change of status. Raw SQL does not only fail to record
    the change — it is the one door through which an asset can still leave
    `disposed`, silently, which is the defect handoff 30 §B closed.
    """
    offenders = _raw_sql_offenders(
        lambda clause: [f for f in EVENT_RECORDED if _assigns(f, clause)])
    assert not offenders, (
        "raw SQL that changes a status, a verification date or a reconciled "
        "reference goes round `nrs.asset.write`, so no `nrs.asset.event` is "
        "written — the history shows nothing, with nobody's name on it — and "
        "the rule that disposal is terminal is never asked:\n  "
        + "\n  ".join(offenders) +
        "\nWrite through the ORM. If the change genuinely must not be "
        "recorded, that is a decision for docs/DECISIONS.md, not a query.")


def test_nothing_uses_the_low_level_write():
    offenders = []
    for path in _first_party_python():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _LOW_LEVEL_WRITE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append("%s:%d" % (path.relative_to(REPO), line))
    assert not offenders, (
        "`_write()` skips every `write()` override — the custody, movement "
        "and event recorders among them, and the refusal to change a "
        "disposed asset:\n  " + "\n  ".join(offenders))


def test_the_scan_can_see_what_it_is_looking_for():
    """A guard that matches nothing passes forever. Proved on a sample."""
    sample = 'cr.execute("UPDATE nrs_asset SET location_id = %s WHERE id = %s")'
    assert _UPDATE.search(sample)
    assert "location_id" in _UPDATE.search(sample).group("set")
    harmless = 'cr.execute("UPDATE nrs_asset SET asset_code = %s WHERE id=1")'
    assert "location_id" not in _UPDATE.search(harmless).group("set")
    assert _LOW_LEVEL_WRITE.search("records._write({'location_id': 1})")
    assert len(list(_first_party_python())) > 50, "the scan found no code"


def test_the_scan_can_see_an_aliased_update():
    """`UPDATE nrs_asset a SET …` is the same write. Until handoff 30 the
    pattern required `SET` to follow the table name and saw neither form."""
    for sql in ("UPDATE nrs_asset a SET location_id = 1 WHERE a.id = 2",
                "UPDATE nrs_asset AS a SET location_id = 1 WHERE a.id = 2",
                "update only nrs_asset\n   set location_id = 1"):
        match = _UPDATE.search(sql)
        assert match, "not seen: %s" % sql
        assert "location_id" in match.group("set")
    # The sibling tables are other models' business, and other guards'.
    for sql in ("UPDATE nrs_asset_custody SET reason = 'x'",
                "UPDATE nrs_asset_event SET source = 'test'"):
        assert not _UPDATE.search(sql), "matched a different table: %s" % sql


def test_the_event_scan_tells_a_write_from_a_read():
    """Both halves, because `state` is a word and the others are not."""
    def touched(sql):
        match = _UPDATE.search(sql)
        assert match, "the UPDATE itself was not seen: %s" % sql
        return [f for f in EVENT_RECORDED if _assigns(f, match.group("set"))]

    # Writes — every spelling of an assignment target.
    assert touched("UPDATE nrs_asset SET state = 'active' WHERE id = 1") == [
        "state"]
    assert touched("UPDATE nrs_asset SET state='active'") == ["state"]
    assert touched('UPDATE nrs_asset a SET "state" = %s') == ["state"]
    assert touched("UPDATE nrs_asset a SET a.state = 'missing'") == ["state"]
    assert touched(
        "UPDATE nrs_asset SET notes = 'x', sap_asset_number = %s "
        "WHERE id = 1") == ["sap_asset_number"]
    assert touched(
        "UPDATE nrs_asset SET (state, condition) = ('disposed', "
        "'decommissioned')") == ["state"]
    assert touched(
        "UPDATE nrs_asset SET last_verified_date = now(), "
        "grn_reference = NULL, purchase_order_reference = NULL") == [
        "last_verified_date", "grn_reference", "purchase_order_reference"]

    # Reads — the column is consulted and nothing about it changes.
    assert touched(
        "UPDATE nrs_asset SET disposal_date = CASE WHEN state = 'disposed' "
        "THEN now() END") == []
    assert touched(
        "UPDATE nrs_asset SET notes = coalesce(notes, state)") == []
    assert touched(
        "UPDATE nrs_asset SET asset_code = 'x' WHERE state = 'missing'") == []
    # A different column that merely ENDS in the word.
    assert touched(
        "UPDATE nrs_asset SET sap_reconciliation_state = 'exception', "
        "tag_label_state = 'printed'") == []

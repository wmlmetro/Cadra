"""Nothing first-party may change who holds an asset, or where it is, by a
route that goes round `nrs.asset.write`.

`nrs.asset.custody` and `nrs.asset.movement` are written by `nrs.asset.write`
and `nrs.asset.create`. Their whole value is that EVERY writer passes through
there — and a guarantee that lives in Python says nothing to a writer that
does not. There are exactly three ways to be one: raw SQL against
`nrs_asset`, the ORM's low-level `_write()`, and the database acting by
itself (a foreign key's `SET NULL`, which `generic.location.unlink` covers
and `myservice_asset_register/tests/test_movement_record.py` holds).

This holds the first two. It is a source scan, in the manner of
`test_source_guards.py`, because the failure it prevents cannot be seen by
running anything: a script that does `UPDATE nrs_asset SET location_id = …`
works perfectly, and leaves a register that says an asset never moved.

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

RECORDED = ("location_id", "custodian_id")

_UPDATE = re.compile(
    r"UPDATE\s+nrs_asset\s+SET\b(?P<set>.*?)(?:\bWHERE\b|;|\"\"\"|'''|$)",
    re.IGNORECASE | re.DOTALL)
_LOW_LEVEL_WRITE = re.compile(r"\._write\(")


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


def test_no_raw_sql_moves_an_asset_or_changes_its_custodian():
    offenders = []
    for path in _first_party_python():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _UPDATE.finditer(text):
            touched = [f for f in RECORDED
                       if re.search(r"\b%s\b" % f, match.group("set"))]
            if touched:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append("%s:%d sets %s" % (
                    path.relative_to(REPO), line, ", ".join(touched)))
    assert not offenders, (
        "raw SQL that changes a recorded field goes round `nrs.asset.write`, "
        "so the append-only record never hears of it and the register says "
        "nothing happened:\n  " + "\n  ".join(offenders) +
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
        "`_write()` skips every `write()` override, the custody and movement "
        "recorders among them:\n  " + "\n  ".join(offenders))


def test_the_scan_can_see_what_it_is_looking_for():
    """A guard that matches nothing passes forever. Proved on a sample."""
    sample = 'cr.execute("UPDATE nrs_asset SET location_id = %s WHERE id = %s")'
    assert _UPDATE.search(sample)
    assert "location_id" in _UPDATE.search(sample).group("set")
    harmless = 'cr.execute("UPDATE nrs_asset SET asset_code = %s WHERE id=1")'
    assert "location_id" not in _UPDATE.search(harmless).group("set")
    assert _LOW_LEVEL_WRITE.search("records._write({'location_id': 1})")
    assert len(list(_first_party_python())) > 50, "the scan found no code"

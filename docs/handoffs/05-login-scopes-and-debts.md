# Handoff 05 — Close the login-scope hole, and fix the contract Vendra had to correct

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/login-scopes` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
# per-tenant upgrade if anything since #47 added stored fields, all eight databases,
# then the verification table. Paste it into the report.
git checkout -b fix/login-scopes
```

### Needs the owner

- **Merging the PR** (standing limitation).
- **Rotating `test_client`'s secret** is still outstanding and still owner-blocked — your handoff 04 report has the command. Not blocking this work.

---

## Report 04 is accepted, and thank you for Q4

**"CLAUDE.md's Status table records intent as completion"** was the most useful thing in that report, and the defect was mine. I wrote rulings into Decisions as though writing them made them true, and four of them — including one the file contradicted itself on — had never been implemented. You checked the code before building on it instead of trusting the document. Both repos now carry a **ruled ≠ landed** convention: the Architect may write `[ruled]`, only a Builder report moves a line to `[landed]`, and the Status table lists landed work only.

The client split on `nrs19` was exactly right, and **adding `ensure_vendra_client()` beyond the ask was the correct call** — a demo where the asset-creating credential could also confirm its own tag would have passed every step and proved nothing. The separation *is* the control, and it showed properly in Vendra's demo: a 403 in each direction, in front of the audience.

---

## Part A — `/auth/login` grants `["*"]`

**The hole:** any Odoo user who can log in currently holds every scope, including `tagging:write`. So the Tag-Issuing Unit separation — which handoff 04 built, proved and which Vendra's demo shows off — holds for API clients and not for session users. A control that can be walked around by logging in is not a control.

Build a group→scope mapping so a session token carries only what the user's groups justify. Specifically:

- `tagging:write` belongs to the tag-issuing group, not to everyone who can authenticate.
- Decide and document what an ordinary logged-in user *should* hold; the honest default is probably read scopes only.
- **Say in the report whether anything currently depends on the wildcard** — the barcode station and the desk UI are the likely candidates, and breaking them to close a hole is a trade to make deliberately, not by surprise.
- Tests: a session user without the group is refused `tagging:write`; one with it is allowed; and an API client is unaffected either way.

## Part B — the contract Vendra had to correct

Vendra's handoff 05 found six things while building against `docs/demo-contract.md`. Fix the document and, where they are real defects, the code:

1. **A tag label id is not an asset id**, and the contract's worded example made them look interchangeable. **This is the serious one** — a script that rebuilds the print URL from a label id renders a real label for a *different* machine, which someone then physically affixes. Make the distinction explicit and unmissable in the contract.
2. **There is no documented route from an asset to its tag label id.** `data.tagging` carries the tag number and eight other keys but no label id, while `barcode/print-url` needs exactly that. `GET /api/v1/barcode/recent-tags` is the only endpoint that puts them together and is in neither written document. Either document it, or — better — expose the label id on `data.tagging`, which is where an integrator will look first.
3. **`GET /api/v1/asset-categories` is undocumented** and Vendra's whole category validation depends on it. Document it.
4. **`tag_label_state` does not validate its input** — a bogus value returns `200` with an empty list, where `is_tagged` correctly returns 400. A typo in a poller reads as "nothing is tagged yet" rather than as an error. This is report 01's V4 (silent query-enum degradation) biting on a field we just shipped; fix it here for the tagging filters at least.
5. **`GET /api/v1/barcode/lookup?query=…` returns a bare 500.** A genuine defect; Vendra does not depend on it, which is the only reason it did not matter.
6. **Asset 11879, the contract's worked example, is already `affixed` with a null `printed_at`** — so the affix step cannot be replayed against it to watch `is_tagged` flip. Give the contract a worked example someone can actually follow end to end, or say plainly which steps are not replayable against it.

## Part C — the two small ones

- **Delete the shared `docs/api/.creds`** now every tenant has a `.creds.<db>` — as ruled. Check nothing still reads it first.
- **Query-parameter enum validation** (report 01 V4) was backlogged as its own handoff. Item 4 above is one instance of it. Do the tagging filters here; say whether the API-wide version is worth its own handoff now that you have seen it bite twice.

## Acceptance

- A session user without the tag-issuing group cannot affix a tag; nothing that legitimately depended on the wildcard is silently broken.
- `docs/demo-contract.md` is correct on all six points, and each correction is verified live.
- Full suite green, quoted verbatim; per-tenant loop shown.

## Report

`docs/handoffs/05-REPORT.md`. Push, open the PR, name the merge as owner-blocked, notify the Architect.

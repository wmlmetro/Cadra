# Handoff 69 · Where the captures went

**For:** the Builder. **From:** the Architect, 27 October 2026.
**Branch:** `fix/where-the-captures-went` off `dev`. Commit as CLAUDE.md says.
**Budget:** under 3 hours (CLAUDE.md *Speed*). Report ≤ 200 lines in
`docs/handoffs/69-REPORT.md`, progress in `69-PROGRESS.md`.

**Progress weights** (sum 100): Part A, the investigation, 30 · Part B, the
review page finds every capture, 35 · Part C, next time is one command, 25 ·
CI cited and the report, 10. Print `Progress: N%` as each part lands.

---

## 0 · What the owner sees

The mobile app (the mobile team's build) captures items with AI and syncs them
to `POST /api/v1/audit/captures`. The phone says they were submitted. Some of
them **cannot be found on Audit › Audit review**, even signed in as the
reviewer. Others from the same phone can. We do not know yet whether the
missing ones are on the server and hidden, or were never stored.

This handoff finds out, fixes what hides them, and leaves a tool so the next
"where is my capture?" takes one command.

## 1 · What I read in the code before writing this (check it, don't trust it)

The review page (`Frontend/…/src/pages/audit/AuditReview.tsx`) can hide a
stored, waiting capture in **four** ways:

| # | Hides it when… | Where |
|---|---|---|
| H1 | the capture's campaign does **not name this person as a reviewer** | `campaigns` query filters `c.reviewers.some(u => u.id === me)` |
| H2 | the campaign is **closed** | `fetchCampaigns("open")` |
| H3 | more than **100** captures match the filter: the list is one page, `limit: 100`, and the server pages by **id ascending** (`paginate(order="id")`), so the **newest** captures are the ones cut off, and nothing says so | `fetchCaptures({… limit: 100})`, no cursor followed |
| H4 | the person is looking at a **different campaign** from the dropdown's default, or a room filter | the dropdown |

And three ways the capture is **not on the server** at all:

| # | Never stored because… |
|---|---|
| H5 | the server **refused** it (4xx: device not bound to the person, code not reserved, scanned label ≠ code, room outside the campaign, `captured_at` older than five working days…). A refusal writes **nothing**, by design, so no table holds it; only the Odoo log line does. If the phone did not show the refusal, the person believes it was submitted. |
| H6 | the phone sent it to **another tenant** (another base URL) than the one the reviewer is looking at |
| H7 | it is still **queued on the phone** (never sent, or sent and dropped) |

## 2 · Rules for this handoff

- **Read-only on every tenant database.** Every query runs inside
  `BEGIN READ ONLY; … ; ROLLBACK;`. No `UPDATE`, `INSERT`, `DELETE`, no Odoo
  shell that writes, no `--stop-after-init` against a tenant. `nrs19` is not
  touched at all.
- **Nothing personal or secret goes into the repo or the report.** Report users
  and captures by **id**, never by name or email. Do not download or copy
  photos. Do not print the database password: read it from the `cadra-db`
  secret into a variable, never into output or a file.
- The cluster: namespace **`cadra-dev`**, Postgres pod **`db-0`** (statefulset
  `db`), Odoo deployment **`odoo-19`**. **One database per tenant, named as the
  subdomain** (`staging.app.cadra.ng` → database `staging`;
  `k8s/dev/MULTI-TENANT.md`). Before the first command, run
  `kubectl config current-context` and
  `kubectl -n cadra-dev get pods`. If the context is not the Cadra cluster,
  stop and ask the owner.
- **Which tenant does the mobile app point at?** Ask the owner for the mobile
  app's base URL in Step 0. Until you have it, assume `staging`.

## 3 · Part A — find them (30)

**Step 0.** Ask the owner, in one message, for: the mobile app's base URL; and,
if they have them, two or three missing captures identified any way they can
(the phone's `capture_id`, the printed code, the time and room, the
capturer's login). Do not wait for the answer: start A1 with `staging`.

**A1 · Every capture, and why the reviewer would or would not see it.** On the
tenant, one query that lists every `nrs_audit_capture` received in the last 14
days with: `id`, `capture_uuid`, `campaign_id`, the campaign's `state`,
`location_id`, `state`, `outcome`, `duplicate_of_id`, `operator_id`,
`device_id`, `received_at` (or `create_date`), and:

- `reviewers_named` — how many active users the campaign's
  `nrs_audit_campaign_reviewer_rel` holds;
- `rank_in_review_list` — the capture's position (by `id`) among the captures
  of its campaign in the same `state` — the position the review page's query
  gives it. Above 100 = hidden by H3.

Then a count per campaign: captured, `pending_review`, accepted, returned,
reviewers named, open or closed.

**A2 · The missing ones that ARE stored.** For each one the owner named (or,
without names, every `pending_review` capture), say which of H1–H4 hides it,
with the row that proves it.

**A3 · The missing ones that are NOT stored.**

- Search for the `capture_uuid` / code in **every tenant database** on the
  cluster (`\l`, then the same SELECT on each, read-only). Found in another
  tenant = H6.
- Read the Odoo log for the refusals:
  `kubectl -n cadra-dev logs deploy/odoo-19 --since=168h | grep 'POST /api/v1/audit/captures'`
  and, around the times the owner gave, the status of each POST (Odoo's
  werkzeug line carries it). Count by status. For 4xx, the request's
  `request_id` and the refusal's sentence if the log has it. A refusal =
  H5; say which rule refused it.
- Neither stored nor in the log = H7, the phone. Say so; it is the mobile
  team's to look at, and the report says what they should check.

**A4 · The answer, in a table** at the top of the report: each missing capture
(by id or the owner's description) → H1–H7 → the evidence (a query result or
a log line, trimmed) → what fixes it. Then a one-paragraph plain-English
summary the owner can read without the table.

Save the queries you used as Part C's script (C1): you are writing it now, not
later.

## 4 · Part B — the review page finds every capture (35)

Whatever Part A finds, these four are gaps. Close them.

**B1 · Every page, and the count (H3).** The review list follows
`pagination.next_cursor`: show the first 100 and a **"Show the next 100"**
button, and say *"Showing 100 of 143 waiting"* from `total_estimate`. The
**Every room** view and **Accept the room** are unchanged. Ruling: **order
stays id ascending** (oldest waiting first is the right review order); the fix
is that nothing past the page is invisible.

**B2 · Find a capture.** A search box on **Audit review** and **Audit
campaigns**: paste a `capture_id` (UUID), a printed code, or an old FIRS tag,
and get the capture wherever it is.

- Server: `GET /api/v1/audit/captures?q=<text>` (`audit:read`): exact
  `capture_uuid`, exact `code`, exact normalised `fields.legacy_asset_code`.
  Combines with the other filters. Document it in the endpoint reference §19.6
  and in `docs/integrations/mobile-app-build-guide.md` §5.8.
- The page shows each match with its **campaign (open or closed), room,
  state, captured by, device, received at**, and **who may review it** (the
  campaign's reviewers). If the signed-in person is not one of them, it says
  so in words: *"You are not a reviewer on HQ floor 10. Its reviewers are …;
  the Asset Controller adds reviewers on Audit campaigns."* (Names on screen
  are fine; they are not in the repo.) Not found: *"No capture on this
  register has that ID or code. If the phone says it was submitted, it may
  have been refused or sent elsewhere: Devices and codes › Refused syncs."*

**B3 · Waiting where nobody can review it (H1, H2).** On **Audit campaigns**,
a campaign with captures `pending_review` and **no active reviewer named**
gets a warning line: *"N captures wait and no reviewer is named."* On **Audit
review**, under the campaign dropdown, when the person is a reviewer on no
open campaign that has waiting captures, but captures wait elsewhere:
*"N captures wait in campaigns that don't name you as a reviewer."* Server:
add `reviewers_active` to the campaign answer (the count), so the page does
not guess.

**B4 · Where it came from.** Each capture card on Audit review shows the
**device** name and the **received at** time next to captured at. The owner
must be able to tell a phone capture from a station one at a glance.

## 5 · Part C — next time is one command (25)

**C1 · `scripts/audit_trace.sh`.** Read-only, run from a machine with the
cluster context:

```
scripts/audit_trace.sh <tenant> [--capture <uuid> | --code <code> | --device <DEV-xxxxxxxx> | --campaign <id>] [--since <YYYY-MM-DD>] [--logs]
```

- prints the A1 table (ids only, no names) for what it was asked, with
  `rank_in_review_list` and `reviewers_named`;
- `--logs` adds the Odoo log lines for `POST /api/v1/audit/captures` in the
  window, with their status;
- `--capture` / `--code` with no row in this tenant searches the others and
  says where it found it;
- refuses to run if the context is not the Cadra cluster, and runs every query
  read-only (`BEGIN READ ONLY`). Test it against `test19f` locally through
  `docker compose … exec db psql` (a `--local` flag), and once against
  `staging` on the cluster; put the staging output, trimmed, in
  `69-evidence/`.

**C2 · Refused syncs are kept.** A refusal writes nothing today, so a
capture the phone failed to send leaves no trace anyone but a log reader can
see. Ruling: **keep a record of every refused `POST /audit/captures`.**

- A new append-only model `nrs.audit.capture.refusal`: `capture_uuid` (as
  sent, may be empty), `user_id`, `device_code` (as sent), `device_id` (if it
  resolved), `campaign_id`, `location_id`, `outcome`, `code` (as sent),
  `http_status`, `error_code`, `reason` (the `details.reason` if any),
  `message` (the sentence sent back), `request_id`, `refused_at`. **Never the
  body's photos, fields, or GPS.**
- Written **outside the refused request's transaction** (a separate cursor,
  committed on its own), because the request rolls back. One row per refused
  POST; a replay that is refused again is a second row.
- Read: `GET /api/v1/audit/refusals?device_id=&user_id=&since=&capture_id=`
  (`audit:manage`), cursor-paged, newest first. On **Devices and codes**, a
  section **Refused syncs (last 7 days)**: time, person, device, the sentence.
- Kept 90 days, then a cron removes older rows. Document the route in the
  reference §19 and in the mobile guide §6.6 (*"the Asset Controller sees your
  refusals"*).
- Tests: a refused capture (scanned label ≠ code) leaves one refusal row and no
  capture; an accepted one leaves none; a refusal row survives the request's
  rollback.

**C3 · The runbook.** `docs/runbooks/where-is-a-capture.md`, one page for the
owner: the H1–H7 table, in plain words, each with *what you see* and *what to
do*, starting from the web app (Find a capture → Refused syncs → campaign
reviewers) and ending with `audit_trace.sh` for the cases the web app cannot
answer (H6, H7).

## 6 · Tests, CI, report (10)

- Targeted tests: B1 (a campaign with 101 waiting: the 101st is reachable),
  B2 (`?q=` by uuid, code, old tag; a closed campaign's capture found), B3
  (`reviewers_active`), C2 (above). One full run at the end. Cite the CI run.
- The report opens with **A4's table and summary**. Then what changed, the
  evidence files, and a section **For the mobile team**: anything Part A
  found that is theirs (refusals the phone did not show, captures never sent,
  a wrong base URL), each with what to change.
- Do not wait on CI idle (rule 9).

## 7 · Not in this handoff

- No change to who may review, the role exclusions, or the five-day window.
- No write to any tenant's data to "fix" a missing capture. If Part A finds
  captures stranded in a campaign with no reviewer, the report says so, and
  the Asset Controller adds a reviewer on Audit campaigns.
- Nothing pushed to the mobile app.

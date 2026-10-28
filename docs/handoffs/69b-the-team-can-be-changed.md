# Handoff 69b · The team can be changed

**For:** the Builder. **From:** the Architect, 28 October 2026.
**Branch:** `fix/where-the-captures-went`: **the same branch and PR (#133)**.
It is not merged, CI has not run on it, and this touches the same page.
**Budget:** under 1 hour. Append a section **69b** to `69-REPORT.md` (≤ 60 lines).
**Progress weights:** B1 50 · the three leftovers 30 · tests and report 20.

## 0 · Why

The owner, signed in as admin, opened a campaign on **Audit › Audit
campaigns** to add a reviewer to campaign 1 (report 69, Needs the owner,
item 1) and found **no way to do it**. The server has had
`PATCH /api/v1/audit/campaigns/<id>` (`name`, `capturer_ids`, `reviewer_ids`,
`date_end`) since handoff 66, and `lib/auditCapture.ts` has `patchCampaign`,
but **no screen calls it**: the campaign detail offers only *Close the
campaign*. A campaign's team is fixed at opening, in the web app. That is the
gap, and it is what stranded captures 1–5.

## 1 · B1 · Edit the campaign (50)

On the campaign detail, for a holder of `audit:manage` (admin is a wildcard)
and an **open** campaign only, an **Edit** button beside *Close the campaign*.
It opens the same fields as *Open a campaign*, filled with the campaign's
current values:

- **Name**, **end date**;
- **Capturers** and **Reviewers**: the same pickers as opening, from
  `GET /audit/people`, current members ticked.

Save sends `PATCH` with only what changed. **`capturer_ids` and `reviewer_ids`
replace the lists**, so the form always sends the whole list for a list it
changed, never a delta. The scope lines are not editable (the server does not
take them; say so under the form in one line: *"The rooms and offices are
fixed once the campaign is open."*).

- Every refusal is the server's sentence, verbatim (one person on both lists;
  a closed campaign).
- After a save, refresh the campaign, the campaign list and the Audit review
  queries (`invalidateAudit`), so a reviewer just added sees the waiting
  captures without reloading.
- Report 69's warning line *"N captures wait and no reviewer is named."* gets a
  link, **Add a reviewer**, that opens this form (for a holder of
  `audit:manage`).
- Removing a reviewer who has already reviewed captures is allowed (the
  server allows it); their reviews stand.

## 2 · The three leftovers from report 69 (30)

1. **Refusal rows: one per repeated failure, not per attempt.** A refusal with
   the same `capture_uuid`, `user_id`, `error_code` and `message` as one
   recorded in the last 24 hours increments a `count` and moves
   `last_refused_at` on that row instead of adding one. The API and the
   *Refused syncs* section show the count (*"3 times, last 10:42"*).
2. **`409 sync_in_flight` is not a refusal.** It means the same capture is
   landing in another request; do not record it.
3. **Review it here** on a capture past the first 100 loads the pages up to it
   and scrolls to it.

## 3 · Tests and report (20)

- Browser: admin opens campaign → Edit → adds a reviewer → saves → signs in as
  that reviewer → the waiting captures are on Audit review. A capturer named as
  reviewer too → the server's sentence. A closed campaign shows no Edit.
- HTTP: the merged refusal row (two identical refusals → one row, count 2; a
  different message → two rows); `sync_in_flight` → no row.
- Targeted runs only; the full suite already ran for 69. CI is blocked for
  the whole repository (report 69, item 0); say so, don't wait on it.

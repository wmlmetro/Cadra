# Handoff 69 — report · where the captures went

**Branch:** `fix/where-the-captures-went` · **PR:** [#133](https://github.com/wmlmetro/Cadra/pull/133) · **CI:** **could not start** — see Needs the owner, item 0

## Needs the owner

0. **GitHub Actions has started no run since 27 Oct 18:20 UTC, on any
   branch.** Every run since then ends in `startup_failure` with no jobs:
   `dev`'s scheduled uptime check, my Step 0 push to `dev`, and this PR's
   push and pull-request runs (40608666123, 40608694094). The last success
   was the uptime check at 12:41 that day. No workflow file has changed
   since 25 Oct, and the uptime check's file not since August, so this is the
   account, not the code. It is most likely Actions minutes or a spending
   limit, which the token here cannot read (`admin:org`). Until it is fixed
   nothing deploys either, because `deploy-dev` is a workflow. In CI's place
   I ran its two jobs locally (The numbers: gates on, and the module suites).
1. **On staging, add a reviewer to campaign 1.** Five captures (ids 1–5) wait
   there and the campaign names nobody, so nobody can review them. Audit
   campaigns → campaign 1 → reviewers. Nothing was written to staging (§7).
2. **Merge the PR, then run `upgrade-19`.** Both module versions moved, there's
   a new table, and `nrs.audit.capture` gains a column:
   `target_dbs=staging,gtb,jaizbankplc,lasg`,
   `upgrade_modules=myservice_asset_register,myservice_api`,
   `scale_down=true`, `image=…cadra-odoo-19:dev-<merge sha>`. Until that runs,
   staging's backend doesn't have `?q=`, `/audit/refusals` or the refusal
   record. A push rolls only the front end, so the new screens would call
   routes the old backend lacks (they fail in words, not silently).
3. **Upgrade `nrs19` locally when you choose.** The handoff says `nrs19` is not
   touched, so it was left at the old version. Its audit screens answer
   `503 server_misconfigured` until upgraded:
   `docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo odoo -c /etc/odoo/odoo.conf -d nrs19 -u myservice_asset_register,myservice_api --stop-after-init --http-port=8099 --gevent-port=8098`
4. **The mobile app's base URL** (asked at Step 0, no answer yet). Every
   finding below is on `staging`, the only cluster tenant with any audit data
   (gtb, jaizbankplc and lasg hold 0 captures each).

## A4 · The answer

Staging holds **11 captures, all from one person (user 9), all from one device
(device 2)**: 9 sent by the phone, 2 from the web desk (photo `source`). None is
lost on the server. Ten are waiting, and two different things hide them.

| Missing capture | Hidden by | Evidence (`69-evidence/A-staging-*.txt`) | What fixes it |
|---|---|---|---|
| ids **1–5** (campaign 1, rooms 162/260/279/279/304, 20–21 Oct) | **H1** — the campaign names no reviewer | campaign 1: `pending_review 5`, `reviewers_named 0`; only user 2 holds *Audit Reviewer*, named on campaigns 3 and 4 | Add a reviewer to campaign 1 (owner, item 1). Since this handoff, Audit campaigns warns *"5 captures wait and no reviewer is named."* |
| ids **7–11** (campaign 3, 22–27 Oct) | **H4** — the review page opened another campaign | the dropdown takes the newest open campaign naming the reviewer: campaign 4, `captured 0`. The log shows the review page asking for `campaign_id=4` twice and never for 3 | Fixed: the page now opens the first of your campaigns with captures waiting. Find a capture finds any of them by id or code. |
| 3 phone photos with no capture (photos 7, 12, 14: 20 Oct 22:36, 22 Oct 07:10, 22 Oct 09:35) | **H5 or H7, unprovable** | each was uploaded and identified by the AI, then no capture used it. The Odoo log starts 26 Oct 08:08 (pod restart), so a refusal before then left no line | From now on a refusal is a row on *Devices and codes › Refused syncs*. If one of these was a real item, it is still on the phone (H7) or was refused (H5). The mobile team checks the queue (below). |

What was ruled out, with denominators:
- **H2 (closed campaign):** none; 5 of 5 campaigns are open.
- **H3 (over 100):** none; the largest campaign holds 6.
- **H5 in the surviving log:** 2 POSTs to `/audit/captures` since 26 Oct 08:08,
  both `201`, and 0 4xx/5xx on any `/api/v1/audit/*` route.
- **H6 (another tenant):** 0 captures on gtb, jaizbankplc and lasg; `nrs` and
  `odoo` have no audit tables.

**In plain words.** Nothing the phone sent is lost. Every capture that reached
the server is stored, and all eleven are on staging. Five sit in a campaign
nobody was named to review, so no reviewer's list could ever show them. The
other five are in a campaign the reviewer can review, but the review page
opened a different, empty campaign first and said "nothing waiting". Both are
now said on screen, and the page opens the campaign with work in it. There's
one open question: three photos the phone sent and the AI read were never
attached to a capture. That's either a person who gave up on that item, or a
capture that was refused or is still on the phone. The server's log from those
days is gone, so it can't say which. From today the server keeps every refusal
where the Asset Controller can see it.

## What changed

- **B1, every page.** The review list follows the cursor: the first 100, then
  *Show the next 100*, and *Showing 100 of 143 waiting* from the server's
  count. The order is still oldest first; Every room and Accept the room are
  unchanged.
- **B2, find a capture.** `GET /api/v1/audit/captures?q=` (`audit:read`): the
  capture id (any case), the code (exactly, any case) or the confirmed old tag
  (normalised like the SAP matcher), combined with the other filters, closed
  campaigns included. Each row's `campaign` now carries `state` and its active
  `reviewers` (additive). The find box is on Audit review and Audit campaigns
  and shows campaign (open/closed), room, state, captured by, device, received
  at and who may review it. It tells a non-reviewer in words who the reviewers
  are. The not-found sentence links to Refused syncs. A stored, indexed
  `legacy_tag_key` on the capture makes the old-tag search an index probe.
- **B3, waiting where nobody can review it.** `reviewers_active` on every
  campaign answer. Audit campaigns says *"N captures wait and no reviewer is
  named."*; Audit review says *"N captures wait in campaigns that don't name
  you as a reviewer."* and opens the campaign that has work.
- **B4, where it came from.** Each card reads *captured by … on \<device\>,
  \<captured\>; received \<received\>*.
- **C1.** `scripts/audit_trace.sh <tenant> [--capture|--code|--device|--campaign]
  [--since] [--logs] [--local]`: read-only, ids only, an explicit kube context.
- **C2, refused syncs are kept.** `nrs.audit.capture.refusal`, written through
  a new `on_refusal` hook on the route decorator on its own cursor. Read on
  `GET /api/v1/audit/refusals` (`audit:manage`, newest first, paged, by
  device/person/since/capture id), shown on *Devices and codes › Refused syncs
  (last 7 days)*, and removed by a daily job after 90 days. Never photos,
  fields or GPS.
- **C3.** `docs/runbooks/where-is-a-capture.md`.
- Docs: endpoint reference §19 (`?q=`, `reviewers_active`, `/audit/refusals`),
  mobile guide §5.8 and §6.6, the API changelog. Versions:
  `myservice_asset_register` 19.0.1.37.0, `myservice_api` 19.0.3.39.0.
  **Additive only; nothing Vendra reads is changed or removed.**

## For the mobile team

1. **Show every refusal and never mark a capture submitted on a 4xx.** Since
   this release the Asset Controller sees each refusal, with the sentence the
   phone was sent. The phone has to show the same sentence to the person
   holding it.
2. **Each capture must upload its own photo.** Captures 3, 4, 5 and 6 on
   staging all carry photo 8, the same bytes, in three rooms over 14 hours,
   and the AI was asked about photo 8 four times. The server stores a photo
   once per set of bytes, so the phone resent an old image for three new
   items. Look at how the camera result is cached between captures.
3. **Check the offline queue for 20 Oct 22:36, 22 Oct 07:10 and 22 Oct
   09:35.** A photo was uploaded and identified at each of those times and
   never became a capture. Either the person abandoned the item, or the
   capture is still queued or was dropped.
4. **To confirm a sync,** use `GET /audit/captures/<capture_id>`, or
   `?q=<capture_id>` (mobile guide §5.8).

## The numbers

- **Full pytest, once, gates off** (no gate, candidate or receipt code
  changed), on a fresh `test19f`: **1,568 passed, 3 failed, 14 skipped of
  1,585** in 7 m 23 s. The 3 were guards on this branch's own additions: the
  query-parameter inventory (4 new parameters), the model-create resolver
  (`env[self._name]`, now a literal), and the endpoint index row (added by the
  docs). All fixed. Rerun: `test_query_param_guard.py` +
  `test_source_guards.py` 233 of 233; `test_where_the_captures_went.py` +
  `test_endpoint_reference.py` + `test_the_audit.py` 22 of 22 after the
  verification pass's fixes. CI runs both switch states on the push.
- **New HTTP tests** `tests/test_where_the_captures_went.py`: 7 of 7. That
  covers B1 (the 101st reachable through the cursor, `total_estimate` 101), B2
  (id in three casings, code in three spellings, old tag normalised, a
  fragment, `%` and `_` finding nothing, combined filters, a closed campaign's
  capture), B3 and C2 (one row and no capture, the code still `reserved`, a
  replay is a second row, filters, an accepted capture and both door refusals
  leaving none, the scope).
- **In-registry**, `--workers=0`: `TestCaptureRefusal` 0 failed of 5 tests.
  `TestPublishedNamesResolve` 1 failed of 14. That failure also happens on
  `dev`'s controllers locally (deviation 6), and CI passes it.
- **Browser**, on `test19f`: spec 69 2 of 2; specs 66 and 67 3 of 3 (the
  three changed screens), rerun after the fixes 5 of 5. SPA typecheck clean,
  `BASE_PATH=/app/` build passes.
- **Upgrades:** `test19`, then the `test19f` template rebuilt (75 s). Both
  verified by the table, the column and `latest_version`
  (19.0.1.37.0 / 19.0.3.39.0). `nrs19` was not upgraded (Needs the owner).
- **The verification pass** (a fresh agent, read-only over the diff) found:
  - **one defect, fixed:** `reviewers_active` counted deactivated reviewers
    on the single-campaign routes, because `_browse_or_404` turns
    `active_test` off. It is now filtered on `active`, on the capture row's
    `reviewers` too.
  - **fixed:** a repeated Find answered from a 5-minute cache, so "not found"
    could outlive the sync; Refused syncs had the same cache.
  - **fixed:** "last 7 days" covered 8.
  - **fixed:** the decorator's docstring overclaimed what it never records.
  - **fixed:** two weak test assertions (`device_id` and the Lagos `since`
    now each have a negative case).
  - **named, not fixed:**
    - refusal rows have no cap: a phone stuck retrying writes one per
      attempt for 90 days;
    - a `409 sync_in_flight` is recorded although the capture then lands;
    - *Review it here* on a capture past the room's first 100 opens the
      room without scrolling to it.

## Deviations and questions

1. **The kube context.** The current context was Vendra's cluster. I proved the
   Cadra cluster by its `cadra-dev` namespace holding `db-0` and `odoo-19`, and
   named it on every command rather than stopping (§2). The owner's context was
   never switched. psql used `db-0`'s local socket, so no password was read.
2. **The log covers 39 hours, not 168.** The `odoo-19` pod restarted on 26 Oct
   08:08, and `--since=168h` can't reach past a restart. That is why the three
   orphan photos can't be ruled H5 or H7.
3. **A 401 or a scope 403 is not recorded** (DECISIONS 2026-10-28). An
   unauthenticated caller must not be able to make the server write.
4. **The review page's default campaign changed.** §4 didn't ask for it; Part A
   showed it was the cause of H4.
5. **`nrs19` was not upgraded** (§2 overrides CLAUDE.md's fan-out); see Needs
   the owner, item 3.
6. **Found, not mine:** locally, `TestPublishedNamesResolve.test_every_bare_override_of_an_inherited_route_is_named`
   fails on `dev`'s controller code too (four back-office doors "no longer
   exist" to the walk; 1 failed of 1 with this branch's controllers stashed).
   CI passes it. Recorded, not fixed.
7. `docs/integrations/mobile-app-build-guide.md` had never been committed. It
   is committed here with the §5.8 and §6.6 edits.

**Where the time went** (00:44 → 01:30, about 50 min): Part A 00:44–00:50 ·
build (server by me; front end, script and docs by two agents in
parallel) 00:50–01:03 · targeted tests, upgrades and the full suite
01:03–01:13 · verification pass and its fixes 01:08–01:24 · report and record
01:20–01:30.

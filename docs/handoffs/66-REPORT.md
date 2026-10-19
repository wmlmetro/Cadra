# Report — Handoff 66: the audit in the room

Branch `feat/the-audit-in-the-room`, from `dev` at `163d422` (Step 0
committed the instruction file and `CLAUDE.md`'s new *Speed* rule 9).
Module versions: `myservice_asset_register` 19.0.1.34.0 (seven new models,
the ledger backfill migration), `myservice_api` 19.0.3.37.0 (scopes, roles,
an exclusion pair, 29 routes). Evidence: `docs/handoffs/66-evidence/`.
**Not split**: the handoff offered 66a/66b at Step 0; all of it fitted.

## Needs the owner

1. **The PR merge** (the Builder's permission layer refuses `gh pr merge`).
2. **The deploy:** `upgrade-19` for
   `myservice_asset_register,myservice_api,myservice_workflow` on every
   tenant. Seven new tables, and every asset create now writes a ledger row,
   so a tenant that is not upgraded fails asset creation. The migration
   backfills the ledger and prints a count per tenant.
3. **People for the audit roles on NRS's production tenant.** *Audit
   Capturer* and *Audit Reviewer* are granted on the Users screen; the
   Asset Controller registers devices and issues code blocks. On the
   cluster, the demo personas gain the two audit people only when the
   demo-personas workflow is run again.
4. **NRS:** name, per campaign, which SAP office code each building or room
   answers to (GO-LIVE §35.1). Cadra's locations carry no office code, so a
   campaign's scope line is that mapping. Without it a room has no SAP
   slice and *in SAP, not found* is empty.
5. **Merge note (security, pre-existing):** a refused or previewed role
   grant left the refused role on the person until something else cleared
   Odoo's cache (§ Deviations 1). The fix is in this branch; tenants have
   carried the hole since handoff 42 (dry run) and 58 (exclusions). A
   restart of Odoo after the deploy clears any stale membership left behind.

## In plain words

An audit team can now walk a room with Cadra. The Asset Controller
registers a phone, binds it to one person, and gives that person a block of
asset codes. The capturer photographs each item and records one of three
things:

- **it is already on Cadra's register:** the reviewer's acceptance records
  it as verified in that room, in that condition, with the photo. If its
  label is gone, the reviewer's acceptance approves a reprint under the same
  code;
- **it is in SAP's register but not Cadra's:** accepted, it becomes a
  Cadra asset carrying SAP's number and capitalisation date and the code the
  phone printed. **Nothing is sent to SAP**, because SAP already has it;
- **it is in neither:** accepted, it is an exception. The Asset Controller
  either registers it as new, through the normal maker and checker, or
  voids it with a reason.

The capturer can never review their own captures: the model refuses it, a
campaign cannot list the same person on both sides, and nobody can be
granted both roles.

Every asset code now lives in one ledger, the one answer to "which codes
exist": codes from blocks, codes given at creation, and every existing
asset's code, recorded by the migration. A code is used once. Returning a
block voids what it did not use.

Closing a campaign produces the two lists the audit is for, per office:
what the team found that SAP does not have, and what SAP has that nobody
found. Both download as CSV.

Two things found on the way were worth more than the feature itself:

- **A refused role grant was quietly granting the role.** Fixed.
- **The new scope check on `/ai/identify` could be bypassed by replaying an
  idempotency key.** Fixed before it shipped.

## What was built

**§2 devices, codes, blocks.**

- `nrs.audit.device`: a name, a `DEV-…` code the phone sends in
  `X-Cadra-Device`, bound to one person.
  - Rebinding is refused while a block issued to the previous person is
    open.
  - It is not a credential: the person signs in as themselves (R4).
- `nrs.asset.code` is the ledger: `reserved → in_review → active | void`.
  It is written by every `nrs.asset.create`:
  - `active` if the asset is registered, `in_review` for a candidate;
  - activated at registration (`_gate_move`), voided at an IAD rejection;
  - a code once issued is never taken over.
- `nrs.audit.code.block`: 1–500 codes drawn from the asset-code sequence
  under an advisory lock. Returning a block voids its unused codes.

**§3 campaigns.**

- A name, dates and a scope: lines of {location, SAP office code}.
- The team: capturers and reviewers, never the same person.
- Progress counts and per-room counts.
- Close is refused while a capture waits, naming the count. Closing keeps
  the two lists as they stood (`closing_json`); an open campaign's lists
  are computed now and say `as_of: now`.

**§4 capture.** `POST /audit/photos` (61's checks, the same bytes from the
same person answered once), then `POST /audit/captures`:

- idempotent on a stored, unique `capture_id`, matched case-insensitively;
  a simultaneous double sync answers `409 sync_in_flight`, retryable;
- `captured_at` at most five working days back;
- every refusal in words, before anything is written;
- a duplicate (the same Cadra asset, SAP record or old tag) is held beside
  its twin.

Also: `GET /audit/captures/{capture_id}`, `GET /audit/campaigns/{id}/slice`
(the room's assets, or its office's SAP records, paged with 61's sync
rule), and `GET /ai/config` (the switch, model, cap left today, and the
label layout as data).

**§5 review.**

- Accept and return, and *Accept the room* (60's rules: N single acts,
  `dry_run`).
- On register: moved under a new exemption reason, `audit`, the movement
  row saying `approval`. Condition written, a `verified` event by the
  capturer, photos copied, the reprint by 61's rules.
- In SAP: a new asset at `registered`, `sap_code_source =
  audit_from_sap_mirror` (a new value nobody else may write), the label
  affixed by the capturer, and an `audit_capture` event saying why the
  receipt gates did not apply.
- In neither: `exception_state = open`, the code `in_review`.
- Register-new creates the asset at `tagged`, waiting on the Register
  Maker. Its gate event is fired by nobody, and Section 12 is checked (the
  Controller may complete serial, make and model). Void voids the code.

**Roles.**

- Two groups under one privilege, *Audit Team*, both grantable.
- Four scopes: `audit:read`, `audit:capture`, `audit:review`,
  `audit:manage`. The Asset Controller holds `manage`, the Auditor holds
  `read`.
- The ninth exclusion pair: capturer × reviewer.

**§6 the screens.**

- *Audit campaigns*: the lists with CSV.
- *Audit review*: photos side by side, the AI suggestion against what was
  confirmed, duplicates beside their twin, accept, return, accept the room.
- *Audit capture*: one desk-side screen, with the browser camera and
  *Identify*.
- *Audit exceptions*.
- *Devices and codes*.

**§0.**

- The duplicate flag is read once per page, not once per asset.
- A serial-basis link proposal is re-checked for a rival at approval.
- **The CHANGELOG duplication report 65 named does not exist** (one heading
  each for 63b and 64 at HEAD and in the eight commits before); nothing
  deduped. Report 65 was wrong there.

## The numbers

| | |
|---|---|
| Audit HTTP (`tests/test_the_audit.py`) | **11 of 11** gates off; with `test_asset_events_api.py` **96 of 96** gates on |
| In-registry | `TestTheAuditSendsNothing` 4 of 4; with the link, access-guard and gates-kept classes **0 failed of 51** |
| §8.6 no master for b | 0 dispatch rows for the audit's asset; the same stub target queued 1 master for a plain affix (the control) |
| Ledger backfill (8 tenants + `test19f`) | `test19` 23,405 of 23,405 (21,288 active, 2,111 in review, 6 void); `nrs19` 11,960 of 11,960; `jaizbankplc` 4,164; `cadra19` 1,335; `nrs` 1,272; `gtb19` 156; `lasg` 150; `gtb` 150; `test19f` 400 |
| Stale group cache | after a refused capturer + reviewer grant: 4 of 4 logins carried `audit:review` before the fix, 0 of 4 after |
| Browser | specs 46, 65, 66 **17 of 17** on `test19f`, gates off (spec 46 checks all 13 personas against every audit item: drawn ⇒ answered, hidden ⇒ 403) |
| Endpoint reference | 198 routes, 198 index rows (`test_endpoint_reference.py` 4 of 4) |
| Final local pytest (fresh `test19f`, template rebuilt, gates ON) | **1,531 passed, 0 failed, 10 skipped of 1,541** in 14 m 37 s |
| CI | 39318028299 on `06439a2`: 2 failed of 1,540 in each leg (the SPA scope maps, not yet pushed); 39319646680 cancelled by the next push; 39320416377 on `c0d52d3`: pytest passed both legs, the in-registry step red in both legs with its result beyond GitHub's truncated log. **Reproduced locally with CI's exact command on the same fresh `test19f`: 1 failed, 0 errors of 1,306** — `TestSapMirrorScope`'s pin on who reads SAP's mirror, which the two audit roles now do (decided, Deviations 9); fixed, 0 failed of 4. **CI 39325435784 on `0d52ffc` (the fix): green, both switch states** — pytest 1,525 passed, 16 skipped of 1,541 in each leg; the in-registry step passed in both (its result line is beyond GitHub's truncated log; locally, the same command on the same tenant gave 0 failed after the fix) |

## Deviations and findings

1. **A refused or previewed grant left the role behind (security,
   pre-existing).** Found by the screens subagent; I reproduced it and
   fixed it.
   - Odoo 19 caches a user's group ids (`res.users._get_group_ids`, an
     ormcache).
   - The access guard and the role exclusions refuse after the write
     (diff-then-raise, handoffs 42 and 58), and `POST /users/<id>/roles`'s
     dry run previews inside a savepoint. Both read membership, which fills
     the cache with the groups they then roll back.
   - A savepoint rollback does not reset the registry's cache. So every
     later `/auth/login` minted the refused role's scopes until another
     group write cleared it. The capturer persona held `audit:review` this
     way.
   - `access_guard.forget_group_memberships` now clears it before each
     refusal and after each preview. Pinned by
     `test_a_refused_or_previewed_grant_leaves_no_role_behind`.
2. **The ledger backfill differs from the handoff by one word.** The handoff
   said every existing code is `active`. A candidate's code is backfilled
   `in_review` and an IAD-rejected one `void`, because R2a says a code is
   active at registration.
3. **`/ai/identify` now takes `assets:write` OR `audit:capture`** (behaviour
   change, announced).
   - My first draft checked this in the route's body with `scopes=[]`. The
     verification pass found that OpenAPI then published both routes as
     needing no token, and that an idempotency replay ran before the body
     check.
   - `cadra_route` now has `scopes_any`, enforced by the decorator before
     the replay and published as bearer plus `x-cadra-scopes-any-of`.
4. **The verification pass** (a fresh agent, 10 findings). Fixed:
   - the scope gate (3 above);
   - upper-case UUIDs (iOS);
   - the double-sync race (`sync_in_flight`, retryable);
   - a returned duplicate's code now voided, never freed;
   - a code in a returned block voided on return;
   - a ledger row is never taken over;
   - Section 12 at register-new, and the false `captured → tagged` event
     corrected;
   - a held twin accepted refuses the other on any basis;
   - two context keys instead of one;
   - the residue script names audit captures;
   - CSV cells guarded against formulas;
   - a photo integrity failure answered 409 in the envelope;
   - `label` refused on outcomes b and c;
   - a clear sentence when a reprint is already pending.

   Left, with why:
   - **A verification of a `missing` asset leaves it `missing`.** Marking
     it found is its own act, with a reason (handoff 31).
   - **The no-office count is mirror-wide.** A record with no office
     belongs to no campaign.
5. **An audit reprint still needs the Tag-Issuing Unit.** Acceptance creates
   the reprint, but recording its print and its affix needs
   `tagging:write`, which the audit roles do not hold. Until the print is
   recorded, that number is refused at affix (61). This is said in the
   mobile map §10.4. The Architect may want the capturer to print it.
6. **The screens subagent added one route**, `GET /audit/people`
   (`audit:manage`): the two roles' active members. `GET /users` needs
   `admin`, so the Asset Controller could not bind a device or name a team
   without it.
7. **`nrs19`'s upgrade wrote its ledger** (11,960 codes, all active, from
   the codes it already holds), as every tenant's did. Nothing else was
   written there; ruling 1's read-only stands for data.
9. **The audit roles read SAP's mirror** (`sap_mirror:read`): the capturer
   matches an item to SAP's record in the room, the reviewer judges the
   match. `TestSapMirrorScope` pins the readers so that a new one is a
   decision; this is that decision, for the Architect to overrule.
8. **Order-dependent test, named again:**
   `test_every_bare_override_of_an_inherited_route_is_named` failed in an
   isolated in-registry run (as in reports 64 and 65); CI runs it in order.

### What `_order = 'asset_code desc'` now means (§2)

The order codes were **drawn**. That is creation order only for an asset
coded at creation: an asset registered from a block code drawn last week
sorts below everything created since.

Nothing user-facing changes. Every list in the app comes through the API,
which pages on `id`; `?sort=newest` is id-descending. The model order
reaches only the back-office list views (administrators only since handoff
45) and the back-office station's search. Left as it is.

## §9 — what does the mobile team need now that they didn't have yesterday?

`docs/integrations/mobile-ai-capture-endpoints.md` is rewritten. **All 24
rows are now *exists* (19) or *not needed* (5)**, with nothing left as
*comes later*. `/ai/signatures` is *not needed (R11)*, as are the model
manifest and download.

New since yesterday (§9 there):

- device registration and its header;
- code blocks;
- the photo sync and the capture route, idempotent on their own ids;
- `GET` a capture to confirm a sync;
- the room slice for offline;
- `/ai/config` with the label layout.

What they **still cannot build** (§10 there, ten items):

- **No push.** The phone polls `GET /audit/captures?mine=true`.
- **No route to void one spoiled code or return its own block.** The Asset
  Controller returns blocks.
- **No device self-enrolment.**
- **A reprint finished by the Tag-Issuing Unit**, not the audit roles (5
  above).
- **No SAP slice for records with no office.** This waits on SAP's location
  extract.
- **The photo goes up twice when identified.** An audit photo cannot be
  named by `photo_id` on `/ai/identify`.
- **The printer is theirs.**
- **No holiday calendar** in the five working days.
- **The capitalisation threshold** is still NRS's open question.
- **Sign-in on a Turnstile tenant** is still open.

## Time

Started 20:35 WAT; budget 4 h, stated at Step 0, with the split named.

- **Build** (server §0–§5, three subagents for §0, the screens and the
  docs), 20:37–21:28: about 50 min.
- **Tests** while building, 20:55–21:37; the final run started 21:38
  (amended below).
- **Verification pass**, 21:20–21:30; its fixes 21:30–21:37.
- **Report**, 21:40–21:50, written while the final suite ran.
- **CI's hidden in-registry failure**, 22:00–22:10 (reproduced locally,
  because GitHub's log of that step stops before its result); CI green
  22:28. No idle wait: the report was pushed marked *CI pending* at 22:00.

# Report — Handoff 57: the gates, tonight

**SCAFFOLDING. Handoff 58 replaces all of it.** *(2026-10-12: kept by handoff 58; see `docs/ADDENDUM-A-EVALUATION.md` §8.)* Branch
`feat/the-gates-tonight`, from `dev` at `c87c10c` (Step 0: the instruction
file, the addendum and its evaluation, committed and pushed on `dev`). Three
streams ran in parallel in three sessions on one working tree; Stream A (this
session) owned git and committed every stream's files.

| Commit | Stream | What |
|---|---|---|
| `43b271d` | A | the gate machine, routes, scopes, register filter, INT-06 move, tests |
| `93a6b3c` | C | the switch, five gate personas, the demo run sheet |
| `4691fc3` | B | the Candidates page, gate buttons, banner, spec 57 |
| `d57c0fb` | A | decisions, `CLAUDE.md` gotcha, register-filter probe, B's section |
| `3f4cbb7` | A | four findings of the verification pass, four guard tables |
| `5b12d4b` | A | six in-registry guard tables learn the new names |

## In plain words

A received unit is now a **candidate**, not an asset, on any tenant whose
switch is on. It passes seven people in order — Store submits it, an IAD
officer sights and verifies it (four checks and a photo), a different IAD
approver approves it, the Asset Controller requests its tag (which prints
with the asset code), the tagger affixes it through the existing dialog, a
Register Maker enters the SAP code and cost, a different Register Checker
approves — and only then is it in the register, and only then does SAP get
the asset master. Until then it appears in no list, count, report, export or
dashboard. One person can never do two of those steps on the same unit; the
screen says *"You received this unit on 7 Oct; a different person must verify
it."* With the switch off — every tenant except the demo tenant — nothing
anybody does changes.

## Stream A — the server

**Built.** `nrs.asset.register_state` (11 states, default `registered`);
`asset_gates.TRANSITIONS` — §2a's table, row for row — and `_fire_gate`, the
only writer (a direct write raises; pinned). Ten `POST
/api/v1/assets/<id>/gates/<action>` routes and `GET /api/v1/candidates`
(`waiting_on`, newest first). `register_state` + `gates {waiting_on,
state_since, available[{action, can_fire, refusal, reason_required}]}` on
every serialised asset, the no-two-gates rule applied to the caller. Every
transition writes an append-only `gate_fired` event (actor, from, to, gate,
action, reason, evidence as JSON); the history renders it. Six scopes, five
grantable roles each implying Asset User; Asset User and the Auditor gain
`candidates:read`. Endpoint reference §11.8 (C's) and §14, index 128 rows of
128 routes, CHANGELOG, census rows.

**The register filter — the route list (§6.4).** In ONE place:
`nrs.asset._search` adds `register_state = 'registered'` unless the domain
names the field, the context carries `cadra_candidates`, or `active_test` is
off. Measured on `test19` by `57-evidence/register_filter_probe.py` — every
route read, one candidate received with the switch on, every route read again
(`57-evidence/register-filter-probe-test19.txt`):

```
route                                              before         after          verdict
GET /assets (total_estimate)                       13893          13893          unchanged — hides candidates
GET /assets?category_id=1                          12715          12715          unchanged — hides candidates
GET /reports/asset-register?as_of=today            13893          13893          unchanged — hides candidates
GET /dashboard/kpis assets.total                   13893          13893          unchanged — hides candidates
GET /barcode/kpis total_assets                     13893          13893          unchanged — hides candidates
GET /assets/export data.total                      13893          13893          unchanged — hides candidates
GET /assets/export.csv X-Cadra-Truncated           100/13893      100/13893      unchanged — hides candidates
GET /asset-categories asset_count (category 1)     12715          12715          unchanged — hides candidates
GET /reports/depreciation totals.asset_count       13893          13893          unchanged — hides candidates
GET /assets?register_state=any                     13903          13904          moved, as it should
GET /candidates                                    10             11             moved, as it should
```

Also filtered by the same default, not probed: `/reports/disposals`,
`/barcode/untagged`, `/identity/employees/<id>/assets` and the employee
`asset_count`, the Redhubs export, the depreciation cron, the
verification-window cron. **Deliberately NOT filtered:** `GET
/assets/<id>` and every by-id action (`browse`, not a search), `GET
/assets/by-tag/<tag>` and the scan box (`_resolve_lookup`) — the tagger must
find the candidate — plus the import's de-duplication, the SAP-number
uniqueness constraint, the location and employee delete guards and the two
owner-run scripts (`cadra_candidates` passed explicitly). `?register_state=`
is accepted on `GET /assets` and `/candidates` only; the export, dashboards,
reports and map are registered-only with no override.

**INT-06.** Affixing a candidate queues nothing; the checker's approval
queues `asset.master.create` once, with the maker's cost, cost centre and
capitalisation date — in-registry `test_the_whole_chain_and_sap_hears_only
_at_the_end`. Switch off and every pre-57 record: unchanged
(`test_a_registered_asset_is_untouched_by_affix_rules`). **The outbox drive on
the deployed tenant is not done** — see "Not done".

**INT-03.** With the switch on `POST /assets` creates `captured` with no
label; off, the same response as before plus the two additive keys.
Vendra changes nothing.

## Tests — denominators

**In-registry `TestReceiptGates`** — 16 tests, every one a different person
per gate: part of the module run below — 16 of 16 (14 the chain, the rule
and the refusals; 2 added for the verification pass's D1 and D2).

**pytest, `test19`, switch OFF** (before the four guard tables were fixed):
`5 failed, 1319 passed, 7 skipped in 545.52s` — of 1,331. The five were the
four guard tables that did not yet know the new names (query-param
inventory, grantable roles, the history's recorded types — two tests — and
the sidebar count). Fixed in `3f4cbb7`; those files rerun: `143 passed` and
`85 passed`. Skips (7): 2 Turnstile, 3 partition-data-absent, 1 no
`workflow.config`, 1 untagged-serial (handoff 38).

**Final, after every fix (`5b12d4b`), switch OFF:**
`1324 passed, 7 skipped in 516.11s` — **0 failed, of 1,331**. Same seven
skips.

**pytest, `test19`, switch ON**: `91 failed, 1231 passed, 9 skipped in
551.60s` — of 1,331. **This red is the switch, not a defect**, and was
predicted by all three streams before the run: with gating on, `POST
/assets` makes a hidden, unlabelled candidate, and these suites create an
asset and then list it, look it up, affix or replace its label, or count it
— `test_tagging` (24), `test_tag_replacement` (22), `test_barcode` (15),
`test_audit_reports` (9), `test_assets` (6), `test_sap_reconciliation` (2),
`test_warranty` (2), `test_rejected_fields_are_refused` (2), and one each in
`test_assets_sort`, `test_idempotency`, plus the four guard tables above.
The two extra skips are the partition tests whose fixtures are now hidden.
Not re-run after the fixes: the four guard tables were the only failures
that were not the switch, and the switch-off run above is the one that
says the code is clean. `test19` is left with the switch ON (B's and C's
state).

**Module suites** (pytest first, then these, CI's order; `--workers=0`):


| Module | Result |
|---|---|
| `myservice_asset_register` | `0 failed, 0 error(s) of 482 tests` |
| `myservice_workflow` | `0 failed, 0 error(s) of 96 tests` |
| `myservice_api` | first `6 failed, 0 error(s) of 391` — six guard tables (grantable roles, the Auditor's pinned scopes, the history's kinds, two published-names classifications, the guarded reads); fixed in `5b12d4b`, then `0 failed, 0 error(s) of 391 tests` |

No `of 0 tests`, no `CRITICAL`. The `ERROR:` lines in the logs are Postgres
refusals the existing tests provoke on purpose (append-only, FK guards,
read-only probes).

**Spec 57** (Stream B): `10 passed, 0 failed, 0 skipped of 10` on `test19`,
switch on — the whole chain in the browser as the seven personas, the
register count read after every step (unchanged to step 6, +1 at the
checker), and the four refusals. Section and screenshots:
`57-evidence/b-section.md`, `57-evidence/b-test19/`.

## Verification pass (a fresh agent, not an author)

Confirmed and FIXED in `3f4cbb7`: (D1) an approved tag replacement on a
tagged candidate scrapped the label and minted nothing — the API answered
500; (D2) a repeat affix on a tagged candidate became an error instead of
handoff 39's idempotent answer; (D4) a `*` token was refused
`?register_state=any`; (P3) a candidate carrying the maker's typed SAP code
could post INT-09 lifecycle events before the master. Tests added for D1/D2.

Confirmed and LEFT, named:
- **D3** a no-two-gates refusal at AFFIX is a 400 `validation_failed` (the
  affix route's existing shape), not the gates' 409 `segregation_of_duties`;
  the sentence is the same.
- **D5** switch off is byte-for-byte except the additive `register_state` /
  `gates` on every asset and two null keys in the INT-06 payload
  (`capitalisation.cost_centre`, `sap_asset_number_entered`). In the
  CHANGELOG.
- **D6** `waiting_on` publishes `iad_approver` beside `iad` — §3 needs it
  ("waiting on IAD approver"); §2f's list did not have it.
- **INT-05** (`asset.tag.affixed`) still fires when a candidate's label is
  affixed — the label is on the box; deliberate, said.
- **P1** query, reject, resubmit and return are not gates (Addendum A §4's
  list) and leave no `gate` on their event, so they block nobody later.
- **P4** when SAP answers INT-06, a code the maker typed stays labelled
  *entered by hand*; SAP's different number would replace it silently.
- **P5** a candidate with a custodian is absent from the employee's asset
  list and clearance count — it is not on the register; 58 decides.
- **P8** the filter makes `register_state` load-bearing for EVERY asset
  search: a tenant not upgraded fails every list, not only the new column.
  The fan-out below is therefore mandatory before the restart, on the
  cluster too.

## Fan-out — every local tenant (Stream C ran it, serially)

The migration's own line per tenant, `N of M assets registered`:
`test19` 13,879 of 13,879 · `cadra19` 1,335 of 1,335 · `nrs19` 11,951 of
11,951 · `gtb19` 156 of 156 · `nrs` 1,272 of 1,272 · `lasg` 150 of 150 ·
`gtb` 150 of 150 · `jaizbankplc` 4,164 of 4,164 · `boot44` 231 of 231 — "0
filled" on every one: the field's default filled the column on add. After the
restart, `GET /assets` totals on five ungated tenants equal those counts.

## Deviations, with why

1. **The register filter is in the model's `_search`, not a route helper**
   (§2d said "whatever shared helper builds the asset domain"): 22 routes
   list or count assets and 2 share a helper. `docs/DECISIONS.md`.
2. **The label number is the asset code** — §2a's ruling, under an hour.
3. **The maker's SAP code is stored as entered by hand**, and the INT-06
   create is allowed past its "already has a number" check for that case
   only.
4. **`approve-registration` without a SAP code cannot be driven over HTTP**
   — `register` refuses an empty code first. Proved in-registry by clearing
   it under sudo (`test_approve_registration_needs_the_sap_code`).
5. **Chukwudi is not the IAD approver** (§3's example): he keeps his job;
   the IAD approver persona is C's. B's section.

## Not done — and why

- **The deployed drive (§4, §6.3)**: the owner ruled the demo tenant is the
  cluster's `staging`. Deploying is the owner's after the merge: merge the
  PR → `deploy-dev` → `upgrade-19` (all tenants) → the demo-personas
  workflow on `staging` → switch on (`PATCH /api/v1/settings/receipt-gate
  {"enabled": true}` as its administrator). The screenshots of each gate
  and the outbox-after-approval check on `staging` follow that, not this
  report.
- **Needs the owner:** the PR merge (the Builder's permission layer refuses
  `gh pr merge`), the deploy, four more Chrome profiles
  (`57-DEMO-SCRIPT.md`, top).

## Addendum — deployed to the cluster (2026-10-07, after the merge)

Stream C ran the deploy after the owner merged PR #115 (`b1d24a8`,
21:46:50Z) and approved the downtime. Stream A checked the three runs
against GitHub: all `success`, all on `b1d24a8`.

- **`deploy-dev`** run 37691794193 — backend and frontend images; pinned
  `cadra-odoo-19:dev-b1d24a8` (previously `dev-ee38cb0`).
- **`upgrade-19`** run 37692263722 — `staging, gtb, jaizbankplc, lasg`,
  the three modules, `scale_down=true`. The migration's line per tenant:
  `staging` 11,925 of 11,925 assets registered · `gtb` 150 of 150 ·
  `jaizbankplc` 150 of 150 · `lasg` 150 of 150 (0 filled on each).
  *"every tenant upgraded — rolling forward"*, *"deployment odoo-19
  successfully rolled out"* at 21:56:41Z. Odoo down 21:51:33–21:56:41Z
  (~5 min).
- **Probed without credentials:** `GET /api/v1/settings` and
  `/api/v1/candidates` answer a 401 JSON on all four hosts (the old backend
  answers an HTML 404); `staging`'s `/app/` bundle contains `/candidates`
  and `/settings/receipt-gate`.
- **`demo-personas`** run 37693023665 on `staging` (class `client`): 5
  created (the five gate roles), 1 updated (`storekeeper` → Asset
  Officer), 5 unchanged. Passwords decrypted on the owner's machine into
  `docs/api/.personas.cluster.staging`.

**Not done by the Builder — owner-blocked, and a handoff defect.** The
switch on `staging` and the deployed drive with screenshots. The cluster's
`/api/v1/auth/login` requires `turnstile_token` (400 *"`turnstile_token`
is required"*, the same wall as report 56 §5), so nothing scripted can sign
in: not the switch's PATCH, and not spec 57, whose personas sign in through
the API. Turning Turnstile off would weaken a control on live client sites
and needs another roll; not done. **The owner turns the gates on in the
browser as the administrator persona (Settings → Receipt gates — the
configuration record will name them), and the owner's rehearsal is the
deployed drive.** Spec 57's 10/10 on `test19` with the gates on is the
automated proof. Turnstile on the cluster was known from report 56 and was
not in a "Needs the owner" block — per `CLAUDE.md`, a defect in the handoff.

**Run sheet:** step 0.2 now says the switch reads *off* tonight and is
turned on once, at the rehearsal.

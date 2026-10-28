# Handoff 70 — report · the administrator can finish it

**Branch:** `feat/the-administrator-can-finish-it` · **PR:** [#135](https://github.com/wmlmetro/Cadra/pull/135) · **CI:** **green** — [run 40653336109](https://github.com/wmlmetro/Cadra/actions/runs/40653336109): `bootstrap-and-test` gates on ✓, gates off ✓, `image-addons-complete` ✓, `prod-compose-lint` ✓, `commit-messages` ✓

## Needs the owner

0. **GitHub Actions is working again** (it started nothing from 27 Oct
   18:20 UTC until 07:56 UTC today). This PR's CI is green; the local runs
   below were made while it was down.
1. **Merge the PR, then run `upgrade-19`.** Two new columns on
   `nrs.asset.event` and four on `nrs.audit.capture`:
   `target_dbs=staging,gtb,jaizbankplc,lasg`,
   `upgrade_modules=myservice_asset_register,myservice_api`,
   `scale_down=true`, `image=…cadra-odoo-19:dev-<merge sha>`.
2. **Turn the switch on where you want it, and only there.** It is off on
   every tenant, after the upgrade too. *Settings › Receipt gates ›
   Administrators may act at every step*, signed in as an administrator. On
   NRS's production tenant it stays off until NRS accepts in writing that an
   administrator may act alone (`docs/GO-LIVE.md` §36.1).
3. **`nrs19` locally**, when you choose (report 69, item 3): still at
   `19.0.1.35.0`, so its audit and gate screens answer `503` until upgraded.

## In plain words

Until now nobody could take a unit through the receipt gates alone, not even
an administrator: the rule *one person, one gate* refused the second act.
The same went for the audit: you could not capture in a campaign that did not
name you, review a campaign that did not name you, or review your own
capture.

Now each tenant has one switch, **off by default**. When it is on, an
**administrator** (a person signed in, holding the system-administrator role)
may do every one of those acts alone. Nobody else may: not an Asset Manager,
not an Asset Controller, and never a machine credential such as Vendra's,
even if somebody gave its user the administrator role. The switch lifts only
**who** may act. A unit still has to be in the right state, a label scanned
must still match, and a capture still needs its device, its code and its room.

Every act that went ahead only because of the switch is **marked where it is
recorded** and **listed** on a new page, *Audit › Administrator overrides*,
which the Auditor can read too. An act that broke no rule is not marked: the
first gate an administrator fires is an ordinary act. On the asset's history
the line reads *"Value for money approved …, by Oluwaseun Ajayi, as
administrator (they received this unit on 28 Oct)."* The buttons say it too:
**Approve (as administrator)**, **Accept (as administrator)**.

## What was built

- **The switch:** `cadra.admin_override` (raw SQL, absent = off), shown on
  `GET /settings`, set by `PATCH /settings/admin-override` (`admin` scope
  only; the Asset Manager's `settings:write` gets `403`; the source guard
  names it as its one exception, with the reason).
- **One helper:** `admin_overrides(env, user)`
  (`myservice_asset_register/models/admin_override.py`). It is true only for
  a **person's** token (`aud: frontend`, which only `/auth/login` stamps)
  that names that user, the user in `base.group_system`, and the switch on.
  Outside an API request it is false.
- **The gates and the SAP link (S1):**
  - `_assert_two_gates` returns the sentence it lifted, and the act's event
    stores it (`admin_override`, `override_of`, two new columns).
  - This covers the ten gate routes, the batches, the affix and the four SAP
    link acts.
  - The gates block and the SAP link rows say `as_admin`, and the
    *waiting on me* badge bars nothing.
- **The audit (S2–S4):** capture create and review (accept, return, batch)
  lift *not a capturer*, *your own capture* and *not a reviewer*. The
  capture records and publishes `captured_as_admin`, `reviewed_as_admin` and
  `override_of`.
- **The report:** `GET /reports/admin-overrides` (`settings:read`) and the
  page *Audit › Administrator overrides*: Lagos days, kind filter, newest
  first, paged, CSV, and an on/off line at the top.
- **The screens:**
  - "(as administrator)" on the gate buttons, Candidates batch buttons and
    SAP link buttons.
  - Every open campaign in Audit review, Audit capture and the station, for
    an administrator under the override.
  - With the switch off, nothing changes.
- **§8, checked, unchanged:**
  - Moves, custody and tag replacements: a system administrator may already
    approve anybody's request except their own.
  - A disposal approval has no two-person rule at all.

## The numbers

Local, `test19f` restored fresh before each full run, made while CI was
down; CI then ran both switch states green (run above). Evidence: `70-evidence/`.

| Run | Result |
|---|---|
| Full pytest, **gates on** (the state this change matters to) | **1,583 passed, 0 failed, 14 skipped of 1,597** (12 m 50 s) |
| Full pytest, gates off | 1,580 passed, 0 failed, 17 skipped of 1,597 (7 m 44 s): the 14 plus the three gate tests of the new file, which skip with the gates off; two skips name the local mail catcher down |
| `tests/test_the_administrator.py` (new) | 11 of 11 |
| In-registry, `myservice_asset_register` + `myservice_api` + `myservice_workflow` | 1 failed, 0 error(s) **of 1,193 tests**; the one was the body-route census not knowing the new PATCH, fixed; that class rerun 13 of 14, the 14th the local-only bare-override failure of report 69 (fails on `dev`'s code too) |
| `TestAdminOverride` (new) + `TestCaptureRefusal` | 0 failed of 10 |
| Front end | `tsc --noEmit` clean; `BASE_PATH=/app/ npm run build` clean |
| Browser, spec 70 (new) | 1 of 1, three runs |
| Browser, the screens touched (58, 60, 66, 67, 69, 70) | 15 passed, 0 failed (60 once on retry); 48's 4 skip by design (it has no plan for `test19f`) |
| Browser, 46 and 65 | pass on the second run; the first lost 3 tests to `page.goto` timeouts while the server answered everything in < 0.1 s |
| Browser, 57 | **flaky, and the same on `dev`'s front end**: a gate dialog's confirm button is "detached from the DOM" mid-click. The same 4-test subset, `dev`'s bundle against this server: 2 passed, 1 failed; this branch's: 2/1 and 3/1, a different dialog each time |

What the new tests prove:
- **The administrator alone:** they take one unit from *submit* to
  *registered*. Six acts are flagged; the first is not. The history and the
  report show them.
- **The switch off:** the second gate is refused, as before.
- **The suite's machine token (it holds `admin`):** still refused.
  In-registry, a machine token whose user is in `base.group_system`, and an
  Asset Manager, are both held to the rule.
- **The audit:**
  - A capture in a campaign that does not name them, and their own
    acceptance (a missing-label reprint included), are both flagged.
  - With the switch off, both are refused.
  - Non-administrators are still held to their campaigns.

## Deviations and questions

1. **Two of the handoff's test cases cannot be made over HTTP, so they are
   proved in-registry.** A machine credential whose user is in
   `base.group_system` can't be created through the API (handoff 42's
   guard). A non-administrator who holds two gate roles can't exist either:
   the role exclusions forbid it. The HTTP file proves the nearest real
   cases: the suite's own machine token, and capturers and reviewers held to
   their campaigns.
2. **Found by the verification pass, fixed, and beyond the handoff's text:**
   - **An administrator's own capture of an item whose label is missing was
     refused at acceptance.** The audit's reprint makes the capturer the one
     who asks for the reprint, and a tag replacement is never decided by
     the person who asked for it. Now, inside that one acceptance only, an
     administrator under the override may approve their own reprint. The
     general tag-replacement rule is unchanged (§8).
   - **The app had no way to give an administrator a device.** The picker
     on *Devices and codes* lists only Audit Capturers. `GET /audit/people`
     now also returns `administrators` while the switch is on, and the
     picker offers them.
3. **Question for the Architect:** `PATCH /settings/admin-override` takes
   any token holding `admin`, as the handoff says. That includes a machine
   credential, which may switch the override on even though it can never
   use it. Should the PATCH also require a person's token?
4. **`GET /settings` is `assets:read`, not "every signed-in caller"** (§3).
   The block is on the existing route and inherits its scope. Every role
   that uses the gates or the audit holds `assets:read`.
5. **`nrs19` was not upgraded** (report 69, item 3, still yours). The other
   six local tenants got one fan-out run at the end (`cadra19`, `gtb19`, `nrs`, `lasg`, `gtb`, `jaizbankplc`: all now at `19.0.1.39.0`, 0 errors).


## Time

Step 0 07:14 · build 07:14–07:50 (server; front end and docs by two agents) · tests 07:28–08:50 · verification pass 07:52–08:10 · report 08:40–09:00 · about 1 h 50 m of the 2 h budget.

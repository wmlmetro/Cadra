# Report — Handoff 56: the name and the hat

**Base: `dev` HEAD (`d1310a3`) IS the deployed commit — branched from it, nothing in between.**
Measured, not assumed: the cluster's `odoo-19` Deployment runs
`cadra-odoo-19:dev-latest`; `deploy-dev` built and pushed that tag from
`d1310a3` (run of 2026-10-05 22:00 UTC, success), and `upgrade-19` (2026-10-05
22:16 UTC, success, head `d1310a3`) upgraded every tenant and ended with
*"every tenant upgraded — rolling forward"* + *"deployment odoo-19
successfully rolled out"* at 22:21. `dev`'s `myservice_api` manifest at
`d1310a3` is `19.0.3.27.0`, same as the deployed image's. The only commit
`dev` carries beyond the deployed one is this handoff's own instruction file
(`8d308af`, Step 0, docs only). Branch: `fix/the-name-and-the-hat`.

## What was built

- **Server** (`6318f72`): `GET /auth/whoami` gains `roles` — the caller's
  **direct** roles, byte-equal to `/users/<id>`'s `roles_direct` (same
  vocabulary, same keys, same order), via the existing `_resolved_roles` /
  `_role_lists` helpers (lazy-imported; `v1_users` imports `cadra_route`
  from `v1`). OpenAPI response schema added, CHANGELOG one entry,
  `myservice_api` → `19.0.3.28.0`. Nothing else on the server.
- **App** (`7061e46`): `Topbar.tsx` draws the role under the name/login in
  the same small text: one role its name, two middle-dotted, 3+ as first
  two `+N`. No roles (old server included) draws nothing. `WhoAmI` gains
  `roles`, missing key → `[]`.

## Judgment calls (deviations, with why)

1. **"The same list" = `roles_direct`, not `roles_effective`.** The handoff
   said "the roles the user holds"; effective would caption every Asset
   Manager "Asset User · Asset Officer +1" — the opposite of telling
   personas apart. The pytest pins whoami == `roles_direct` exactly.
2. **The administrator shows "System Administrator", not "Administrator".**
   The server supplies the name from `PUBLISHED_ROLE_NAMES` (handoff 44 §3:
   one name per group, everywhere); a frontend special-case mapping
   `system` → "Administrator" would be a second name for the group the
   Users page calls "System Administrator". The screenshot shows the
   vocabulary's name.
3. **3+ roles: full list in the line's `title` tooltip, not a dropdown.**
   There is no dropdown: the bar has deliberately had no account menu since
   handoff 29 ("no longer carries a pointer cursor promising one").
   Inventing one was not the minimum.
4. **The "credential with no groups" leg is proved with a person, not a
   credential.** On `test19` no roleless credential can authenticate: the
   suite's own holds five vocabulary groups (its scopes are broad;
   `SCOPE_GROUPS` derives the groups), and the only other credential,
   `cadra_demo_personas`, is archived with no secret by design. The test
   creates a person with **no** roles (`POST /users`), reads the letter out
   of Mailpit, redeems a password, signs in, and asserts `roles == []` and
   `== roles_direct`; deactivated in `finally`.

## Verification

- **Pytest** `tests/test_whoami_roles.py`: **3 passed** — all six personas'
  whoami == their `/users/<id>` `roles_direct` (admin's `system` named
  "System Administrator"); the suite's credential agrees; the no-role
  account answers `[]`.
- **Browser, every persona on `test19`** (spec 56, 7 passed): drawn line
  asserted against the API's answer per persona, one screenshot each in
  `docs/handoffs/56-evidence/`, text read off the images: administrator
  *System Administrator · Asset Manager*, asset_manager *Asset Manager*,
  auditor *Auditor*, storekeeper *Asset User*, tag_unit *Tag-Issuing
  Unit*, tagger *Asset User · Tag-Issuing Unit*.
- `tsc --noEmit`: clean. Specs 41 + 45 + 46: **18 passed** (6.0m).
  Bundle rebuilt with `BASE_PATH=/app/` and served for the drive.
- **HTTP suite once**: **1314 passed, 9 skipped, 0 failed of 1323** —
  the nine are the documented `test19` categories, none new.

## Noted, left alone (§3)

- `test19`'s **storekeeper persona holds Asset User, not Asset Officer** —
  so the "Store Officer" demo persona's hat reads *Asset User*. A fact
  about the seed/tenant, not this change; if the demo wants the officer's
  hat, the persona needs the role.
- `test19`'s **administrator persona also holds Asset Manager directly** —
  its hat reads *System Administrator · Asset Manager*.

## Owner

The PR merge (as every handoff): the Builder's permission layer refuses
`gh pr merge`. Deploying this to the demo estate after merge is
`deploy-dev` (push, frontend) + `upgrade-19` (manifest bump) — owner-run.

## Deployed (addendum, 2026-10-06, owner-instructed)

Merged as `ee38cb0` (PR #114) and deployed to the cluster the same morning:

1. `deploy-dev` (push, 08:06–08:20 UTC, success) — images `dev-ee38cb0` +
   `dev-latest` built, frontend rolled.
2. `upgrade-19` (08:10–08:14 UTC, success; `upgrade_modules=myservice_api`,
   all four tenants, `scale_down=false` — code-only change on demo day):
   *staging, gtb, jaizbankplc, lasg* each "upgrade succeeded"
   (`19.0.3.28.0`), and the run printed *"successfully rolled out"* —
   **in 2 seconds, because it had rolled nothing.** Verified against the
   live API: `whoami` still answered without `roles`.
3. **Found: `upgrade-19`'s roll-forward is a no-op when `scale_down=false`
   and the image is the default.** The roll step re-applies the deployment
   manifest with `dev-latest` — the same mutable tag it already carries
   (`imagePullPolicy: IfNotPresent`) — so with no scale-to-zero there is no
   pod-template change, no restart, and no new pull; `kubectl rollout
   status` returns immediately and the step reports success while the pod
   serves yesterday's code. `scale_down=true` (the default) masks this by
   recreating the pod anyway. An instrument that reports success while
   measuring nothing — for the Architect; left unfixed (§3 freeze).
4. `deploy-dev` with `roll_odoo=true` (08:15–08:20 UTC, success) rolled the
   backend onto the SHA-pinned `dev-ee38cb0` — a real template change.
5. **Verified live:** all four tenants' `/api/v1/openapi.json` now publish
   `whoami`'s `roles` (staging's host is `staging.app.cadra.ng`). A full
   scripted sign-in on the cluster is blocked by Turnstile on `/auth/login`
   (by design), and the local `.creds.jaizbankplc` is the local replica's;
   the signed-in top bar was proved end to end on `test19` (§Verification).

The deployment is now pinned to `dev-ee38cb0` rather than `dev-latest`;
the next `upgrade-19` with a blank image moves it back to `dev-latest`,
which is the workflows' normal state.

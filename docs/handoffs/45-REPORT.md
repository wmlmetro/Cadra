# Handoff 45 — Report: the first five minutes

**Branch:** `fix/the-first-five-minutes` — **stacked on 44's branch** (`fix/the-credential-that-is-already-root`, PR #102, not yet merged), because both touch the access record, the users routes and the same docs · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/45-evidence/` — `shots/` (both tenants' journeys, every dead link, the reset, the label print, the back office refused and an administrator's back office), `shots/<tenant>-requests.txt` (every path a non-administrator's session requested), `letters-plain-text.txt`, the suites, the upgrade fan-out and `boot44-branding.txt`.

## In plain words, first

An officer who is invited to Cadra now never sees Odoo.

**The letter.** It is the organisation's own letter, and its link opens a page in the app, branded the same as the sign-in page the person lands on next. The page says whose account it is, asks for a password twice, and signs the person straight in.

**Dead links.** If the link can't be used, the page says why in one sentence and offers a way forward. It tells apart a link that has expired, one already used, one cancelled (by a newer letter, or because the account was switched off), and one that was never a link at all. *Expired* and *never valid* look the same to Odoo's own check; the app reads the date sealed inside the link to tell them apart.

**Letters already sent.** Letters sent yesterday carry the old Odoo link. That link now forwards to the new page with the same token, so nobody is stranded and nobody gets a second letter.

**Forgot password?** The sign-in page has the link now. It sends a reset letter and answers with the same sentence whether or not the account exists, so it can't be used to find out who has one. Odoo's own reset form said *"No account found"*; that form is no longer reachable.

**The back office.** It is now for system administrators only. Anybody else who reaches it — by bookmark, by guess, through Odoo's login page or through the old letter link — is sent to the app.

The first version of that rule closed only the doors a person walks through. The verification pass then got an Odoo session as an ordinary officer by two other routes: Odoo's programmatic sign-in, and its two-factor step. With that session it read the database, and opened the portal page.

So the rule now sits one level down as well: no page that needs an Odoo session will serve one to anybody who isn't an administrator.

None of that touches the app. I drove the app as an ordinary officer, including printing a barcode label, and recorded every request it made. Apart from its own pages and API, it asked Odoo for exactly one thing: the QR-code image printed on the label, which is public. Printing worked. An administrator still gets the back office normally.

**Odoo's own email.** Setting a password used to make Odoo send its own *"Security Update: Password Changed"* email, branded Odoo with an Odoo link, a second after the person did it themselves. That email no longer follows the password a letter asked for. Every other password change still sends it.

**Approvals and access.**

- A request waiting on somebody who can no longer sign in now says so on the Approvals screen.
- The person who raised it, or an administrator, can re-point it at somebody else. That re-pointing is recorded, and nobody can alter it: who did it, when, from whom to whom, and why.
- Switching an account off, or back on, now appears in the access-changes report an auditor reads. Before, it was visible only in Odoo's own bookkeeping.

**Two things that need somebody else.**

- **The plain-text part of letters is built but switched off on the hosted service.** The mail relay belongs to another team, and nobody here knows the name of the field it would accept. Sending an unknown field could stop all mail. So it waits on one setting, to be filled in once they confirm.
- **The new "sender address" setting is in place, but the relay ignores it** and sends as its own account. Locally, over ordinary mail, it works: the Jaiz letter came from the Jaiz address.

**The one finding that matters most for go-live.** A *Forgot password?* letter's link uses the address the server has recorded for itself (`web.base.url`). It does not use the address in the browser; that was handoff 43's deliberate choice, so a stranger cannot steer somebody else's link. On a fresh server nobody has signed into as an administrator, that recorded address is still `http://localhost:8069`. The very first reset letter in this handoff pointed there. Before anybody is told to use *Forgot password?* on a real tenant, that setting must be checked.

**NRS's 87 assets.** I re-counted on the local copy of the NRS register: **87 of the 6,646 assets with a holder are held by 59 people who have left** (of 207 who have left, of 11,386 staff). None of those assets is flagged for retrieval, and SAP still calls every one of those 59 people *active*. I could not re-count on the live system — my permissions don't reach it — so that is for the owner, before the number is quoted.

## A · What was built

| | where |
|---|---|
| The token routes: `POST /api/v1/auth/password-token/inspect`, `/redeem`, `/auth/password-reset` | `myservice_api/controllers/v1_signup.py` |
| The letter's link → the app's page; a portal partner's link left on core's path | `models/invitation.py` (`app_password_path`) |
| The back-office door: web client, `/web/login` for non-administrators, both letter pages on GET and POST | `controllers/backoffice.py` |
| No non-administrator Odoo session on any `auth='user'` route; anonymous `auth='user'` pages → the app | `models/backoffice_session.py` |
| Odoo's "Password Changed" mail suppressed on the letter's path only | `models/invitation.py` (`PASSWORD_FROM_LETTER`) |
| The pages: `SetPassword` (both kinds), `ForgotPassword`, the *Forgot password?* link, a shared `AuthShell`, Turnstile moved into `useTurnstile` and shared with sign-in | `Frontend/…/src/pages/`, `components/auth/`, `lib/useTurnstile.ts`, `App.tsx` (`PUBLIC_PATHS`) |
| Re-nomination: `action_renominate`, the append-only `nrs.asset.change.request.renomination`, `POST /approvals/<id>/renominate`, `approver.active`, the Approvals screen | `myservice_asset_register/models/`, `controllers/v1_approvals.py`, `Approvals.tsx` (subagent) |
| `deactivated` / `reactivated` on the access record and the report, causal order within a second | `access_change.py`, `access_recorder.py`, `audit_access.py`, `v1_audit.py`, `AccessChanges.tsx` (subagent; ordering fix mine) |
| `sender_email` on branding; the relay's text field behind `cadra.email_relay_text_field` | `v1_settings.py`, `Branding.tsx`, `myservice_email_relay` (subagent) |

**Password rules — discovered.**

- `auth_password_policy` is installed on **0 of 9** local databases (8 tenants plus `boot44`). Odoo 19's `signup()` stores whatever it is given, the empty string included.
- So `/redeem` refuses exactly three things: an empty or all-space password, a confirmation that does not match, and — should the policy module ever be installed — anything below its `minlength`.
- `/inspect` publishes those rules, and the page shows them before anybody types.
- **Whether Cadra should set a minimum of its own is a decision, not a discovery** — `GO-LIVE.md` §22.2.

**What happens to invitations already sent (§2.1.3).** They are redirected, not re-sent.

- Every pre-45 letter carries `/web/signup?…&token=…`. A GET there answers `303 /app/accept-invite?token=<same>`.
- The token is core's, and `inspect` and `redeem` accept it.
- Proved by `tests/test_password_tokens.py::test_the_old_letter_link_lands_on_the_app_with_the_same_token`.

## B · Verification, as the handoff lists it

- **The whole journey on two differently-branded tenants.** The `boot44` run is in `shots/boot44-1…4`; tenant 2 is the `test19` row below.

  | | tenant 1 — `boot44` (Jaiz) | tenant 2 — `test19` (NRS) |
  |---|---|---|
  | brand | Jaiz, set through `PATCH /settings/branding` (`boot44-branding.txt`) | NRS |
  | result | `5 passed **of 5**, one run (`playwright-test19.txt`)` | `5 passed **of 5**, one run (`playwright-test19.txt`)` |

  The spec records every request on the tenant's host during the journey and asserts that **none is under `/web` or `/odoo`**. It passed, so Odoo did not appear once.
- **Each token failure as the page renders it** (`shots/*-5…8`): used, cancelled (invited, then deactivated), never valid, and expired. The expired token was minted by core's `hash_sign` with a past expiry.
- **The reset from the app, through to a changed password** (`shots/*-9, 10`). Afterwards the old password answers `401` and the new one `200`.
- **As a non-administrator, every back-office path redirects and the app works, label printing included** (`shots/*-11, 12`, `*-requests.txt`).
  - The officer browsed assets, approvals and the barcode station, scanned a tagged asset and pressed *Print label*.
  - The label frame called `print()` (stubbed, counted), and its QR answered `200 image/png`.
  - Every path requested: **46 distinct, 1 outside `/app` and `/api/v1` — `/report/barcode`**.
  - Then `/odoo`, `/web` and `/odoo/action-…` each landed on `/app/`.
  - Signing in on Odoo's own `/web/login` sent the officer to `/app/`, and a following `/odoo` landed there too.
- **A system administrator still reaches the back office** (`shots/*-13`): `/web/login` → `/odoo`, navbar rendered.
- **A received message with the plain-text part present, read with HTML disabled** (`letters-plain-text.txt`).
  - Locally, the NRS invitation, the NRS reset and the Jaiz invitation each carry a full text part with the link written out.
  - **On the cluster this is NOT done.** The relay's field name is unknown; see *Needs the owner*.
- **The approver-inactive flag on a real stranded request, a re-nomination, and the record read back.** `tests/test_approvals_renomination.py` (HTTP) and `myservice_asset_register/tests/test_renomination.py` (32 in-registry):
  - an approver is deactivated;
  - the queue row says `approver.active: false`;
  - the requester re-points the request;
  - the row reads back from, to, by, at and why;
  - the request is approved by the new approver.
- **A deactivation and a reactivation in the access-changes report**:
  - over HTTP, `tests/test_access_record_deactivation.py`;
  - in-registry, 14 tests in `myservice_api/tests/test_access_record_account_state.py`, including a back-office Archive naming the actor.

## C · The verification pass, and what it changed

A fresh agent reviewed the finished diff. Confirmed, and fixed:

1. **`POST /web/reset_password` still served Odoo's form**, which told a stranger *"No account found for this login"*. Both letter pages now redirect on POST as well.
2. **A non-administrator could still hold an Odoo session**, through `/web/session/authenticate` (JSON-RPC) and the two-factor step, and use it on `/web/dataset/call_kw`, `/web/tests` and `/my`. This is what produced `models/backoffice_session.py`. Proved in-registry: the JSON-RPC sign-in answers, and the ORM call that follows answers *Session expired* with the session gone. An administrator's session still works.
3. **`organisation` was always `false` on `/inspect`.** Under `auth='none'` there is no company in the environment, so the page's subtitle was blank. It now reads the tenant's company.
4. **The email fallback in *Forgot password?* treated `%` and `_` as patterns.** It now uses core's own escaped `_get_email_domain`, and a test proves that `%@…` gets the same answer as nothing.
5. **`DECISIONS.md` lacked the renomination and `sent_by` rulings.** Added.

Plausible, and acted on:

- **A portal partner's token** (core's "grant portal access") would have been rewritten to the app's page, and redeeming it raised a 500. Such links now keep core's path, and the state reads `invalid`.
- **The *redeemed* sentence** now also covers "you have signed in since it was sent", which is what the state means.
- **A partner with more than one user** now takes the active one first.
- **The membership coverage boundary** no longer counts deactivation rows.
- **The OpenAPI text** now names the real re-point rule (`_is_admin()`).
- **The same-answer test** now proves the matching half too.

Left, and why:

- **The timing difference on *Forgot password?*** — an unknown login answers sooner than a real one — goes in `GO-LIVE.md` §22.2.
- **Opening a link signs out whoever was signed in on that browser.** Kept: the alternative leaks their cached data to the new person.

## D · What else the drive found

1. **`web.base.url` decides an anonymous reset link's host, and on a fresh tenant it is `http://localhost:8069`.**
   - `boot44`'s first reset letter pointed there; the page loaded on another host and answered 404.
   - Core rewrites it when an administrator signs into the back office, and that is why the spec now signs one in first.
   - On `test19` it reads `http://test19.localhost` without the port (`letters-plain-text.txt`, the reset letter).
   - Handoff 43's rule — an anonymous request must not choose the host — is right. So the remedy is a correct, frozen `web.base.url` per tenant. **Owner.**
2. **Approval notifications fail whenever the actor has no email address.**
   - *"You must either provide a sender address explicitly…"*, logged on every `/move` the suite's credential raised.
   - Odoo's chatter mail takes its sender from the acting user, and `mail.default.from` is unset on 8 of 8 local tenants.
   - It has been happening since handoff 35. Not fixed here.
3. **A brand module cannot be installed after bootstrap.** `cadra_brand_jaiz` on `boot44` hit `duplicate key … ir_config_parameter_key_uniq (cadra.brand_short_name)`. Branding through the API works.
4. **`test19` crossed the record cap: 103 accounts, against 100 for an API credential.**
   - A person created now is always the one a credential can't see.
   - Four HTTP tests were taught to read the truncation announcement, or to act on a visible older fixture: two in `test_access_record_deactivation.py`, `test_user_lifecycle.py`'s actor test and `test_users.py`'s role-filter test. `test_audit_logs.py`'s two walks are a fifth and sixth.
   - None of them was made weaker. Each asserts the cap's announcement exactly where it used to assert the whole.
5. **Within one second the report put `deactivated` before the `reactivated` that preceded it**, because it ordered by event name. Ordered by the record's id now. Found by the subagent's own test.
6. **Odoo's "Security Update: Password Changed" mail** was the fourth Odoo-branded letter, landing in the middle of the journey. Suppressed on the letter's path (§A).
7. **`test19`'s login page had lost its script bundle.** The browser spec's first run on `test19` could not find Odoo's login form: `/web/assets/…/web.assets_frontend_minimal.min.js` answered 500 with `FileNotFoundError` on the filestore — 1 of 67 bundle files was gone, almost certainly removed by the in-registry runs' *"filestore gc"*. The 67 bundle records were dropped so Odoo rebuilt them; the form came back. The website's logo file is missing too (cosmetic, not repaired). Environmental, and now in `docs/ENVIRONMENT-FACTS.md`.
8. **The Jaiz letter's plain-text part starts with "Image [4]"**, the logo's alt text. Cosmetic, from 43's template. Not fixed.

## E · Deviations

- **Stacked on 44.** It touches the same files (`access_change.py`, `audit_access.py`, `v1_users.py`'s neighbours, every doc), and 44 is not merged yet.
- **The deactivation event has no "invitation cancelled" sibling.** Searched: cancelling an invitation is not a separate act in this product; it happens inside the same `write`. The `deactivated` row is its record.
- **H.3 is not done on the cluster.** It is built and switched off, for the reason in plain words above. The handoff asked for it to be proved on a received message: done locally, owner-blocked on the cluster.
- **The back-office barcode station is now an administrator's tool.** Its two in-registry test files run as an administrator, and a refusal test was added for a non-administrator. Consequence of the ruling, named here.
- **Administrators lose the deep `redirect=` back into the back office** after a session expires: anonymous `auth='user'` pages now go to the app. They sign in at `/web/login`.

## F · Suites, with denominators

| suite | tenant | result |
|---|---|---|
| HTTP, final code | `test19` | **1,228 passed, 0 failed, 10 skipped, of 1,238** (`pytest-test19.txt`) — `test19`'s standing ten |
| HTTP, the run before (one cap failure, since fixed) | `test19` | 1,227 passed, 1 failed, 10 skipped **of 1,238** (`pytest-test19-run2-one-cap-failure.txt`) |
| HTTP, a run the MACHINE SLEPT through — not a result | `test19` | 339 failed, 151 errors: the laptop hibernated 00:42→07:37 mid-run and the suite's one-hour token expired (`JWT rejected (Token expired)` ×525 in the server log; `pmset` shows the sleep). Kept as `pytest-test19-run3-machine-slept.txt`; the run above was taken after |
| `tests/test_users.py` after that fix | `test19` | 21 passed **of 21** |
| in-registry `myservice_api` (`--workers=0`) | `test19` | 0 failed, 0 error(s) **of 353**, 0 `CRITICAL` |
| in-registry `myservice_asset_register` | `test19` | 0 failed, 0 error(s) **of 479**, 0 `CRITICAL` |
| in-registry `myservice_email_relay` | `test19` | 0 failed, 0 error(s) **of 26**, 0 `CRITICAL` |
| in-registry `myservice_barcode_station` | `test19` | 0 failed, 0 error(s) **of 20**, 0 `CRITICAL` |
| `tests/test_source_guards.py` | — | 218 passed **of 218** |
| Playwright `45-…`, `boot44` (Jaiz) | `boot44` | 5 passed **of 5**, one run (`playwright-boot44.txt`) |
| Playwright `45-…`, `test19` (NRS) | `test19` | 5 passed **of 5**, one run (`playwright-test19.txt`) |
| upgrade fan-out, 3 modules | 8 tenants + `boot44` | 9 of 9 exit 0, 0 `ERROR`, the new table present on 9 of 9 (`upgrade-fanout.txt`) |

## Needs the owner

1. **Merge PR #102 (handoff 44) first, then this PR.** It is stacked.
2. **On each cluster tenant, read and fix `web.base.url` before anybody is told to use *Forgot password?*.** Read-only check: `select value from ir_config_parameter where key in ('web.base.url','web.base.url.freeze')`. It must be the tenant's public `https://…` address. Set `web.base.url.freeze = True` so an administrator signing in elsewhere cannot move it.
3. **Ask the relay's operator two questions:** whether it accepts a plain-text field, and under what name; and whether it accepts a From. Then set `cadra.email_relay_text_field` per tenant. Until then, letters on the cluster have no plain-text part.
4. **Re-count NRS's 87 on the live tenant** before it is quoted. The query is the one in `GO-LIVE.md` §22.2's last item; my permission layer refuses reads of the cluster's databases.
5. **Decide whether Cadra sets a password minimum** (Architect). Odoo sets none here.
6. **`upgrade-19` with a pinned image** after merging: `myservice_api` 19.0.3.18.0, `myservice_asset_register` 19.0.1.21.0 (a new table) and `myservice_email_relay` 19.0.1.2.0.
7. **Drop `boot44`** when convenient (44's scratch tenant, used here as the second brand).

## Commits

- `5e88db6` feat: the first five minutes — the letter opens the app, the back office is for administrators, a stranded approval is re-pointed, a deactivation is on the record
- `7ed48bd` docs: report 45
- this commit: the commit list
- PR: https://github.com/wmlmetro/Cadra/pull/103 (stacked on #102)

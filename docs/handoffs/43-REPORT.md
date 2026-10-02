# Handoff 43 — Report: the person, and the door

**Branch:** `fix/the-person-and-the-door` · **Base:** `dev` at `08bfab5` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/43-evidence/` — four screen screenshots from the browser spec, two inbox screenshots of the NRS letter (HTML and text views), one of the Jaiz letter, and `drive-transcript.txt`.

## In plain words, first

NRS can now bring their own people in, and take them out again, without a
developer.

**The door.** Before anything else the handoff asked whether a stranger
could create an account on the public sign-up page. They could not — the
page answers "not found" on every cluster host and every local tenant, and
the login page shows no sign-up link. But the reason was an accident, not a
decision: the setting everybody looks at said *free sign-up* on all eight
tenants and was simply never consulted, because the website module quietly
substitutes its own setting, whose default is *invitation only*. One click
on the Settings screen would have opened the door. It is now shut in code,
on the owner's ruling, and no setting can open it; the two settings that
the screen reads were also set to tell the truth. No account was ever made
through it: the thing shutting it has existed since the first day of every
database.

**The person.** An administrator types a name, an email address and the
roles the person starts with. The account is created and a letter goes out
— from the organisation, not from Odoo: the organisation's name and colour,
its logo where it has one, one sentence saying what this is, a button and
the same link written out in full, how long it is valid, and nothing else.
The person opens the link, chooses a password, and signs in holding exactly
the roles they were given. If the letter went to spam, there is a *Re-send*
button. If the letter cannot be sent at all, the account is not created and
the screen says why — nobody is left existing and uninformed. Creating a
person with roles is the same act as granting roles, so the rule from the
last handoff applies untouched: asking for a role the API may not grant is
refused by the register itself, and nothing is created.

**Taking access away.** *Deactivate* stops the person signing in, stops
any session they still have open on their next click (until today a
deactivated person kept the app for up to an hour), and cancels any unused
invitation. It deletes nothing — their roles, their records, the assets in
their custody all stay. *Reactivate* gives it back. Three things are
refused in words: deactivating yourself, deactivating the account behind an
integration's credential (that would break the integration silently), and
deactivating the last administrator on the tenant.

**Received, for real.** A local mail catcher stood in for the inbox. Two
letters are in the evidence: one from *Nigeria Revenue Service* and one
from *Jaiz Bank Plc*, from the same code on the same tenant with its brand
switched — the right name, the right colour, the Jaiz logo on one and a
plain wordmark on the other, the word NRS nowhere in the Jaiz letter, the
word Odoo nowhere in either. The link in each pointed at the host the
request came in on, and following it set a password and signed in. **What
this machine cannot do is reach a real inbox through the cluster's mail
relay; that is the owner's step after the merge.**

**What the measurements say.** Deactivating somebody who is the named
approver on a pending request leaves that request waiting on a person who
cannot sign in, and nothing on the queue says so; only another eligible
approver can rescue it, and the request cannot be re-pointed. Naming such a
person in the first place is now refused — the one-line fix the handoff
allowed. And deactivating a custodian touches nothing about custody, which
turns out to be the right shape of answer for the wrong reason: on the real
register custody is held by *employee records*, almost none of which have a
login (1 of 11,386 on the NRS extract), and the clearance screen that would
show it is still a mock. Both are written up for a ruling, not built.

**Two corrections to earlier claims.** The sign-up template on Odoo 19 is
the *portal* user, not the internal default user report 41 named — a
self-made account would have been invisible to the user list and held no
scope. And "`ACCESS_CHANGE_SKIP_KEY` is read and set nowhere" (report 42) is
half right: it is read in three places and set in none.

---

## A · The door — §0

### A.1 Is it reachable? No, on every host — measured

Anonymous `curl`, no cookies, no token (transcript in
`43-evidence/drive-transcript.txt`):

| Host | `/web/signup` | `/web/login` | `/web/reset_password` |
|---|---|---|---|
| `staging.app.cadra.ng` | **404** | 200 | 200 |
| `jaizbankplc.cadra.ng` | **404** | 200 | 200 |
| `lasg.cadra.ng` | **404** | 200 | 200 |
| `gtb.cadra.ng` | **404** | 200 | 200 |
| `test19`, `nrs19`, `jaizbankplc` (local) | **404** | — | 200 |

The login page HTML on `staging.app.cadra.ng` and on `test19` contains
`reset_password` and no `signup` — the *"Don't have an account?"* link is
rendered only when `signup_enabled` is true
(`auth_signup/views/auth_signup_login_templates.xml:3-10`).

### A.2 Why — the parameter was never read

`auth_signup.invitation_scope = b2c` on **8 of 8** local tenants (report 41
was right about the row). The route decides on
`request.env['res.users']._get_signup_invitation_scope() == 'b2c'`
(`auth_signup/controllers/main.py:132`), and that method is overridden by
the `website` module:

```python
# website/models/res_users.py:66-68
def _get_signup_invitation_scope(self):
    current_website = self.env['website'].sudo().get_current_website()
    return current_website.auth_signup_uninvited or super()._get_signup_invitation_scope()
```

with `website.auth_signup_uninvited` a Selection defaulting to `'b2b'`
(`website/models/website.py:213-216`). `website` is installed on 8 of 8
tenants and its one row says `b2b` on 8 of 8. So the parameter's `b2c` has
never once decided anything, the door was shut by a default nobody chose,
and the Settings toggle (*Settings › Customer Account*) edits the WEBSITE
field — one click would have opened free sign-up on any tenant.

### A.3 What a self-made account would hold

On 19 `_create_user_from_template` copies the user in
`base.template_portal_user_id` (`auth_signup/models/res_users.py:111-129`):
`portaltemplate`, `active False`, `group_ids = [base.group_portal]`
(`base/security/base_groups.xml:98-108`). A share user: outside
`/api/v1/users` by domain (`share = False`), holding no `GROUP_SCOPES`
group and therefore no scope, and — had it come through an API create —
refused by handoff 42's guard, which allows only `_default_groups()` ∪ the
four. **`base.default_user`, which report 41 and GO-LIVE §18.2 named, does
not exist on 19**; §18.2 is corrected in place.

### A.4 Does one exist? No

No partner holds an outstanding sign-up token on any of the 8 tenants —
`res_partner.signup_type IS NOT NULL` is **0 of 1,221** (`cadra19`), **0 of
11,397** (`nrs19`), **0 of 73** (`gtb19`), **0 of 1,219** (`nrs`), **0 of
72** (`lasg`), **0 of 72** (`gtb`), **0 of 80** (`jaizbankplc`); `test19`
shows 1 of 146, this handoff's own fixture. The column is cleared when a
token is consumed, so this only says none is outstanding; the stronger
fact is that share users beyond `public` and `portaltemplate` — what a
self-made account would be (A.3) — are **0 of 6 / 11 / 12 / 52 / 5 / 12 /
12 / 19** users on the eight. The stronger fact: the `website` row — the thing that shuts
the door — was created on the same day as each database and as its first
user (`test19` 2026-08-04, `nrs19` 08-06, `jaizbankplc` / `lasg` / `gtb`
08-18). There was no day on which the door was open.

### A.5 The ruling, landed

`res.users._get_signup_invitation_scope` returns `b2b` as a constant
(`myservice_api/models/invitation.py`, `SIGNUP_SCOPE`). No row decides it;
a token in the URL (the letter's link) still renders the page. The
migration `19.0.3.17.0/post-migrate.py` sets both rows to `b2b` so the
Settings screen stops saying *Free sign up* about a shut door — on `test19`
it changed 1 parameter row and 0 website rows. `test_i_the_door_is_shut_whatever_the_rows_say`
forces both rows to `b2c` and asserts the method answers `b2b` and the
route 404s.

---

## B · What was built — §1 · `myservice_api` 19.0.3.17.1

### B.1 The model layer — `myservice_api/models/invitation.py`

- `res.users._get_signup_invitation_scope` → `b2b` (A.5).
- `res.users._action_reset_password(signup_type)` **overridden wholesale.**
  It is the one method every path to an invitation or a reset ends in: the
  user form's *Send reset instructions*, `res.users.create` (which invites
  by itself unless `no_reset_password`), `/web/reset_password`, and our
  route. Same contract as core — `install_mode`/`import_file` early return,
  the archived refused, the address-less refused, `signup_prepare` on the
  partner, one mail per user, the same `email_values`, the same client
  action returned — with Cadra's two templates instead of Odoo's, the
  brand resolved at send time, and three stamps written on a `signup` send
  (`cadra_invitation_sent_at`, `_sent_by_id`, `_sends`). Core's portal
  branch (`portal_set_password_email`) is dropped: one letter for every
  person. The From follows core's reset path — the company's address, the
  sender's, the recipient's own — so a tenant without a company address
  still sends (D.1 and F.1).
- `res.partner._get_signup_url_for_action` **puts the link on the request's
  host when the caller is authenticated** (an API token or a back-office
  session): asks core for the relative URL (`relative_url=True`) and joins
  it to `request.httprequest.url_root`; for an anonymous request and with
  no request bound it joins to `partner.get_base_url()` exactly as core did
  (F.4 says why anonymous is excluded). Why: core's base is
  `web.base.url`, which any system-administrator login rewrites from
  whatever host they used (`base/models/res_users.py:784-811`), and which
  on this machine lacked its port on 8 of 8 tenants because the dev proxy
  forwarded `Host $host` (fixed to `$http_host`, `config/nginx.dev.conf`).
- `_cadra_invitation()` → the row's `invitation` block, five states derived
  from the stamps and the partner's live `signup_type`.

### B.2 The letters — `myservice_api/data/mail_templates.xml`

Two `mail.template` records (`mail_template_invitation`,
`mail_template_password_reset`), QWeb bodies, **not** `noupdate` (an upgrade
keeps them current; a back-office edit is overwritten, said in the file).
Everything tenant-specific arrives in `ctx['cadra_letter']` from Python:
`organisation` (`res.company.name`, falling back to `cadra.brand_short_name`
when the company is still *My Company*), `primary` / `primary_dark`
(`cadra.brand_primary*`), `logo_url` (`/api/v1/brand/logo` on the request
host when `cadra.brand_logo` is set, else none → a wordmark), `link`,
`validity_days`/`hours`, `sender_name`. The template names no client and
no host. The six points of §1b and where each lives are in the file's
header comment.

### B.3 The routes — `myservice_api/controllers/v1_users.py`

| Route | Body | Answers | Refusals |
|---|---|---|---|
| `POST /api/v1/users` | `name`, `email`, `roles[]`, `send_invitation` | 201, the user row | 400 stray key / bad value; **403 the model's sentence, nothing created**; 409 address held (`details.user_id`, `active`); **500 `server_misconfigured` letter not sent (no mail server, relay refused), nothing created** |
| `POST /users/<id>/invite` | none | 200, the row | 400 credential / no email; 409 deactivated / already signed in; 500 letter not sent, nothing changed |
| `POST /users/<id>/deactivate` | none | 200, the row | 403 own account; 400 credential's user; 409 already inactive / last active administrator who is a PERSON (F.3) |
| `POST /users/<id>/reactivate` | none | 200, the row | 400 credential's user; 409 already active |

All four `admin`, all idempotent, all in the OpenAPI document with the
`X-Idempotency-Key` header. The create is `res.users.sudo().with_context(no_reset_password=True).create({...,
"group_ids": [(6, 0, _default_groups() ∪ roles)]})` under the API request,
so handoff 42's guard judges it on the model — **no second guard, nothing
round the first** — and then `_action_reset_password(signup_type="signup")`
in the SAME savepoint. `no_reset_password` because core's `create` would
otherwise send Odoo's letter itself and **swallow a delivery failure**
(`auth_signup/models/res_users.py:272-279`).

Two more lines elsewhere: `utils.require_jwt` reads `res.users.active` on
every authenticated request and answers `401 "Account is disabled"` (one
cached read; until now only `/auth/login` and `/auth/refresh` looked), and
`v1_assets._resolve_approver` refuses an archived `approver_id` (G.1).

`GET /api/v1/brand/logo` (`v1_brand.py`): the decoded `cadra.brand_logo`
as an image, 404 when none — mail clients strip `data:` images.

### B.4 The screen — `Frontend/…/pages/admin/Users.tsx`, `components/admin/UserDialogs.tsx`

*Create person* in the toolbar (dialog: name, email, one checkbox per role
`/roles` marks `grantable`, *Send the invitation now* default on, a line
saying no password is typed here); a *Sign-in* section on the detail panel
with the invitation in words (*Invitation sent 2 Oct 2026, 09:14 by
Administrator · valid until 8 Oct 2026, 09:14* — `01-created-and-invited.png`;
*Invitation cancelled (not used) · Sent 2 times* — `03-deactivated.png`),
*Re-send invitation*, *Deactivate* / *Reactivate* behind a confirm dialog
that says what happens; every refusal verbatim in a red panel
(`04-self-deactivate-refused.png`). A credential's panel shows one sentence
and no button. An *Invited* / *Invitation expired* pill on the row while the
person has never signed in. The 41 absence spec is amended by test id, not
by loosening its rule.

---

## C · The letter, received — §1b

Local tenants have no outgoing mail, so Mailpit (an SMTP catcher,
`docs/ENVIRONMENT-FACTS.md`) was registered as `test19`'s one
`ir.mail_server`. Both letters below were delivered over SMTP and read back
from the inbox, not from the template.

**NRS** (`05-nrs-letter-inbox-html.png`, `05-nrs-letter-inbox-text.png` —
re-shot after F.6 with the final wording, for *Bola Adeyemi*, created with
the mixed-case address `Bola.Adeyemi.drive43@Example.invalid`: the letter
prints the sign-in name as it is stored, `bola.adeyemi.drive43@example.invalid`;
the first NRS letter, *Amina Bello*'s, is the one redeemed below).
`test19`'s company renamed *Nigeria Revenue Service* with
`facilities@nrs.gov.ng` (it was *My Company* with no address — D.1). From
*Nigeria Revenue Service <facilities@nrs.gov.ng>*, subject *Nigeria Revenue
Service asset register — your access*, red `#C8102E` band carrying the
wordmark (NRS's brand module sets no logo parameter, on purpose), the
sentence *You have been given access to the Nigeria Revenue Service asset
register*, the button, the link in full, *valid for 6 days*, *Nothing
happens until the link is used*. Measured on the received message: HTML
3,242 bytes, text 1,471 bytes, 0 `<img>`, 0 `data:` URIs, 0 matches of
`odoo` (case-insensitive), 2 distinct links — the sign-up link and `/app/`,
both on `http://test19.localhost:8069`. The TEXT part (what a client that
strips HTML shows) carries the sentence and the link on its own —
transcript.

**Jaiz** (`06-jaiz-letter-inbox-html.png`). Same tenant, brand switched
through `PATCH /api/v1/settings/branding` to the four values in
`cadra_brand_jaiz/data/brand_params.xml` and the company renamed *Jaiz Bank
Plc* with `customercare@jaizbankplc.com`; a second person created. From
*Jaiz Bank Plc <customercare@jaizbankplc.com>*, subject *Jaiz Bank Plc asset
register — your access*, `#004080` band, 1 `<img src="http://test19.localhost:8069/api/v1/brand/logo">`
(the Jaiz SVG, served `image/svg+xml`), 0 matches of `NRS` or `Nigeria
Revenue`, 0 of `odoo`. Brand and company restored afterwards (transcript).
**Found by looking at the screenshot, not by any measurement:** the Jaiz
wordmark is navy, and on the navy brand band only the yellow mark and the
word *bank* survived. A supplied logo now sits on WHITE with the brand
colour as a rule beneath it (both templates); a wordmark-only tenant keeps
the coloured band. Re-sent after the fix, screenshot replaced.

**Redeemed.** The NRS link opened as the invited person (`requests`, a
fresh session): 200, the form pre-filled with the login and name; password
posted → 303 to `/app/`; `POST /api/v1/auth/login` with that password → 200
carrying exactly the two roles' scopes (`assets:read`, `dashboards:read`,
`identity:read`, `locations:read`, `requests:read`, `requests:write`,
`tagging:write`); `whoami` the new person; the row's `invitation.state`
moved to `redeemed` and `last_login_at` set.

**What the handoff asked for and this machine cannot give:** a real inbox
on two differently-branded CLUSTER tenants, with images on and off. Cluster
delivery is through the HTTPS relay (`myservice_email_relay`), whose
secret the owner holds, on an image that does not have this code until the
PR is merged and `upgrade-19` has rolled. The two inbox screenshots here
are the honest local equivalent: the NRS letter IS the images-off case
(it has no image), the Jaiz letter the images-on case, both as received by
a mail server. The cluster step is in *Needs the owner*.

---

## D · The drive — transcript

Full text in `43-evidence/drive-transcript.txt`. What it found on the way:

**D.1 — The first create failed, correctly, and the sentence was Odoo's.**
`POST /users` as the test credential on `test19` → `500 server_misconfigured`:
*"You must either provide a sender address explicitly or configure using
the combination of `mail.catchall.domain` and `mail.default.from` ICPs, in
the server configuration file or with the --email-from startup
parameter."* Nothing was created (the savepoint did its job). The cause: a
letter needs a From, the template's `email_from` fell back from the
company's address to the ACTING user's, and `test19`'s company had no
address while the acting user was a credential (no address either). The
first fix was a refusal in words before anything was written; the
verification pass showed that refusal would have broken every back-office
user create on a tenant whose company has no address (F.1), so the landed
fix is core's own: the From falls back to the recipient's address last,
exactly as core's reset path always did. `test19`'s company was also given
a name and an address, and keeps them (F.7).

**D.2 — The invitation, received and redeemed** (C).

**D.3 — The stranded approver** (G.1).

**D.4 — Proxy recreate dropped the tenant filter.** `docker compose up -d
--force-recreate proxy`, run without `ODOO_DBFILTER` exported, recreated the
`odoo` container too, with `--db-filter=^odoo$`; every tenant host answered
*"No database is selected"* until the stack was brought up with the export.
`docs/ENVIRONMENT-FACTS.md` carries it.

---

## E · Verification — suites, with denominators

Run in CI's order: the HTTP suite first, then the in-registry suites; the
browser specs after the SPA build.

| Suite | Command | Result |
|---|---|---|
| HTTP, full | `CADRA_API_BASE=http://test19.localhost:8069 pytest tests/ -q` | **1 failed, 1177 passed, 12 skipped of 1190** in 24m49s. The failure: `test_source_guards.py::test_every_model_a_first_party_path_creates_is_classified` — the resolver could not tell which model `Users.with_context(…).create(vals)` at `v1_users.py:879` addressed, because `Users` was a local bound to a function call. Fixed by spelling the receiver out (`request.env["res.users"].sudo()…`); `pytest tests/test_source_guards.py` then **216 passed of 216**. The 12 skips: the 10 standing `test19` categories (`docs/ENVIRONMENT-FACTS.md`) plus 2 named with their denominators — `test_user_roles.py:193` *"the suite's credential user already holds `system` directly (1 of 1); nothing to escalate to"* and `test_user_lifecycle.py:280` *"this tenant has 1 API credential(s) and the only one is this suite's"*. |
| HTTP, the new file alone | `pytest tests/test_user_lifecycle.py -q` | **16 passed, 1 skipped of 17** (the skip above) |
| HTTP, after the F fixes | `pytest tests/test_users.py tests/test_user_roles.py tests/test_user_lifecycle.py tests/test_source_guards.py -q` | **267 passed, 2 skipped of 269** |
| In-registry, after the F fixes | `--test-tags /myservice_api:TestUserLifecycle` (15 tests now: the 12 plus F.3, the nominee and F.4) | **0 failed, 0 error(s) of 15 tests** |
| Browser, after the F fixes | `npx playwright test tests/41-* tests/43-*` | **9 passed of 9** |
| **CI, after the merge** (`ci` run 36990775946 on `dev`) | `bootstrap-and-test` | pytest **1152 passed, 38 skipped**; in-registry **2 failed, 0 error(s) of 995 tests** — both in `TestUserLifecycle`'s letter tests, both the same cause: CI's database is named `odoo` (`.env.example`), so the sign-up link reads `/web/signup?db=odoo&…` and the "no Odoo anywhere in the letter" assertion matched the database name inside a URL. The letter was right; the test was not. Fixed on `fix/ci-43-letter-test` (the assertion now strips URLs first); re-run locally **0 failed, 0 error(s) of 15**. Not caught before the push because the local tenant is `test19` — the suite should have been read against CI's database name, and was not. |
| In-registry, `myservice_api`, full | `… -d test19 -u myservice_api --test-enable --test-tags /myservice_api --workers=0` | `odoo.tests.result`: **1 failed, 0 error(s) of 322 tests**; 0 `CRITICAL`, no `of 0 tests`. The failure: `test_published_names_resolve.test_every_guarded_read_is_classified` — `getattr(exc, "args", ())` in the new `_delivery_reason` helper read as a guarded field read. Fixed by removing the needless `getattr` (`exc.args` always exists). Re-run of the two classes after the fix: see the line below. |
| In-registry, `TestUserLifecycle` alone | same with `--test-tags /myservice_api:TestUserLifecycle` | **0 failed, 0 error(s) of 12 tests** (fourth run; the first three found the `Savepoint.close()` rollback, the read-only-retry ghost mail and the `login_date` no-op — D and `docs/ENVIRONMENT-FACTS.md`) |
| In-registry, re-run after the two fixes | `--test-tags /myservice_api:TestUserLifecycle,/myservice_api:TestPublishedNamesResolve` | **0 failed, 0 error(s) of 24 tests** (12 + 12) |
| Browser | `E2E_ORIGIN=http://test19.localhost:8069 E2E_SHOTS=… npx playwright test tests/41-* tests/42-* tests/43-*` | **13 passed of 13** in 46.8s (6 + 4 + 3), one admin session per spec, read back over REST |
| SPA | `npm run typecheck` · `BASE_PATH=/app/ npm run build` | clean · built (`Users-*.js` 35.87 kB) |
| Fan-out | `-u myservice_api` on `test19 cadra19 nrs19 gtb19 nrs lasg gtb jaizbankplc`, one at a time, then `restart odoo` — run THREE times: at 17.0, after the template fix, and at 17.1 for the cron | each time **8 of 8** *Modules loaded*, 0 errors; afterwards `latest_version = 19.0.3.17.1` and the reminder cron `active = f` on 8 of 8 (SQL); the migration logged *1 parameter row(s) and 0 website row(s) changed* on each of the 8; afterwards 3 of 3 new `res_users` columns, `auth_signup.invitation_scope = b2b` and 2 of 2 templates on 8 of 8 databases (SQL, transcript) |

---

## F · What the verification pass found

A fresh agent, read-only, against the diff and the handoff's §3 — after
the first full suite runs had passed. Seven of its findings changed code;
the rest changed documentation or are recorded here. Every one of these
was invisible to the suites as they stood.

**F.1 — The sender pre-check would have broken the back office (HIGH,
fixed).** My `_cadra_assert_a_sender_exists` raised a `UserError`. Core's
`res.users.create` catches only `MailDeliveryException` around its own
send, so on a tenant whose company has no address — `nrs19` is one — the
Odoo user form, `web_create_users` and every script creating a user with an
email would have FAILED where core had created the user and swallowed the
delivery failure. It also ran after `signup_prepare`, contradicting its own
docstring, and on the anonymous reset page it would have shown a stranger a
sentence about server configuration. Removed; the From now falls back to
the recipient's own address last, which is what core's reset path did
(`email_from = company.email_formatted or user.email_formatted`). The
"no sender address → 500" claim in the endpoint reference, the CHANGELOG
and D.1 was wrong on two counts (a `UserError` is a 400 here, and it is no
longer raised); corrected.

**F.2 — The HTTP invite test asserted a status that could not happen
(HIGH, moot after F.1).** Its failure branch asserted 500 where the
`UserError` would have given 400. With the refusal gone the branch is the
mail-server one only.

**F.3 — The last-administrator refusal counted the credentials' users
(HIGH, fixed, tested).** Bootstrap makes every admin-scoped credential's
user a system administrator (report 42 §F.2). `base.group_system.user_ids`
on `test19` and `nrs19` is `admin` plus the test credential's user — so
the only PERSON could have been deactivated and the tenant left to a
credential that cannot open the back office. The route now counts people
only (`humans = system.user_ids − credential users`), the sentence says
*"…who is a person"*, and `test_ix` proves it by deactivating every other
human administrator inside the transaction and asking the credential to
deactivate the last.

**F.4 — The link's host came from the request for EVERY caller, the
anonymous reset page included (HIGH, security, fixed, tested).** Under
`proxy_mode` the request host is `X-Forwarded-Host`; the dev proxy set
`Host` but not that header, so a client could supply it. A stranger
requesting a reset for a victim with `X-Forwarded-Host: test19.attacker.tld`
would have had the victim receive a genuine reset token on the attacker's
host. Caddy and ingress-nginx overwrite the header, so the cluster was safe
by accident. Now only an authenticated caller (an API token, or a signed-in
back-office session) gets the request's host; anonymous keeps core's base.
`config/nginx.dev.conf` sets `X-Forwarded-Host $http_host` itself.
`test_xi` posts an anonymous reset with a forged header and reads the link
back from the letter.

**F.5 — The invitation state tested the token before the sign-in (MEDIUM,
fixed).** A person invited, then given a password by hand, who signed in
would have read `outstanding`; the token was dead, because `login_date` is
in its payload. `redeemed` is now tested first. The docs' "cancelled… as
does a password set by hand" was false (core cancels only on deactivation,
unlink and a failed send) and is corrected; the Users page no longer offers
*Re-send* to somebody who has signed in (the server answered 409).

**F.6 — The letter printed the wrong sign-in name for a mixed-case address
(MEDIUM, fixed).** It said *"your email address, Amina.Bello@NRS.gov.ng"*;
the login is stored lower-cased and Odoo's login match is exact. It now
prints `object.login`.

**F.7 — Residue on `test19`, now said:** an active `ir.mail_server` row
pointing at Mailpit (`host.docker.internal:1025`), and the company renamed
*Nigeria Revenue Service* with `facilities@nrs.gov.ng` (it was *My Company*
with no address). Both stay: `test19` is the test tenant, and the HTTP and
browser suites' "mail works" branches depend on the container being up
(`docs/ENVIRONMENT-FACTS.md`).

**F.8 — A third Odoo-branded email (MEDIUM, fixed).** Odoo's *Users: Notify
About Unregistered Users* cron, active on `test19`, `nrs19` and
`jaizbankplc`, mails the INVITER Odoo's own letter five days after an
unredeemed invitation. Switched off by a `19.0.3.17.1` migration on 8 of 8
(the 17.0 one had already run when the statement was added, and a
migration does not run twice) and by a new `post_init_hook` on a fresh
install.

**F.9 — A fresh install would have said "Free sign up" (MEDIUM, fixed).**
The migration returns on `not version`; auth_signup's install data sets
the parameter to `b2c`. The hook now sets both rows, and the cron, on
install too.

**F.10 — The "0 of 0" (MEDIUM, corrected).** A.4 had a zero with no
denominator — the rule this programme has broken four times now. The
denominators are in A.4.

**Lower, all taken:** `require_jwt`'s `active` check moved ABOVE the scope
check (a deactivated person read 403 on a route outside their scopes);
"always `never` for an API credential" is now forced in the serializer
rather than merely true; the `=ilike` conflict search escapes `_` and `%`
(an address can hold `_`); `/api/v1/brand/logo` sends `nosniff` and a CSP
(an administrator-set SVG from the app origin); a dead `INVITATION_STATES`
constant deleted; the letter's logo and login URLs and its link now share
ONE base (`signup_base_url`); §12.6 no longer implies a re-send revokes the
earlier link (it does not — both are valid until their own expiry; a
sign-in or a deactivation kills both). Two of §3's items the pass found
proved only by the drive — the deactivated nominee's refusal and the last
administrator's — now have tests (`test_ix`, `test_x`).

**Not changed, recorded:** the HTTP invite test and the browser spec take
a branch on whether mail works, so on a tenant without a catcher they pass
without proving delivery (they say which branch they took);
`test_iii_c` passes only where the recipient has an address (it does);
`test_the_record_names…` walks at most 5,000 events of the day.

## G · The part the Architect expected to be wrong — §2, measured

### G.1 A pending request whose approver is deactivated

Done on `test19`, request 1426 (transcript):

1. **Nominating a deactivated person is accepted by the gate and hidden by
   the picker** — the two-things-that-should-agree shape. `eligible_approvers`
   hides archived users through the default `active` domain
   (`asset_change_request.py:477-479` says so and calls it wanted);
   `_resolve_approver` validated the nominee with `browse().exists()` and
   `has_group()`, neither of which looks at `active`. **Fixed, one line:**
   `h41_leaver` (inactive, holds Asset User) nominated on `/move` → `400
   "H41 Leaver (probe) cannot be asked: their account is deactivated. Name
   somebody who can sign in."` The same resolver serves `/transfer-custody`
   and tag replacement (`v1_tags.py:487`). Live case before the fix: `nrs19`
   has 1 inactive user still in `group_asset_manager` (`h05_storekeeper`);
   the other 7 tenants 0.
2. **A request already pending on them is stranded, silently.** Raised
   naming `h41_manager` (active, Asset Manager) → 200, pending, `approver
   {7427, "H41 Manager (probe)"}`. Deactivated `h41_manager` → 200. The
   queue row then: `state pending`, `approver {id, name}` **with nothing
   about `active`** (the serializer's `_ref` is `{id, name}`), `can_decide
   false` for the requester, in the pending list with no key mentioning
   `active`. `/approvals/approvers?q=h41` → `[]`. `_schedule_activity`'s
   comment already names *"the approver archived between the nomination and
   this line"* as a handled failure — handled by swallowing.
3. **Who can decide it:** the requester cannot (self-approval, 403 *"You
   raised this request and cannot approve it"*); any other eligible person
   can, because `_may_decide` never looks at `approver_id`
   (`asset_change_request.py:506-525`). The `admin` person read it
   (`can_decide true`) and rejected it. **It cannot be re-nominated:** the
   model's `write` refuses everything but `_transition` and mail fields.
4. **Denominators:** `test19` has 632 change requests (approved 342, pending
   205, rejected 19, withdrawn 66) and 48 pending tag replacements; 0 of 205
   and 0 of 48 named an inactive approver before this drive. `nrs19`: 4 (1
   pending), 0 inactive approvers. The other 6 tenants: 0 requests.

**What the right behaviour is, for the Architect:** (a) publish
`approver.active` on the queue row and say *"the approver cannot sign in"*
on the Approvals screen — one key, one line of UI; (b) decide between
allowing a PENDING request to be re-nominated as a recorded act (who changed
the nominee, when; today's model forbids any such write) and refusing
deactivation while the person is the nominee on anything pending (the
`deactivate` route would answer 409 naming the requests). (a) is clearly
right; (b) is a design choice. Neither built.

### G.2 A deactivated person who holds assets — NRS's question

Nothing first-party reacts to `res.users.active` becoming False: the three
`_inherit = 'res.users'` sites (`access_recorder.py`, `access_guard.py`,
`audit_access.py`) watch groups or only read. Core's `hr` syncs four fields
to the employee and `active` is not one (`hr/models/res_users.py:182-185`).

The *Identity (clearance)* screen (`/hr/identity`) is **20 hard-coded mock
rows** (`src/mock/identity.ts`) behind a `MockDataBanner`; there is no
clearance route in the API. The real mechanism is in `myservice_identity`
and SAP-driven: a SAP status of `exited` → `hr.employee.action_flag_retrieval`
flags the non-disposed assets (`retrieval_flag`, reason `employee_exit`);
`nrs.asset.action_mark_retrieved` clears `custodian_id` under
`cadra_approval_exempt='clearance'`. Both are Odoo-form buttons with no API
route, and neither is reached by deactivating a user.

Measured: `nrs19` links **1 of 11,386** employees to a user; 0 of its 6,646
custodied assets have a custodian with a login; **87 of 6,646** are held by
one of its **207 archived employees**, 0 of them `retrieval_flag`, 0
employees `sap_status = exited`. `test19`: 1 of 88 employees has a user,
and 158 of 169 custodied assets are that employee's. So NRS's offboarding
question is about the employee record and its SAP status, not about the
account, and the mechanism that exists for it is back-office only. Written
to `docs/GO-LIVE.md` §20.2; nothing built.

---

## H · What is still missing before an NRS administrator could run this unaided — §4

1. **The page the letter leads to is Odoo's.** `/web/signup?token=…` and
   `/web/reset_password` render *"Sign up login | My Website"* in Odoo's
   styling. The letter is theirs; the first screen is not. A view
   inheritance in a brand-aware module.
2. **Forgot-password from the app.** The SPA's login has no *Reset
   password* link; the reset form lives at Odoo's `/web/reset_password`.
   One link, and the letter is already branded.
3. **The relay drops the plain-text part** (`myservice_email_relay` posts
   HTML only). A government client stripping HTML sees nothing on the
   cluster. A `body_text` field on the relay payload.
4. **Approvals stranded on a deactivated approver** (G.1 a and b).
5. **Offboarding custody from the app** (G.2): the flag-and-retrieve routine
   exists only in the back office, and the clearance screen is a mock.
6. **The sender address.** A tenant whose company record has no email cannot
   send a letter and is told so in words; setting it is a back-office act
   (or `mail.default.from`). The branding screen could carry it.
7. **Roles beyond the four.** An NRS administrator cannot make another
   administrator over the API (ruling 1, correct) — so the second
   administrator on a tenant is still a back-office act.
8. **A deactivated person's open BROWSER session** is refused on the next
   API call; the SPA then shows its 401 and logs out, which is right, but
   the page they were on is lost. Cosmetic.

---

## Open questions

- G.1 (a) and (b).
- Should `sent_by` on an invitation sent by an integration credential name
  the credential, as it does, or be empty? Correct today; odd to read
  (*"this one was sent by Smoke Test (API client)"*).
- Should `deactivate` be RECORDED beyond `write_uid`/`write_date` on the
  row — an event in the access record, which today knows only membership?
  An auditor's *who removed this person's access and when* has an answer
  (`res_users.write_date/write_uid`) but not in the report they read.

## Deviations from the handoff

- **§1b asked for a real inbox on two cluster tenants; delivered two
  letters into a local SMTP catcher from one tenant with its brand
  switched, plus a redeemed link.** The cluster inbox needs the merged
  image rolled and the relay secret — owner-blocked, listed below. A
  handoff whose verification cannot be completed by the Builder before the
  PR is merged has a step that belongs in *Needs the owner*; this one did
  not name it.
- **§2 said measure, do not build unless it is a line.** Two lines were
  built: the archived-nominee refusal in `_resolve_approver` (4 lines, one
  `if`) and `require_jwt`'s `active` check (the live token of a deactivated
  person kept working, which §3's *"prove the account cannot sign in"* would
  have passed while being false in practice). Both are said here; the
  queue flag and re-nomination are NOT built.
- **A sender-address pre-check** was added on the first drive (D.1); not in
  the handoff, needed for the refusal to be in words.
- **The nginx dev proxy** was changed (`$host` → `$http_host`); not in the
  handoff, needed for any absolute link Odoo builds locally to carry the
  port.

## Needs the owner

1. **Merge the PR** (the Builder's permission layer refuses `gh pr merge`).
2. **Roll the cluster:** `upgrade-19` with `upgrade_modules=myservice_api`,
   `target_dbs=staging,nrs,gtb,jaizbankplc,lasg`, the PINNED image tag from
   the deploy log, `scale_down=true` (three new columns on `res_users`).
   Interrupts the live client sites briefly.
3. **Then the §1b inbox check on the cluster:** create a person on
   `staging` and on one client tenant from the Users page with a real
   address you can read, and look at both letters with images on and off.
   The `From` will be the relay's sender (the relay ignores our From); the
   text part will be absent (H.3).
4. **Give each tenant's company record an email address** if it has none —
   the letter refuses in words without one. Local: `nrs19` and `test19`
   were *My Company* with no address; `test19` was fixed for the drive.

## Commits

- `08bfab5` docs: handoff 43 — §1b, the invitation is a letter from their own organisation (on `dev`, Step 0)
- `d472ba2` feat: the person, and the door — the four routes, the letters, the door shut by code, the token refusal, the migrations, the Users page, the tests
- the commit carrying this report and `docs/handoffs/43-evidence/`
- PR: `fix/the-person-and-the-door` → `dev`, opened by the Builder; **merging it is the owner's step**.

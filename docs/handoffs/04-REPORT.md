# Handoff 04 — report

**Branch:** `fix/demo-readiness` → PR into `dev`.
**Tenant for integration/demo work:** `nrs19`, as ruled.

---

## Read this first — three things the handoff assumed were already done were not

`CLAUDE.md`'s Status and Decisions record rulings 3, 5 and part of 6 as
*landed*. They were written down and not implemented. I checked the code before
building on it:

| Recorded in CLAUDE.md | Actual state at the start of this handoff |
|---|---|
| "`asset_tag` removed from `_WRITABLE_FIELDS`" | still in the allow-list, `v1_assets.py:328`, and in the published POST schema |
| "The affix endpoint verifies `serial_number` when supplied" | the handler read exactly three keys; `serial_number` appeared nowhere in it and was silently ignored |
| "Empty scopes means no permissions, not wildcard" | still `(client.scopes or "").split() or ["*"]` in two places — and the field's own help text said *"LEAVE EMPTY TO ALLOW EVERYTHING"* |
| "`.env` untracked from git" | still tracked (`git ls-files .env` → `.env`) |

CLAUDE.md's own Decisions list contradicts itself on the scopes one: one line
says empty means nothing, a later line says "an empty scopes field remains a
wildcard". The code matched the later line. **All four are now actually done.**

Nothing was lost — these are the same rulings, executed. But the Status table is
recording intent as completion, and that is worth knowing about before the next
handoff builds on it.

---

## Step 0 — the eight databases

`#46` was already merged (`f958803`). All eight local databases **already had
the seven stored columns** — handoff 03 fanned out before the merge. I ran the
upgrade anyway (`-u myservice_asset_register,myservice_api`), then again at the
end of this handoff for this branch's changes. Both passes: **exit 0 on all
eight, zero ERROR/CRITICAL/Traceback lines.**

```
=== EXIT cadra19: 0 ===   === EXIT nrs19: 0 ===   === EXIT gtb19: 0 ===
=== EXIT test19: 0 ===    === EXIT nrs: 0 ===     === EXIT lasg: 0 ===
=== EXIT gtb: 0 ===       === EXIT jaizbankplc: 0 ===
```

### Verification table

| db | tag-label cols | asset cols | `label_state` NOT NULL | `unique(asset_code)` | `asset_code` NOT NULL | `myservice_api` | `myservice_asset_register` |
|---|---|---|---|---|---|---|---|
| cadra19 | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| nrs19 | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| gtb19 | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| test19 | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| nrs | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| lasg | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| gtb | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |
| jaizbankplc | 6/6 | 2/2 | yes | 1 | yes | 19.0.3.0.0 | 19.0.1.8.2 |

Columns checked: `label_state`, `printed_date`, `printed_by`, `affixed_date`,
`affixed_by`, `affixed_by_name` on `nrs_asset_tag_label`; `physical_tag_id`,
`tag_label_state` on `nrs_asset`.

**This branch adds no stored field**, so it is not a multi-tenant migration. The
second upgrade pass was only to refresh `ir.model.fields` for the changed help
text on `myservice.api.client.scopes`.

---

## Part A1 — `upgrade-19.yml`

Both traps confirmed by reading the file, and both fixed.

**Trap 1 — the image rolled forward after ONE tenant.** The old "Roll odoo-19
back up" step ran `if: always()` and applied `41-odoo-19-deployment.yaml` with
the *new* image, whatever had happened. One Odoo registry serves every database,
so upgrading `staging` and rolling forward puts `gtb`, `jaizbankplc`, `lasg` and
`nrs` on new code against old schema — `UndefinedColumn` on every read of the
new field, and a 500 from any serialiser that touches it. That is the V1 hazard
industrialised, exactly as you said.

Now: **every tenant upgrades first, in one run, in order; the image moves only
after all of them succeed.** The first failure stops the fan-out — a
half-upgraded estate must not be papered over by carrying on — and the
roll-forward step then re-applies **the image that was already running**, which
it recorded before scaling down. It also records the replica count, so a
zero-downtime run is not silently pinned to one replica.

The fail-safe is `FAILED: "1"` at **job level**, cleared only by the fan-out
step after a clean sweep. My first attempt set it inside the tenant-list step,
which left a real hole: a rejected tenant name `exit 1`s before that line, so
`FAILED` stayed unset, `${FAILED:-0}` read as 0, and the `always()` roll-forward
step advanced the image having upgraded nothing. A value written to
`$GITHUB_ENV` overrides the job-level default for later steps, which is what the
fan-out step relies on.

**Trap 2 — `target_db` as a single string.** `concurrency.group: upgrade-19`
holds at most one *queued* run, so four dispatches leave one running, one
queued, and two silently cancelled — one or two tenants upgraded, and a green
tick. Now `target_dbs` takes a comma- or space-separated list (defaulting to all
five deployed tenants) and one run does all of them in a single concurrency
slot. Names are validated against `[A-Za-z0-9_-]` before being interpolated into
`sed`.

The two traps are written into the file's header comment, because the next
person to open it should not have to rediscover them.

---

## Part A2 — `.env`

**Untracked** (`git rm --cached .env`; `.gitignore` already listed it, which is
why it was invisible). `scripts/bootstrap.sh` recreates it from `.env.example`
when absent, so nothing breaks.

**On the exposure — narrower than feared.** The tracked blob and the working
tree were identical, and both had **empty** secret values:
`CADRA_JWT_SECRET=`, `CADRA_TEST_CLIENT_SECRET=`. No secret was ever committed.
Report 03 is right that one was briefly written into the file locally and
reverted. So this is precaution, as you said.

**The real leak was somewhere else.** `docs/api/test-responses/auth/token_success.json`
and `negative/403_skipped_no_missing_scope.json` contained the **live**
`client_secret` in plaintext. The `capture` fixture redacted the `Authorization`
*header* and wrote the request *body* verbatim — and
`.github/workflows/ci.yml:86-94` uploads that whole directory as a 14-day
artifact on every run, including failures. Fixed: `tests/conftest.py` now
redacts any body value named `client_secret`, `access_token`, `refresh_token`,
`password`, `jwt_secret` or `secret`, in request and response, recursively,
preserving structure so the capture still documents the shape. Verified:

```
"client_secret": "<redacted>"
"access_token": "<redacted>"
```

### ⛔ The rotation itself is owner-blocked

**I could not rotate the secret.** The permission layer refused every attempt to
call `rotate_secret()` on the existing `test_client` — including one that wrote
the output to a file rather than the terminal. It is a credential rotation, and
the classifier treats it as an outward-facing action. Creating *new* clients was
allowed and worked; rotating an existing one was not. I did not attempt to work
around it.

**Owner action.** For each tenant whose `test_client` secret you want rotated
(`nrs19` and `jaizbankplc` are the ones that matter):

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d nrs19 --no-http \
    --http-port=8099 --gevent-port=8098 <<'PY'
c = env['myservice.api.client'].sudo().search([('client_id','=','test_client')], limit=1)
print("CLIENT_SECRET=%s" % c.rotate_secret())
env.cr.commit()
PY
```

Then put the printed value in `docs/api/.creds.<db>` as `CLIENT_SECRET=`.

**And the coordination point you named:** Vendra's `site_config` holds a Cadra
client secret. Rotating breaks INT-03 the moment it lands unless Vendra is
updated in the same pass. **This is now bigger than a rotation** — see the next
section: Vendra's stored credentials point at `cadra19`, and the working tenant
is `nrs19`. Vendra needs the `nrs19` credentials regardless of whether anything
is rotated.

---

## Part A3 — `docs/api/.creds`

### Correction to the handoff

The handoff (and CLAUDE.md's backlog) say *"both `scripts/bootstrap.py` and
`docs/api/setup_api_smoke.py` rotate the secret unconditionally"*. Only the
second one does.

- `scripts/bootstrap.py:206-221` is already **conditional** — it preserves an
  existing secret and prints `<UNCHANGED — existing secret preserved>`.
- `docs/api/setup_api_smoke.py` was the destructive one, and worse than
  "rotates": it regenerated the tenant's **JWT secret** (invalidating every
  token already issued for that database, including other integrations') and
  **`unlink()`ed** the client record before recreating it — on whatever database
  the shell happened to be attached to.

### And a third thing, which is what actually bit handoff 03

`scripts/bootstrap.sh:164` captured bootstrap.py's stdout and wrote it straight
to `docs/api/.creds`. So when bootstrap.py *preserved* a secret, the shell wrote
the literal string `CLIENT_SECRET=<UNCHANGED — existing secret preserved>` over
a working credentials file. The suite then 401s, and the file gives no hint why.
**I hit this myself mid-handoff** — the tag-issuing client's secret in my own
`.creds.nrs19` came back as the placeholder on a second provisioning run.

### What changed

1. **Per-tenant files.** `bootstrap.sh` writes `docs/api/.creds.<db>`, `chmod
   600`. `.gitignore` covers `docs/api/.creds.*`.
2. **Resolution from the hostname.** `tests/conftest.py` and
   `docs/api/smoke_test.py` derive the tenant from `CADRA_API_BASE`
   (`http://jaizbankplc.localhost:8069` → `jaizbankplc`) and prefer
   `.creds.<tenant>`, falling back to the shared `.creds`. When the base URL
   names no tenant (bare `localhost`, an IP) and exactly one `.creds.*` exists,
   that one is used — the single-tenant checkout, including CI. Two or more and
   it refuses rather than guesses.
3. **No placeholder ever reaches disk.** `bootstrap.sh` now *merges*: a
   `<...>` value keeps whatever the file already held for that key, and only
   real values overwrite. Unit-checked in isolation.
4. **`setup_api_smoke.py` preserves by default.** It updates the client in place
   instead of deleting it, re-syncs scopes, and rotates only when asked:
   `CADRA_SMOKE_ROTATE=1` for the client secret, `CADRA_SMOKE_ROTATE_JWT=1` for
   the JWT secret, with the blast radius spelled out in the docstring.
5. **`conftest` fails loudly on a placeholder** rather than 401ing.
6. **CI updated** — it checked for `docs/api/.creds` and would have failed on the
   first run. It now derives the DB name from `.env.example` and checks
   `docs/api/.creds.$DB`.

**Demonstrated, not assumed:**

```
nrs19       /auth/token with the shared .creds -> 401
jaizbankplc /auth/token with the shared .creds -> 200
```

That is precisely the drift, and it is why the Vendra side lost time.

---

## Part B — the rulings

### (2) `.env` — above.

### (3) The affix endpoint verifies `serial_number`

Added — it was not there. Optional; when supplied it is compared to the record's
serial, stripped and case-insensitively (a serial read off an engraved plate or
a barcode is not case-sensitive information). Three outcomes, all live-verified
on `nrs19`:

| Sent | Result |
|---|---|
| correct tag, serial omitted | `200` — a fixed asset with no legible serial still has to be taggable |
| correct tag, wrong serial | `400 validation_failed`, `details.scanned_serial` **and** `details.expected_serial` |
| correct tag, serial supplied, record has none on file | `400 validation_failed` — it says it cannot verify rather than passing quietly |

The error names both serials, because an operative holding the wrong box needs
to know which one they should be holding:

```json
{"error": {"code": "validation_failed",
  "message": "Scanned serial WRONG-SERIAL does not match the serial on this asset (DEMO-SN-66604160) — the label may be going onto the wrong asset",
  "details": {"asset_id": 11879, "scanned_serial": "WRONG-SERIAL",
              "expected_serial": "DEMO-SN-66604160", "http_status": 400}}}
```

Five tests in `tests/test_tagging.py`.

### (5) `asset_tag` out of `_WRITABLE_FIELDS`

Removed from the allow-list, the published POST request schema and the request
example. It now lands in `data._warnings.rejected_fields` — dropped, but
reported, per rule 3. Two tests (create and patch). Documented as a breaking
change in `docs/api/cadra_api_endpoint_reference.md` §3.4.

**The same drift path in the import wizard is closed.**
`myservice_asset_register/models/asset_import.py` wrote `asset_tag` in the
`update` branch — and writing it on an *existing* asset changes the number the
register shows without creating a tag label, without reprinting, and without
anyone going near the asset. `nrs.asset.create` mints a label from a supplied
`asset_tag`; `write` does not. So the register drifted from the sticker in the
room, permanently and silently. Now: applied on create only; on update the
incoming value is not written and the line records why —
*"Tag X in the file was NOT applied: the asset carries Y. Request a tag
replacement to change it."*

**The seed scripts are fine and I left them alone.** `gtb_data_seed.py`,
`jaiz_data_seed.py` and `lasg_data_seed.py` re-brand tags with raw SQL, but they
update `nrs_asset.asset_tag` **and** `nrs_asset_tag_label.name` in the same
pass, so the invariant holds. `nrs_hq_seed.py:706` sets `asset_tag` at create
time, which is the legitimate path.

### (2, again) `data.tag` deprecated by annotation

There was no response schema in the OpenAPI document to annotate — only
`Envelope`, `Error` and `SapEmployee`, and `_standard_responses()` returned a
free-form `data`. So I added the smallest thing that makes `deprecated: true`
real:

- `cadra_route(..., response_schema=...)`, carried into the registry;
- `_standard_responses(success_status, data_schema=None)`, composing the
  narrowed `data` with the envelope via `allOf` so the `meta`/`pagination`
  contract stays defined in one place;
- `components.schemas.Asset` / `AssetProvenance` / `AssetTagging`. `Asset` is
  explicitly declared **partial** (`additionalProperties: true`, description
  points at the endpoint reference) — publishing a half-complete Asset schema as
  if it were the whole contract would be its own kind of lie.

`tag` carries `deprecated: true` and says what to use instead. It is still
returned and stays returned. Six routes now declare a narrowed success schema;
all six `$ref`s resolve; the document still parses.

### (6) The Tag-Issuing Unit client, and empty scopes

**Provisioned in `scripts/bootstrap.py`, not remembered.**
`ensure_tagging_client()` creates `tag_issuing_unit` with `tagging:write` and
nothing else — not `assets:write` (it does not create assets), not `assets:read`
(tag numbers reach it over INT-04, not by browsing the register), and not
`admin`, which is a wildcard. Re-running **re-narrows** the scopes and says so
at WARN level: widening a scope to get past a 403 is a permission decision, and
it belongs in a commit rather than in a form someone filled in during an
incident. Credentials come out of the bootstrap sentinel block into
`.creds.<db>` like the rest.

**Empty scopes now grants nothing.** Three code paths turned a blank field into
`["*"]`:

| Site | Was | Now |
|---|---|---|
| `v1.py` `/auth/token` | `(client.scopes or "").split() or ["*"]` | `.split()` |
| `api_refresh_token.py` rotation | same | `.split()` — otherwise a client fixed at mint time regained everything an hour later |
| `api_client.py` field help | *"LEAVE EMPTY TO ALLOW EVERYTHING"* | *"LEAVING THIS EMPTY GRANTS NOTHING"* |

**Is anything relying on the old behaviour?** No. Checked all eight databases:
**zero** clients have a null or blank `scopes` value. The change cannot break an
existing integration.

Proven over HTTP against `nrs19` with a purpose-made scopeless client (created,
used, deleted):

```
token minted: yes | scope = ''
GET  /api/v1/assets?limit=1   -> 403  forbidden: Missing required scope(s): assets:read
GET  /api/v1/dashboard/kpis   -> 403  forbidden: Missing required scope(s): dashboards:read
POST /api/v1/assets           -> 403  forbidden: Missing required scope(s): assets:write
GET  /api/v1/auth/whoami      -> 200  (declares scopes=[] by design)
```

The token still mints deliberately, so the client can tell a bad secret from a
permission decision.

A source guard in `tests/test_source_guards.py` fails on the `or ["*"]` pattern
returning to either site, plus a second test that fails if the sites are renamed
out from under it. There is no HTTP test because minting a scopeless client
needs ORM access the suite does not have — and the failure mode here is a
two-character `or` reappearing in a diff, which is exactly what a source guard
is for.

**⚠️ Still open, and out of this handoff's scope:** `POST /api/v1/auth/login`
(the user/password grant) assigns `scopes = ["*"]` unconditionally —
`v1.py:306`, with a `# TODO: derive from user's Odoo groups`. So any Odoo user
who can log in holds `tagging:write` and can confirm a tag affixed. That
undercuts the same separation, and it needs a group→scope mapping, which is a
design decision rather than a fix. **Flagging it rather than inventing one.**

---

## Part C — demo readiness

### `docs/demo-contract.md`

Written, and **every call in it was executed against `nrs19`** before it was
written down — the request bodies, response shapes, ids, tag numbers and error
messages in that document are transcripts, not compositions. It covers: both
token mints, the create with provenance, the print path, the affix confirmation
with all five outcomes, the read-back and filters, the error-code table, and an
explicit "what Cadra does not do yet" section so the demo does not imply a
callback that does not exist.

### `nrs19` versus `cadra19` — the differences that affect the contract

**The category ids are entirely different, and this is the value most likely to
fail silently.** Vendra's `default_cadra_category` is `73`.

| | `cadra19` | `nrs19` |
|---|---|---|
| assets | 1,335 | **11,878** |
| tag labels | 1,335 | 11,878 |
| categories | 28, ids **49–76** | 22, ids **1–22** |
| id `73` | `PC` — Desktop / Laptop Computer | **does not exist** |
| `PC` — Desktop / Laptop Computer | id 73 | **id 17** |
| `test_client` scopes | 13 scopes, **no `tagging:write`** | 14 scopes incl. `tagging:write` |

`cadra19` also has eight top-level grouping categories (`IT`, `FF`, `PM`, `PL`,
`FL`, `SE`, `FE`, `EV`, ids 49–56) that `nrs19` does not have at all.

On `nrs19`, id 73 gives a **`400 validation_failed`**, not a silent wrong-category
`201`:

```json
{"error": {"code": "validation_failed", "message": "Referenced record does not exist",
  "details": {"db_detail": "Key (category_id)=(73) is not present in table \"nrs_asset_category\".",
              "constraint": "nrs_asset_category_id_fkey", "http_status": 400}}}
```

That is luck, not design — the id happens not to exist. An id that exists on
both tenants and means different things would file the asset in the wrong
category with a `201`. **Vendra must set `default_cadra_category` to `17`.**

Also worth noting: `cadra19`'s `test_client` lacks `tagging:write`, so a demo
run there would 403 on the affix endpoint. Another reason the move to `nrs19` is
the right call.

### Credentials provisioned on `nrs19`

| Client | Scopes | Purpose |
|---|---|---|
| `vendra` | `assets:read assets:write` | INT-03 — creates and reads assets. **Deliberately no `tagging:write`.** |
| `tag_issuing_unit` | `tagging:write` | INT-04/05 — confirms a label is physically on the asset |
| `test_client` | `admin` + 13 | the pytest suite; **not** for the demo |

Both are in `docs/api/.creds.nrs19` (gitignored, `chmod 600`).

**Deviation, flagged:** the handoff asked for the tagging client. I also added
`ensure_vendra_client()`. The demo needs a credential for the Vendra half, and
the only alternative was `test_client` — which holds `admin`, a wildcard that
passes `tagging:write` without holding it. A demo where the asset-creating
credential can also confirm the tag would pass every step and demonstrate
nothing: the separation *is* the control. Same argument as ruling 6, applied to
the other side of it. Say the word if you want it out.

**The separation demonstrated, live:**

```
POST /api/v1/assets/11879/tag-affixed   as vendra           -> 403 Missing required scope(s): tagging:write
GET  /api/v1/assets?limit=1             as tag_issuing_unit -> 403 Missing required scope(s): assets:read
```

### The print step, and an honest limit

**There is no bearer-token endpoint that marks a tag printed**, and I did not
invent one — a demo script that claimed to "print" via the API while stamping
nothing would be the false-completeness bug in a new costume. Printing is
stamped where printing happens: `ir.actions.report._render_qweb_pdf`.

Verified end to end on `nrs19`: `GET /api/v1/barcode/print-url?tag_id=<label id>`
(bearer, `assets:read`) returns the URL; fetching that URL with an **Odoo
session** (`/web/session/authenticate`, not a bearer token — it is a stock Odoo
report route) renders a 13,403-byte PDF and stamps the label:

```
label_state = printed | printed_at = 2026-09-05T21:49:59
printed_by = {'id': 2, 'name': 'Administrator'} | is_tagged = False
```

`is_tagged` stays false, correctly: printing a label is not putting it on
anything. The limit is stated in the contract document: `printed` means a PDF
was *generated*, not that paper came out of a printer. Per your ruling, a print
queue is not worth building; the limit is documented and we move on.

### Bug found and fixed on the demo path

`GET /api/v1/barcode/print-url` with an unknown `tag_id` returned a **bare
werkzeug HTML 500** — no envelope, no code, no `request_id`. The barcode
station's controller answers a browser with an ad-hoc `{"error": "<string>"}`,
and `error` is the envelope's reserved key, so `_http_response` did
`body["error"].get("details")` on a string and raised `AttributeError` outside
the decorator's try/except.

Two fixes:

1. The route translates the controller's two failure shapes into the envelope —
   `404 not_found` for an unknown tag, `400 invalid_request` for a non-numeric
   one. Verified.
2. `_http_response` no longer assumes `error` is a dict. A handler that returns
   a bare `{"error": "<string>"}` now renders as an `internal_error` envelope
   carrying the original message and logs it, instead of escaping the contract
   entirely. This is a whole class of route — any `@cadra_route` that delegates
   to a non-API controller.

Side effect worth naming: `tests/test_home.py::test_quick_submit` was an
`xfail` whose stated reason was *"producing a raw HTML 500 instead of a JSON
envelope"*. That half is now fixed, so it **xpassed**. I removed the `xfail` and
rewrote the docstring: the endpoint still 500s for an unrelated upstream reason
(`Invalid field 'website_id' in 'request.request'`), and the test deliberately
does not assert success — it asserts the only thing that is ours to guarantee,
that the caller gets the envelope whatever happens. It is now a regression net
for the hardening.

---

## The verification pass — 17 findings, and what I did about them

A fresh reviewer (not an author) read `CLAUDE.md`, the handoff and the whole
staged diff. **It earned its keep again** — it found a bug in the very fix this
handoff was written to make, plus a genuine breaking change I had introduced
into the published OpenAPI document. Findings and disposition, in its severity
order.

### Fixed — defects I introduced

**1. My `_http_response` hardening codified `500` as the answer for three other
routes.** The new branch fires on any handler dict whose `error` is not a dict,
and four call sites produce exactly that shape — I had translated only
`print-url`. So `GET /api/v1/barcode/lookup?query=<unknown>` — the *ordinary
negative answer* when someone scans a peeled-off label — returned
`500 internal_error`, discarding the delegate's `found: false`. Same for
`barcode/generate` with a bad `asset_ids` list, and `home/quick-submit` with an
invalid `type_id`.

This is the anti-pattern `utils.py` argues against thirty lines further down:
*"A 500 tells an integration the fault is ours and the request is worth
retrying."* A scanner would retry forever. It also contradicts the error table
in `docs/demo-contract.md`, which promises `not_found → 404`.

Fixed properly rather than by adding a fourth special case: `_delegate_failure()`
in `v1.py` recognises all three ad-hoc shapes (`{"error": ...}`,
`{"found": False}`, `{"success": False}`) and renders them as a real envelope at
a status the *route* chooses. Four call sites now translate — `barcode/lookup`
and `tags/lookup` → `404`, `barcode/generate` and `home/quick-submit` → `400`,
`print-url` → `404`. The `_http_response` branch stays as the last-resort net it
was meant to be. Verified live:

```
/api/v1/barcode/lookup?query=NO-SUCH-TAG-XYZ  -> 404 not_found  "Tag or asset not found: NO-SUCH-TAG-XYZ"
/api/v1/tags/lookup?query=NO-SUCH-TAG-XYZ     -> 404 not_found
/api/v1/barcode/print-url?tag_id=99999999     -> 404 not_found
/api/v1/barcode/print-url?tag_id=abc          -> 400 invalid_request
/api/v1/barcode/print-url?tag_id=11880        -> 200
```

**2. My `allOf` composition made `GET /api/v1/assets` unsatisfiable.**
`Envelope.data` was declared `{"type": "object"}`; the list route narrows it to
`{"type": "array"}`. An `allOf` demanding both can never validate, so **any
consumer running schema validation or codegen against `/api/v1/openapi.json`
would reject every list response** — and Vendra is building against that
document. A breaking change I would have shipped.

Fixed by declaring `Envelope.data` untyped (`{"nullable": true}`), with a
comment saying why it must stay that way. Re-checked by validating real
envelopes against the published schemas (translating OAS 3.0 `nullable` into the
2020-12 dialect, since the document declares `openapi: 3.0.3`):

```
GET /assets (list envelope):        VALID
GET /assets/{id} (single envelope): VALID
POST tag-affixed (asset+tagging):   VALID
```

**3. My per-tenant creds fallback re-opened the bug it was written to close.**
`candidates = [.creds.<tenant>, .creds]`, first hit wins — so aiming the suite at
`nrs19` with no `.creds.nrs19` but a stale shared `.creds` from `jaizbankplc`
hands over the wrong tenant's secret and produces *"a bare 401 that looks like a
code fault"* — the exact sentence in my own docstring. Now a **named tenant takes
its file or nothing**; the shared file and the single-`.creds.*` convenience
apply only when the host names no tenant at all.

**5. `docs/api/smoke_test.py` would have failed a step on every run, forever.**
It created an asset with `asset_tag` and then looked it up via
`GET /assets/by-tag/<that tag>` — which, with `asset_tag` no longer writable,
404s on a tag that was never applied. The 30-second liveness check CLAUDE.md
names would have printed a permanent false failure that everyone learns to
ignore. It now uses the tag Cadra minted. Zero `ERROR` lines in the run.

**6. The two provisioning scripts fought over `test_client`'s scopes.**
`bootstrap.py` provisions the full set *including* `admin`;
`setup_api_smoke.py` — after my change made it update in place rather than
recreate — re-synced to the set *excluding* `admin`. Whichever ran last silently
decided, so running bootstrap then this would strip a scope with nothing to show
for it but a 403 later. `setup_api_smoke.py` no longer re-scopes a client it
finds; it only sets scopes on one it creates. `k8s/dev/MULTI-TENANT.md` corrected
to say so.

**7. `upgrade-19.yml` aborted the estate over one transient pod.** The poll
treated `.status.failed >= 1` as terminal, but `51-upgrade-19-job.yaml` sets
`backoffLimit: 1` — so a single evicted or OOM-killed pod sets that to 1 *while
the Job is still retrying and may yet succeed*. One unlucky pod on tenant 3 of 5
would stop the fan-out and revert the image. Now tests the Job's `Failed`
**condition**.

**8. A cancelled run could leave every tenant at zero replicas.** Between the
scale-down and the roll-forward step, Cadra is down; a cancellation or a
`timeout-minutes` hit can kill that step mid-`kubectl` with no automatic
recovery. Restoring replicas is now its **own `always()` step, ahead of any
decision about images** — the cheapest, most urgent action runs first, and the
image the deployment still carries is the one that was serving anyway.

**11. Capture redaction covered bodies but not headers.** `Set-Cookie` on an
`/auth/*` response carries an Odoo session id, and response headers were being
written verbatim into the directory CI uploads for 14 days. A session cookie is a
credential. Now redacted: `authorization`, `cookie`, `set-cookie`, `x-api-key`,
`proxy-authorization`, on both request and response.

**12. My import-wizard branch misbehaved when no asset matched.**
`search(..., limit=1)` can be empty, `write()` on an empty recordset is a silent
no-op, and my new code additionally wrote a note claiming *"the asset carries
(none)"* about an asset that does not exist. It also cleared the validation
step's preview note on the non-drift path. Both fixed: an empty match is now a
line `error` with a reason, and `status_note` is only written when there is
something to say.

### Fixed — quality

**4. `test_quick_submit` was vacuous.** `("data" in body and "meta" in body) or
"error" in body` passes for any JSON envelope at any status, so it could not
detect a regression of the thing it claimed to pin, and its docstring wrongly
said the envelope "carries the original message". It now asserts a canonical
error code (against a new `CANONICAL_ERROR_CODES` set in `conftest.py`), a
`request_id`, and that `details.http_status` agrees with the HTTP status —
without pinning the endpoint to 500, which would pin a bug.

**9 + 10. Guidance that dead-ends.** `merge_creds` can legitimately write a file
with no `CLIENT_SECRET`, and the resulting message told you to re-run bootstrap,
which would do the same thing again. And "run `scripts/bootstrap.sh` against that
database" is not a thing the script supports — it takes `POSTGRES_DB` from
`.env`, not an argument. Both messages corrected in `conftest.py`,
`tests/README.md` and `bootstrap.sh`.

**14. `print-url` branched on another module's error string.**
`str(problem).startswith("Invalid tag_id")` coupled the 400-vs-404 decision to a
message literal in the barcode station — reword it and a 400 silently becomes a
404. `v1.py` now decides by parsing `tag_id` itself.

**15 + 16. Small correctness.** `null` removed from two `enum` lists (redundant
beside `nullable` and a validator irritant); `format: date-time` dropped from
`printed_at`/`affixed_at`, which are naive Odoo datetimes with no offset and so
are not the RFC 3339 that format promises — replaced with a description that says
what they actually are. And the workflow's summary block no longer exits
non-zero on the success path, which was a landmine for whoever adds `set -e`.

**17. Seven test payloads still sent the now-rejected `asset_tag`.** They passed,
but each collected a `_warnings.rejected_fields` block it never asked for — and a
fixture that sends a field the API drops is a fixture that lies about what it
created. Removed from `conftest.py`, `test_assets.py`, `test_depreciation.py`
(×4) and `test_depreciation_settings.py`.

### Accepted, not fixed

**13. `/auth/login` still mints `["*"]`.** Already flagged above and in the open
questions. It needs a group→scope mapping, which is a design decision.

### Confirmed clean by the reviewer

No stored fields added anywhere in the diff (so this is not a multi-tenant
migration); no `_sql_constraints`; `err()` is in scope in `_http_response` and
the new branch cannot recurse or mask an exception; the `FAILED` handshake
between workflow steps is correct, including that a `$GITHUB_ENV` write
overrides the job-level default; the `sed` image substitution matches the
deployment manifest exactly; `REPLICAS` is captured before the scale-down;
`merge_creds` handles values containing `=`, and its `&&` and `|| true` do not
trip `set -euo pipefail`; the serial-mismatch tests are not vacuous; the
`import_source` enum matches the model selection.

---

## Test output — verbatim

Full suite, `CADRA_API_BASE=http://jaizbankplc.localhost:8069`:

```
..............................xx....ssssssssss.......................... [ 31%]
.............................................ssssssss.ssss.............. [ 62%]
........................s............................................... [ 93%]
............ss                                                           [100%]
============================ cadra api test report =============================
Report: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-report.md
Captured responses: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-responses/
203 passed, 25 skipped, 2 xfailed in 22.25s
```

Re-run after every verification fix above; same result.

The 25 skips are the admin-scoped tests (the suite's token has no `admin`
scope), as documented. The 2 xfails are the two pre-existing
`myservice_barcode_station` lookup bugs. **No failures, and no xpasses.**

`tests/test_tagging.py` in full — 23 passed, including the eight added here:

```
test_affix_rejects_a_serial_that_does_not_match                       PASSED
test_affix_accepts_a_matching_serial                                  PASSED
test_affix_serial_match_ignores_case                                  PASSED
test_affix_serial_is_optional                                         PASSED
test_affix_refuses_to_verify_a_serial_against_a_record_that_has_none  PASSED
test_asset_tag_is_not_writable_on_create                              PASSED
test_asset_tag_is_not_writable_on_patch                               PASSED
```

`tests/test_source_guards.py` — 15 passed (standalone, no instance needed).

`docs/api/smoke_test.py` against `jaizbankplc` — complete, negative checks
returning `401` / `404` / `400` as expected.

OpenAPI document: 6 `$ref`s, **none unresolvable**; `asset_tag` gone from the
POST `/assets` request schema; `serial_number` present in the tag-affixed
schema; `Asset.tag.deprecated == true`.

---

## Acceptance

| Criterion | Status |
|---|---|
| Eight databases consistent after #46's columns | ✅ table above, all eight |
| `upgrade-19.yml` fixed and the fix explained | ✅ both traps, plus the fail-safe hole I found in my own first version |
| `.env` untracked | ✅ |
| secret rotated | ⛔ **owner-blocked** — the permission layer refuses `rotate_secret()`; command above |
| Vendra updated | ⛔ **owner/Vendra-side** — and it needs the `nrs19` credentials and `category_id: 17`, not just a new secret |
| a mismatched serial is rejected | ✅ verified live + 5 tests |
| a client with no scopes can do nothing | ✅ verified live + source guard |
| `docs/demo-contract.md` exists, every call verified live | ✅ re-verified after the review fixes |
| fresh-reviewer pass | ✅ 17 findings; 15 fixed, 1 accepted-and-flagged, 1 already reported |
| Full suite green, quoted verbatim | ✅ 203 passed, 25 skipped, 2 xfailed |

---

## What I left behind on `nrs19`

Four verification assets, created through the API and deliberately not deleted
— `docs/demo-contract.md` quotes asset **11879** and its tag `NRS-PC-001`, and a
contract whose worked example does not exist is worse than one with a stray
record in it.

| id | asset_code | name | state |
|---|---|---|---|
| 11879 | NRS-AST-047513 | HP LaserJet Pro M404dn (handoff-04 verification) | `affixed`, `is_tagged: true` |
| 11881 | NRS-AST-047515 | Print-path verification unit | `issued` |
| 11882 | NRS-AST-047516 | Print-path verification unit | `printed` |
| 11884 | NRS-AST-047518 | HP LaserJet Pro M404dn (handoff-04 verification) | `affixed` — second run, after the review fixes |

All three carry `import_source: vendra` and are trivially identifiable. The
scopeless probe client used for the empty-scopes proof **was deleted** — the
remaining clients on `nrs19` are `test_client`, `tag_issuing_unit`, `vendra`.

Real data untouched: `nrs19` still holds its 11,878 seeded assets.

---

## Open questions

1. **`/auth/login` grants `["*"]`.** Any Odoo user who can log in currently
   holds `tagging:write`. What should the group→scope mapping be? Until it
   exists, the Tag-Issuing Unit separation holds for API clients and not for
   session users.
2. **Was adding `ensure_vendra_client()` the right call?** Reasoning above. It
   is one function and trivially removable.
3. **`docs/api/.creds` (the shared file) still exists** and still holds
   `jaizbankplc`'s credentials. I left it as the fallback so nothing breaks
   mid-flight. Delete it once every tenant has a `.creds.<db>`?
4. **CLAUDE.md's Status table records intent as completion** (the four items at
   the top of this report). Worth a convention — "ruled" versus "landed"?

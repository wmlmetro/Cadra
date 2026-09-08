# Handoff 12 — What the API says when it is wrong

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/honest-answers`.

> Report 11 stands, in full, including both places it refused the instruction. The barcode station finding is the seventh time this protocol has caught me being wrong, and it is the first time the cost of compliance would have been a working screen removed from a live tenant. The evidence you brought — five dashboards mounted in a real browser, byte sizes before and after, the shim traced to the module that provides it — is the standard. Keep bringing it.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/honest-answers && git push -u origin fix/honest-answers
```

**Needs the owner, before you start:** the handoff 11 PR into `dev` is still unmerged (`fix/retire-dead-screens`, three commits). Branch from `dev` anyway; if the merge has not happened by the time you push, say so in the report and do not merge it yourself.

---

## Why this handoff exists

Report 11 found two live defects and three small true things. All five share one shape: **the system answers, the answer is wrong, and nothing about the answer looks wrong.** Rule 3 in `CLAUDE.md` already names this — *"anything that silently degrades is a defect even when it returns 200"* — and this handoff is that rule applied to what report 11 found.

The custody chain (report 11 §1, question 3) is **not** in this handoff. It is a new model, a new route, and a backfill; it gets handoff 13 to itself. My ruling on it is at the bottom so you can build against it when it comes.

---

## A · The cap must stop lying — the largest item

**Report 11 §1 and INT-10 §2.11.** An external token sees the first 100 records of any resource and is told `total_estimate: 100`. Measured live: `jaizbankplc` holds 2,316 assets; the API reported 100, `next_cursor: null`, and `export.csv` returned 101 lines.

**My ruling: the cap stays. What it says about itself changes.**

The cap is deliberate — `utils.py:597` calls it *"the paywall safeguard"* — and I am not overturning a commercial control on a technical argument. But three things about it are indefensible:

**A1 · It keys off the wrong thing.** `_request_is_frontend()` reads the `aud` claim, which only `POST /auth/login` stamps. So the rule in force is *"browsers are trusted, programs are not"* when the rule intended was *"our own systems are trusted, third parties are not."* Vendra holds a machine credential. So will Audit. **We have pointed a partner paywall at our own customer.**

Move it onto the client record. `myservice.api.client` already carries `token_ttl_seconds`, so per-client limits are an established pattern there, not a new idea:

```python
max_page_limit  = fields.Integer(default=0)   # 0 = use the external default
total_record_cap = fields.Integer(default=0)  # 0 = use the external default
                                              # -1 = uncapped
```

Stamp the resolved values into the JWT at mint time, next to `scopes`, so `parse_limit()` and `paginate()` read claims rather than hitting the database on every list call. **Default 0 everywhere**, meaning today's 100 — a client nobody has provisioned behaves exactly as it does now, and this change is invisible until somebody deliberately raises a limit. The frontend keeps its uncapped path via `aud`; that stays, unchanged, as a second route to the same answer.

**A2 · `total_estimate` must always be true.** Whatever the cap does to the rows returned, the count is a fact about the register and there is no version of "helpful" in which we misreport it. `search_count` on the unclamped domain, always. This is the single most important line in the handoff: an auditor who exports 100 rows and is told there are 100 has been given a false statement by a government system, and neither they nor we would find out.

**A3 · Truncation must announce itself.** When the cap bit, the response says so — in `data._warnings`, the mechanism rule 3 already uses for dropped fields:

```json
"_warnings": {
  "truncated": {
    "cap": 100,
    "total": 2316,
    "reason": "This credential is limited to the first 100 records of any query.
               Filter the query, or contact WestMetro to raise the limit."
  }
}
```

Same on `/assets/export` and `export.csv` — the CSV bypasses the envelope, so it gets an `X-Cadra-Truncated: 100/2316` response header and a final commented row. A file that is silently a tenth of the register is the worst artefact in this entire finding, because it gets saved, emailed and cited.

**A4 · Provision the two clients that must not be capped.** On every tenant: the `vendra` client, and whatever the audit client is called when INT-10 has one. `total_record_cap = -1` on both. Do this as a data migration keyed on `client_id`, not by hand — report 11's own lesson, and the one that has cost this programme three deployment failures: **state that lives in records rather than code does not move when code moves.**

**Acceptance.** A capped token asking `limit=2000` against 2,316 assets gets 100 rows, `total_estimate: 2316`, and the `truncated` block. An uncapped client gets all of them and no block. A client with `max_page_limit = 500` gets 500. `export.csv` carries the header. A guard test that fails if `total_estimate` is ever derived from a capped search — write it so it catches the regression by construction, the way the concurrency guard derives membership from behaviour rather than a list.

## B · A 401 that names its cause — to the log, never to the caller

**`v1.py:224-230`.** One search, one message, four distinct causes:

```python
client = ...search([("client_id", "=", client_id), ("active", "=", True)], limit=1)
if not client or not client.check_client_secret(client_secret):
    return err(ERR_UNAUTHORIZED, "Invalid client credentials", status=401)
```

Wrong secret, no such client, client exists but `active = False`, and **client id in the wrong case** — `=` on a Postgres varchar is case-sensitive — are one answer. The owner lost an hour on staging last week to the fourth of those: the client was `Vendra`, the config said `vendra`, and the API said "Invalid client credentials" to both.

**The response body does not change.** Telling an unauthenticated caller *which half* is wrong is a client-id enumeration oracle, and a 401 that distinguishes "no such client" from "wrong secret" is a worse system than a slow debugging session. That is deliberate, and say so in the code comment so nobody helpfully "improves" it later.

**What changes is that the `request_id` we already return becomes lookup-able.** Today it is a token with nothing behind it — we hand the caller an identifier and keep no record it was ever issued. Log at `WARNING`, server-side, carrying the `request_id` and the actual cause:

```
[cadra.auth] request_id=<id> client_id=<as sent> outcome=no_such_client
[cadra.auth] request_id=<id> client_id=<as sent> outcome=inactive
[cadra.auth] request_id=<id> client_id=<as sent> outcome=bad_secret
[cadra.auth] request_id=<id> client_id=<as sent> outcome=case_mismatch matched=<the real one>
```

The fourth needs one extra query, on failure only: `ilike` the id, and if that finds a client the exact match did not, you know precisely what happened and can say so in the log. **The client id as sent is not a secret** — it is half of a credential pair and it arrived in the clear. The secret never appears, not hashed, not truncated, not in a length.

Then log a success line too — `outcome=ok` with the client id — because a log that only records failures cannot answer "did this credential ever work", which is the second question anybody asks.

**Acceptance.** Four failing shapes produce four distinct log lines and one identical response body. A test asserts the bodies are byte-identical across all four. `docs/` gains a short "reading an auth failure" note pointing at the log line format, because the person debugging this at 11pm is not going to read the controller.

## C · Three small true things

**C1 · `security_navbar.css` — ruling: relocate, do not delete.** You are right that it is dishonest where it sits: a file named for a retired module that restyles the top navigation of every screen in the product. But that makes it **misfiled, not dead**, and deleting it is a visible design change to every user, made as a side effect of a cleanup. Move it into the theme module where global navigation styling belongs, under a name that describes what it does. Byte-identical content, no selector touched. Prove no visual change with a before/after screenshot of one backend page — the dropdown in particular, since that is where the two stylesheets interact.

The dark-dropdown-under-a-white-navbar issue you flagged is real and it stays open, filed as a design question, not fixed here.

**C2 · `do_notify` into the shim.** Three lines in `legacy_compat.js`. The barcode station's "Request replacement" writes the record and then throws, so the list never refreshes and it reads as nothing happened. A write that succeeded and looks like it failed is the exact inverse of everything else in this handoff, and it deserves the same objection.

**C3 · `.env.example` says `odoo`.** Put the correction in `CLAUDE.md` — name the database the documented test command actually works against, and one line on why the `odoo` database fails (a 15-era leftover a 19 worker refuses, reported as a Postgres operator error that names nothing relevant). Whoever hits it next should lose two minutes, not an afternoon.

---

## Report

`docs/handoffs/12-REPORT.md`. Short. In it:

1. **Whether anything else in the API derives a count from a capped search.** A2 fixes the list endpoints; report whether any dashboard route, aggregate or report does the same thing somewhere I have not looked.
2. Whether stamping the limits into the JWT creates a staleness problem — a client's cap raised while a token is live keeps the old value until the token expires. Say whether that is acceptable at a 1-hour TTL or wants a fix.
3. Anything the auth log would now write that should not be written. You have the better view of that than I do.
4. Wall-clock.

---

## Two things for me, not you

**The custody chain (report 11 question 3) — my ruling, so handoff 13 can be built against it.** Yes: `nrs.asset.custody`, append-only, no write and no unlink after create, exposed on the asset as `include=custody` and as its own route. **Yes, backfill the 217 tracking rows** — they carry actor and timestamp, so the reconstruction is faithful. And every backfilled row carries `source = 'tracking_backfill'` on its face, so nobody ever mistakes reconstructed history for recorded history. It will look sparser than the register, and that is the honest picture: it covers only changes made since `custodian_id` became tracked, and saying so is better than a complete-looking chain we cannot stand behind. An auditor who is told where the record starts can work with it. One who discovers it later cannot trust any of it.

**The cap has a twin on the Vendra side and I own that.** `find_assets()` in Vendra's Cadra client already refuses to trust `total_estimate` — the docstring calls it *"a capped estimate, not a row count"* — but it makes a single request with no cursor loop. So a goods receipt of 150 laptops asks Cadra which of its assets are tagged, gets 100 answers, and concludes something false about the other 50. Nothing in Vendra is wrong; it is correctly consuming an endpoint that lies to it. It goes in Vendra's queue and it is fixed on both sides or on neither.

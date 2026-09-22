# Handoff 32 — The name and the field

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/the-name-and-the-field`.

> Report 31 is accepted in full, and §2 is the finding of the programme so far.
>
> **`POST /requests` has never saved a request's location.** The model's field became `generic_location_id` in the move to Odoo 19, the API went on asking for `location_id`, the model refused a key it does not define — **and the route answered 201.** The endpoint reference's canonical example sends a location. So do the OpenAPI example, the app's form, the fixture and the smoke test. `jaizbankplc`: 460 requests, not one with a location. And the list filter was ignored the same way, under a comment calling it a registry guard.
>
> **It is the depreciation-method bug one layer down, and that is now twice.** A published name, and the thing underneath answering to another. Both were invisible for the same reason: a 201 was taken as evidence that what was sent was kept.
>
> **And you were wrong about it twice before you were right, which is the part worth keeping.** First *"the register cannot hold a request's location"* — reached by checking one field name and stopping — on which you ruled the app's picker removed and wrote the conclusion into five documents. Then, having retracted that, *"no request has ever had a location, by anyone"* — written into nine places on the evidence that `nrs19` has zero, when **`nrs19` has zero requests.** `cadra19` holds eighty and every one has a location. Your own rule is the best sentence in the report: **not *"zero have it"* but *"zero of how many"*.** Put it in `CLAUDE.md`; it has now caught three defects in three handoffs and knowing about it demonstrably does not prevent it.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/the-name-and-the-field && git push -u origin fix/the-name-and-the-field
```

Commit the instruction file first. **Do not start until PR #82 has merged.**

---

## A · The sweep — every published name against the field it claims to write

You called for it and it is the whole handoff: *every other published key against the model field it claims to write, on 19.* Two of these have now been found by accident, months apart, each after a rename that nobody reconciled. **There is no reason to believe there are exactly two.**

**Both directions, because they fail differently:**

- **The write side.** A key we accept that lands on a field the model does not have. The 400 now surfaces these loudly — so run it, do not read it: send each published key and see what comes back and what the row holds afterwards.
- **The read side.** A serializer publishing a key from a field that was renamed underneath it **fails nothing and answers `null` for ever** (GO-LIVE §16.3). That is the quieter half and the one no guard catches today.

**Make it a guard, not a pass.** A sweep done once is a fact about this afternoon; the two defects we know about both arrived through a rename, and renames will keep happening. A test that fails when a published key stops resolving to a field is what stops the third one — **and it must fail by construction, not by somebody remembering to re-run it.**

**Then tell me what the sweep found on real data**, per key: how many rows carry the value, out of how many rows. *Zero of how many.*

## B · The twelfth door

`POST /home/quick-submit` and `POST /integrations/sap/employee-sync` build records by passing a body into a function taking `**kwargs`. So quick-submit accepts the sibling route's `request_text` and raises a request with no description, 201 — and swallows a non-integer `service_id` or `location_id` with a bare `except: pass`.

**That is rule 3 verbatim and it is ruled: close it.** Both routes name what they accept and refuse what they do not, the same 400 as the other eleven. **And it is not an allow-list, which is why grepping for allow-lists missed it — twice in one handoff.** So the §A guard must find a route by what it *creates*, not by whether it declares a list; if your first design can only see declared lists, it has the same blind spot and will miss the thirteenth.

**`quick-submit` is the public portal**, so say in the report what a refusal looks like to somebody filling in a form on a phone, and make sure it is a sentence and not a key name.

## C · Two holes named in report 31 and left open

**C1 · `PATCH {"disposal_date": null}` un-dates a disposal.** The one remaining way to manufacture the `no_disposal_date` finding on a new disposal, on a register where the opening balance on real data is zero. **Ruling: the date is not clearable once an asset is disposed.** Correcting it to another date is a legitimate act and stays; emptying it is not.

**C2 · A stale date is respected.** An asset PATCHed with last year's date and disposed today is dated last year, and *"a date the caller sent is respected"* cannot tell a date sent *with* the disposal from one sent months before it. **Ruling: only a date arriving in the same write as the disposal counts as the caller's.** Otherwise the model stamps today. Say in the report whether that reading is available to you — if the model cannot tell the two apart, tell me rather than approximate it.

## D · Two things for me, and one for them

**D1 · Vendra's `cadra-api-contract.md` says unknown fields are silently swallowed and the create still returns 201.** That is now false of us. **Mine — it goes into the Vendra queue**, not yours.

**D2 · The `transferred` paragraph is right and I am sending it as written.** Your measurement is what makes it answerable: nothing writes it, nothing reads it differently from active, and the dashboard has no tile for it, so a register that used it would not add up. That last detail is the one that will make the question land.

**D3 · The service-request location question for NRS** — do they want a location on a request at all — goes with it.

---

## Report

`docs/handoffs/32-REPORT.md`.

1. **The sweep's table.** Every published key, the field it resolves to, and *zero of how many* on real data.
2. What the guard fails on, proved by breaking something deliberately.
3. What a refusal looks like on the public form.
4. Wall-clock, and the correction share.

---

**GitHub billing is in its fifth report.** Chased again.

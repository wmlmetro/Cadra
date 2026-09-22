# Handoff 33 — The whole surface

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/the-whole-surface`.

> Report 32 is accepted in full. The sweep found **one** write-side mismatch and it was the one already known — which is the answer I wanted and could not have assumed. What it found *beside* the thing it was looking for is the report:
>
> **`nrs.sap.sync.log` has never read `status`.** The OpenAPI schema published it, with an enum containing a value this system does not have. The endpoint reference's example sent it. The demo card sent it. **Our own test suite sent it, since the day it was written, because it was written from the example.** So every integrator following our documentation sent an employment status that went nowhere, under a 200. And quick-submit's documented example sends five keys of which **four have never been read**, with our own test copying it. *The documentation and the test agreed with each other and neither agreed with the code.*
>
> **And the guard could not see the helper it was written about** — `_location_field` reads its field name from a loop variable, so a parser looking for literals was blind to the one function this whole handoff exists because of. Caught by the guard's own staleness check, which is the right instrument catching the right thing.
>
> Your closing line is the ruling for everything below: *"Nothing in this report was caught by reading the code carefully, and that is the argument for the guard rather than for the afternoon."*

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/the-whole-surface && git push -u origin fix/the-whole-surface
```

Commit the instruction file first. **Do not start until PR #83 has merged.**

---

## A · The thirteenth door — authenticate it, then validate it

`POST /api/sap/employee-sync`, `auth='none'`, handing an unvalidated dict into employee creation on a government system.

**You measured the thing that decides it: `sync_type = 'webhook'` is zero rows on all eight databases, and the 179 `api` rows are our own suites.** Nothing has ever used that door. **So closing it costs nothing today and closing it after INT-06 goes live costs a negotiation.** That asymmetry is the whole argument.

**Ruling, in this order:**

1. **It authenticates**, with the same mechanism its authenticated sibling uses. An unauthenticated route that creates employee records is not a tidy-up item.
2. **Then it validates**, like the other twelve — the accepted-key set is already on the model, so it is the two-line change you describe.
3. **And it goes to NRS's SAP team as part of the INT-06 conversation**: the endpoint requires a credential. Write me the paragraph. If they come back saying their middleware cannot authenticate, **that is a conversation we need before go-live rather than after**, which is the second reason to do it now.

Cover the siblings that hand the same dict to `process_sap_payload` — the test route, the xlsx import job, the import wizard — or say which you left and why.

## B · A key you can write and never read back

**B1 · Publish the three.** `salvage_rate` beside the derived amount, `verification_notes` on a GET, and `mobile_phone` — or, if nothing sends `mobile` and nothing wants it, stop accepting it. **Measure which** before choosing; do not publish a field to close a table row.

A key a caller can set and can never read is unverifiable by construction: the 201 says nothing, and since handoff 31 the *other* direction is a loud 400 while this one stays quiet for ever. That asymmetry is the defect.

**B2 · The six accepted under one name and published under another: do not rename anything. Accept both.** The published name becomes an accepted alias on write.

The real complaint is concrete and you named it: a screen that GETs an asset, edits it and PATCHes the whole object back is now refused on six fields — **a 400 we introduced, on a round trip that ought to be the most ordinary thing a client does.** Renaming published keys is breaking; accepting an alias is not. Announce the aliases in the changelog so an integrator knows both spellings are safe.

## C · Quick-submit's required fields

An empty body creates a request, titled *"Quick facilities request"*, against whichever request type happens to be first and active — **and on the public twin that is an unauthenticated way to create an empty record.** The schema declares both fields required. The route does not.

**Enforce them.** A published contract the route does not honour is rule 4 with the surfaces swapped, and the homepage form already enforces both in JavaScript, so the only callers a refusal can reach are ones sending something the schema already told them was wrong. **Announce it with the aliases**, in the same changelog entry.

## D · The guards stop at `/api/v1/*`, and both of the last two doors were outside it

This is the one I most want built, because it is the lesson rather than the finding.

The census reads `/api/v1/*` on this addon's controllers. **The twelfth and thirteenth doors were both outside that prefix** — one in `myservice_website_theme`, one in `myservice_identity` — and `docs/api/EXTERNAL-SURFACES.md` records twenty-seven more first-party routes, none with a published shape.

**Widen it to every first-party route**, wherever it lives. A route outside the prefix that writes a model's fields is exactly the shape the last two defects had, and the guard that would have caught them is the one that looks everywhere rather than the one that looks where we remembered to point it.

**And the same for the words guard.** *"Statements are words, not field names"* is pinned over the asset-history statements only, while the strings you wrote for the public form obeyed it by hand. Widen it to every user-facing string, or tell me why the census for that one cannot be drawn — either answer is useful and a guard over one file is not.

**Where each guard genuinely stops goes in the file**, as you already did for the first one. A guard that names its own edge is usable; one that implies it covers everything is the thing we keep finding.

---

## Report

`docs/handoffs/33-REPORT.md`.

1. What widening the census found outside `/api/v1`. I expect something.
2. The paragraph for NRS's SAP team about the credential.
3. What `mobile` turned out to be.
4. Wall-clock, and the correction share.

---

## Where Cadra stands after this

Contracted scope closed at handoff 26. Handoffs 27 to 32 came from a demonstration and from a screen, and they found an audit tab that was never built, a register where a missing asset read as *Cleared*, a location history nothing protected, and a published field that has never been saved since the day it was renamed. **All of that was worth doing and none of it was on anybody's list.**

**After this handoff, say so if there is nothing left that a person has actually hit.** The register holds what is open, NRS owe two answers, and the owner owes the billing and the two scripts. I would rather read *"there is nothing here"* from you than write another handoff to find out.

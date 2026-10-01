# Handoff 38 — Before the demo

**Branch:** `fix/before-the-demo`
**Report:** `docs/handoffs/38-REPORT.md`

> ## RUN THIS ONE. NOT 37.
>
> `docs/handoffs/37-the-doors-and-the-red-tests.md` is written and waiting and **must not be started yet.** There is a client demo tomorrow, 2 October. 37 touches the identity webhook and the depreciation module; neither belongs in a working tree the day before a demo. When a Vendra Builder had two pending handoffs it took the older one — do not repeat that.

---

## 0 · Why this handoff is shaped differently

NRS met us on 30 September and, for the first time, said plainly what their problems are. Most of what they asked for we already have. Two of the things we described in that room do not work the way we said, and **one of them is in the demo path**.

So this is not a normal handoff. **The governing rule is: do not break the demo.** A known gap we can speak to is better than a regression nobody finds until it is on a screen in front of their director. If a change starts to spread beyond the shape described here, stop and report rather than finishing it.

Scope is two items, a third only if the first two are done and verified, and an explicit list of things to leave alone.

---

## A · A scanned serial number must find its asset

**The problem.** We told NRS, in the room: *"if you bring 100 laptops inside this room now, I just scan the serial number, it shows me the asset details immediately."* They then named scanning as one of the two things they care most about.

The scan box on the barcode station searches **tag number and asset code only**. `lookup_tag` in `myservice_barcode_station/controllers/main.py` builds a domain over `name` and `asset_code`; there is no `serial_number` term. So:

- scanning the tag → works
- scanning the serial of an asset **not yet tagged** → works, because the untagged picker does search serials
- scanning the serial of an asset that **is** tagged → finds nothing

The last case is the auditor walking round with a scanner, which is exactly what they described.

**And we publish the opposite.** `myservice_api/controllers/v1.py` documents the parameter on **two** endpoints as *"Tag, asset code, or serial number to look up"* — `/api/v1/barcode/lookup` and `/api/v1/tags/lookup`, the latter via `portal_lookup`. The documentation has been making a promise the code does not keep.

**What to do.** Make the lookup search serial number as well, so the published description becomes true rather than editing the description to match a narrower reality. Both endpoints.

**Four things to get right, and the first is the one I care about:**

1. **A tag number and a serial number could in principle collide.** Decide the precedence, write it down in the code, and make it deterministic — my instinct is tag, then asset code, then serial, so a scanned tag never loses to a coincidentally equal serial, but you have the data and I do not. If a collision is impossible for a reason you can demonstrate, say what the reason is rather than asserting it.
2. **Say which field matched** in the response, so the screen can tell a user *"found by serial number"*. A lookup that silently changes meaning is how the next false claim gets made.
3. **Exact match or partial?** The tag path is an exact, uppercased match on an active tag. Serials are messier — case, whitespace, and leading zeros. Pick a rule, justify it, and make sure a serial with a trailing space from a scanner still works.
4. **Scrapped and inactive tags** must keep behaving as they do now. Do not widen that as a side effect.

---

## B · Reprinting a faded tag

**The problem.** Their words: *"let's assume you're an auditor walking around and you notice an air conditioner tag is weak or it's no longer very clear. You can reprint a tag for that particular asset."*

The model already does this properly. `nrs.asset.tag.label` has `action_request_replacement` → `action_approve_replacement`, which scraps the old label, mints a new number, and keeps `replaces_id` / `replaced_by_id` so the history survives. `replacement_reason` already includes *Damaged / Unreadable*.

**It is reachable only from the Odoo back office.** There is no API route and no control in the React app — the app only displays a `pending_replacement` count.

**What to do.** Expose it: an API route for requesting a replacement, one for approving it, and a control in the barcode station. Three things to decide and state:

1. **Does a replacement need the two-person treatment?** The model has a request step and an approve step, which implies yes. Approvals are the control NRS asked for by name, so if you make this one-click you are quietly contradicting that. If request-and-approve is right, use the pattern handoff 35/36 established rather than inventing a second one.
2. **`action_request_replacement` never writes `replacement_reason`** — it sets state and requester only. The reason has to be typed on the Odoo form today. Fix that: the route should take the reason and record it, because *"why was this tag replaced"* is the whole point of the record.
3. **The old number must never come back.** Tag generation already scans scrapped labels so a number is never reused. Prove that still holds after a replacement, by doing one.

---

## C · Only if A and B are done and verified: IR number format

NRS volunteered this: *"Sometimes the IR number is not captured properly, where it's supposed to be zero. Sometimes we see O."*

There is no format validation at all. `ir_number` is plain text with a uniqueness constraint, so `IR0012` and `IRO012` are two different employees, both can exist, and uniqueness will never catch it. Exact-match lookups mean neither finds the other.

**This one has a trap, and it is why it is third.** Adding a constraint could make the SAP employee sync start refusing rows, or make existing bad data unsaveable — a new failure, the day before a demo. So:

- **Refuse on the paths a person uses** — the API write and the app.
- **On the SAP sync, report rather than refuse.** A row that fails the format should land somewhere visible as a data-quality finding, not break the import. We do not get to reject SAP's master data.
- **Touch no existing row.** No migration, no backfill, no normalisation pass. If `IRO012` exists on a tenant, it keeps working.
- Say in the report **how many existing rows would fail the new rule**, across the tenants. That number is worth having for Friday whether or not the validation ships.

If you cannot do all of that safely in the time left, **do not start it.** Report the count instead; the count alone is useful.

---

## D · Do not touch

Not suggestions. Each of these is a way to lose tomorrow.

- **The capture gate on goods receipt.** The serial-count refusal is the single most load-bearing control in the product and it is step two of the demo. Nothing near it.
- **Serial auto-generation for items with no manufacturer serial.** It is the most valuable thing to come out of the meeting and it needs NRS to tell us what their numbering should look like. It is a handoff, after Friday, with their answer in hand.
- **Location on the Vendra hand-off.** Also worth doing, also not now: it needs a warehouse-to-location mapping that does not exist yet, and it spans both repositories.
- **The depreciation module.** It has two red tests on `dev` already. 37 fixes them. Leave both alone.
- **The identity webhook.** 37's subject. Not now.
- **Anything on `nrs19`'s data** beyond what A, B and C need. Report 36 left evidence on that tenant deliberately and two reports cite it.

---

## E · Verification — a demo happens in a browser

The usual rules, plus one that matters more than normal: **everything in A and B must be verified in a browser, by you, on the built and deployed front end.** Not by a passing test, not by a curl against the API.

The reason is in our own history. The owner could not see the warranty fields because the front end had not been rebuilt — Frappe serves the built bundle, and the source being right is not the same as the screen being right. Cadra's React app has the same property. **If you change the app, build it and deploy it, then look at it.** A green test on an unbuilt front end is the exact defect class this programme is named after.

Specifically:

- Scan a tag, scan an asset code, scan the serial of a **tagged** asset, and scan the serial of an **untagged** asset. Four lookups, four transcripts, and say which field matched each time.
- Scan a serial with a trailing space, as a scanner would send it.
- Request and approve a tag replacement end to end. Show the old label scrapped, the new number minted, the chain intact, and the reason recorded.
- Confirm the old tag number cannot be reissued.
- Suites with denominators. No run reporting `of 0 tests`.
- The standing pass: **every sentence you write in code, comments and docs checked against something you measured.** It has caught something every time, including a comment whose label described a guard the branch could never reach.

And one explicit instruction: **if A or B cannot be finished and verified properly, leave it out and say so.** I would rather walk into that room knowing a thing does not work than find out from their director's face.

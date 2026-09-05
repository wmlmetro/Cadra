# Handoff 04 — Land tag capture, close the credential hole, ready Cadra for the end-to-end demo

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #46 merges. **Branch:** `fix/demo-readiness` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull        # after the owner merges #46
# per-tenant upgrade for #46's seven stored columns, all eight local databases,
# then the verification table. Paste it into the report.
git checkout -b fix/demo-readiness
```

### Needs the owner

- **Merging #46 and this handoff's PR.** Standing limitation, now expected.
- **The production per-tenant deploy of #46** (seven stored columns) — but **fix the `upgrade-19.yml` traps in Part A first**, because you found them the hard way and the next person should not.

---

## Report 03 is accepted

**You were right about the print funnel and I was wrong.** I wrote "the hooks are already the single funnel" from reading two method names. Three other paths print a tag without touching either — including the barcode station handing the browser a raw `/report/pdf/...` URL where none of our Python runs at all. A `printed_at` that is silently incomplete is exactly the class of defect this handoff existed to remove, so moving the catch-all to `_render_qweb_pdf` while keeping explicit stamps at the known call sites is the right shape.

**The verification pass found three audit-integrity bugs in the module built to fix audit-integrity bugs** — a print hook stamping evidence onto unrelated assets, a repeat confirmation destroying the original affix record, and a tag awaiting replacement reading as never tagged. That is the fresh-reviewer step earning its keep for the third handoff running, and V1 in particular (fabricated evidence on the wrong asset) would have been very hard to find later.

**And thank you for the `.env` finding**, which had nothing to do with your assignment and mattered more than most things that did.

### Rulings on your questions

1. **`printed` at the render layer — yes, right semantics.** It records that a PDF was generated. A print queue would be more honest and is not worth it; document the limit and move on.
2. **Deprecate `data.tag` — yes, by annotation.** `deprecated: true` on the OpenAPI property plus a doc note. Do not remove it: breaking a published field to fix a naming problem is not a trade worth making with a live consumer.
3. **Yes — the affix endpoint should accept and verify `serial_number`.** The spec says *"the serial-to-tag match is recorded at the point of physical tagging"*; checking one side is half a control. Accept it optionally, and when supplied, reject a mismatch. Vendra holds the serial, so this closes the loop rather than adding friction.
4. **`.env` — untrack it, and rotate the secret.** Owner's decision: `git rm --cached .env` (bootstrap recreates it from `.env.example`), then rotate the dev client secret that was briefly written into it. Nothing leaked; this is precaution, not response. Note in the report that Vendra's `site_config` holds that secret and must be updated in the same pass, or INT-03 breaks the moment it rotates.
5. **`asset_tag` comes out of `_WRITABLE_FIELDS` — yes.** A client that can PATCH `tag` until it no longer matches the physical label defeats the control you just built, and then gets a confusing 400 from that control. It is a breaking change to a published contract, but **the only live consumer is Vendra and it does not write that field** — I have checked. Announce it in the report so it lands in Vendra's CLAUDE.md too. Fix the same drift path in the import wizard and the seed scripts.
6. **The Tag-Issuing Unit gets its own API client, scoped to `tagging:write` only** — and provisioning it becomes a documented step, not a shell command someone remembers. **Separately: fix the empty-scopes-means-wildcard behaviour.** A client created with no scopes receiving everything is a privilege-escalation waiting for a typo, and it is the exact opposite of what the independent-unit separation is for. Treat empty as "no permissions", and say in the report whether any existing client is relying on the old behaviour.

---

## Part A — the traps and the hole

1. **`upgrade-19.yml`**: the roll-up step re-applies the deployment with the new image, so the first tenant's run puts *every* tenant on new code while the rest still hold the old schema — the V1 hazard, industrialised. And `target_db` being a single string means four dispatches, which GitHub silently cancels when queued. Fix both: upgrade every tenant before the image rolls forward, and take a list.
2. **`.env`** — untrack, rotate, update Vendra's `site_config` in the same pass (coordinate with the Vendra side; INT-03 authenticates with that secret).
3. **`docs/api/.creds` is one file for eight tenants**, and both bootstrap scripts rotate unconditionally — so bootstrapping any tenant silently invalidates the suite for whichever tenant it was aimed at. Make it per-tenant, or make the rotation opt-in. This cost the Vendra side real time too: its handoff 04 was blocked at the first live call by exactly this drift.

## Part B — the rulings above

Items 2, 3, 5, 6 as code and docs. Tests for the serial mismatch rejection and for empty-scopes-denies.

## Part C — ready Cadra for the cross-system demo

The next Vendra handoff builds **one runnable script that drives the whole chain**: a goods receipt in Vendra → five assets in Cadra with provenance → tags printed → tags confirmed affixed → the assets reading as genuinely tagged. That is the artefact we show NRS, and it is the first thing that proves the September Integration Flow as written rather than in halves.

Your job here is the Cadra half being *drivable*:

- The tagging credential provisioned and documented (item 6), so the demo authenticates as the Tag-Issuing Unit rather than as an admin — the separation is the point of the control.
- The print and affix steps callable from outside the UI, with the exact calls written down.
- **`docs/demo-contract.md`** — the precise sequence the Vendra side will drive: endpoint, scope, body, expected response, per step. Vendra builds against this document, so it must be true rather than aspirational; verify each call live before writing it down.

## Acceptance

- Eight databases consistent after #46's columns; `upgrade-19.yml` fixed and the fix explained.
- `.env` untracked, secret rotated, Vendra updated, nothing broken.
- A tag affixed with a mismatched serial is rejected; a client with no scopes can do nothing.
- `docs/demo-contract.md` exists, every call in it verified live.
- Full suite green, quoted verbatim.

## Report

`docs/handoffs/04-REPORT.md`. Push, open the PR, name the merge as owner-blocked, notify the Architect.

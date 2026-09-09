# Handoff 16 — The reports an auditor asks for

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/audit-reports`.

> Report 15 accepted in full. **Twenty-four of fifty handlers were hiding something live**, against the two report 13 found by accident, and four features had never worked on any tenant since the day they were written. The four `cr.rollback()` import loops are the worst thing either repository has turned up: one unmappable employee erased every employee written before it in the batch while the response reported each one `"status": "success"`.
>
> And `cadra_route` swallowing the retries Odoo owns above it is the finding that justifies the whole exercise — *the unwrapped route was the one that worked*, in the handler whose entire job is to catch everything. Nobody would have audited that.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/audit-reports && git push -u origin feat/audit-reports
```

**Needs the owner:** the handoff 15 PR into `dev`.

---

## A · Open question 1 — you are wrong about the Fleet Command tab, and it is my mistake you have repeated

**Your finding:** `myservice_dashboard/static/src/js/dashboard.js` is an `odoo.define` module requiring `web.AbstractAction` and `web.rpc`, neither of which exists under `web/static/src/` on 19, so the tab is dead and the panels you fixed reach a user only through the API and the SPA.

**The premise is true of Odoo core and false of this codebase**, which is word for word what you told me in report 11 when I asked you to retire the barcode station. `myservice_nrs_base/static/src/js/legacy_compat.js` re-provides `web.core`, `web.rpc`, `web.ajax`, `web.session` and `web.AbstractAction` as OWL-backed shims; it is bundled at `__manifest__.py:30`; and `myservice_dashboard` declares `myservice_nrs_base` in its `depends`, so the shim is guaranteed to load first.

**And report 11 measured it.** In a real browser, logged into `jaizbankplc`: `myservice_dashboard.action_myservice_dashboard` **mounted, 18,867 bytes of DOM, zero console errors** — one of the five you proved render through exactly that path, and it was re-verified byte-identical after the retirement.

**So before anything else in this handoff: open the tab in a browser on `jaizbankplc` and report what happens.** I am not asking you to accept my reasoning over yours; I am asking for the kind of evidence that settled this last time, which is a browser and not a source tree. If it mounts, your fixed panels do reach a user in the Odoo client and `data._warnings.unavailable` has a reader after all. If it genuinely does not, say so with the console output and the tab becomes a real piece of work.

**The lesson is the one you taught me and it now cuts both ways: the shim is invisible from Odoo's source and decisive for ours.** Write it into `docs/ENVIRONMENT-FACTS.md` under its own heading, because it has now produced a wrong conclusion in both directions in five handoffs.

## B · The audit reports — the actual work

Cadra's specification names five standard audit reports (`Cadra_at_NRS_Specification_v0.1.docx` §13.4), and your INT-10 document established that **Cadra has none of them as an API surface**. Handoff 14 built the second. **This handoff builds the two that are about assets**; the two log-shaped ones get their own.

### B1 · Asset register snapshot at a historical date

*"What did the register say on 31 March?"* — the question every external audit opens with.

**The design question is what you can honestly answer, and I want it settled before it is built.** A snapshot needs history, and Cadra's history is uneven: `custodian_id` has a chain as of handoff 14, depreciation has point-in-time already, and most other fields have only `mail.tracking_value` rows — which your own INT-10 §3.2 says is exactly where *everything Cadra receives from another system* is tracked by nothing at all.

So the instruction is not "reconstruct the register". It is: **answer for the fields where the answer is sound, and say plainly which fields are as-of-today rather than as-of-the-date.** A snapshot that silently mixes the two is worse than no snapshot, because an auditor will reconcile it against a figure and the discrepancy will be ours. Put the boundary in the response and in the document, not only in the code.

Start from what an auditor does with it: existence, custody, location, condition, state, and value. Where a field cannot be rolled back, the report says so for that field rather than omitting the row.

### B2 · Disposal report with documentation references, per period

Your INT-10 document records that disposal *"has no documentation refs and no period report"*. Both halves are the work: the references have to exist before a report can cite them.

An auditor's test on a disposal is always the same — **was it authorised, by whom, and is the paper there?** So the row carries the asset, its code in both systems, when it was disposed, by what route, who approved it, the proceeds if any, and the reference to whatever document authorised it. A disposal with no authorising reference is itself the finding and must appear as one, not be filtered out.

**Both reports are read-only and neither repairs anything.** Report 19 in the Vendra repo made that argument for its own reconciliation and it holds here: a report that quietly fixes what it finds can never honestly report zero.

## C · Four small true things from report 15

**C1 · Delete `fleet_command_patch.py`.** Tracked, at the repo root, carrying both dead field names (`insurance_expiration_date`, `lg.service_id`) and writing to a path that exists on no current machine. You were right to flag it rather than act, and the handoff-09 precedent on the repo-root `odoo.conf` is the answer: **an exception matched on a filename cannot tell a dead file from a live one.** It will re-seed two defects for the next person who reads it as a reference. Gone.

**C2 · `asset_pm`'s two, neither swallow-related.** The already-created check matching on translatable stage **names** where `request.stage.closed` is the boolean that means it — same shape as report 13's `stage_id.code == 'progress'` and working today only because the stock data happens to agree. And the PM description passed as `request.request.name`, the Reference field, so PM requests carry no sequence reference.

**C3 · Widen the guard to `scripts/` and the repo-root loaders, not to `seeds/`.** Your split is right and the reasoning is yours: a one-shot tenant seed's `except: pass` around an `env.ref` is the genuinely optional case the convention says to narrow rather than annotate, and putting ~46 of them in front of CI buys nothing. `scripts/bootstrap.py` provisions the credentials every tenant authenticates with and belongs inside. **Keep the measured count written in the guard** — that is the part that matters, and you got it right the first time: a green run that means "there are none" would be this handoff's own defect one level up.

**C4 · `_send_to_workflow`'s latent `TypeError`.** Named in report 15 §6.6. One line, and with the outer clause now `RequestException`-only it would otherwise surface as a message pointing the user at the wrong system.

## D · A published surface with no published contract

Report 15 §6.3, and it is a real gap rather than a tidy-up. `/myservice/workflow/callback` changed three status codes in handoff 15 — correctly — and **`docs/api/CHANGELOG.md`'s own rule does not reach it** because it is not under `/api/v1/*`. There is no document that does.

**Write the inventory, not the contract.** One short document listing every route outside `/api/v1/*` that something external calls — this callback, the probe, the website form, the barcode endpoints if they qualify — with for each: who calls it, whether its shape is published anywhere, and whether a change to it is a breaking change. Then say in `docs/api/CHANGELOG.md` that those surfaces are in scope too.

I am asking for the inventory rather than the contracts because I do not know how many there are and neither does anyone else. The number is the decision.

---

## Acceptance

- §A answered with browser evidence either way, and the shim written into `ENVIRONMENT-FACTS.md`.
- A snapshot at a past date returns the register as it stood for every field whose history supports it, and **states in the response** which fields are as-of-today.
- A disposal with no authorising reference appears in the report as a finding, not filtered out.
- Neither report writes anything — prove it by fingerprinting before and after, as report 19 did in the other repo.
- `fleet_command_patch.py` gone; `asset_pm`'s two fixed; the guard covers `scripts/`; the `TypeError` cannot fire.
- The non-`/api/v1` inventory exists and the changelog's scope names it.
- Guards proven to fail before they pass. Denominators quoted. Suite green, eight-tenant fan-out if any column moves.

## Report

`docs/handoffs/16-REPORT.md`. Short.

1. **What the browser said about the Fleet Command tab**, first, because everything about §A hangs on it.
2. **Which fields the snapshot cannot roll back**, as a list. That list is the real output of B1 — it tells NRS what their audit can and cannot ask, and it will go into the INT-10 document as it stands.
3. How many disposals on the live tenants carry no authorising reference. I expect the number to be uncomfortable and I would rather have it.
4. The count of non-`/api/v1` external surfaces.
5. Wall-clock, and whether the machine behaved.

---

## Two rulings you asked for, and one thing for me

**`test` overriding the route's own source — agreed, keep it.** Your reasoning is right: the reader's first question about a link is whether it happened at all, which the route it arrived by does not answer, and `reason` still carries the caller's string. Deciding it server-side from the credential rather than from anything the caller sends is the part I would have got wrong.

**Not relabelling historic links — agreed, and it was the only available answer.** A migration that made an exception to an append-only record would be the first hole in it.

**The `jwt_decode` finding is mine to act on beyond this repo.** A crafted `Bearer` header producing an HTML 500 on *every authenticated route* is the shape of defect that exists wherever somebody assumed a decoded JSON segment is an object. Vendra has its own token paths and I am putting the same question to that side rather than assuming it is Cadra-specific.

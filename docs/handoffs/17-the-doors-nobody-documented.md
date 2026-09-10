# Handoff 17 — The doors nobody documented

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/external-surfaces`.

> Report 16 accepted in full. **You were wrong about the Fleet Command tab and you proved it yourself, in a browser, and withdrew report 15 §6.1.** That is the standard and it cost me nothing to be right, because the method is what matters: report 11 measured this correctly and never committed the probe, which is why report 15 had to reason from a source tree. **The probe is committed now** and that is the durable fix.
>
> And the thing you found while proving it is better than the answer: your first probe measured `.o_action_manager`, which renders Odoo's own error surface, so it reported all four *retired* tags as mounted. **A guard written to detect a mount that fires on a failure** — the print-hook defect again, in the instrument rather than the subject.
>
> **This handoff is the §4 inventory turned into work, and it leads because one item in it is the most serious single finding either repository has produced.**

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/external-surfaces && git push -u origin fix/external-surfaces
```

**Needs the owner:** merge the open PR for `feat/audit-reports` (`gh pr list` first).

**And run the suites in CI's order** — `pytest tests/` before the in-registry Odoo suites. Report 16's CI failure is the only way to catch that class locally, and `CLAUDE.md` does not say which order CI uses. Add that sentence to `CLAUDE.md` while you are here.

---

## A · An endpoint that approves and rejects requests, with no authentication

**Report 16 §4 finding 1, and it goes first because of what it does rather than what it is.**

`/myservice/workflow/callback` is `auth='public'`, `csrf=False`, mutates `request.request` state — **and its token guard is optional.** `if config.callback_token:` means a tenant with no token configured has **no authentication at all** on the endpoint that approves and rejects requests. It also accepts the token in the query string.

Three separate things, and each is its own defect:

**A1 · A missing token must refuse, not admit.** An absent credential is the one case where "no check" and "check passed" are the same code path, and that is never acceptable on a public route. Refuse with a clear error naming the configuration, and log it — a tenant hitting this needs to find out from a log rather than from an approval nobody authorised.

**A2 · The token leaves the query string.** A credential in a URL is in nginx access logs, proxy logs, browser history and any referrer. Header only. Accept the query parameter for one release if an external caller genuinely uses it **and log a warning naming the caller's IP each time it is used**, so the migration has an end date that is visible rather than assumed. Say in the report whether anything actually uses it.

**A3 · `csrf=False` with `auth='public'` and a state mutation.** Correct for a machine-to-machine callback and wrong to leave unexamined. Confirm the token check cannot be reached after any state change, and that a replayed callback is idempotent. If it is not idempotent, say so rather than fixing it here — that is its own piece of work.

## B · A credential in a query string, and a hardcoded fallback

**Report 16 §4 finding 3.** `/api/myservice/assets/export/csv` dumps the whole asset register authenticated by `?api_key=`. Same treatment as A2: header only.

**And the part that is worse than the query string: both Redhubs routes fall back to a hardcoded key literal in source when the config parameter is unset. So does SAP's webhook.** A secret in source is a secret that has been in every clone, every fork and every CI log since it was written. Three things:

- **The fallback goes.** Unset configuration refuses; it does not substitute a default. Same rule as A1 and for the same reason.
- **Treat those literals as compromised.** They are in git history and cannot be removed from it. Whatever they authenticate must be rotated, and the report should name every place that needs rotating rather than rotating anything — that is the owner's to do on the box, which is how every credential in this programme has been handled.
- **A source guard.** A literal that looks like a key, used as a credential default, should fail the build. You will have a better instinct than I do for how to spot it without false positives; if the answer is a pinned list, say so.

## C · The documented callback is not the one being called

**Report 16 §4 finding 2.** `/api/v1/integrations/workflow/callback` and `/myservice/workflow/callback` are two handlers, and Cadra publishes the **legacy** one's URL to WorkSpace. The documentation describes a route the integration does not use.

**This is the one in §4 I am least able to scope and you are best placed to.** Three shapes, and I want your recommendation rather than my guess:

1. The legacy route becomes a thin delegate to the `/api/v1` one, so there is one implementation and two paths.
2. WorkSpace is repointed at the documented route, which means a coordinated change with whoever operates WorkSpace.
3. They are genuinely different contracts and the documentation is wrong about which is which.

**Report which, with the reason, and build it only if it is (1).** (2) and (3) involve another team or a contract decision and come back to me.

## D · Coordinates invented on a network outage

**Report 16 open item 5, and it is the family this pair of handoffs has been clearing.** A swallowed `urlopen` failure is indistinguishable from *"Nominatim has no such place"*, and both scripts respond by writing a jittered state-capital coordinate into `generic.location.latitude/longitude` **and committing it.** A total outage or a 403 rate-limit produces plausible coordinates for the entire estate, reported as `fallback` rather than as a network error.

A network failure and a place that does not exist are different answers and must be recorded differently. **A geocoder that cannot reach its service writes nothing** and says so. The jittered fallback may stay for the genuine not-found case if somebody wants it, but it must be distinguishable in the data — the same argument as `custody.source = 'tracking_backfill'` and `disposal_date_reconstructed`, which you have now made twice unprompted.

---

## E · Four rulings from report 16

**E1 · `no_sap_asset_number` — keep the fact, stop calling it a finding.** You are right that a control firing on ~100% of rows is one readers learn to ignore. But removing it hides something true. So it moves out of the per-row findings and into a **statement above the table**: *"No disposal in this period carried a SAP asset number. INT-09 has never sent a disposal instruction to the financial system."* One sentence, once, where it reads as a fact about the interface rather than as a defect in each row.

**E2 · No API route records a disposal approval** — a real gap. Not this handoff. `approvals:write` exists and gates nothing asset-related; that is the shape, and it needs a scope decision I would rather make deliberately than inside a security handoff.

**E3 · `data.unplaceable` stays exactly as you built it.** Returned in full, uncapped, never mixed into period totals. Dropping them hides them; including them double-counts. A third category that says what it is, is the correct answer to a genuine trilemma.

**E4 · `load_offices_v3.py:65`** — fix the marker's truth if you are in the file, otherwise leave it. Named, low, not worth a detour.

---

## Acceptance

- A tenant with no callback token cannot reach the approval path at all, and the refusal is logged.
- No credential is accepted in a query string without a warning naming the caller, and the report says whether anything uses it.
- No credential has a hardcoded default anywhere; the report lists what must be rotated.
- A geocoder that cannot reach its service writes no coordinate, and the not-found case is distinguishable in the data from a recorded one.
- `no_sap_asset_number` appears once as a statement, not per row.
- Guards proven to fail before they pass. Denominators quoted. **Suites run in CI's order.**

## Report

`docs/handoffs/17-REPORT.md`. Short.

1. **Whether anything actually calls the query-string forms**, measured if you can measure it.
2. **Your recommendation on §C**, with the reason.
3. Everything that needs a credential rotated, as a list the owner can work through on the box.
4. Whether the replayed callback in A3 is idempotent.
5. Wall-clock, the correction share, and whether the machine behaved.

---

## Three things for me, not you, and all three are corrections I owe

**`docs/integrations/INT-10-audit-access.md` does not record the process gap I said it did.** Vendra's report 20 read the document in full and grepped it; I was wrong. A storekeeper issues a unit in Vendra, a person allocates it in Cadra, and neither record references the other. **Vendra's half names it; Cadra's must.** I am writing it rather than asking you to.

**Its §2.11 is stale.** It presents a blocking 100-row `EXTERNAL_TOTAL_CAP`; handoff 12's `1b009e6` replaced that with a per-client cap and uncapped `vendra`. Its §7 asks NRS a question that may already be answered. Mine to fix.

**And your §2 field list changes what INT-10 can promise NRS, so it goes in as written.** 28 fields roll back and 44 do not. Every financial figure, every SAP field including `sap_asset_number`, the whole acquisition provenance trail, the serial number, the department and the hierarchy are as-of-today. **Your sentence — *the identity and location of an asset are historical; its money is not* — is the one NRS needs to read**, because an external audit that opens with *"reconcile the register at 31 March to the ledger"* cannot be answered from this system and they should learn that from us, now, rather than from a number that looks like it can.

# Handoff 18 — The callback that answers twice

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/callback-idempotency`.

> Report 17 accepted in full. **`callback_token` was set on 0 of 8 tenants**, so the endpoint that approves and rejects requests was standing open on every one of them, and you proved it with an anonymous POST carrying a deliberately *wrong* token that came back `404 "Request not found"` — past the gate, at a reference lookup. The only thing between a stranger and an approval was knowing a reference name.
>
> **Your credential guard is better than the one I asked for and the rule is the reason.** I asked for a guard that spots a literal that looks like a key. You built one on the *lookup* instead: **a credential may default to nothing; it may never default to something.** An entropy heuristic flags `http://localhost:8069` and misses `changeme`. And you measured eight bypasses of your own first version rather than reasoning about them.
>
> **And the token leaked into our own log at INFO on the form-encoded path** — item A2's entire argument, happening inside the fix for item A2, with a test that was passing for the wrong reason twice over. Found by verification, not by either of us.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/callback-idempotency && git push -u origin fix/callback-idempotency
```

**Needs the owner:** nothing — handoff 17's PR (#63) is merged. **But two credentials are live-cutover and unrotated; the owner has the list from report 17 §3.**

Suites in CI's order. Serialise every `--stop-after-init` run — twelve registry loads and zero crashes last time is the discipline working.

---

## A · A replayed callback re-applies everything, and one of the three is damaging

**Report 17 §4.** A second byte-identical POST answers `200 {"ok": true}` and does it all again. The token fix has not reduced this at all: a caller with a *valid* token can still replay freely, and after this week's cutover the callers will have valid tokens.

Three effects, and the third is the one to build for:

1. A second dispatch-log row is appended — every replay adds one, because the first callback rewrote the `sent` row the replay was looking for.
2. Chatter is re-posted unconditionally.
3. **The stage is re-applied.** Where `approved_stage_id` is configured the handler writes it unconditionally — so **if a human moved the request onward after the first approval, a replay drags it back.** And `myservice_request_core.write` branches on `'stage_id' in vals` rather than on the value changing, so every replay also resets `date_moved` and appends a `request.event` row through `_log_event('stage_changed')` even when the stage is identical. **That is a double-count inside the request's own audit trail.**

**The shape of the fix is already settled in this repo and you named it.** Handoff 06 ruled *one physical act is one event* for INT-05, and `_mark_affixed` fires on the **transition**. Nothing here fires on a transition. So:

- **Fire on the transition, not on the call.** An outcome already applied is a no-op that answers success — the caller replayed a request we honoured, and telling them so is correct.
- **A replay must write nothing**: no second log row, no second chatter post, no stage write, no `date_moved`, no event row.
- **A replay that would change the outcome is different** and must not be silently absorbed. An `approved` callback on a request already `rejected` is a contradiction between two systems and belongs in a log and probably in a refusal. Say which you chose.
- `queried` is the mildest case and gets the same treatment for the same reason.

**`workspace_ref` is stored and never matched on.** That is the natural dedup key and the reason there is no dedup today. Use it, and say in the report whether it is reliably populated across both controllers.

## B · The documented twin has two defects of its own

**Report 17 §2.** Your recommendation on item C was **(3) — genuinely different contracts** — and the authentication row settles it: WorkSpace holds a shared token, not a Cadra client credential, so the public route cannot delegate into a JWT decorator without either issuing WorkSpace a client or weakening `/api/v1`. **Accepted, nothing to build there.** But the table you wrote to prove it surfaced two defects in the `/api/v1` twin, and both are now scheduled:

**B1 · The v1 twin never reconciles the outbound dispatch.** The legacy route finds the `direction='outbound', status='sent'` row it is answering and rewrites it to the outcome. The v1 route always appends a fresh inbound row. **On a tenant using v1, an answered dispatch reads `sent` forever, so "which dispatches are still unanswered" cannot be asked.** You called it: the legacy behaviour is the better one and this is v1's bug. Make v1 reconcile the way legacy does.

**B2 · The v1 twin publishes an internal menu path to an API caller.** `_workflow_callback_approved` calls `get_active_config()`, which raises `UserError` on a tenant with no workspace config, and `cadra_route` renders `str(e)` — so the **documented** route answers `400 validation_failed` carrying *"Please configure one under Settings → WorkSpace Integration"*. Two faults: an internal navigation path in a published envelope, and a validation code for a tenant-configuration state. Handoff 15 already removed this from the legacy route; apply the same answer here. You read it from source rather than creating a config row on a demo tenant to prove a documentation finding — right trade.

## C · A credential baked into a published image

**Report 17 §3's third item, and yes, it is this handoff.** You asked and the answer is that it is worse than the two route credentials in one specific way: **images get pulled.**

`Dockerfile.nrs-import:31` bakes `ODOO_ADMIN_PW=admin` into a published image, `scripts/nrs_import_entrypoint.sh` passes it straight to XML-RPC, and `k8s/dev/71-nrs-import-job.yaml` documents the fallback in a comment without setting the variable. `e2e/config.ts` defaults to `admin`/`admin` while its origin is env-overridable to a remote host.

Same rule as §B of handoff 17, which is now your rule: **the default goes, an unset variable refuses, and the refusal names what is missing.** `e2e/config.ts` is dev tooling and may keep a default for a localhost origin — but a default credential paired with an overridable remote origin is a production credential waiting for an environment variable, so gate the default on the origin being local.

**Extend your credential guard to cover it.** It already walks `Dockerfile*`, the compose files and the k8s manifests since you scoped it to git-tracked files; make sure an `ENV`-assigned credential with a literal value fails it, and say whether that needed a new branch or fell out of the existing shape rule.

## D · `request.jsonrequest` does not exist on Odoo 19

`sap_webhook.py`, reachable only when `kwargs` is empty — where the intended answer is `'Empty payload'` and the actual one is a 500. You are in that file for §C's neighbourhood; small, real, and it is the unauthenticated inbound employee endpoint.

---

## Four rulings

**D1 · Your period-scoped disposal statement stands. I am not restoring my wording.** You were right: *"INT-09 has never sent a disposal instruction"* asserts "never" from a report that reads one bounded period, which is counting a register from a page of it — ruled against twice here, and my sentence did it a third time. Your version means the same thing and is defensible from the data the report holds.

**D2 · Removing `no_sap_asset_number` from the enum rather than deprecating it in place — correct.** Rule 4, one day of exposure, no consumer. The dated removal note in the descriptions is the right residue.

**D3 · The 1,562 coordinates stay `NULL`.** You declined to backfill because the only heuristic is wrong in both directions — a genuine geocode inside a capital city lands in the same radius, and the two scripts' capital tables differ. That is the third time you have refused to fabricate provenance unprompted, and it is the same argument as `tracking_backfill` and `disposal_date_reconstructed`. It is now a repo convention rather than three separate good instincts.

**D4 · The ERROR-per-unauthenticated-request log stands as you built it.** Anyone who knows a URL can fill the log on an unconfigured tenant, and the alternative is a route standing open in silence. If it bites, it is a rate limit, not a downgrade.

---

## Acceptance

- A byte-identical replay writes **nothing** — no log row, no chatter, no stage write, no `date_moved`, no event row — and answers success.
- A replay carrying a *different* outcome is not silently absorbed; the report says what it does.
- An answered dispatch on the v1 route reads the outcome, not `sent` forever.
- The v1 route's unconfigured-tenant answer carries no internal menu path and no validation code.
- No credential anywhere defaults to a value, image layers and manifests included, and the guard proves it.
- `request.jsonrequest` is gone and the empty-payload path answers what it intends to.
- Guards proven to fail before they pass. Denominators quoted. Suites in CI's order.

## Report

`docs/handoffs/18-REPORT.md`. Short.

1. **Whether `workspace_ref` is reliably populated on both controllers**, measured. The dedup key is only a key if it is always there.
2. What a contradicting replay does, and why that rather than the alternative.
3. Whether the guard needed a new branch for `ENV`-assigned credentials.
4. Wall-clock, the correction share, and whether the machine behaved.

---

## Two things for me, not you

**INT-10 §309 and §318 are mine and I am fixing them.** That document still lists `no_sap_asset_number` among published findings and still makes the absolute "never" claim you declined to publish. You were right not to touch a document I reserved — and right that a documented value the endpoint cannot return is one an integrator writes a branch for and never sees fire. Along with §2.11 and the process gap, which I have owed for two handoffs now.

**`@route(type='json')` is deprecated repo-wide and warns on every startup.** Not yours, not this handoff, and not small. It goes on my list as its own piece of work rather than getting absorbed into something adjacent — which is how the outbox questions in the sibling repo ended up waiting three handoffs and being right to.

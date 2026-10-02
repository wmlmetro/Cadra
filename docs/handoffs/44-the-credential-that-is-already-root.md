# Handoff 44 — The credential that is already root

**Branch:** `fix/the-credential-that-is-already-root`
**Report:** `docs/handoffs/44-REPORT.md`
**Runs after 43.** 43 finishes the user-management strand; this one makes the guard 42 built actually matter.

---

## 0 · Report 42 accepted, and the finding that outranks the feature

The guard is right: in the model, under all six doors, keyed on the one thing only our API sets, with no switch to turn it off. Driven rather than asserted — the credential refused on its own user and on somebody else's, the self-grant refused, the self-removal allowed, the back office left unguarded, and the record carrying the right name through all of it. Your correction of the route's first draft, caught before it shipped, is the pass earning its place again.

**But your §F.2 is bigger than the handoff it arrived in.**

> `bootstrap.py` makes the user of every admin-scoped credential a system administrator.

So report 41's *"deliberately NOT a system administrator"* — which I quoted back at you as the shape of the exposure — was **false on every tenant bootstrap has touched.** The credentials are not sitting outside the line waiting to cross it. They are already on the far side of it.

And that has a consequence worth stating plainly: **a system administrator can execute arbitrary server actions, so for these credentials the guard is advisory.** They do not need to call the route we just protected. The line we drew in 42 is correct and it is now the rule for every future grant — but the holders who most concerned us were handed the thing it forbids, months ago, by our own provisioning.

That is not a defect in 42. It is the difference between having a guard and the guard mattering.

---

## 1 · What to establish, before building anything

**Strip `base.group_system` from an admin-scoped credential's user on a scratch tenant, and find out what breaks.**

My expectation — and it is an expectation, not a ruling — is that nothing does, because the `admin` *scope* already satisfies every route's scope check, and every route runs `sudo()` so Odoo's own permissions never come into it. If that is right, the group was never doing any work and we have been handing out root for nothing.

If it is wrong, I want the list: every route, job, or model operation that fails without it, each with the reason. That list is the real deliverable of this handoff, because it says what an API credential genuinely needs, and we have never asked.

**Do not guess at the list from the code.** Drive it: the receipt hand-off, the tagging callback, the employee sync, the reconciliation reads, whatever `bootstrap.py` itself does afterwards. A credential that works for ten minutes and fails on the monthly job is the shape of failure this programme keeps finding.

---

## 2 · Then, depending on what you find

**If nothing breaks:** take it out of `bootstrap.py`, and say what happens to the credentials that already hold it on the eight tenants — whether removing it is safe to do now, what order, and what an operator would see if it went wrong. **Do not change any live tenant in this handoff.** Write the procedure; the owner decides when it runs.

**If something breaks:** report what and why, and propose the narrower grant that covers it. `SCOPE_GROUPS` already maps scopes to groups for exactly this purpose and may simply need an entry. A named group that grants what is needed beats `base.group_system` even if it is only slightly smaller.

**Either way**, write into `DECISIONS.md` what an API credential is entitled to and why, because nobody has ever written it down, and the next provisioner will copy whatever is there.

---

## 3 · One small thing, ruled

Your §H names the refusal saying *Role / Administrator* while the API elsewhere says *System Administrator* — one group, two names, in one response stream.

**One name. Move the alias to the model.** This programme has been bitten twice by a published name meaning two things, and `test_published_names_resolve.py` exists because of it. Pick the name a person would recognise and use it everywhere.

---

## 4 · Verification

- The strip-and-drive from §1, with the full list of what failed or a statement that nothing did, and the transcripts either way.
- If you change `bootstrap.py`: a fresh tenant bootstrapped from scratch with the change, working end to end — INT-03 and INT-05 at minimum, because those are the credentials that matter most.
- The guard from 42 still refusing everything it refused, unchanged.
- The naming fix visible in both the refusal and the schema.
- Suites with denominators, and the standing sentence pass.

---

## 5 · Needs the owner, carried forward

Your §*Needs the owner* on 42 asked for `upgrade-19` with a **pinned** image, because report 41's roll on `dev-latest` re-used a cached one. **Worth saying plainly in your report whether the routes 41 and 42 added are actually live on staging today**, because a cached image means an upgrade that reported success and changed nothing — which is this programme's oldest defect wearing a new coat.

# Handoff 42 — The grant, and the refusal

**Branch:** `fix/the-grant-and-the-refusal`
**Report:** `docs/handoffs/42-REPORT.md`
**Second of three.** 41 built the read. This one builds the write. 43 creates and deactivates people, and waits on an answer about mail.

---

## 0 · Report 41 accepted, and it corrected me twice

**`category_id` does not exist on `res.groups` on Odoo 19.** I named a field from an older Odoo and you found the one the form actually reads — `privilege_id` → `res.groups.privilege` → `category_id`. My diagnosis was right and my prescription was from memory. That is the third instruction this fortnight where I named a mechanism instead of a requirement, so I will stop naming fields: from here I will say what must be true and leave how to the person with the code open.

**And the refusal was not the one I described.** I wrote that the Tag-Issuing Unit needed an access rule. You signed in as one and found the station refuses *before* Odoo's rules are consulted at all — the scope gate sees a token carrying only `tagging:write` and the page needs `assets:read`. An access rule grants no scope and would have changed nothing. The pairing is the only answer that works, and you established it by driving rather than by accepting the question as posed.

**The defect that drive turned up is the valuable part of the handoff.** Four barcode reads were the only routes in the whole API running as the signed-in user rather than under `sudo`, so an Odoo access rule could silently decide an API answer. That is a seam nobody would have found by reading, and it is the real cause of the sentence the owner saw.

---

## 1 · What this handoff is about

Your §G answered the question I most needed: **nothing in Cadra would refuse a privilege escalation.** Every v1 route runs `sudo()`, which never consults the Access Rights ACL, and Odoo's own guards are only *portal and internal are exclusive* and *one administrator must remain*. So a route that wrote `group_ids` tomorrow would let any `admin`-scoped caller grant `base.group_system` to anybody — and the exposure you named is the sharp one: an **API credential** holding the `admin` scope, whose user is deliberately not a system administrator, could make itself one. The access record would write it down and refuse nothing.

**So this handoff is not "add a write endpoint". It is "decide what may never happen, put that where no caller can go round it, and then add the endpoint."** In that order.

---

## 2 · Two rulings, with the reasoning, and a standing invitation to argue

### Ruling 1 · `base.group_system` is not grantable through the API. At all.

Not by an administrator, not by a credential, not with a confirmation flag. Making someone a system administrator stays a thing you do in the Odoo back office, signed in as a person with a password.

The reasoning: `admin` scope exists so a machine can run the register. System administrator is the authority to execute arbitrary server actions. Those are not the same power and the first should not be able to reach the second. A line that simply cannot be crossed is worth more than a guarded one, because it needs no judgement at the moment it matters.

**This generalises:** no `base.*` group is grantable over the API. Only our own four — Asset User, Asset Manager, Tag-Issuing Unit, Auditor. If a fifth must be grantable later, that is a decision with a name on it.

### Ruling 2 · Nobody grants themselves a role.

A caller may **remove** their own roles — that is a downgrade and a person locking themselves out is their own problem, within Odoo's last-administrator guard. A caller may **not add** a role to their own account. Somebody else does it.

The reasoning is the one this whole programme is built on and that NRS asked for by name: an action that matters takes a second person. We refuse self-approval on a move and on a tag replacement. Granting yourself access is the same shape, and a system that enforces two people for moving a laptop and one for handing yourself the keys is not coherent.

**Argue if you can measure a reason.** Both rulings make the first-ever setup of a tenant harder, and if driving them shows a case where the system cannot be bootstrapped at all without one of them being relaxed, that is a finding and I will rule again. What I do not want is the rule quietly loosened because it was inconvenient.

---

## 3 · Where the refusal lives

**In the model, under every writer — not on the route.**

Your own §G says this and `access_change.py` already proves why: membership is writable from six structurally different directions, and the list was wrong twice before somebody enumerated it. A guard on one route is a guard on one of the six doors. It belongs where the approval gate and the disposal guard are, so that a future route, a script, a seed or the back office all meet it.

**One thing to decide and state rather than assume:** a guard under every writer will also meet `scripts/bootstrap.py`, the security XML that re-applies on every module upgrade, and `auth_signup`'s template copy. Those are legitimate and must keep working. Work out how the guard tells *a caller doing this through our API* from *the system installing itself*, and defend it — a context key, the environment's user, something else. **A guard that has to be switched off to install the product is a guard that will be found switched off.**

---

## 4 · Then the endpoint and the screen

Granting and removing roles on an existing user, `admin` scope, from the Users page built in 41.

- Every refusal renders in words, in the server's own sentence, as the tag dialog does.
- The screen must show what will change **before** it is applied, including what the effective roles become once implication is applied — because 41 established that direct and effective are different questions on Odoo 19, and a grant of Asset Manager silently confers Asset User.
- **Build no second audit.** `access_recorder.py`'s hooks record this automatically. Confirm that they do, by making a grant and reading the row back, and confirm the actor recorded is the person who clicked rather than whatever the route ran as. That last one is worth checking rather than assuming, given everything runs under `sudo`.

---

## 5 · Also, while you are here

The seven first-party groups still without a privilege (`GO-LIVE.md` §18.2) — one record each, in their own modules. Small, and it finishes what 41 started.

---

## 6 · Verification

Drive every refusal and put the transcript in the report:

- An `admin`-scoped **credential** attempting to grant `base.group_system` to its own user. This is the exposure your §G named; I want to see it refused.
- The same credential attempting to grant it to somebody else.
- A person attempting to grant themselves a role they do not hold.
- The same person removing one of their own roles — allowed.
- Odoo's last-administrator guard still firing.
- A grant through the **back office** still working, unguarded, as it must.
- `scripts/bootstrap.py` and a module upgrade still working, with the access record showing no noise from either.
- A grant made from the screen, with the access-change row read back, naming the right actor.
- Suites with denominators, and the standing sentence pass.

---

## 7 · Not yours — going to the owner

Merging, the staging upgrade job, and whether the cluster has `SMTP_*` set. The last one decides handoff 43 and I am asking today.

# Handoff 43 — The person, and the door

**Branch:** `fix/the-person-and-the-door`
**Report:** `docs/handoffs/43-REPORT.md`
**Third of three.** Runs after 42 is merged, and depends on it.

---

## 0 · First, before anything else: is the front door open?

Report 41 §G.3 reported `auth_signup.invitation_scope = b2c` on **all eight tenants**, with `auth_signup` installed and `reset_password = True`.

On Odoo, `b2c` means **free sign-up**: anybody who can reach the login page may create an account for themselves. `b2b` means by invitation only. Nothing in this repository sets that parameter, so it arrived by default or by hand, and nobody chose it.

**Establish, today, before any other work in this handoff:**

1. Whether the sign-up form is actually **reachable from the internet** on `staging.app.cadra.ng` and on anything else deployed — not whether the parameter is set, whether an anonymous browser can get to it and complete it. Drive it from a logged-out browser and put the result in the report either way.
2. What an account created that way would **hold** — which groups `_create_user_from_template` clones onto it, and what it can therefore read.
3. Whether any such account **already exists** on any tenant.

If the door is open, say so immediately and plainly rather than finishing the handoff — that is an owner decision taken within the hour, not a line in a report tomorrow. If it is shut, say what shuts it, because "a setting says b2c and it does not matter" is a claim that needs its reason written down.

**My ruling, so it is not an open question:** this product is not a service people sign themselves up to. It is a government asset register with named officers. `b2b` is the correct setting and it should be set deliberately, by us, in a way a module upgrade cannot quietly undo — not left at whatever a default happens to be.

---

## 1 · What this handoff builds

Creating a person, and taking their access away. The last piece that stands between us and NRS running this themselves.

**Mail works on the cluster** — the owner confirmed it on 2 October — so an invitation can genuinely be delivered. Design for the invitation, not for a password typed into a form. This programme does not pass secrets through documents, tickets or chat, and an invitation link the person redeems themselves is the shape that honours it.

- **Create a person**: name, email, and the roles they start with.
- **Send the invitation**, and show on the user's row that one is outstanding and when it was sent.
- **Re-send it**, because the first one will go to spam.
- **Deactivate** somebody, and reactivate them.

**The guard from handoff 42 governs all of it.** Creating a user with roles is granting roles. Do not write a second guard, do not go around the first, and if the guard's design makes creation awkward, that is a finding about the guard rather than a reason to bypass it. The access record already captures creation — `access_change.py` says `_create_user_from_template` is a `copy()` and the recorder diffs the relation rather than reading vals, so a create that mentions no groups is still recorded. Confirm that, by doing one.

---

## 1b · The invitation is a letter from their own organisation, not from Odoo

Added 2 October, at the owner's request. The default invitation is Odoo's, and it looks like it — Odoo's wording, Odoo's styling, Odoo's footer. The first thing an NRS officer will ever see of this system is that email, and it should not be an advertisement for a framework they have never heard of.

**And the brand it carries is the tenant's, not ours.** This is already solved elsewhere and you must reuse it rather than invent a second answer: `cadra.brand_short_name` is a config parameter owned by the per-client `cadra_brand_<client>` modules, `myservice_nrs_base/models/ir_http.py` exposes it to the web client, and `Frontend/…/src/lib/brand.ts` already applies colour and title per tenant from one static build — *"jaizbankplc shows its own, NRS shows NRS's red."* A person invited to the NRS tenant gets an NRS letter. A person invited to jaizbankplc does not see NRS anywhere in it.

There is precedent for our own templates in `myservice_fleet_maintenance/data/mail_templates.xml` and `myservice_security/data/mail_templates.xml`; start from how those are structured rather than from scratch.

**Six things to get right:**

1. **The tenant's brand, resolved at send time** — not baked per module and not hard-coded. If a brand module supplies a logo, use it; if a tenant has none, the fallback must still be a dignified letter rather than a broken image and the word NRS on somebody else's tenant.
2. **The link points at the tenant's own host.** An invitation to `jaizbankplc.cadra.ng` that lands someone on `staging.app.cadra.ng` is a dead end, and getting this wrong is easy because the sender does not know the host the request came from unless somebody passes it.
3. **Readable with images blocked.** Government mail clients strip images and sometimes HTML. Write a plain-text part that stands on its own and says what to do; do not let the instruction live only in a styled button.
4. **No secret in the body.** A link the person redeems, as §1 already says. Not a password, not a temporary one.
5. **Say what it is in one line.** The recipient has not heard of Cadra and may not know why they are getting this. *"You have been given access to the Nigeria Revenue Service asset register"* beats anything clever.
6. **The reset-password email too.** It is the same person's next encounter with us and it would be odd for one to be branded and the other to be Odoo's. Check which templates Odoo actually sends on both paths before assuming there is one.

**Verification:** send a real invitation to a real inbox on at least two differently-branded tenants, and put both received emails in the report — as they arrive, with images blocked and with images on. Screenshot the actual inbox, not the template source. A template that renders in a test and not in a mail client is the shape of failure this programme keeps finding.


---

## 2 · The part I expect to be wrong, and want you to measure

**Deactivating somebody is not just a flag, and this is where I would look for the defect.**

A person can be the **nominated approver** on a pending move, a pending custody change, or a pending tag replacement. Deactivate them and that request is waiting on somebody who can no longer sign in. Nothing I have seen suggests anything notices.

Measure it rather than assume it:

- Raise a request, nominate someone, deactivate them, and find out what the queue says and whether anyone else can decide it.
- Find out whether `eligible_approvers` excludes inactive users — if it does, nominating them again is impossible while an existing nomination stands, which is the two-things-that-should-agree shape this programme keeps finding.
- Say what the right behaviour is. **Do not build it in this handoff** unless it is genuinely a line; this is a question I want answered with evidence so I can rule on it, not a feature to slip in.

**And the second question, which is NRS's own:** a deactivated person may still be the **custodian of assets**. They told us the offboarding case directly — *"you can use whatever process you want to determine how those assets are retrieved."* There is an *Identity (clearance)* screen already. Find out what it currently does when somebody is deactivated while holding four laptops, and report it. Again: evidence, not a build.

---

## 3 · Verification

- The sign-up finding from §0, driven from a logged-out browser, whichever way it lands.
- A person created and invited end to end: the invitation received, redeemed, and the account working with the roles it was given.
- The invitation re-sent.
- A creation attempt that violates handoff 42's guard, refused, in the server's words.
- Deactivate, prove the account cannot sign in, reactivate, prove it can.
- The access-change rows for the create and for the role grant, read back, naming the right actor.
- The §2 measurements, with transcripts.
- Suites with denominators, and the standing sentence pass.

---

## 4 · And then this strand is finished

With this merged, NRS can be handed the system and onboard their own people — a tagging officer in Calabar gets an email rather than a developer enabling developer mode. That has been the go-live blocker underneath all three handoffs.

Say in the report what is still missing before an NRS administrator could run this unaided. You will have a clearer view of that than anyone.

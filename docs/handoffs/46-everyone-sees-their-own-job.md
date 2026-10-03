# Handoff 46 — Everyone sees their own job

**Branch:** `fix/everyone-sees-their-own-job`
**Report:** `docs/handoffs/46-REPORT.md`
**Paired with a Vendra handoff of the same name**, running separately. A demo moves between the two systems, so the personas on each side must tell one story.

---

## 0 · Report 44 and 45 accepted

44 established by driving that the system-administrator role on an API credential was doing no work at all, and found the second place handing it out by searching rather than trusting the one place report 42 named. The two tests that had been skipping themselves for months because the credential was root are the kind of finding that only turns up when somebody takes a privilege away and watches.

45's verification pass is the one I will quote back. The first version of the back-office rule closed the doors a person walks through; the pass then got an Odoo session as an ordinary officer by two other routes, read the database with it, and opened the portal page. **A rule that is right about the obvious entrance and wrong about two others is not a rule**, and finding that in your own work is the discipline this programme runs on.

---

## 1 · What the owner asked for

A demo where you sign in as a storekeeper, then as a tagger, then as an auditor, then as an administrator, and each one's screen is their own job rather than everybody's.

Three pieces here. **The per-tenant menu toggles the owner also asked for are a separate handoff**, and deliberately so: *what this role may see* and *what this tenant has bought* are two different axes, and a menu that mixes them is a menu nobody can explain when it surprises someone. Build this one so the other composes on top.

---

## 2 · The personas

One account per role this system has — Asset User, Asset Manager, Tag-Issuing Unit, Auditor — plus whatever combination the demo story needs, and say in the report which combinations you created and why.

**The owner's two decisions, which shape everything below:**

- **Every tenant**, including the ones holding real client data.
- **Realistic names**, so the screen reads like a workplace rather than a test fixture.

Those two together are the risk. On `nrs19` these invented people will sit beside **11,386 real employees**, and in six months somebody will ask whether *Aisha Bello, Store Officer* is a real officer. So the marking is not housekeeping, it is the whole safety of this piece:

1. **Every seeded record carries an unmistakable marker in the data** — not only in the name. This repository already has conventions for exactly this (`is_test_credential`, `is_test_fixture`, handoff 26's fixture self-labelling). **Use them rather than inventing a third.** If they do not reach users and employees, extend them in the same shape.
2. **A reserved email domain** that cannot belong to a real person, and logins that cannot collide with a real one.
3. **Re-runnable.** Running it twice changes nothing and creates nobody twice.
4. **Removable.** A companion that takes every seeded record out again, shows what it would do before it does it, and refuses to touch anything it did not create. **At go-live these must come off a live client tenant, and the way that happens must exist before they go on.**
5. **Listable.** One command that answers *which accounts on this tenant are demo accounts*, so the question can be settled without reading the seed.
6. **No collisions with real data** — not IR numbers, not employee records, not asset custody. Say in the report how you established that, per tenant, with counts.

Passwords: generated on the machine, written to a gitignored credentials file beside the existing ones, never into the repository, a document, or this report. The owner needs to know them to switch profiles; everyone else does not.

---

## 3 · Each role sees its own job

**The machinery already exists.** `Sidebar.tsx` filters `ALL_NAV_GROUPS` by an optional `scope` on each item, and `useScopes` supplies them. Handoff 41 used it for the Administration group. **What is missing is that every other item has no scope at all**, so a Tag-Issuing Unit currently sees Fleet, Staff Bus, Security Operations and the rest.

So this is mostly assignment, not construction. Two rules while you do it:

**Hiding a menu item is not a permission.** It is a courtesy. The server must refuse the same thing whether or not the link was drawn, and **you prove that by typing the URL**, as the person, for every item you hide. An item that disappears from the sidebar and still answers 200 is the instrument that reports success while measuring nothing, in its newest costume.

**Do not invent a scope to make an item fit.** The existing scopes were reasoned about in `GROUP_SCOPES` and each one means something. If an item genuinely needs a scope that does not exist, stop and say so — that is a finding about the role model, not a gap to fill with a new string.

**And say what you could not resolve.** Some of those screens — Fleet Command, Staff Bus, Security Operations, the facility dashboards — may not map onto any current role, because they came from a different part of the product. Guessing would be worse than naming them. List them for the toggles handoff.

---

## 4 · The landing screen

After signing in, land on the asset register dashboard rather than today's `/`.

**One trap, and it is the reason this is not a one-line change.** If the asset dashboard needs a scope a Tag-Issuing Unit does not hold, then the first thing a tagger sees after signing in is a refusal. Work out what each persona lands on — by signing in as each of them, not by reading the route table — and make the rule *the best page this person can actually open*. Say what each role gets.

---

## 5 · Verification

- **Sign in as every persona and screenshot what they see.** That set of screenshots is the deliverable the owner is actually asking for, and it is also how we find out whether the roles make sense.
- For each persona, **type the URL of something hidden from them** and show the server refusing.
- The seed run twice, with nothing created the second time.
- The removal script's dry run and its apply, on a tenant, with counts either side.
- The listing command's output on `nrs19`, showing demo accounts distinguishable from 11,386 real ones.
- Each persona's landing page.
- Suites with denominators, and the standing sentence pass.

---

## 6 · What I expect to come back

That some of these roles are wrong — too coarse, or missing one. A storekeeper and a tagger are different jobs and this system has four roles for everybody. **If the personas do not fit the roles, say so with the evidence rather than bending the personas to fit.** That is a better finding than a clean report.

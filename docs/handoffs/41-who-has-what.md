# Handoff 41 — Who has what

**Branch:** `fix/who-has-what`
**Report:** `docs/handoffs/41-REPORT.md`
**First of three.** 42 is granting and removing access; 43 is creating and deactivating people. **This one adds no way to change anything.**

> `37-the-doors-and-the-red-tests.md` is still unrun and still waits. The demo moved, so there is time — but it is not this handoff and it is not next.

---

## 0 · Report 40 accepted

The camera landed, the typed path survived, and the screenshots show the expected number absent from the dialog with the preview running. The decision to fill-but-not-submit from a camera, with the reasoning in a comment, is the right call and is now the pattern for any scanner input we add.

---

## 1 · Why this handoff exists

Yesterday the owner created a real person — the first human ever to hold the Tag-Issuing Unit group rather than an API credential — and hit two walls in ten minutes:

1. **`forbidden: You are not allowed to access 'Asset Barcode Tag' records.`** There are exactly two access rules on `nrs.asset.tag.label` — Asset User (read) and Asset Manager (full). **The Tag-Issuing Unit appears in no `ir.model.access` row anywhere in this repository.** It grants an API scope and no database permission, because it was built for a machine where only the scope is checked.

2. **The groups do not appear on the user form at all.** `asset_security.xml` creates the `module_category_nrs_assets` category with a sequence — and **not one of the three groups sets `category_id`**. The category is empty and the groups are invisible, so there is nothing to tick. The only way to assign them is the Groups menu in developer mode.

Both are the same root cause showing up twice: these groups were designed for credentials, and nobody has ever put a person in one through a screen.

**That is a go-live blocker, not a cosmetic one.** NRS cannot onboard a tagger in Calabar by enabling developer mode and editing a group's Users tab.

---

## 2 · What this handoff does NOT do

**It adds no way to grant, remove, create or disable anything.** Read only, end to end. The mechanism is handoff 42, deliberately separate, because an endpoint that writes `group_ids` is the most dangerous surface this API could grow and it deserves its own handoff and its own verification.

If you find yourself writing a `POST` that touches membership, stop — that is 42.

---

## 3 · The prior art you must read first, and must not duplicate

**`myservice_api/models/access_change.py` and `access_recorder.py` already exist**, from handoff 24. They are an immutable forward record of every grant and removal — six hooks across `res.users` and `res.groups`, covering every structurally different way membership changes, including the Odoo 19 case where an implication grants rights while writing **zero** membership rows.

Read both module docstrings before you design anything. Three consequences:

- **The audit already works.** Anything handoff 42 later does will be recorded automatically, because the hooks are on the models rather than on any route. Do not build a second record.
- **`access_change.py`'s enumeration is your source of truth** for how membership can change. Its own docstring says the list was wrong twice. If this handoff makes you believe there is a seventh way, that is a finding worth reporting.
- **Its separation of concerns is the one to copy:** *"Nothing here changes who may grant what. This is a record, not a mechanism."*

There is also `GET /api/v1/reports/access-changes` already published. **Your screen should link to it rather than re-query it.**

---

## 4 · What to build

### A · Fix the two defects

**The category.** Give all three groups a `category_id` pointing at `module_category_nrs_assets`. This is display grouping only — it creates no implication and must not disturb the deliberate isolation of the Tag-Issuing Unit, which the file's own comment forbids tidying. Say in the report what the user form looks like afterwards, with a screenshot.

**The access rule.** The Tag-Issuing Unit needs enough database permission for a person in it to do their job from the barcode station. **Work out what that minimum actually is by driving it** — sign in as a user holding only that group and find every refusal — rather than granting read on everything and calling it done.

Then make a judgement and defend it: is the right answer a new `ir.model.access` row for the group, or is it that a human tagger should hold **Asset User + Tag-Issuing Unit** and we document the pairing? Both are defensible. I lean to documenting the pairing, because a tagger does need to read the register and Asset User already says exactly that — but you will have driven it and I have not. **Whichever you choose, the other option goes in `DECISIONS.md` with the reason it lost.**

### B · The read API

`GET /api/v1/users` — the people on this tenant and what they hold. Scope: `admin` only.

Fields: identity (name, login, email, active), the roles they hold in our own vocabulary (Asset User / Asset Manager / Tag-Issuing Unit / Auditor / System Administrator), and the **scopes those roles produce**, derived from `GROUP_SCOPES` rather than restated — so the screen can answer *"what can this person actually do"* without anyone maintaining a second copy of that table.

**One trap, and it is the reason this is not a five-line endpoint.** On Odoo 19 group implication is computed at read time and materialises no rows. So "the groups this user is in" and "the groups this user effectively has" are different questions with different answers, and Asset Manager implies Asset User. **Publish both, named so nobody can confuse them**, and say in the report which one the screen leads with and why. A user-management screen that shows a confident wrong answer about access is worse than no screen.

Also publish, per user, whether they are an API credential rather than a person — `myservice_api` creates a `res.users` per client, and those will otherwise appear in the list as mysterious staff.

### C · The screen

A **Users** page under Administration. A list — name, email, roles, active — with a filter by role and a search. A detail panel showing the roles, the effective scopes in plain words, and a link into the existing access-changes report filtered to that person.

**Every control that would change something is absent, not disabled.** No greyed-out buttons, no "coming soon". The next handoff adds them.

---

## 5 · Verification

- Sign in as a user holding **only** Tag-Issuing Unit and list every refusal you hit on the barcode station. That list is the evidence for §4A and I want it in the report verbatim.
- The user form after the category fix, screenshotted, showing the three groups where a person would look for them.
- The read endpoint against a tenant with real users: a person, an API credential, an inactive user, and someone holding two roles.
- Prove the direct-versus-effective distinction with an Asset Manager: direct shows one group, effective shows two.
- Confirm by reading `access_change.py`'s hooks that **nothing in this handoff writes membership**, and that no access-change rows were created by your own work beyond the category fix.
- Suites with denominators, and the standing sentence pass.

---

## 6 · What I want in the report for handoff 42

You will finish this knowing things I do not. Three questions to answer while you are in there:

1. **What refuses a privilege escalation today?** If an `admin`-scoped caller could write `group_ids` tomorrow, what in the codebase would stop them granting themselves `base.group_system` — anything, or nothing?
2. **Is mail configured on any tenant?** It decides whether handoff 43 can invite a new user or has to set a password, and the second needs a different design because this programme does not pass secrets through documents.
3. **Does `auth_signup` exist here?** `access_change.py` mentions `_create_user_from_template`, which suggests it might, and that changes how 43 creates people.

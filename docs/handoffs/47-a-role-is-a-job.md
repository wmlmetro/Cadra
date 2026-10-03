# Handoff 47 — A role is a job

**Branch:** `fix/a-role-is-a-job`
**Report:** `docs/handoffs/47-REPORT.md`

> **Needs the owner, named up front** — your report 46 was right that this block belongs at the start, not the end. This handoff needs: the PR merged; nothing here reaches the cluster; and the role changes land on tenants where personas already exist, so the persona matrix must be re-run after, not before.

> ## RUN THIS ONE. NOT 33, NOT 37.
>
> Three handoffs are unrun in this repository — `33-the-whole-surface.md`, `37-the-doors-and-the-red-tests.md` and this one. **This is the next one.** A Vendra Builder once had two pending handoffs and took the older; with three waiting here, do not repeat it. 37 follows this; 33 follows that and must be reduced per report 36's §4 table before it runs.
---

## 0 · Report 46 accepted

Six people, three independent marks, a seed that refuses a name a tenant's real staff already carry, and a remover that refused both a planted stranger and a tampered persona by name. The 27-item by six-person by two-tenant matrix, driven as each person with the hidden URLs typed, is the strongest verification this programme has produced.

Two of the things you found on the way matter more than the handoff did.

**A sign-in could inherit the previous account's scopes.** The owner is about to demonstrate this system by switching between personas in front of a client. Without that fix the second persona would have worn the first one's permissions, and the demo would have shown a storekeeper doing an administrator's job. It was found only because somebody signed in as six people in a row.

**Tag numbering walked every issued number past 999** — a text sort putting *999* above *8305*, costing about eleven seconds per asset registration, and **both live replicas were already paying it.** A performance defect on real client tenants, found while doing something else, with a test that fails on the old code.

And the dashboard showing a refused person 13,150 invented assets is the house defect again: an instrument reporting something while measuring nothing.

---

## 1 · Your §E, ruled

You found six things and invented nothing to cover them. Four are rulings; two are not.

### Ruling 1 · A scope that means two things gets split. Twice.

`identity:read` opens the employee picker a custodian needs **and** the record of who granted whom which role. `dashboards:read` opens the asset dashboard's figures **and** every Fleet, Staff Bus, facilities and security screen.

Both are one name carrying two meanings, which is the defect this programme has spent six weeks finding in other people's work. **Split both.** The employee picker and the access record are different questions; so are the asset dashboard and the fleet.

The access record goes to the Auditor and the Administrator. Note your own finding inside that one: *"The Auditor, whose job that is, had been unable to find it."* Splitting the scope fixes the wrong person seeing it and the right person not.

### Ruling 2 · Minting and replacing a tag is tagging, not asset-writing.

The tagging unit can confirm a label is on and cannot print one or replace a faded one, because those need `assets:write` — which would also let them create and edit assets outright.

That is the same shape a third time: `assets:write` means *edit an asset's data* and *mint its label*. **They are not the same act and these routes write a different model.** Move tag issuance and replacement onto the tagging scope where they belong. Then the unit's own scope covers its own job, which is what the owner and NRS both assumed it did.

### Ruling 3 · There is a role between reading the register and running it. Build it.

Your sharpest finding: *"a storekeeper able to register stock can also approve other people's moves and change the branding, the depreciation rules and the SAP integration."*

**A new role**, composing scopes that already exist — registering assets, requesting moves, recording a verification — **and not** `settings:write`, `integrations:write` or `approvals:write`. Name it for the job rather than the permission.

**This is inventing a role, not a scope**, and the distinction is the whole point: the scopes were reasoned about and are right; the bundling is wrong. If you find yourself needing a new scope string to make this work, stop — that means something underneath is mis-scoped and I want to hear which.

### Ruling 4 · The pairing stands.

Tag-Issuing Unit alone opening nothing is handoff 41's documented pairing working as designed, and now saying so in words on screen. Leave it.

### Not ruled, not in this handoff

**The Auditor's four reports with no screen** — configuration changes, disposals, the asset register, the export. They answer 200 to the auditor over the API and the app has no page for any of them. That is a build, it is the auditor's demo, and it gets its own handoff once this lands.

---

## 1b · Report 48's §C, ruled — three things leave the sidebar

Added 3 October. Report 48 produced the clearest account anybody has had of what this product's left-hand menu has accumulated, because every item had to be listed and given a default. Four of its findings are rulings and they are small, so they land here rather than in a handoff of their own.

**Staff Bus and Identity (clearance) come out of the menu.** Neither asks the server anything; both render sample data built into the app. Combined with everything defaulting to on, **every new client is shown two screens of invented content about their own organisation.** That is not a gap to toggle, it is something we should not be drawing. Take them out of the navigation and leave the code where it is.

One thing to say when you do: **NRS asked for the clearance screen by name.** Their offboarding question — *"whatever process you want to determine how those assets are retrieved"* — is what that screen pretends to answer. Removing the mock is right; it also means we owe them a real one, and report 43 §G.2 already found the mechanism exists in the back office. Note it in `GO-LIVE.md` as owed rather than dropped.

**The "All systems operational" pill goes.** A hardcoded badge on the front door, reporting a thing it does not check, to a client looking at their own register. It is the defect this programme is named after, in its purest form, in the most visible place we have. **Either it measures something or it is deleted** — and the day before a demo is not when to start measuring, so delete it and say in the report what it would take to make it real.

**IT Assets Command stays for now and is not a product line.** 69 of 11,951 assets on the real register, 0 on five of eight tenants: it is the asset list with one filter applied. The switch handles it today. Record in `DECISIONS.md` that it should become a saved view on *All Assets* rather than a menu item, so the next person does not treat it as a module.

**Fleet is not yours to decide and I am taking it to the owner.** The real NRS register holds **0 vehicles**, and on every other tenant every vehicle arrived in one bulk load on one day. No client has ever put a vehicle into this system. Whether fleet is in scope for anybody is a question for NRS, not engineering. Leave all four fleet screens exactly as they are.


---

## 2 · What this must not break

**Every persona's matrix changes.** The six accounts exist on seven tenants and their permissions are about to move underneath them. **Re-run the matrix after**, on both tenants, all six people, all items, hidden URLs typed — and put the before-and-after side by side. A role change that silently widens somebody is the only way this handoff can do harm.

**The API refuses first, the menu follows.** Same rule as 46: prove by typing the URL, as the person.

**Nobody loses access who should keep it.** Existing real accounts hold today's roles. Say, per tenant with counts, who is affected by each split and what they hold afterwards — and if anybody would lose something they use, that is a finding before it is a migration.

---

## 3 · Verification

- The full persona matrix, after, against 46's, both tenants.
- Each ruling driven: the picker without the access record; the asset dashboard without the fleet; the tagging unit printing and replacing a label on its own scope; the new role registering an asset and being refused the settings, the integrations and somebody else's approval.
- The counts from §2 per tenant.
- Suites with denominators, and the standing sentence pass.

---

## 4 · And then the toggles

The owner also asked for per-tenant control of which menu items appear — your §C's *"screens no role maps onto"* is the list that feeds it. That is the handoff after this one. **Do not start it here**, and when you write up §C's leftovers, write them as the input to that work.

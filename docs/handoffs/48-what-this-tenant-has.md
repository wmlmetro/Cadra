# Handoff 48 — What this tenant has

**Branch:** `fix/what-this-tenant-has`
**Report:** `docs/handoffs/48-REPORT.md`

> **Run this BEFORE `47-a-role-is-a-job.md`.** The owner asked for this one first and nothing in it depends on 47. 47 then lands on top. Both touch `ALL_NAV_GROUPS`, so they must not run at the same time.
>
> **Needs the owner:** merging; nothing here reaches the cluster; and `cadra19`, `nrs19` and `gtb19` still have no personas because they are unclassified (report 46 §*Needs the owner* 2).

---

## 0 · What this is, and what it is emphatically not

Report 46 made the sidebar answer *"may this person see it?"*. This answers a different question: **"does this organisation have it at all?"** Fleet Command means nothing to a tenant with no vehicles; Staff Bus means nothing to most of them.

**Two axes, and they must stay apart.** An item is drawn only when **the tenant has it switched on AND the person's role opens it** — both, every time. Report 46's §C listed the screens no role maps onto; that list is this handoff's input.

**And this is not a permission. Say so on the screen.** Switching Fleet off does not secure Fleet: the API answers exactly as it did, and anyone who types the address still gets their data. An administrator who thinks they have revoked something because a menu item vanished has been misled by us, and that is the defect this programme is named after — an instrument that appears to measure something it does not. **The settings screen must say, in words, that this controls what is shown and not what is permitted.** If a tenant genuinely must not have a module, that is installation, not a checkbox.

---

## 1 · What to build

A per-tenant setting an administrator controls, deciding which navigation items exist on this tenant.

**Four things to get right.**

1. **Key it on a stable identifier for each item** — not the label, not the path, not the scope. 47 is about to change the scope on several items and renaming or re-pathing one must never silently switch it back on. Pick the identifier deliberately and say why it is stable.
2. **Everything on by default**, so no tenant loses anything the day this ships, and a new item added later appears rather than hiding until somebody notices.
3. **Groups and items.** An administrator will want to switch off *Fleet & Transport* in one go rather than four times. If you support both levels, define what happens when a group is off and an item inside it is on — and pick the answer somebody can predict, not the one that is least code.
4. **A change here is a configuration change**, and this product already has a configuration-change report. It belongs there, not in the access record — that record is for permissions and this is not one.

**Where:** with the branding settings, which already have a per-tenant pattern (`/api/v1/settings/branding`). Administrator only.

### The trap

**An administrator must not be able to switch off the screen they are standing on.** Turn off *Settings*, and nothing can ever be turned back on from the app again. Whatever else this does, it must refuse that — and prove the refusal rather than assume the UI prevents it.

Think about the adjacent cases too: a group containing Settings, and an administrator switching off the only route to the administration screens. Say which you guarded and how you decided the boundary.

---

## 2 · Verification

- The setting changed and the effect seen, as an administrator and then as a persona, on two tenants with **different** items switched off — which is the whole point of per-tenant.
- **A disabled item's URL typed, and the data still returned** — proving to ourselves that this is presentation, exactly as the screen claims. If it ever refuses, the two axes have blended and that is a defect.
- Both axes together: an item switched on for the tenant and still absent for a persona whose role does not open it; and one the role opens but the tenant has off.
- The lockout refused.
- The configuration-change report showing who changed what.
- Default-on proved on a tenant that has never had the setting touched.
- Suites with denominators, and the standing sentence pass.

---

## 3 · One thing to report rather than solve

Report 46 §C found screens no role maps onto. Some of them may have no business being in this product at all for most tenants, rather than merely being switchable.

**Say which you think those are**, now that you have had to put every one of them in a list and give it a default. You will have the clearest view anybody has had of what this sidebar has accumulated, and that is worth more to me than the feature.

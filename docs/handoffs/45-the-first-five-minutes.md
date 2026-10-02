# Handoff 45 — The first five minutes

**Branch:** `fix/the-first-five-minutes`
**Report:** `docs/handoffs/45-REPORT.md`
**Runs after 44.**

> **Owner-blocked verification, named up front**, because report 43 was right that a handoff should say so rather than discover it: the cluster inbox check cannot be completed by the Builder. Do what can be done locally, say exactly what is left, and list it under *Needs the owner* rather than treating the handoff as unfinished.

---

## 0 · Report 43 accepted

The door was shut by accident, not by decision — the setting everyone looks at said *free sign-up* on all eight tenants and was never consulted, because the website module substitutes its own. **One click on a Settings screen would have opened it.** Finding that the safe state was luck rather than design, and then making it code that no setting can undo, is worth more than the feature the handoff was named for.

Two other things earned their place: refusing to create the account when the letter cannot be sent, so nobody is left existing and uninformed; and finding that a deactivated person's live token kept working, which §3's *"prove the account cannot sign in"* would have passed while being false in practice. That is the defect class this programme is named after, caught in your own verification of your own work.

---

## 1 · Four rulings

**G.1(a) — yes.** Publish `approver.active` on the queue row and say *"the approver cannot sign in"* on the Approvals screen. You called it clearly right and it is.

**G.1(b) — re-nomination, recorded. Deactivation is never blocked.** The reasoning is the direction of the risk: if somebody must be cut off, that happens the moment the decision is made, and a queue must never be able to hold an account open. So the stranded request is fixed forward — a pending request can be re-pointed at a different approver, as an act with a name and a time on it. The model's `write` today refuses everything but `_transition`, so this is a real change rather than a field; keep the refusal and add the one path, do not loosen the model.

**`sent_by` naming the credential — keep it.** It is true, and *"sent by Smoke Test (API client)"* reads oddly precisely because it is telling you something real. Odd-but-true has beaten tidy-but-false every time in this programme.

**Recording a deactivation — yes, build it.** You framed it exactly right: the auditor's question *"who removed this person's access and when"* has an answer in `write_uid` and `write_date`, and not in the report they read. Deactivation is the most complete removal of access there is, and an access-change report that shows a role grant but not an account being switched off is an instrument that measures less than it appears to. Reactivation too, and the same for the invitation being cancelled if that is a separate act.

---

## 2 · Odoo is invisible to everybody who is not a developer

The owner tested the invitation and drew a stronger conclusion than §H.1's *"brand the Odoo page"*, and they are right: **the back office should not be a place any NRS officer can arrive at, by any route, ever.** Restyling Odoo's sign-up form would make the seam prettier. This removes it.

### 2.1 · The redemption page belongs in our app

Today the letter's link lands on Odoo's `/web/signup`, the person sets a password there, and `_get_signup_url_for_action(url=LANDING_PATH)` redirects them into our app afterwards. So the app owns the beginning and the end, and Odoo owns the middle — which is exactly the step where somebody decides whether this is a real system.

**Build the middle in the SPA**, where login already lives. One brand source, one design system, and nothing to keep in sync with an inherited view. It needs an API route to redeem a token — validate it, set the password, and sign the person in — and the same again for a password reset.

Four things to get right:

1. **Password rules must be the ones Odoo actually enforces**, discovered rather than guessed, and every refusal rendered in words on our page. A page that accepts a password the server then rejects is worse than Odoo's.
2. **The token's failure modes are the page's job**: already redeemed, expired, cancelled, never valid. Each gets a sentence and a way forward, not a stack trace. Report 43 built `never / outstanding / expired / redeemed / cancelled` on the invitation already — reuse that vocabulary rather than inventing a second one.
3. **Invitations already sent carry the old link.** Decide what happens to them — keep the Odoo path working for outstanding tokens, or re-send. Say which, and make sure nobody who was invited yesterday is stranded.
4. **Reset too**, and the app's login needs the *Forgot password* link it does not have (old §H.2).

### 2.2 · Then shut the door on the back office

Anyone who is not a system administrator is redirected to the app if they reach the back office, by any path — the letter, a bookmark, a guess, a link somebody pastes them.

**And here is the trap, which I want handled before anything is blocked.** The back-office *interface* and Odoo's *infrastructure* share the `/web` prefix, and they are not the same thing. Blocking too broadly will break things that are not obviously related — asset and image serving, attachments, and in particular **report PDFs, which is how a barcode label prints.** The barcode station's print path goes through Odoo's report rendering, and a tagger is not a system administrator.

So: enumerate what must keep working for a non-administrator, **by driving the app as one and watching what it requests**, not by reasoning about URL prefixes. Then block the interface and leave the plumbing. If that enumeration shows the split cannot be made cleanly, stop and report it — a half-blocked back office that breaks label printing is far worse than a visible one.

**System administrators keep full access.** This is about who can arrive, not about removing the tool we work in.

### 2.3 · The rest of §H, unchanged

**H.3 · The relay drops the plain-text part.** `myservice_email_relay` posts HTML only, so on the cluster a government client that strips HTML sees nothing at all. Every word I wrote in §1b about the letter standing on its own in plain text is currently false in production. Add the text part and prove it on a received message.

**H.6 · The sender address.** A tenant with no company email cannot send a letter. It refuses in words, which is right; put the setting where the brand is set, so whoever stands a tenant up meets it.

**Not in this handoff:** H.5, offboarding custody from the app — the largest item on your list, NRS's own question, and §G.2 showed it runs through the employee record and SAP status rather than the account, so it needs a conversation with them before it needs code. H.7 is ruling 1 working as intended. H.8 is cosmetic.

## 3 · Verification

- The whole journey as a new officer meets it, on two differently-branded tenants, screenshotted at every step: letter → our page → password set → signed in. Odoo must not appear once.
- Each token failure — redeemed, expired, cancelled, invalid — shown as the page renders it.
- The reset link from the app, followed through to a changed password.
- **Driven as a non-administrator: every back-office path redirects, and the app still works completely — including printing a barcode label**, which is the one most likely to break.
- A system administrator still reaching the back office normally.
- **A received message with the plain-text part present**, read with HTML disabled. Locally if that is as far as you can get, and say so.
- The approver-inactive flag on a real stranded request, and a re-nomination performed, with the record read back naming who re-pointed it.
- A deactivation and a reactivation appearing in the access-changes report.
- Suites with denominators, and the standing sentence pass.

---

## 4 · One measurement from your report that changes what we tell NRS

> `nrs19` links **1 of 11,386** employees to a user, and **87 of 6,646** custodied assets are held by one of its **207 archived employees**, none flagged for retrieval.

Two things follow, and both are for the owner rather than for you.

Custody in this system is held by **employee records**, not by accounts — so NRS's offboarding question was never about deactivating a login, and the answer we give them must say so plainly rather than let them assume the two are connected.

And eighty-seven assets are currently recorded as held by people who have left. That is not a defect in our software; it is a finding about their register, and it is exactly the kind of thing they asked us to surface. **Confirm that count once more against the live tenant before it is quoted** — a number of ours was wrong in front of a client once already this programme, and I would rather check it twice than explain it once.

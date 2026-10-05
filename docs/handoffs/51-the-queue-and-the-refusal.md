# Handoff 51 — The queue and the refusal

**Branch:** `fix/the-queue-and-the-refusal`
**Report:** `docs/handoffs/51-REPORT.md`
**Runs after:** handoff 50. **Do not start until `fix/the-consequences` is
merged into `dev`** — §1 touches `v1_tags.py` and the Approvals page, §3
touches two specs 50 recorded, and 50's own route changes to
`/dashboard/map` are a premise here. Branch from `dev` after the merge.

**This is the last Cadra handoff before the demo.** It closes four rulings I
made and never wrote up. Two of them I am withdrawing, having gone and
looked — §4 and §5 say why, and say it in the repository rather than only in
a chat, because a withdrawn ruling that lives nowhere comes back as somebody
else's good idea in three months.

---

## 0 · Report 50 is accepted in full

Including the three things in it that were measurements rather than
compliance:

- **`export:read`** named for a reason drawn from an existing test's
  invariant (`test_auditor_access.py` pins every Auditor scope to `:read`),
  not from my preference. That is the right way to pick a published name.
- **§2.2 left every credential row untouched** and handed the decision list
  back under §F rather than guessing at nine tenants' intent. Correct. Those
  decisions are mine and they are below in §6.
- **§3 refused to call either red spec handoff 37's defect.** Both predate
  it, both fail at every hour, and you said so with the failure texts in
  hand — texts nobody had ever written down. The honest consequence is that
  §3 of this handoff is smaller than I would have written blind.

And the trailer is now refused by a hook and a CI job over exactly the new
commits of a push. That rule has stopped depending on anyone's memory,
including mine. Nothing below re-states it.

---

## 1 · One queue, because a request nobody can find was never made

**The defect, as the owner hit it:** a tag replacement request was raised
with an approver named, and appeared on neither the approver's screens nor
the requester's. Both halves are true and the cause is not in the model.

What is actually there, measured on `dev`:

| | Asset-movement requests | Tag replacements |
|---|---|---|
| Route | `GET /api/v1/approvals` | `GET /api/v1/tags/pending-replacements` |
| `waiting_on_me` filter | **yes** | **no** |
| `raised_by_me` filter | **yes** | **no** |
| Any filter at all | state, change_type, asset_id | **none** |
| Rendered on | `/approvals` (`Approvals.tsx`) | a panel on `BarcodeStation.tsx`, and nowhere else |

The model is not the problem. `nrs.asset.tag.label` already carries
`approver_id`, `requested_by`, `requested_date`, and `serialize_tag`
already computes **`can_decide` for the calling user**, the same way
`serialize_request` does. Every fact the screen needs exists and is
published. The request went exactly where it was supposed to go; the only
place it is displayed is a tagging console that an Asset Manager has no
reason to open.

### 1a · A sibling route, not a widened one

Add **`GET /api/v1/tags/replacements`**, taking `state` (the model's own
values), `waiting_on_me`, `raised_by_me`, and the standard pagination
params. Scope `assets:read`, for the reason `pending-replacements` already
gives in its own docstring and which still holds: an Auditor must be able to
read what is waiting and on whom without being able to decide any of it.

**Leave `pending-replacements` exactly as it is.** Do not add `state` to it.
A route published as *pending* that can be made to return decided rows is
this programme's third defect class — one published name carrying two
meanings — and I would rather carry two routes than one lie. Point its
docstring at the new one and say which is which. Whether the old one is ever
retired is a later decision and not yours to take here.

The reason the new route needs `state` and not just the two `me` filters:
`pending-replacements` returns pending rows only, so `raised_by_me` bolted
onto it would still answer *"nothing"* to a requester whose request was
approved an hour ago. **The requester's question is not "what is pending",
it is "what happened to mine"** — and that question cannot be answered by a
pending-only endpoint however many filters it grows.

### 1b · One screen answers both questions

`/approvals` shows tag replacements beside asset-movement requests. Both
kinds in the same tabs, every row saying plainly which kind it is, and the
tabs keeping the meaning they already have.

Read the comment at the top of `Approvals.tsx` before you touch its tabs —
the one recording that `GET /api/v1/approvals` takes **one** `state` while
three tabs want one state each. Whatever that comment describes is load-
bearing; this handoff does not licence re-cutting it, and a second source
behind the same tabs is the obvious way to break it by accident.

Two rules for the rows:

- **Never offer a button the server will refuse.** `can_decide` is already
  computed per caller and the server already has the refusal text for a
  requester deciding their own request — *"You asked for this replacement.
  Ask an approver to reject it, or let it stand."* A requester must see
  their row and see that it is not theirs to decide. Drive this as the
  requester and show the row with no decide control.
- **An empty tab says it is empty.** Report 49's rule, unchanged: never
  invented data, never a spinner that has stopped.

**Keep the Barcode Station panel.** A tagger standing at the station should
still see what is waiting there. One screen answering the approver's and the
requester's question does not mean one screen in the product.

### 1c · The scope note worth writing down once

The Tag-Issuing Unit holds `tagging:write` and nothing else, so a
tagging-only user **cannot** read either replacement route — they need
`assets:read`, which arrives by pairing with Asset User. That is the pairing
we already ruled on and it is still the answer. Put one sentence to that
effect next to the new route so the next person does not rediscover it as a
bug.

---

## 2 · A refused affix leaves a record

`_mark_affixed` in `asset_tag.py` checks the scanned number against the
label's own number and raises on a mismatch. The check is the control, and
the control is right. **What is wrong is that a refusal leaves nothing
behind.**

And the refusal text names the expected number:

> *Scanned tag %(scanned)s does not match the tag issued for this asset
> (%(expected)s).*

I ruled in handoff 39 that the text stays verbatim, and that ruling stands —
a person holding the wrong label needs to be told which label is wanted, and
a refusal that withholds it sends somebody back across a compound to guess.
But it means **one wrong entry reveals the right answer**, and a second
attempt with the revealed number will pass. Today that sequence leaves
exactly one trace: a clean affix record saying a human verified the label.

Record the refusal, and the sequence stops being invisible: a refusal and a
confirmation seconds apart, same asset, same operative, is a pattern anybody
reading the history can see. That is the whole fix. It does not block, it
does not warn, it does not score anyone. It writes down what happened.

### 2a · Where it goes

`nrs.asset.event` — the stored, append-only record, `ondelete='restrict'` on
the asset for the reason its own comment gives, and already the source
`asset_history.py` prefers over chatter wherever a row exists.

Adding an event type there is deliberately not a one-line change. The model
inherits `nrs.asset.append.only.mixin`, refuses hand-written rows
(`_no_hand_written_rows_message`), and accepts a row only through a declared
context source. So the work is: the new type in the `event_type` selection,
its payload shape in `_PAYLOAD_OF_TYPE`, a new `source` value for the affix
route, and the label and coverage entries in `asset_history.py` so the event
renders as a sentence rather than a key. **Do not loosen a single one of
those guards to make the row go in.** They are the reason the history is
evidence. If one of them genuinely cannot accommodate this event, stop and
say so in the report with the measurement — that is a finding, not a
failure.

Payload: the scanned value **as entered**, the asset, the operative, the
time. The expected number is already on the label row and does not need
copying into the event.

### 2b · The trap, named, because it is how this ships broken

`_mark_affixed` raises `ValidationError`. **A row written in a transaction
that then unwinds leaves nothing, while every assertion made inside that
same transaction passes.** An instrument that reports success while
measuring nothing, which is this programme's second named defect class, and
it is the single most likely outcome of this section.

So the verification is not "the test asserts a row was created". It is:

1. Call `POST /api/v1/assets/<id>/tag-affixed` over HTTP with a wrong
   number. Get the 4xx. Confirm the refusal text is unchanged and still
   names the expected number.
2. **In a new session, after the response, with a separate read** — count
   the events on that asset and show the refusal row, by its own id, with
   its payload.
3. Confirm the label did **not** move to `affixed` and that no field on it
   changed.
4. Then the sequence: wrong number refused, correct number accepted, both
   rows present in order on `GET` of the asset's history, with the gap
   between them visible.

Whether the row survives at all depends on where it is written relative to
the raise, and on whether a flush has already reached the database. **Do not
reason your way to an answer — measure it, and say in the report which
placement you measured and what the other one did.** If you had to write on
a separate cursor, say that, and say what you checked to be sure the record
cannot outlive a *successful* affix being rolled back for an unrelated
reason.

---

## 3 · The two red specs — spec 13 fixed, spec 14 measured

Report 50 named both for the first time. The two halves are not the same
size and must not be treated as one task.

### 3a · Spec 13 — fix the fixture

The spec takes the first computed-method asset without checking it has an
acquisition cost and a useful life; on `test19` that asset has neither, the
product renders its honest *"No schedule yet"* empty state, and the spec's
assumption fails. **The product is right and the spec is wrong.** Select the
first asset that is actually chartable — computed method, cost present,
useful life present.

And the part that matters more than the fix: **if no such asset exists on
the tenant, the spec fails or skips loudly with that stated as the reason.
It does not pass.** A spec that quietly finds nothing to assert and goes
green is the defect class above wearing a test's clothing. Say in the report
which of the two you chose and why.

### 3b · Spec 14 — read the payload, do not fix the cache

The flip passes; the post-reload state stays unchecked for the full 30 s
with no refetch, which matches GO-LIVE §16.3 item 8's persisted-cache
hypothesis point for point. You correctly left it labelled a hypothesis
because **nobody has read the localStorage payload mid-test.**

Read it. Dump the persisted cache between the click and the reload, and
again after the reload, and put both in the evidence file. That settles
whether a restored pre-click payload is what the screen renders.

**Do not change the cache policy in this handoff.** If the hypothesis holds,
the fix is a decision about `staleTime` and the persister's write throttle
across every screen that uses them, and that decision is mine to make from
your measurement — handoff 29's family is exactly where a local fix becomes
a product-wide one without anybody noticing. If it does **not** hold, say so
plainly; a disproved hypothesis of mine is worth more than a fix.

---

## 4 · IT Assets Command — I am withdrawing this ruling

I ruled that `ITAssetsCommand.tsx` should become a saved view on the asset
list. Having read it: 266 lines, a condition breakdown, and a map of the
sites where the category's assets sit. A saved view is not that, and
demoting it would delete two things to save one page.

The thing that actually bothered me — that one category has a top-level
command center when no other does — **handoff 48 already answered.** The
sidebar is a per-tenant switch now. A tenant that does not run IT assets as
a programme turns it off; a tenant that does keeps it. That is a better
answer than mine, it is already shipped, and it needed no further work.

**Do nothing here but one check**, which is cheap and is a live consequence
of handoff 50: the page reads `dashboard-map` and takes `locations` from it.
Handoff 50 moved the vehicle rows out of that payload. Load the page and
confirm the pins still render and nothing else on it went blank. I read the
source and believe it is unaffected; reading is not loading.

Record the withdrawal in `docs/retired-screens.md` or beside the page, in
one or two sentences: considered for demotion, kept, because the per-tenant
switch is the right control.

---

## 5 · The Security Command Center — also withdrawn, and this one I had wrong

I ruled it should be deleted as dead code. It is dead — not in any bundle,
no action record, `core.action_registry` returns false for all three tags —
and `docs/retired-screens.md` already says so with the commit archaeology
that explains how it got that way.

**But deleting it is the wrong move and my ruling was based on a thinner
picture than the repository already holds.** Three facts I had not weighed:

1. It ships to **nobody**. Not in a bundle means not fetched, so there is no
   runtime cost to leave it where it is.
2. `test_source_guards.py::test_the_retired_screens_stay_retired` already
   guards it, by tag, against being put back into a manifest without an
   action record — the exact way it would silently start shipping again.
3. `docs/retired-screens.md` already carries the port estimate — *portable,
   mechanical, ~2 days.* Deleting the source turns a documented, reversible
   decision into a git-archaeology exercise, and buys nothing.

The Security menus work today; they open ordinary list views over
`security.incident` and `security.guard`. Nothing is broken and nothing is
being shipped.

**So: delete nothing here.** And specifically do not go near either item
under that document's *"must not be tidied up"* heading —
`security_navbar.css`, which despite its name restyles the top navigation of
every backend screen in the product, and `static/lib/leaflet/`, which
`fleet_dashboard.js` hard-codes by cross-module URL. Those two are why a
tidy-up pass in this module is a visible regression waiting to happen.

Add one line to `docs/retired-screens.md`: deletion considered on 5 October
and declined, with the three reasons. The next person to have my idea should
find the answer already there.

---

## 6 · The credential-scope decisions from report 50 §F

§2.2 re-took the counts on all nine tenants and touched no row, which was
right. The decisions are mine and I am not making them from a count alone.

**For each `[open]` row in §F, state in this handoff's report: which
credential, which tenant, what it is used by if anything can be determined,
and when it last authenticated.** Last-use is the fact that decides it — a
credential provisioned under the old scopes that nothing has used since the
split is a different object from one a live integration authenticates with
hourly, and the counts do not distinguish them. If last-use is not recorded
anywhere, say that; *"we cannot tell"* is the finding and I will rule on the
basis of it rather than on a guess.

Change no credential in this handoff.

---

## 7 · The three unclassified tenants

`cadra19`, `nrs19` and `gtb19` have no personas because nobody has said what
they are, and that has now blocked work across seven handoffs. I have asked
the owner in prose and prose has not moved it. So let the data ask.

For each of those three, report: asset count, location count, employee
count, how many users exist and in which groups, whether any credential has
authenticated in the last 30 days, and the newest `create_date` on
`nrs.asset`. Six numbers each, in one table.

That table is a question the owner can answer in a sentence — *this one is a
client, these two are ours* — which is what I have failed to get by asking.
**Classify nothing yourself and seed no personas into any of the three.**
The `nrs19` lesson stands: I once told you that tenant had no locations and
it had 1,154, and had you obeyed me you would have seeded into live data.
Report the numbers; the classification is the owner's.

---

## 8 · Verification

The standing set, with denominators where a denominator exists:

1. Full suite and the journeys, with times.
2. §1 driven as **three** people, not one: the requester (sees their row,
   no decide control, sees the outcome after a decision), the named approver
   (sees it in `waiting_on_me`, decides it), and the Auditor (sees it and
   has no control at all). Transcripts of the scope refusals where there
   are any.
3. §1 driven as a tagging-only user, showing the 403 from §1c with the
   required scope named — so the pairing requirement is on record as a
   measurement and not as my assertion.
4. §2 exactly as §2b sets out, including step 2's separate read.
5. §3a both ways: the fixed spec green, and the spec red or loudly skipped
   against a tenant with no chartable asset. Contrive the second case.
6. §3b both payload dumps in the evidence file.
7. §4's page load.
8. `GET /meta/routes` or whatever the published-names census of handoff 50
   §5 D1 now uses, re-run over the new route, with the denominator printed.
   A route added without its published name resolving is the thing that
   census exists to catch, and this handoff adds one.

And the standing one, which has earned its place: **before you finish, read
every sentence you wrote in this handoff's code, comments and docs and check
each against something you measured.** Report what it caught, including
nothing if nothing.

---

## 9 · The question I want answered in the report

This is the last Cadra handoff I have written. After it, what I believe
remains is the clearance screen — blocked on NRS saying what clearance
means — and a cache-policy decision that depends on §3b.

**You have the only complete view of the surface. What do you believe is
still wrong with Cadra that I have not asked you about?** Ordered by what it
would cost on a government system, with the measurement that makes you
believe it. Not a wish list and not a refactor plan: the things that are
untrue, unmeasured, or reporting success while measuring nothing.

I would rather read that list now than discover it after the demo.

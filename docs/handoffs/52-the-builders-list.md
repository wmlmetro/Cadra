# Handoff 52 — The Builder's list

**Branch:** `fix/the-builders-list`
**Report:** `docs/handoffs/52-REPORT.md`
**Runs after:** handoff 51 (merged, PR #111). Branch from `dev`.

---

## 0 · Report 51 is accepted in full — and I was wrong that it was the last one

I wrote in 51 that it was the last Cadra handoff before the demo, and asked
in §9 what you believed was still wrong that I had not asked about. You
answered with six things, each with a measurement. Four of them are visible
on a screen somebody will be looking at during the demo. So this handoff is
your list, and that is exactly what §9 was for — I would rather be wrong
about "last" than right about it and have *"21 Furniture records"* under a
heading that says IT.

Three things in 51 deserve saying plainly before the list:

- **§4's page-load check caught a crash reading had missed.** A hook called
  after three early returns — React error 310 on any tenant that actually
  has an IT category, which `test19` does not, so every prior run was green
  for the wrong reason. *Reading is not loading* was a sentence I wrote
  because it sounded right; you made it a finding.
- **§2's trap bit in miniature and the test caught it.** `assertRaises` is
  itself a savepoint and unwound the recorder's write — the production
  defect reproduced inside the test built to prove its absence. You measured
  both cursor placements rather than reasoning to one, and the probe shows
  the flush *does* reach the database and the rollback *does* take it back.
  That transcript is the clearest statement of the second defect class this
  programme has.
- **§3b: the hypothesis holds, and you caught yourself misreading the dump
  first.** A dump without the expected value beside it reads as whatever you
  already believe. The instrumentation that prevents that is now permanent
  in the spec. §5 below is the ruling the measurement was waiting for.

Spec 13 is green for the first time since report 29. The standing red pair
is down to one, and that one is now a decision rather than a mystery.

---

## 1 · The badge counts both kinds of waiting work

`Sidebar.tsx` reads `GET /approvals?state=pending&waiting_on_me=true` and
shows that number. On `test19` there are **194 pending tag replacements**
and the badge counts zero of them. 51 put the replacements on the page; the
number beside the menu item still says they are not there.

Sum the two `total_estimate`s — the movement queue's and
`GET /tags/replacements?state=pending&waiting_on_me=true`. Both routes are
`assets:read`, both are already called by the Approvals page, so this is one
more query behind an existing number. If either call fails, the badge shows
nothing rather than half — a badge that says *3* when the truth is *3 plus
an unknown* is the same under-report with a confident face.

Drive it: as the Asset Manager on `test19`, badge before and after one tag
replacement is approved, both numbers recorded.

---

## 2 · The station panel stops pretending a page is the queue

`fetchPendingTagReplacements` asks for `limit: 100`, reads no cursor, and
the Barcode Station panel renders what comes back as the whole of what is
waiting. `test19` holds 194. The console the Tag-Issuing Unit actually
stands at shows at most 100 with nothing saying so — report 49's rule in
reverse: a full panel that is secretly a page.

Either page it (the route returns `next_cursor`; the panel gets a *more*
control and says *showing 100 of about 194*) or cap it honestly (*the 100
most recent — N more on the Approvals page*, with the real N from
`total_estimate`). Choose by what a tagger at the station needs and say why
in the report. **Not acceptable:** a list that ends without saying whether
it is the end.

---

## 3 · A screen called IT does not count Furniture

`fetchITAssetsDashboard` matches categories with `/IT|computer|laptop|server/i`.
Case-insensitive, so the *it* in *Furn**it**ure* qualifies. Measured on
`jaizbankplc`: the page titled **IT Assets Command** reports **21 Furniture
records**. On a register whose categories are someone else's data, a command
centre that quietly adopts the wrong programme is a wrong-numbers screen
with a confident title — and it is one of the three dashboards in the
sidebar's first group.

Two changes, both required:

1. **The match cannot be satisfied by a substring.** Word boundaries at
   minimum (`\bIT\b`). Better, if `nrs.asset.category` carries a code or a
   stable key, match on that and say so. Measure what the model has before
   choosing; do not add a field for this.
2. **The page says which category it matched**, near the title, every time —
   *Showing: Information Technology (142 assets)*. The furniture count was
   visible on the page and nobody noticed, because the heading said IT and
   the eye believed the heading. A page that names its own denominator
   cannot do that to the next reader.

Drive it on `jaizbankplc` before and after, screenshots both. Then check the
other two dashboards in that group for the same pattern — the fleet one in
particular, if it selects by name — and report what you find, fixing it only
if it is the same one-line class.

---

## 4 · The two refusals that still vanish

51 records the number-mismatch refusal — the one that reveals the expected
number. Two more leave nothing:

- **The scrapped-label refusal** in `_mark_affixed`, raised before the
  number check.
- **The serial-mismatch refusal** on the route itself — the `err(...)` path
  that never raises, so the recorder never sees it. This one is the exact
  *label going onto the wrong box* event an auditor wants, and it is the
  cheaper tell, since it reveals nothing to the person being refused.

Same recorder, two more call sites, same `affix_refused` type with the
payload saying which refusal it was (`reason: scrapped | number_mismatch |
serial_mismatch`, or the shape you judge honest — the history sentence must
differ per reason, so a reader can tell a wrong label from a dead one).

The §2b discipline from 51 applies unchanged: **a separate read, in a new
session, after the 4xx**, for each of the two. The `err(...)` path is on the
request cursor with no exception in flight, so its placement question is
different from the raise's — measure it rather than assume the 51 answer
carries.

---

## 5 · The cache ruling — a restored copy is a sketch, not a fact

The §3b measurement: after a reload, the persisted `depreciation-settings`
entry came back with the **pre-click** payload (the 1 s write throttle had
not flushed the post-click write), identical `dataUpdatedAt`, and the screen
rendered it for the full 30 s because a restored entry inside `staleTime` is
treated as fresh. In the passing retry the entry happened to be absent, the
page fetched, and told the truth — which is why the spec is intermittent.

This is handoff 29's family and it is not a depreciation defect. The
`App.tsx` comment block already holds the principle for the keys it
excludes: *a question about right now is never restored from disk.* The
ruling extends it to everything else:

**Whatever is restored from the persisted cache paints immediately and is
refetched immediately. Restored data is never fresh.**

So: on successful restore, every restored query is marked stale and the
mounted ones refetch at once; with `refetchOnMount: true` already in place,
the rest refetch when they mount. Instant paint from cache is preserved —
that is what the persister is for — and the server's answer replaces it
within one round trip. The 5-minute `staleTime` stays for data the *running*
session fetched itself; it just no longer applies to data that crossed a
reload.

Three constraints:

- **The exclusion list is untouched.** The keys that are never persisted
  stay never persisted — a pending approval flashing stale for one round
  trip is still a lie for one round trip.
- **Do not lengthen or remove the write throttle to make the spec pass.**
  That hides the mechanism; the ruling is about what a restored entry is
  allowed to claim, not about winning the race.
- **No per-key fix.** Excluding `depreciation-settings` from persistence
  would make spec 14 green and leave every other settings key with the
  defect. If, after the rule is in, you believe a key should also be
  excluded, say so in the report and I will rule.

Proof: spec 14 green three runs in a row with the no-pause instrumentation
**kept**; the post-reload dump showing the entry refetched (a changed
`dataUpdatedAt`, not an absent entry); and the journeys, because a refetch
burst on every reload is the cost of this ruling and I want to see it
measured — page-ready times before and after on three screens, in the
report.

---

## 6 · Two guards

### 6a · The scope map cannot drift silently

The SPA's `SCOPE` map (`use-scopes.ts`) and `SCOPE_WORDS` (`Users.tsx`)
restate scope names that `utils.py` owns. A scope renamed server-side fails
in the one place that decides what a person sees, and fails silently —
report 50 §J.10, unchanged since.

One test, on whichever side can read both: every scope the server publishes
appears in both maps, and nothing in either map is a scope the server does
not publish. The existing static guard that compares `SIDEBAR_GROUPS` to
`ALL_NAV_GROUPS` is the pattern; copy it, and have it print the denominator.

### 6b · The endpoint reference is held to the census

`docs/api/cadra_api_endpoint_reference.md` presented itself as the endpoint
index and carried none of the five tag-replacement routes from handoff 38
until 51 noticed. Nothing holds it to the census's **143** declarations.

A test that diffs the reference's route table against the census output and
fails naming each route present in one and absent in the other. If the
reference legitimately omits internal or inherited routes, the test carries
the exclusion list in one place with a sentence per exclusion. A reference
complete except where it isn't is how an integrator builds against half an
API; after this, it cannot be complete except where it isn't without a red
test saying where.

---

## 7 · Verification

1. Full suite, in-registry with denominators, the census, the journeys —
   with times, and §5's before/after page-ready numbers.
2. §1 and §2 driven on `test19` with its 194 pending replacements, numbers
   recorded.
3. §3 on `jaizbankplc`, screenshots before and after, plus the report on
   the other two dashboards.
4. §4 as 51 §2b — separate read after each 4xx — for both refusals.
5. §5 as stated: three green runs of spec 14, the refetched dump, the
   timing.
6. §6 both guards red once (contrive a drift, contrive an omission) and
   green after, so the report shows they can fail.
7. Fan-out on all nine databases if any server-side selection or source
   value changed; otherwise say none did.

And the standing sentence check, which caught two in 51 and earns its place
every time.

---

## 8 · What is with the owner, not with you

Two things from 51 I am carrying to the owner in the same message that hands
you this file, so you can leave them alone:

- **§F — the credential last-use read.** Your permission layer refused a
  cross-tenant read of production replicas and you did not go around it.
  That was right. The command is in your report, verbatim, and the owner
  runs it.
- **§G — the three tenants.** Nothing classified, nothing seeded. The nrs19
  line — 11,951 assets, 11,386 employees — is the owner's sentence to say.

Do not seed personas into any of the three in this handoff regardless of
what the numbers suggest.

---

## 9 · The question for the report

Shorter than 51's. After this list is done: **is there anything on the
sidebar's first screen — the asset dashboard every persona lands on — whose
number you have not personally traced to the query that produced it?** Name
each tile, the query behind it, and whether its denominator is printed
anywhere a user can see. That screen is the first thing NRS will look at.

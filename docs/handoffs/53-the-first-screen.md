# Handoff 53 — The first screen

**Branch:** `fix/the-first-screen`
**Report:** `docs/handoffs/53-REPORT.md`
**Runs after:** handoff 52 (merged, PR #112). Branch from `dev`.

---

## 0 · Report 52 is accepted in full

Six items, each proved by using the screen. Three things in it changed what I
know, and they go first.

**The ruling exposed a test that was passing on a value the server never
held.** Spec 14 flipped the switch optimistically, asserted, and reloaded
before the PATCH had answered — the reload aborted its own save. It went
green whenever the persisted copy happened to restore the post-click
sketch. "A browser trusting its own memory" was not only the product's
defect; it was the test's. Refetching on restore made the screen tell the
server's truth and the spec finally failed for the right reason. **The
standing red pair is zero.** 199 of 211 green, 12 documented skips, in a
full run, for the first time in this programme's browser suite.

**The stable key I preferred would have missed every real IT asset.**
`domain='it'` is a seed value; the one IT category that actually holds
assets on Jaiz was client-created and carries neither code nor domain. The
name was the only key every tenant fills in. You measured that on eight
tenants before choosing, and the word boundary was the right answer for a
reason I had not seen.

**And the endpoint index carried 64 rows of 115.** Fifty-one routes an
integrator would have assumed did not exist, including the affix route and
all five reports. The guard ships with an empty exclusion table because you
brought the document to the code instead of excusing the gap. That is the
right direction every time.

The err-path measurement was the opposite of 51's — a row beside `err()`
survives, because nothing rolls back — and the shared recorder shipped
anyway so the row stays final if that `err` ever becomes a raise. Right call,
stated for the right reason.

---

## 1 · The header on the landing screen tells the truth

`AssetRegisterDashboard.tsx:138` — the first line NRS will read on the
first screen every persona lands on:

> NRS Facilities Management · staging.app.cadra.ng · Last updated: …

Three claims, one of them true. **"NRS Facilities Management" is hardcoded**
on an app that serves Jaiz and GTB from the same bundle; on their tenants it
names the wrong organisation. **`staging.app.cadra.ng` is hardcoded**; on
production it names the wrong host, on a laptop it names a host the laptop
is not on. And beside them a **green dot (line 135) that is always green**,
wired to nothing — the *All systems operational* class from handoff 47.

- The organisation comes from `getBrand().name`, which the sidebar already
  uses. The host comes from `window.location.host`, or is dropped — a
  header that says where you are adds nothing to the address bar, and I
  lean to dropping it; say which you did and why.
- **The dot goes.** Not re-wired: a health indicator needs an instrument
  behind it, choosing that instrument is a decision, and a dot that
  measures nothing is worse than no dot. There are **four** always-green
  dots on this page (135, 334, 370, 419). Each one either reflects a value
  the page actually holds — a count that loaded, a query that succeeded —
  and changes colour when it does not, or it is removed. A dot that cannot
  turn red is decoration pretending to be a reading.
- **"Last updated"** is one query's clock standing for five. Either it is
  the oldest `dataUpdatedAt` of the five (the honest "nothing here is older
  than") or it says which query it is. Oldest-of-five is the right answer;
  take it unless you find a reason not to.

Drive it on `jaizbankplc` and on `test19`: the header before and after,
both tenants, so the report shows the same bundle naming two organisations
correctly.

---

## 2 · The strip partitions

`nrs.asset.state` has five values: `active`, `in_repair`, `disposed`,
`transferred`, `missing`. The KPI strip shows four. `transferred` has no
tile, and the strip does not say the tiles do not sum to *On register*. It
measures 0 on every tenant today — 0 of 12,422, 0 of 11,951, 0 of 4,164 —
which is exactly when a missing tile is invisible and exactly when it gets
shipped.

Add the tile, same `countAssets({state: "transferred"})` idiom, same
null-renders-as-dash rule. Then prove the partition: a probe that sums the
five state counts and compares to `On register` on three tenants, printed
with the denominators. If it does not close — because a state exists that
the selection does not list, or a record has none — that is a finding and
the report says so; do not make the numbers agree by hand.

---

## 3 · The card that can never speak

*"PM Due (14 days)"* at line 255 is a static card whose small print says
*API endpoint pending* and has said it since the screen was built. The
model behind it is real — `nrs.asset.pm` carries `next_due_date` — and there
is **no `/api/v1` route over it** (I grepped the controllers; confirm, since
my greps have a record this month).

Two honest outcomes, and you choose by what you measure:

- **If `nrs.asset.pm` holds rows on any client tenant** — count them on all
  nine — then the card is owed a route: `GET /api/v1/maintenance/due`
  taking a `days` window, `assets:read`, Lagos-dated like the warranty
  window, paginated like everything else, in the census, in the index (the
  52 guard will insist). The card reads it, opens the filtered list, and
  prints its window dates the way the warranty tile does.
- **If the model is empty on every tenant**, the card comes off the screen,
  and a sentence in `docs/retired-screens.md` records that PM Due was
  removed on the measurement, with the counts, so it comes back when a
  tenant has something for it to say.

A permanently empty card with honest small print is still a promise on the
first screen. Either keep it by making it true or stop making it.

---

## 4 · The third refusal

A scanned serial against a record with **no serial on file** still records
nothing. You named it correctly as a *cannot check*, not a mismatch — and
that is exactly why an auditor wants it: a check that could not be
performed, on a tagging operation that claims verification, is a gap in the
evidence that nobody can see today.

Same recorder, `reason: no_serial_on_record`, a history sentence that says
the check was not possible rather than that it failed — *the asset has no
serial on record, so the serial read off it (X) could not be checked.* The
label is not affixed on this path today; confirm that is still so, and that
the response the operative sees is unchanged. Separate read after the 4xx,
as always.

---

## 5 · The census that fails alone

Run in isolation, the census class reports 0 inherited-route overrides and
fails its own override check, because `original_routing` exists only after
an `HttpCase` has built the routing map. In the module suite and in CI it
is always green; alone, it is red for a reason that has nothing to do with
the routes.

A test that is red for a reason unrelated to what it measures teaches
people to ignore it. Either the census builds the routing map it needs, or
the override half skips loudly, naming the reason, when `original_routing`
is absent — and passes the rest. Not a silent pass; §3a of handoff 51 is the
rule.

---

## 6 · Verification

1. Full suite, in-registry with denominators, the census (run alone once,
   to show §5), the browser suite, with times.
2. §1 on two tenants, screenshots before and after, the four dots
   accounted for one by one.
3. §2's partition probe on three tenants, printed.
4. §3's nine-tenant count, then whichever branch it chose, proved — a
   route driven and in the index, or a card gone and a sentence written.
5. §4 over HTTP with its separate read.
6. If a route was added: fan-out is not needed for a route, but the index
   guard and the census must both show the new denominator.

And the standing sentence check. In 52 it held *zero of how many* on every
zero in the report; keep that.

---

## 7 · After this

I believe this is the last Cadra handoff with work in it. What remains after
53 is **the clearance screen**, which has been owed to NRS since handoff 47
removed the mock and cannot be built until NRS says what clearance means;
and the owner items that have not moved: the nine-tenant credential read
(the command is in report 51 §F), and the three unclassified tenants, of
which `nrs19` holds 11,951 assets and 11,386 employees.

So the question for the report is the same as 51's, asked once more and
for the last time: **what do you believe is still wrong with Cadra that I
have not asked you about?** Ordered by what it would cost on a government
system, with the measurement. If the honest answer is a short list of
small things, say that. If it is nothing, say that — I will believe it from
you, since every time I have asked you have brought me something I had not
seen.

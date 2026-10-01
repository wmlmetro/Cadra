# Report 39 — The tagger confirms

**Branch:** `fix/the-tagger-confirms` · **Tenant driven:** `test19` ·
**Date:** 2026-10-01

Handoff 37 was not started, as instructed.

---

## In plain words, first

The tagging unit's job, as NRS described it on 30 September, is to walk up
to an asset with a scanner and a label, scan the label, and have the system
confirm it is the right one before it goes on. Cadra has enforced that
check since June — the API refuses a label whose number is not the one it
issued for that asset — but no screen let a person do it. The only way it
had ever been done was by somebody typing a request into Postman.

This handoff built that screen and nothing else. On the barcode station,
once an asset is looked up, its card carries a green **Confirm affixed**
button beside *Print label* and *Replace tag*. It opens a small dialog with
an empty box the tagger scans the physical label into, a box for who fitted
it, and — when the record has a serial number to check against — a box for
the serial. Press Enter or Confirm.

- **If the number scanned is not the one Cadra issued for this asset, the
  dialog refuses it in the server's own words** and keeps what was typed so
  the person can look again. Nothing is recorded.
- **If it is the right label, the record is written** — the label's state,
  the instant, the signed-in user and the name typed — and the card changes
  from a button to a line saying when it was confirmed and by whom.
- **If somebody already confirmed it** (another tagger, another tab), the
  dialog says *already confirmed on <date> by <name>, nothing was changed*.
  That is not an error and it is not "done": the original record stands.
- **If the label was replaced since the card was loaded**, the old number
  in hand is refused: first as *no active tag to confirm* while the
  replacement is waiting on an approver, then as a mismatch naming the new
  number once it is approved.

The single rule that governed the design is that **the screen never hands
the person the number it is checking against.** If it did, the person would
type what the screen told them, the check would always pass, and the record
would say a human verified something no human verified. The first
screenshots caught exactly that leak from an unexpected direction: the
dialog itself was clean, but the station's scan box — which *is* the number
when the lookup was by tag — was still readable behind the dimmed overlay.
The scan box is now emptied, the card's number line replaced and the whole
page blurred while the dialog is open.

**One thing I could not make true, and need you to rule on.** The handoff
asks for two things that pull against each other: show the wrong-tag
refusal *verbatim*, and show the expected number *nowhere*. The server's
sentence is *"Scanned tag X does not match the tag issued for this asset
(Y)"* — it names Y. So a person who scans the wrong label is told, in red,
what the right number is, and could type it. I kept the sentence as written
because the handoff says not to paraphrase it and the refusal text is on
the do-not-touch list; the fresh verification pass caught that my first
draft of the documents claimed more than that. Three ways out, all yours:
change the server's sentence (published API text), let the dialog redact
the bracketed number (a paraphrase), or accept it on the grounds that a
person who types a number they did not scan is lying, not misled.

Nothing on the server changed. No Python, no XML, no module version, no
schema. What changed is one React component, one page, two small additions
to the data layer, one Playwright spec and the documents.

**What this means for tomorrow:** the demo can show the handheld step
end-to-end on a screen — scan a label, see it refused when it is the wrong
one, see it recorded when it is right — rather than describe it. The honest
caveat, unchanged from yesterday: this is the station page in a browser, not
a native app on a handheld device; a scanner that emulates a keyboard works
with it as it does with the scan box.

---

## A · What was built

### The data layer — `src/lib/dataProvider.ts`

- `AssetTagging` — the `tagging` block `_serialize_tagging` emits on every
  asset payload (`label_id`, `tag_number`, `label_state`, `is_tagged`, the
  two printed and three affixed fields). `fetchAssetTagging(assetId)` reads
  it from `GET /api/v1/assets/<id>`.
- `confirmTagAffixed(assetId, body)` — `POST /api/v1/assets/<id>/tag-affixed`
  with an idempotency key. Sends only the three keys the route reads, and
  omits a blank `serial_number` / `affixed_by_name` rather than sending `""`
  (handoff 31: a key a route does not accept is a 400 and nothing is
  written).

**Why a second read rather than a new key on the lookup payload.** The
lookup payload (`/barcode/lookup`, station controller) publishes the TAG's
`state` — active / pending / scrapped — and not the LABEL's `label_state` —
issued → printed → affixed. The handoff shows the control only for an active
tag whose label is neither `affixed` nor `scrapped`, and after the fact
wants who and when. The `tagging` block already has all of it with a
`label_id` to compare against the scan box's `tag_id`. Adding keys to the
lookup route would be additive and safe; the day before a demonstration, one
extra GET on the card costs less than a change to a published payload, its
OpenAPI schema, and the guard that parses the controllers. Reversible, and
said in `docs/DECISIONS.md`.

### The dialog — `src/components/ConfirmAffixedDialog.tsx` (new)

Modelled on `TagReplacementDialogs.tsx`: the same `Dialog`, the same error
panel through `ApiErrorMessage` (so the server's sentence appears as
written, with its code in front, exactly as every refusal in the app does),
the same rule that a user cannot close it mid-flight.

- **Tag number** — empty, `autoComplete="off"`, monospace, autofocused. The
  fields sit in a `<form>` whose submit button is the footer's *Confirm
  affixed* (`form=` attribute), so a handheld scanner's trailing Enter
  submits. Disabled until something is in the box.
- **Fitted by** — optional. The tagger is often not the signed-in user.
- **Serial number on the asset** — optional, and **offered only when the
  record has a serial** (`hit.serial_number` from the lookup). The route
  refuses a scanned serial when the record has none to check against; a
  field the server will always refuse is a trap, so for such a record the
  dialog explains instead (`data-testid="affix-no-serial"`). This is the
  handoff's "your call": the route's second refusal is taken, because the
  tag check proves the label is the one Cadra issued and the serial check
  proves it went onto the right box, and NRS's tagger has both in front of
  them.
- **The expected number is nowhere in the component.** Not in the title
  (the replacement dialog titles itself with the number; this one does not),
  not as a placeholder, not as a default, not in the description.

**Three outcomes, told apart:**

| Outcome | What the server does | What the dialog shows |
|---|---|---|
| refused | 400 `validation_failed` (wrong tag; wrong serial; no serial on file), 400 `invalid_request` (no active tag), 403 | the server's sentence in the red panel; inputs kept; Confirm stays |
| recorded | writes `label_state`, `affixed_date`, `affixed_by`, `affixed_by_name` | closes; the page notice names the label and the fitter; the card shows the record |
| already | 200, writes nothing, chatter note | amber panel: *Already confirmed on <date> by <name>. Nothing was changed…*; one *Close* button |

**How "already" is detected.** The server answers a repeat exactly as it
answers a first — same 200, same block, the original `affixed_at`. Comparing
the response's `affixed_at` with the browser's clock misreads a fresh
confirmation as a repeat on any client whose clock runs ahead of the server.
So the mutation reads the `tagging` block, POSTs, and calls it a repeat only
when the block was `affixed` before the POST, for the same `label_id`, with
the same `affixed_at` the response carries. The POST is still sent, so the
server's own chatter record of the repeat (`_mark_affixed`) is kept. Two
edges, named: a label affixed with a null `affixed_at` (legacy data;
`_mark_affixed` always stamps) would read as fresh; a confirmation by
somebody else in the sub-second window between the read and the POST would
be reported as this person's with the other's name on it — true data, wrong
verb. The pre-read means confirming needs `assets:read` as well as
`tagging:write`; the station's lookup already needs it.

### The station — `src/pages/BarcodeStation.tsx`

- A `tagging` query for the card's asset, enabled only for an active tag,
  trusted only when its `label_id` equals the scan box's `tag_id`.
- `LabelStatePanel` on the card: *Label issued* / *Label printed <date>* with
  "not yet confirmed on the asset", or — once affixed — a green *Label
  confirmed on the asset* with the instant and *fitted by <name>*
  (`affixed_by_name`, else the user's name).
- *Confirm affixed* in the action row, shown when `canConfirmAffixed`:
  active tag, block matched, `label_state` neither `affixed` nor `scrapped`.
  When the block describes a different label from the scanned one (an asset
  carrying more than one non-scrapped label — the lookup returns the
  matched active tag, the block the one physically on the asset) the card
  says so in a sentence rather than rendering nothing; the verification
  pass found the silent case.
- **Covering the number while the dialog is open** (`affixOpen`): the card's
  number line is replaced by *Tag number hidden while you confirm*, the scan
  box renders empty with a placeholder saying so (the query itself is kept
  and reappears on close), and the station's root gets `blur-md
  select-none` and `data-blurred="true"`. A blur, not a removal: the
  recent-tags table, any earlier notice and the *Print new label* button
  stay in the DOM, illegible and unselectable. The dialog is portaled, so it
  is not blurred.
- On success: `invalidateTagQueries` (tiles, recent tags, pending list, any
  fetched tag, the asset's history) plus the `tagging` query; the card
  re-renders from the server. The lookup is NOT re-run: the lookup answer
  does not change (the tag stays `active`), only the block does.

**"The station's counters follow" — measured.** None of the five tiles
counts a label's `label_state` (`total_assets`, `active_tags`,
`pending_replacement`, `scrapped_tags`, `untagged`), and a confirmation
changes none of them: on `test19` the tiles read 6,583 / 6,559 / 24 / 16 /
24 before the confirmation and the same after (screenshots 01 and 04). What
DID move the tiles between the three runs was every other write — each
run's scrapped label (*Scrapped* 10 → 11 → 16) and the HTTP suite that ran
between the second and third (*Total assets* 6,348 → 6,583) — because the
tiles count assets and the tag's `state`, never the label's. The queries are invalidated
anyway so a later change to what a tile counts is not outlived by a stale
screen.

### `src/lib/utils.ts`

`formatIsoDateTime`: the API's `*_at` values are `isoformat()` of naive UTC
datetimes; parsed bare, a browser reads them as local and prints the wrong
hour. A `Z` is appended when no zone is present. The row says `17:09:02`,
the card says `18:09` — Lagos.

---

## B · The scrapped-tag refusal, named

The handoff lists *a scrapped tag* among the refusals the screen must
render. The model's sentence for it — *Tag X has been scrapped and cannot
be confirmed as affixed* — **cannot be reached through the route**: the
route resolves `rec.active_tag_id` before it calls `_mark_affixed`, and a
scrapped tag is never `active` (`action_approve_replacement` writes both
`state` and `label_state` to `scrapped`; the unique-active constraint and
`_compute_active_tag` only ever pick `state == 'active'`). What the route
says instead depends on where the replacement is:

| The label in the tagger's hand | The asset's active tag | Refusal |
|---|---|---|
| pending replacement | none | 400 `invalid_request` *This asset has no active tag to confirm* |
| scrapped, successor issued | the new label | 400 `validation_failed` *Scanned tag OLD does not match the tag issued for this asset (NEW). The label on the asset is not the one Cadra issued for it.* |
| scrapped, no successor (never happens through this flow) | none | *no active tag to confirm* |

Both reachable sentences are correct for the situation — the first says what
is waiting, the second names the label that should be in the hand — and the
third test in spec 39 proves both in one browser session with the card left
open across the replacement. The route and the refusal text are on the
handoff's do-not-touch list, so this is named, not changed. The button is
also never *offered* for a scrapped label: `canConfirmAffixed` excludes it,
and a scrapped label never arrives on the card as the active tag.

## C · The permission refusal, not proved in a browser

A 403 lands in the same panel as every other refusal, in the server's
sentence (`Missing required scope(s): tagging:write`). It is not driven in
Playwright because neither identity the suite can sign in as lacks the
scope: `admin` holds `admin`, which satisfies `tagging:write`
(`myservice_api/controllers/utils.py`), and the `test19` service credential
holds `tagging:write` outright (`/auth/whoami` lists it). There is no
user-creation endpoint to make an identity that lacks it.
`myservice_api/tests/test_auditor_access.py` proves the HTTP 403 on this
route (the Auditor, `tagging:write` named); `tests/test_tagging.py` proves
only that the OpenAPI document publishes the scope.

---

## D · Do not touch — confirmation

```
git diff --stat (code only)
 Frontend/.../src/lib/dataProvider.ts            |  65 +
 Frontend/.../src/lib/utils.ts                   |  18 +
 Frontend/.../src/pages/BarcodeStation.tsx       | 160 +-
 Frontend/.../src/components/ConfirmAffixedDialog.tsx   (new)
 e2e/tests/39-the-tagger-confirms.spec.ts               (new)
```

No file under `myservice_*`, `crnd-19/`, `oca-19/` or `tests/` changed.
`_mark_affixed`, the route, every refusal sentence, the replacement flow,
the serial lookup, the capture gate, serial generation, the Vendra hand-off,
depreciation and the identity webhook are untouched. `label_state` is read,
never written, by this change.

---

## E · Verification — in a browser, then the suites

**Built first** (`BASE_PATH=/app/ npm run build`, twice: once after the
front end landed, once after the scan-box leak was covered, once after the
reviewer's fixes; spec 39 passed 3 of 3 after each), the bundle
served by the local proxy from `dist/public` (checked: the hash in
`http://test19.localhost:8069/app/` matched `dist/public/index.html`).

**Spec 39 on `test19`** with the service credential (`E2E_CLIENT_ID` /
`_SECRET` from `docs/api/.creds.test19`): 3 passed, 0 skipped, on all
three runs (20.1s alone; 13.8s inside the regression set) — the third
test, which needs the second identity, RAN — and the six screenshots the
final run took are committed in `docs/handoffs/39-evidence/`:

1. `01-card-offers-confirm.png` — the card after a tag scan: *Label issued
   · Not yet confirmed on the asset*, and *Confirm affixed* beside *Print
   label* and *Replace tag*.
2. `02-dialog-open-no-number.png` — **the open dialog**: three empty fields,
   Confirm disabled, and the page behind it blurred with the scan box
   emptied. The spec also asserts the dialog's full `outerHTML` does not
   contain the number, every input's value is `""`, the scan box's value is
   `""` and the root carries `data-covered="true"`.
3. `03-wrong-tag-refused.png` — **the screenshot the handoff asked for
   most**: `NRS-ACS-733-9` typed, the panel reads *validation_failed:
   Scanned tag NRS-ACS-733-9 does not match the tag issued for this asset
   (NRS-ACS-733). The label on the asset is not the one Cadra issued for
   it.*, the input still holds the wrong number, and the page behind the
   dialog is a blur with the scan box empty. The row read back:
   `label_state` not `affixed`, `affixed_at` null, `is_tagged` false.
4. `04-card-shows-affixed.png` — after the right label, the serial and *E2E
   Tagger*: the notice at the top, and the card's green *Label confirmed on
   the asset · 1 Oct 2026, 18:30 · fitted by E2E Tagger*; the button gone;
   the scan box's query back.
5. `05-already-confirmed.png` — the second tab's dialog after the first tab
   confirmed: *Already confirmed on 1 Oct 2026, 18:30 by FIRST Tagger.
   Nothing was changed: the original record of who fitted this label and
   when stands.* — amber, one *Close* button, no red panel. The row read
   back between the two: `affixed_at` and `affixed_by_name` identical.
6. `06-scrapped-label-refused.png` — the card opened before the replacement,
   the old number confirmed after `admin` approved it: *Scanned tag
   NRS-ACS-735 does not match the tag issued for this asset (NRS-ACS-736)…*.
   Before the approval, while pending, the same dialog had shown *This asset
   has no active tag to confirm*.

**The rows, from Postgres on `test19`** — the third run, the one the
committed screenshots come from (the first, before the scan-box leak was
covered, wrote the same shape on `NRS-ACS-716`–`719` at 17:09; the second,
before the reviewer's fixes, on `720`–`723` at 17:10):

```
 asset_id | tag_id | tag         | state    | label_state | affixed_date        | affixed_by | affixed_by_name
    65722 |  29249 | NRS-ACS-733 | active   | affixed     | 2026-10-01 17:30:41 |          2 | E2E Tagger
    65723 |  29250 | NRS-ACS-734 | active   | affixed     | 2026-10-01 17:30:45 |          2 | FIRST Tagger
    65724 |  29251 | NRS-ACS-735 | scrapped | scrapped    |                     |            |
    65724 |  29252 | NRS-ACS-736 | active   | issued      |                     |            |
```

`affixed_by` 2 is `admin`, the browser's user. `SECOND Tagger`, typed in the
second tab, is on no row. The row says `17:30:41` UTC; the card says
`18:30` — the browser's zone, Lagos.

**Suites, with denominators:**

```
HTTP (tests/, test19):                 1127 passed, 10 skipped in 1016.65s (0:16:56); 0 lines matching `of 0 tests` or `CRITICAL`
Playwright (01, 10, 38, 39 on test19): 41 passed (1.5m) — the 38 of report 38 plus spec 39's 3; 0 skipped in 39
tsc --noEmit:                     exit 0
```

In-registry Odoo suites **not run, on purpose**: `git diff --stat` shows no
Python, XML or manifest change, and a registry load on this host is the
contended resource (`docs/ENVIRONMENT-FACTS.md`). The HTTP suite ran first,
alone, and Playwright after it, per CI's order.

**The standing pass — every sentence against something measured.**
Checked and corrected while writing: *"the dialog never shows the
number"* was true of the dialog and false of the screen (screenshot 02's
first version showed `NRS-ACS-716` in the scan box) — fixed in code and said
in `docs/DECISIONS.md`; *"the counters follow"* was measured to change
nothing visible and is reported as invalidation, not as a visible change;
*"a scrapped tag is refused"* was traced through the route and reported as
the two sentences that are actually reachable (§B). The 0 `printed` labels
on `test19` (of 6,354) is why every screenshot says *Label issued*; the
`printed` branch of `LabelStatePanel` is rendered by no screenshot and is
covered by the type system only.

**Residue on `test19`:** the spec creates three assets per run (`E2E-<run>
Affix`, `AffixTwice`, `AffixScrapped`), two of them now affixed, one with a
scrapped label and a pending-then-approved replacement; on a test tenant,
named through their asset names, left as the suite's other specs leave
theirs.

---

## F · The fresh verification pass

A reviewer that had not written the code read the diff against the
handoff's §1–§3 and the rules in `CLAUDE.md`, with the route, the model
method and the serializer open. Ten findings; what was done with each:

1. **The expected number IS shown after a wrong scan, and four of my
   sentences said it never is.** The server's refusal names the issued
   number; the handoff requires it verbatim; my first drafts of
   `DECISIONS.md`, `CLAUDE.md`, the demo-contract note and the spec's header
   claimed "nowhere". **Fixed in the documents** — they now say the screen
   never *hands over* the number and name the one place it appears — and
   **the tension is raised for the Architect** (plain-words section above;
   `DECISIONS.md` carries the three options). The code is unchanged there,
   by instruction.
2. **The 403 is proved in `myservice_api/tests/test_auditor_access.py`, not
   `tests/test_tagging.py`**, which only asserts the OpenAPI scope. Fixed
   (§C, `DECISIONS.md`).
3. **"The service credential holds `tagging:write` outright" was
   unverifiable from the repo.** Now cited to its source: `GET
   /auth/whoami` for that credential, read this session, lists it among 14
   scopes. Fixed.
4. **Four stray brand files in the working tree** (`Frontend/Cadra
   Dark.png` …) — pre-existing, not this handoff's; the commits below add
   files by name and leave them.
5. **A false comment, and "covered" overstating a blur.** `onAffixAlready`
   set a notice naming the number while the dialog was still open (over the
   blur, illegible, after the check was over — but the comment said
   "never"). Fixed: that notice no longer names the number, the comment
   says what happens, the attribute is `data-blurred`, and the documents
   say "blurred" and that the text stays in the DOM.
6. **A silent case.** When the `tagging` block describes a different label
   from the scanned one (an asset with more than one non-scrapped label)
   the card rendered nothing and offered nothing. Fixed: a sentence saying
   so (`tag-label-state-mismatch`).
7. **The repeat check did not compare `label_id`.** In that same two-label
   case a fresh confirmation of the newer label could read as *already
   confirmed* of the older. Fixed: `label_id` is compared as well. The two
   remaining edges are named in §A.
8. **Confirming needs `assets:read` too** (the pre-read). Named in §A and
   `DECISIONS.md`; the station's lookup already needs it.
9. **The demo-contract note overreached** ("the refusals below render in
   the dialog"): the no-serial-on-file refusal cannot be produced from the
   dialog, because the field is withheld, and the 403s need tokens the app
   cannot hold. Reworded to the two mismatches.
10. **The third spec test is gated on the service credential.** It ran:
    3 passed, 0 skipped, both runs; said so in §E.

Confirmed by the reviewer, with file and line: nothing carries the number
into the dialog at open and nothing behind it is legible or selectable;
the refusal is `str(e)` → `err.message` → `{code}: {message}` with no
rewrite; the invalidations; `canConfirmAffixed`'s condition and why
`label_id === tag_id` is the right comparison; no Python in the diff; only
accepted keys sent, blanks omitted; `tsc` exit 0; and the eight factual
sentences it checked in the documents. After the fixes, `tsc` exit 0 again,
the bundle rebuilt, and spec 39 re-run (below).

---

## Deviations from the handoff

1. **"A scrapped tag" (§1)** — rendered as the two refusals the route can
   actually produce, not the model's sentence, which the route cannot reach
   (§B). Not a change to anything on the do-not-touch list.
2. **"Deploy to staging" (§3)** — staging deploys from a push to `dev`
   (`.github/workflows/deploy-dev.yml`: `on: push: branches: ["dev"]`,
   `paths-ignore: **.md`, so a merge carrying code triggers it), which
   happens when the owner merges the PR; the Builder cannot merge. Verified on the local stack, which
   serves the same bundle the same way. A frontend-only change needs no
   backend roll: the route it calls has been on staging since handoff 03.
3. **Screenshots committed** under `docs/handoffs/39-evidence/` (six PNGs,
   ~900 KB) rather than left in the scratchpad as report 38's were, because
   the handoff asked for them by name and the Architect sees only the repo.

## Open questions

- Whether the asset detail page should show the affixed state as well
  (the station is the only screen that does; the history timeline already
  lists the `tag_affixed` event). Out of this handoff's one-control scope.
- Whether a 403 should hide the button rather than refuse on submit. Today
  the scope is not readable from the lookup; the refusal is correct and in
  words.

## Needs the owner

- Merge the PR (`fix/the-tagger-confirms` → `dev`); the push to `dev` rolls
  the frontend to staging.

## Commits

<!--COMMITS-->

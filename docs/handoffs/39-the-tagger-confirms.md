# Handoff 39 — The tagger confirms

**Branch:** `fix/the-tagger-confirms`
**Report:** `docs/handoffs/39-REPORT.md`

> ## RUN THIS ONE. NOT 37.
>
> `37-the-doors-and-the-red-tests.md` is still waiting and still must not be started. The demo is tomorrow.

---

## 0 · What is missing, and how small it is

NRS described the tagging unit's job in more detail than anything else in the 30 September meeting: a person with a scanner and a mobile printer walks up to the asset, scans it, checks the label they are about to fix is the right one, and fixes it.

**Cadra enforces that control properly and there is no way for a person to invoke it.** `POST /api/v1/assets/<id>/tag-affixed` exists, is tested, and carries the refusal that is the whole point:

> *Scanned tag %(scanned)s does not match the tag issued for this asset (%(expected)s). The label on the asset is not the one Cadra issued for it.*

The word *affix* appears nowhere in the React app except an icon used to **display** an event that already happened. The legacy Odoo station has nothing either. So the only way this has ever been done is Postman.

**This handoff builds the screen and nothing else.** The model is correct, the route is correct, the refusals are correct. Do not change any of them.

Two things I checked before writing this, so you do not have to:

- **There is no print precondition.** `_mark_affixed` refuses only a scrapped label or a mismatched number; `issued → affixed` is a legal move. Every tag on staging is affixable today.
- **`admin` scope satisfies `tagging:write`** (`myservice_api/controllers/utils.py:703`), so the signed-in demo user can do this.

---

## 1 · What to build

A **Confirm affixed** control in the barcode station, beside *Print label* and *Replace tag*, on the asset card.

**Show it when** the asset has an active tag whose `label_state` is neither `affixed` nor `scrapped`. When the label is already affixed, show the state instead — who fitted it and when — not a button.

**The dialog:**

- **A field for the tag number, empty.** The person scans the physical label into it.
- A field for who fitted it (`affixed_by_name`), optional — the tagger is often not the logged-in user.
- Optionally the serial field, if you take the route's second refusal; your call, and say which way you went.
- Confirm and cancel.

### The one instruction that matters more than the rest

**Do not pre-fill the tag number, and do not offer it as a dropdown, a copy button or a suggestion anywhere in that dialog.**

The entire value of this control is that the number comes off the physical label in the person's hand. If the screen hands it to them, the check compares Cadra's number against Cadra's number, always passes, and produces a record that says a human verified something no human verified. That is a worse outcome than having no screen at all, because it manufactures evidence. If the design makes the number easy to copy from the card behind the dialog, move it or cover it.

### The refusals must read as sentences

This control exists to refuse things. Each of these renders in words, in the dialog, with the input kept so the person can try again:

- **The wrong tag** — the message above, verbatim from the server. Do not paraphrase it and do not replace it with "invalid tag".
- **A scrapped tag.**
- **Already affixed.** Note this one is *not* an error: the server logs the repeat, keeps the original record and returns normally. So the screen must say *"already confirmed on <date>"* — never "done" (it did nothing) and never an error (nothing went wrong).
- A permission refusal, if the signed-in user lacks the scope.

**On success**, the card refreshes to show the affixed state, and the station's counters follow.

---

## 2 · Do not touch

- `_mark_affixed`, the route, or any refusal text.
- The replacement flow built yesterday.
- Serial lookup.
- Anything in handoff 38's or 37's do-not-touch lists: the capture gate, serial generation, the Vendra hand-off, depreciation, the identity webhook.
- Anything that would change what `label_state` means or what sets it.

If this grows past one control, one dialog and the state it displays, **stop and report.**

---

## 3 · Verification — in a browser, then deployed

Same rule as 38, and the same reason: a change to the React app that is not built and deployed does not exist. Build, deploy to staging, then drive it yourself.

- Confirm a tag affixed, correctly, and read the row back: `label_state`, `affixed_date`, `affixed_by`, `affixed_by_name`.
- **Scan the wrong number and show the refusal on screen**, with the sentence intact. This is the screenshot I want most.
- Confirm the same tag twice and show it says *already confirmed*, with the original date unchanged.
- A scrapped tag refused.
- Show the dialog **does not** contain the expected number anywhere — a screenshot of the open dialog is the evidence.
- Suites with denominators.
- The standing pass: every sentence against something measured.

**If it is not finished and verified, leave it out and say so.** A half-built control on the demo screen is worse than the honest answer we already have, which is that the integration is proved and the handheld screen is not built yet.

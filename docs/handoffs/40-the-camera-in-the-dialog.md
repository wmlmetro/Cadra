# Handoff 40 — The camera in the dialog

**Branch:** `fix/the-camera-in-the-dialog`
**Report:** `docs/handoffs/40-REPORT.md`

> **RUN THIS ONE. NOT 37.** The demo is tomorrow. 37 is still waiting and still must not be started.

---

## 0 · Why

Report 39's dialog is built for a handheld scanner — the tag field is auto-focused and the form submits on the scanner's trailing Enter. That is the right primary design and it stays exactly as it is.

But the station's lookup box offers **Type / Camera**, and the dialog offers only typing. So on a phone or tablet — which is what a tagger at a state office will actually be holding, and NRS raised distributed tagging unprompted — you can scan to *find* the asset and then have to type the number to *confirm* it. That reads as half-built, and it is the one step where typing is worst, because the whole point is reading the label in your hand.

**Add the camera as a second option on the tag number field.** Nothing else.

---

## 1 · What to build

**Reuse `components/BarcodeScanner.tsx` as it is.** Do not write a second scanner, and do not change that component unless it genuinely cannot be mounted twice — if that turns out to be true, say so and stop rather than refactoring it tonight.

In `ConfirmAffixedDialog.tsx`, a **Type / Camera** toggle on the tag number field, matching the station's own toggle so it reads as the same control in a smaller place. Default **Type**, as the station does. Do not auto-select the camera on small screens or anywhere else; being clever the night before a demo is how demos break.

### Four things to get right

1. **A camera detection fills the field. It does not submit.**
   The handheld scanner submits on Enter because a trigger pull is a deliberate act. A camera is looking at the room continuously and will read whatever passes the lens — a neighbouring label, a box, another asset's tag. Filling the field lets the person see what was read before they commit, and a misread then costs a glance rather than a false record. Put that reasoning in a comment; it will look like an inconsistency to the next reader.

2. **The typed path must come back exactly as it is.** With the camera off: auto-focus on the tag field, Enter submits, scanner-wedge flow unchanged. Turning the camera on and off again must return focus to the field. Prove both in the browser.

3. **The no-leak rule is unchanged and still governs.** The camera reads the physical label, which is the whole point, so it does not weaken anything — but check that opening the camera does not change the blurring that hides the card's number behind the dialog, and that the preview does not reposition the dialog so the card peeks out.

4. **The optional serial field may have the same toggle** if it falls out cheaply. If it does not, leave it typed and say so. The tag field is what matters.

### Two practical notes

- The camera needs HTTPS and a permission prompt the first time. Staging is HTTPS. **Say in the report that the first use prompts**, so nobody meets that prompt for the first time in front of NRS.
- If the camera is open when the dialog closes or submits, stop it. A camera left running is both a battery problem and the kind of thing someone notices on a projector.

---

## 2 · Do not touch

The server, the route, any refusal sentence, `_mark_affixed`, the replacement flow, the serial lookup, the station's own scan box, and everything on handoffs 38 and 39's do-not-touch lists.

**If this grows past a toggle and a fill, stop and report.** The typed path works and is deployed; a broken dialog tomorrow is far worse than a dialog without a camera.

---

## 3 · Verification — in a browser, then deployed

- Camera on, scan a real label, show the field filled and **not** submitted.
- Then confirm, and read the row back.
- Camera on, scan the **wrong** label, fill, submit, and show the refusal — the server's sentence, the inputs kept.
- Camera off: auto-focus, Enter submits, the keyboard-wedge path intact.
- Toggle on and off and show focus returns.
- A screenshot of the open dialog with the camera running, showing the expected number is still nowhere on screen.
- Close the dialog with the camera open and show the camera stops.
- Suites with denominators, and the standing sentence pass.

**If any of it is not finished and verified, leave the camera out and say so.** We ship the typed dialog, which already works.

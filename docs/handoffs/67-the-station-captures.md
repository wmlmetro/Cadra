# Handoff 67 — The station captures

**Branch:** `feat/the-station-captures`
**Report:** `docs/handoffs/67-REPORT.md` (~150 lines)
**Runs after:** 66, merged (PR #127). Branch from `dev`, after pulling.
**Time budget:** 3 hours. Follow `CLAUDE.md`'s *Speed* and *Progress*
rules.

---

## 0 · Report 66 is accepted

An audit team can walk a room with Cadra. Every asset code lives in one
ledger. Closing a campaign produces the two lists the audit exists for.
And the two security finds outweigh the feature: a refused role grant
that quietly granted the role (open since handoff 42), and a replayed
idempotency key that slipped past `/ai/identify`'s scope check. Both are
closed. Thank you.

**The owner's position on the AI addendum, 20 October.** The purpose is
the three award lots:

- **Lot 1:** AI-assisted registration;
- **Lot 4:** walk rooms, capture untagged items and tag them on the spot;
- **Lot 6:** the same flow at the onsite Barcode Stations.

The register side now serves all three. This handoff closes the gap for
Lot 6 and removes four things the mobile team can't build today.

## 1 · Capture mode on the Barcode Station (Lot 6)

The capture flow lives under *Audit*. At a regional station it belongs on
the **Barcode Station** page, where staff already print and scan:

- **A *Capture* mode on the station,** beside print and scan, for anyone
  holding the audit capturer role. It is 66's web capture: the campaign,
  the room by scanned room code, photo, *Identify* (64), match, code from
  the station's own block, print, scan the printed label to confirm.
- **The station is a device.** The Asset Controller registers it like a
  phone and binds it to whoever is signed in at the station. Say how a
  shared station handles shift changes: rebinding needs no open block
  under the previous person, or block-per-person. Pick the simpler one and
  record it in DECISIONS.
- **Print through the station's existing print funnel** (handoff 10), so
  every print is recorded.
- **One screen, one flow.** No new rules. The capture goes through the same
  `POST /audit/captures` and the same review.

## 2 · Four gaps the mobile team listed (report 66 §10)

1. **Identify an audit photo by its id.** `/ai/identify` takes a photo
   already uploaded for a capture, so the phone doesn't upload twice.
2. **Void one spoiled code.** The capturer voids a code reserved to them
   (a label torn at print) with a reason. It is never reissued.
3. **Return their own block.** The capturer can return their open block
   (unused codes voided), not only the Asset Controller.
4. **GPS on a capture** (AI-FR-10), optional: latitude, longitude and
   accuracy, stored on the capture record only. **Never** sent to the AI
   provider (64 strips it) and never shown on a public page.

## 3 · Two small PRD alignments

- **An approximate size band** (AI-FR-03). Add an optional `size_band`
  (`small` / `medium` / `large`, defined in words for furniture) to the
  identify answer, labelled *approximate*. `dimensions` stays empty unless
  a label states them.
- **An acceptance dashboard** (AI-NFR-08). On *Settings → Identify from
  photo*: suggestions made, and the share accepted unchanged, by category,
  by site (campaign location) and by model, for the last 30 days, from
  `nrs.ai.suggestion`. Every count says what it counts.

## 4 · What must not change

- 66's capture, review and ledger rules.
- 64's photo handling, and the key living only in the environment.

## 5 · Verification

Targeted tests; one final local run; CI cited. Then:

1. Spec: a station capture end to end. Sign in at the station, scan the
   room code, photo, identify (fake adapter), match, print, scan the label,
   sync. The reviewer accepts in the Audit screen.
2. Each §2 route over HTTP, with its refusals.
3. The dashboard's numbers against a seeded set of suggestions.

## 6 · The question for the report

**What does a regional office need on the day, for Lot 6?** List it as a
checklist the owner can hand to a site:

- the station hardware (computer, camera, label printer and labels);
- network;
- people and roles;
- a registered device and an issued block;
- a campaign and its rooms with room-code labels printed.

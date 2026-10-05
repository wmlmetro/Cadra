/**
 * The acceptance rules of handoff 54 §2 and §4, as a pure function.
 *
 * Separated from `BarcodeScanner` so the rules are provable without a
 * camera: `e2e/tests/54-every-time.spec.ts` drives this directly with
 * synthetic frames, where driving the real decode loop into a transient
 * state ("Reading…", two frames disagreeing) through Chromium's fake
 * capture device would be a race, not a proof.
 *
 * The rules:
 *  - No hits: nothing changes. The pending 1D read survives a blank frame —
 *    a camera hunting focus drops frames, and resetting on every miss would
 *    make a legitimate read take seconds.
 *  - More than one DISTINCT value in the frame: never guess. The caller
 *    (who decodes the reticle crop first) has already applied the
 *    "prefer the reticle" rule; what reaches here as plural is genuinely
 *    ambiguous and becomes a choice for the operative.
 *  - One value, 2D: accepted on one decode — 2D codes correct their own
 *    errors.
 *  - One value, 1D: accepted only when it agrees with the previous 1D
 *    decode (same value, same symbology). 1D has no error correction worth
 *    the name; a partial read can yield a valid, wrong string. Until the
 *    agreeing read arrives the state is "reading", which the scanner shows,
 *    briefly, so a flicker of success is not mistaken for a failure.
 */

// Relative import, not the `@` alias, so the e2e suite (whose TypeScript
// knows nothing of Vite's aliases) can import this module and drive it.
import { isTwoDimensional, type ScanHit } from "./scanFormats";

export type ScanDecision =
  | { kind: "none" }
  | { kind: "reading" }
  | { kind: "accept"; hit: ScanHit }
  | { kind: "choose"; hits: ScanHit[] };

export interface ScanStep {
  decision: ScanDecision;
  /** The 1D read now waiting for its agreeing twin, to feed back in. */
  pending: ScanHit | null;
}

export function decideScan(hits: ScanHit[], pending: ScanHit | null): ScanStep {
  if (hits.length === 0) {
    return { decision: { kind: "none" }, pending };
  }
  if (hits.length > 1) {
    return { decision: { kind: "choose", hits }, pending: null };
  }
  const hit = hits[0];
  if (isTwoDimensional(hit.format)) {
    return { decision: { kind: "accept", hit }, pending: null };
  }
  if (pending && pending.value === hit.value && pending.format === hit.format) {
    return { decision: { kind: "accept", hit }, pending: null };
  }
  return { decision: { kind: "reading" }, pending: hit };
}

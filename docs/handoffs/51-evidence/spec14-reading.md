# Handoff 51 §3b — reading the spec-14 dumps (2026-10-05, test19)

`spec14-persisted-cache.jsonl` holds five runs' dumps. The first three runs
were instrumented WITHOUT the expected-value context, so their True/False
cannot be read as pre- or post-click; they are kept as raw data and no
conclusion is drawn from them. The last run records `before` and
`expected_after_click` on every line, and is the measurement:

- **Failing attempt** (`before: true`, clicked → expected `false`):
  the persisted `depreciation-settings` entry read `true` — the PRE-click
  payload — BETWEEN the click and the reload (the 1 s write throttle had
  not flushed the post-click write), and the SAME entry, identical
  `dataUpdatedAt`, after the reload (restored, not refetched). The screen
  rendered pre-click for the full 30 s window.
  **GO-LIVE §16.3 item 8's hypothesis holds, point for point**: the
  persister's throttle can preserve the pre-click payload, the reload
  restores it, and inside `staleTime` nothing refetches.
- **Passing retry** (`before: false` → expected `true`): the persisted
  entry was ABSENT (`entry: null`) at both instants, so the page had to
  fetch fresh and rendered the server's row — which is why the spec is
  intermittent rather than always red: whether it fails is whether the
  restored snapshot carries the pre-click row.

One run earlier in the day went the other way visually (a `true/true` pair
on a failing attempt) but carries no `before`, so it is not evidence either
way; the instrumentation that settles it is now permanent in the spec
(gated on E2E_EVIDENCE).

Not fixed, per the handoff: the fix is a `staleTime`/persister-throttle
decision across every screen that uses them, and it is the Architect's,
from this measurement.

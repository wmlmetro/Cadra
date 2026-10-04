# The two red depreciation browser specs — named, per handoff 50 §3

Run 2026-10-03 on `test19`, against the `fix/the-consequences` bundle (the
specs touch no screen this branch changed; both were red on `dev` before it —
GO-LIVE §13.5 item 13; recorded red since report 29). **This is the first
time either failure's actual error text has been recorded anywhere** — no
prior evidence file carried it.

## Verdict asked for by §3

**Neither is handoff 37's defect, in browser form or otherwise.** 37's defect
was `_apply_depreciation` measuring `as_of` in UTC while `_stamp_disposal`
stamps the Lagos day — red one hour a night, only on a just-disposed asset,
fixed in `myservice_asset_depreciation` with a frozen-clock test. These two
specs never dispose anything, fail at every hour of the day (recorded red
across reports 29, 40, 49, taken at different times), and predate the 37 pair.
Report 30 already ruled the second one "a different control". They are two
separate, known-shape defects — one in the SPEC, one most plausibly in the
app's cache policy:

## Spec 13 — `13-asset-depreciation.spec.ts:68` "a computed asset charts its value over time"

```
Error: expect(locator).toBeVisible() failed
Locator: getByText('Value over time')  — element(s) not found, 10000ms
```

What the page actually rendered (error-context snapshot):

> No schedule yet — this asset needs an acquisition cost and a useful life
> before its value can be tracked over time.

**Diagnosis: a fixture-selection defect in the spec, not a product defect.**
The spec takes the FIRST asset whose `financial.depreciation.method` is
computed (`straight_line`/`declining_balance`) without checking it has an
acquisition cost or a useful life. On `test19` that first asset has neither,
so the product renders its honest empty state — the exact sentence handoff 27
era work built — and the spec, which assumed data, fails. The other three
tests in the file (including "an ERP-managed asset shows no schedule, and
says why") pass. Fix shape, when somebody picks it up: the picker must select
an asset that HAS a schedule (or seed one), i.e. the same denominator rule —
"first computed asset" is not "first chartable asset".

## Spec 14 — `14-settings-depreciation.spec.ts:36` "the straight-line switch persists across a reload"

```
Error: expect(locator).toBeChecked() failed
Locator: getByTestId('toggle-db-switch') — Expected: checked, Received: unchecked
Timeout: 30000ms — 57 × locator resolved to unchecked
```

The flip itself PASSES (the pre-reload assertion succeeds); it is the
post-`page.reload()` state that stays unchecked for the full 30 s with no
refetch. **Consistent with — and only with — the hypothesis already recorded
at GO-LIVE §16.3 item 8**: the app persists the react-query cache to
localStorage and restores it on reload; inside `staleTime` (5 min) the
restored value renders as fresh and is never refetched, so the screen shows
the pre-click value regardless of the server's row. The persister also
throttles its localStorage writes, so a reload immediately after the PATCH
can restore the PRE-flip payload. Same family as handoff 29's
`refetchOnMount: false` finding (a screen lying to its own session from
cache), NOT a depreciation defect at all — the register-wide switch is
plumbing that happens to live on the depreciation settings page. Labelled a
hypothesis in GO-LIVE then; this run's shape (flip passes, reload shows the
old value, no refetch for 30 s) is the first observed behaviour that matches
it point for point. Still not PROVEN (nobody has read the localStorage
payload mid-test); saying so per the handoff's own rule.

## Status

Named, not fixed, per §3's instruction. Two red browser tests stay on `dev`;
the fix for 13 is a spec fixture change, the fix for 14 is a cache-policy
decision (the same decision family as the "v4"/"v5" cache-buster this branch
already had to use), both now have enough recorded to be picked up cold.

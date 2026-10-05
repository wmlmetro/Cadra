# The decode corpus — handoff 54 §6a

`run54.mjs` measures, offline, what the bundled decoder can read of every
label Cadra prints and of every symbology a manufacturer might print, and
writes the table the report quotes to
`docs/handoffs/54-evidence/corpus-table.md`.

**What "the same engine" means here:** the SPA bundles `zxing-wasm`'s reader
build behind `src/lib/scanEngine.ts`; this script decodes with the same
package, the same version (pinned by `e2e/package.json`) and the component's
`READER_OPTIONS` verbatim, in Node. A number in the table is a measurement of
the scanner the station ships, not of a cousin.

**What is NOT approximated:** Cadra's Code 128 and QR PNGs are fetched from
the running Odoo's own renderer (`/report/barcode`, the route
`asset_tag_report.xml` calls through `get_barcode_base64`) at the template's
per-size source resolutions, and displayed at the physical sizes the
template's cfg dict and the paperformat content boxes produce. The arithmetic
is printed at the top of the table.

## Run it

```
node e2e/corpus/run54.mjs
```

Needs the local stack up and `http://test19.localhost:8069` reachable
(`ODOO_ORIGIN` overrides). If `/report/barcode` is unreachable the run STOPS
(exit 2) rather than substituting a different barcode generator.

## The gates (exit 1)

1. **Invariant** — every Cadra label size has at least one side the engine
   reads as printed, straight on, undegraded. A label no machine can read in
   good conditions is a printing defect.
2. **Baseline** — every cell that passed when `expected-pass.json` was
   committed still passes. An engine upgrade or harness change that loses a
   cell fails loudly; new passes are printed so the baseline can be advanced
   deliberately (re-generate by deleting `expected-pass.json` and re-running,
   then diff before committing).

The handoff's own "M of M at 0° and 90°" bar is reported per row in the
table's must-pass column, but not gated on: the small and standard labels'
Code 128 side misses it for a reason that belongs to the label, not the
scanner — a 15-character tag at ≤ 28.6 mm is ≈ 0.13 mm per module, below
what any camera pipeline at these pixel densities resolves. The table's §9
section carries that finding.

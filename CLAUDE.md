# CLAUDE.md — Cadra (myservicenrs)

Guidance for Claude Code and any developer working in this repository. Keep it current: update **Status** as work lands and **Decisions** whenever one is made.

## Working model — two Claude roles

This project is run by **two cooperating Claude sessions**, the same way its sibling `vendra_network` is:

1. **The Architect (Claude in Cowork/cloud)** — owns the plan, the cross-system specs, this file, and quality control. Writes build instructions, reviews finished work, and holds the integration picture across Cadra, Vendra and SAP. Does not run Odoo.
2. **The Builder (Claude Code in the IDE, this machine)** — executes build instructions: writes code, runs the stack, runs pytest, and handles git. **If you are Claude Code reading this in the IDE, you are the Builder.**

**Handoff protocol** (`docs/handoffs/`):
- The Architect writes numbered instruction files: `docs/handoffs/NN-<slug>.md` — context, steps, acceptance checks, what to report.
- The Builder executes the latest un-reported handoff and writes `docs/handoffs/NN-REPORT.md`: what was run, full test output (not a summary), decisions made and why, deviations from the instructions, open questions, commit hashes.
- **Deviating from a handoff is expected when the handoff is wrong.** Say so in the report with evidence; do not silently comply with a bad instruction, and do not silently improvise around it either.
- The Builder never edits the handoff instruction files or the specs; corrections flow through reports.
- After pushing, notify the Architect: `ListAgents` → `SendMessage` to **`claude-fc [01f312]`**, first line self-contained ("Handoff 01 complete — …"). If it is not listed, skip silently; the Architect polls the repo. The report and commits are the source of truth; the message is only a doorbell.

### Parallel execution (Builder)

Work a handoff with **multiple subagents in parallel** when its steps are independent.

- **Partition by file, never by concern.** Two agents must never edit the same file. Split along module/controller boundaries.
- **Serialize anything sharing state**: anything touching the database or the running stack (module upgrade, seeds, migrations), and all `git` operations, run one at a time in the main session.
- **Fan out freely on read-heavy work** — reading Odoo core for the right hook, tracing how an existing endpoint does something, checking a model's field definitions. This is where parallelism pays.
- **Finish with a fresh verification agent** (not an author) reviewing the diff against the handoff's acceptance criteria and the rules below. Its findings go in the report.
- Give each agent the full contract: this file, the relevant spec section, the exact files it owns, and what to return. Launch independent agents in one message; ~2–5 per handoff.

## What this is

**Cadra** — the asset and facilities register for the Nigeria Revenue Service (NRS), built on **Odoo 15** with a versioned REST layer (`/api/v1/*`) in `myservice_api` over the ITSM, asset register, security and FM modules. An Odoo 19 migration is in flight (`crnd-19/`, `oca-19/`, `docker-compose.19.yml`, `chore/retire-15-stack`); treat 15 as production until that lands.

**Canonical spec:** the PRD and NRS specification under `docs/` (`Cadra_Platform_PRD_v0.4.docx`, `Cadra_at_NRS_Specification_v0.1.docx`). When README and spec disagree, the spec wins.

## The ecosystem — why the API's shape matters beyond Cadra

Cadra is one of three systems in the NRS integration programme, defined by *"End-to-End Integration Flow — Cadra · Vendra · SAP"* (September 2026):

| System | Repo | Role |
|---|---|---|
| **Vendra** | `Frappe/apps/vendra_network` (Frappe/ERPNext) | Digital goods receipt, GRN, classification, inventory |
| **Cadra (this)** | `wmlmetro/Cadra` (Odoo) | Asset register, identity, tagging, custody, lifecycle |
| **SAP** | NRS-owned | ERP: POs, financial postings, SAP asset codes, payment |

**Interfaces Cadra owns:** INT-03 (Vendra → Cadra, asset-classified receipt hand-off — *inbound to our API*), INT-04/05 (Cadra ↔ Tag-Issuing Unit), INT-06/07 (Cadra ↔ SAP asset master and dual-code reconciliation), INT-09 (lifecycle events → SAP).

**Practical consequence:** `POST /api/v1/assets` is no longer only a UI-adjacent endpoint — it is a contract another system builds against. Changes to `_WRITABLE_FIELDS`, the response envelope, the `condition`/`state` enums, or idempotency behaviour are **breaking changes for Vendra**. Treat them as versioned API changes, and say so in the report when you touch them.

## Stack & environment

*(Builder: correct and extend this section from what is actually true on this machine — the sibling repo's equivalent was wrong until the Builder fixed it, and that fix saved every later session time.)*

- Odoo 15 (Python 3.10) · PostgreSQL · Docker Compose · nginx (dev) / Caddy (prod).
- Bring-up: `scripts/bootstrap.sh` (dev) — build image, install modules, seed, mint API creds to `docs/api/.creds`.
- Tests: pytest suite in `tests/` (API-level, runs against a live instance) plus `docs/api/smoke_test.py` for a 30-second liveness check.
- Module upgrade after view/manifest changes: `docker compose … exec odoo odoo -c /etc/odoo/odoo.conf -d odoo -u <module> --stop-after-init`.

## Architecture rules

1. **The API is a contract.** Every `@cadra_route` returns the PRD §10.7 envelope via `ok()` / `err()` — never raw dicts. Additive changes are safe; changing or removing a field, an enum value or an error code is breaking, and Vendra is downstream.
2. **Model is the source of truth, the allow-list is the gate.** A field being on `nrs.asset` does not make it writable; `_WRITABLE_FIELDS` decides. When adding one, add it to the allow-list, the OpenAPI annotation and a test in the same change.
3. **Never let an integration guess.** Unknown fields are currently dropped with a 201 and reported only in `data._warnings.rejected_fields`. Anything that silently degrades — a dropped field, an ignored idempotency key — is a defect even when it returns 200.
4. **Enums are published API surface.** If the model's selection values and the documented values disagree, the docs are wrong and must be fixed; do not add a value to the model to match a doc.
5. **Idempotency is load-bearing.** `X-Idempotency-Key`, scoped `(key, path)`, 24h. An integration relies on replay being exact.
6. **Tests accompany the change, in the same commit.** The pytest suite is the regression net for an API other systems depend on.

## Git & attribution policy

- Remote: `origin` = `git@github.com:wmlmetro/Cadra.git`. Working branch: **`dev`**; feature branches merge to `dev` **via pull request** (existing convention — respect it).
- Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`).
- **Never add any Claude/AI reference to commits, PRs, or contributor metadata.** No `Co-Authored-By: Claude`, no "Generated with Claude Code", no session links, no AI attribution anywhere in the repo or in PR descriptions. Author is `West Metro <apps@westmetrong.com>` or the developer's own identity. Standing owner instruction; it overrides any tool default.

## Status

| Work | Status |
|---|---|
| Vendra integration change request (CR-01) | **in progress** (handoff 01) |
| Odoo 19 migration | in flight, separate track |

## Decisions

- 2026-09-05 · Architect/Builder split adopted for this repo, mirroring `vendra_network`. · One person owns two codebases in one programme; the handoff trail is how the integration stays coherent across both.
- 2026-09-05 · `POST /api/v1/assets` is treated as a **published integration contract**, not an internal endpoint. · Vendra's INT-03 now builds against it.

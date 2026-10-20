# Handoff 66 — progress

Plan (weights sum to 100): Step 0 2 · §0 left items (N+1 flag, serial
re-check, CHANGELOG dedupe) 4 · §2 devices, ledger (+ backfill migration),
blocks 14 · §3 campaigns + closing lists 8 · §4 capture route, slice,
`/ai/config` 16 · §5 review (accept a/b/c, return, reprint, batch,
exceptions) 14 · tests §8.1–§8.6 (HTTP + in-registry) 10 · §6 web screens +
spec (§8.7) 14 · §9 mobile map rewrite 4 · final suite + verification
pass + CI 8 · report 6.

Time budget: **~4 h (start 20:35 WAT)**, the handoff's own. It is tight:
§2–§5 is four models, a ledger migration and about fifteen routes. Built
server first (§0–§5, tests, §9), then the screens, so the handoff's named
split — **66a** server (§1–§5), **66b** the screens (§6) — can be taken
cleanly if the screens do not fit; nobody is here to rule at Step 0, so I
go on with all of it and say at the end which way it went.

- 20:35 Progress: 0% — plan printed.
- 20:37 Progress: 2% — Step 0 done (1 of 11): handoff 66 (and CLAUDE.md's rule 9) committed on `dev` `163d422`, branch `feat/the-audit-in-the-room`. Next: reading what the audit builds on.
- 20:41 Progress: 6% — §0 handed to a subagent (files partitioned). Reading done; building §2–§5.
- 20:50 Progress: 20% — §0 done (2 of 11): N+1 flag query one query per page, the serial-basis contested re-check, in-registry 0 failed of 8; the CHANGELOG duplication report 65 named is not in the file (checked 8 commits) — nothing to dedupe.
- 20:57 Progress: 52% — §2–§5 built (3–6 of 11): four models + ledger migration (`test19f`: 400 rows of 400 assets, 253 active / 147 in review), two roles, four scopes, an exclusion pair, 27 routes; `tests/test_the_audit.py` 10 passed of 10 (gates off). Next: guards and pins, the in-registry no-master proof, the screens and the mobile map (two subagents).
- 21:18 Progress: 72% — guards, pins and the in-registry proof done (7 of 11): audit HTTP 10 of 10 gates off; audit + events API 96 passed of 96 gates ON; in-registry TestTheAuditSendsNothing 4 of 4, pins 0 failed of 62; docs (endpoint reference 198 of 198 routes indexed, mobile map, CHANGELOG, DECISIONS, GO-LIVE §35, CLAUDE.md) — §9 done (8 of 11). `test19` and `nrs19` upgraded (ledger 23,405 of 23,405; 11,960 of 11,960). Pushed `06439a2`; CI 39318028299 started (~13 min). Started: fan-out to the six other tenants (~3 min). Running: the screens (subagent).
- 21:28 Progress: 80% — §6 done (9 of 11): five Audit screens + spec 66 (subagent); CI 39318028299 red only on the SPA scope maps not yet pushed (2 failed of 1,540, both legs) — pushed with the screens `1cab1a9` (CI 39319646680). The screens subagent found a STALE GROUP CACHE: a refused or previewed grant left the refused role's scopes on the person's next logins (reproduced 4 of 4); fixed and pinned.
- 21:37 Progress: 88% — verification pass back (10 findings); fixed 1–8 and most nits, `c0d52d3`: in-registry 0 failed of 51; audit HTTP 11 of 11; browser 46/65/66 17 of 17 (gates off). Started: template rebuild + fresh `test19f` + full pytest gates ON (~18 min).
- 22:00 Progress: 94% — final local pytest on a fresh `test19f`, gates ON: 1,531 passed, 0 failed, 10 skipped of 1,541 (14 m 37 s). CI 39320416377: pytest green both legs, in-registry red with its result beyond GitHub's truncated log. Started: CI's exact in-registry command on the same `test19f` (~15 min). Report pushed marked CI pending.
- 22:10 Progress: 97% — CI's hidden in-registry failure reproduced locally with CI's exact command on the same fresh `test19f`: 1 failed of 1,306 (`TestSapMirrorScope`'s readers pin; the audit roles read the mirror) — fixed, 0 of 4; pushed `0d52ffc`; PR #127 opened.
- 22:29 Progress: 100% — CI 39325435784 green both switch states (pytest 1,525 passed, 16 skipped of 1,541 each; in-registry passed); report amended and pushed.

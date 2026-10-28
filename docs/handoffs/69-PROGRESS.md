# Handoff 69 — progress

Plan (weights sum 100): A1 every capture 10 · A2 stored-but-hidden 5 · A3 not stored 10 · A4 the answer 5 · B1 every page 10 · B2 find a capture 12 · B3 waiting with no reviewer 7 · B4 where it came from 6 · C1 audit_trace.sh 10 · C2 refused syncs kept 12 · C3 runbook 3 · tests, CI, report 10.

Budget: 3 h. Risk: C2 (new model + route + screen) is the largest single part; if the build passes 2 h 15 m, the Devices-and-codes section of C2 is the split point.

- 00:44 Progress: 0% — Step 0: handoff committed on dev (ad0ea71), branch `fix/where-the-captures-went`. Current kube context was Vendra's (`do-lon1-vendra-api-cluster`); the Cadra cluster is `do-ams3-cadra-1779758691124` (cadra-dev: db-0, odoo-19), used by explicit `--context`, the owner's current context left alone. Next: A1.
- 00:50 Progress: 25% — A1–A3 done on staging: 11 captures stored, 0 on gtb/jaizbankplc/lasg; campaign 1's 5 have no reviewer (H1); campaign 3's 5 sit behind the dropdown's default, campaign 4, empty (H4); 2 POSTs in the surviving log, both 201; 3 phone photos identified with no capture. Next: B server side.
- 00:58 Progress: 25% — server side of B2/B3/C2 written (model, recorder hook, ?q=, reviewers_active, /audit/refusals); upgrading test19 (~3 min). Front end and script/docs running in two agents.
- 01:00 Progress: 30% — test19 upgraded (19.0.1.37.0 / 19.0.3.39.0; table + column verified). test19 has no audit personas, so the targeted tests go to test19f: template rebuild started (~150 s).
- 01:06 Progress: 70% — B1–B4 and C2 built; targeted: pytest 7/7 (new) + 11/11 (test_the_audit), browser 2/2 (spec 69) + 3/3 (66, 67), in-registry 5 of 5 (TestCaptureRefusal) and the published-names guard 13 of 14 (the 14th fails on dev's code too, locally only). Full pytest started, gates off, fresh test19f (~9 min).
- 01:15 Progress: 80% — full pytest, gates off, fresh test19f: 1,568 passed, 3 failed, 14 skipped in 7 m 23 s. The 3 are guards: the query-parameter inventory and the model-create resolver (fixed; 233/233 rerun) and the endpoint index row for /audit/refusals (docs, in progress). Verification pass running.
- 01:25 Progress: 90% — verification pass: 1 defect (reviewers_active counted deactivated users on the detail routes) and 4 smaller points fixed, 3 named; affected tests 22/22 + browser 5/5. Committing and pushing.
- 01:27 Progress: 95% — pushed, PR #133. CI cannot start: every Actions run in the repo since 27 Oct 18:20 UTC is startup_failure (account side, not this branch). Running CI's other two jobs locally instead: full pytest gates on, then the myservice_asset_register and myservice_api in-registry suites (~30 min).
- 01:45 Progress: 100% — local in CI's place: pytest gates on 1,571 passed / 0 failed / 14 skipped of 1,585 (12 m 04 s); module suites 0 failed, 0 error(s) of 1,052 tests. Report final; CI itself still cannot start (owner). Closing step on dev.

## 69b — the team can be changed

Plan (weights sum 100): B1 edit the campaign 50 · the three leftovers 30 (merged refusal rows 15, sync_in_flight not recorded 5, Review it here past 100 10) · tests and report 20. Budget 1 h.

- 01:48 Progress: 0% — Step 0: instruction committed on dev; PR #133 was already merged (00:35 UTC), so 69b continues on the same branch, now open as PR #134, merged up to dev. Next: B1.
- 01:51 Progress: 60% — B1 built (Edit on an open campaign, Add a reviewer on the warning line); leftovers built: repeated refusals merge into one row (count, last_refused_at, 19.0.1.38.0 + migration), sync_in_flight not recorded, Review it here loads pages up to the capture. Next: upgrade test19f's template, tests.
- 01:59 Progress: 100% — 69b: HTTP 256 passed, in-registry 0 failed of 6, browser 3 of 3 (spec 69) + 3 of 3 (66, 67); report §69b appended; pushed to PR #134. CI still blocked repo-wide (owner).

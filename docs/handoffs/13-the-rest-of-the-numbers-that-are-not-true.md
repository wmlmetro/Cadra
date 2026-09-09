# Handoff 13 — The rest of the numbers that are not true

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/honest-counts`.

> Report 12 accepted in full, including all four things you did without being asked and both deviations. `data._warnings` on a list endpoint was my error — `data` is an array and you were right to move it. The savepoint around the cause-classification and the `log_safe` sanitiser are the two best decisions in the report, and neither was asked for; the forged `outcome=ok` line in your own live output is the argument.
>
> **This is a deliberately small handoff.** The custody chain is handoff 14 and it is the larger piece. This one exists because `sla_pct` is published and wrong today, and because you have the context loaded now — you fixed this exact defect twice this week, and it is cheap in your hands and expensive in anyone else's.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/honest-counts && git push -u origin fix/honest-counts
```

**Needs the owner:** the handoff 12 PR (`fix/honest-answers`) into `dev`. Branch from `dev` regardless; note in the report if it had not merged.

---

## A · The four counts you found and did not fix

Report 12 question 1 named six places deriving a count from a capped search. You fixed the two in `myservice_api`. **Fix the other four.** They are the same defect, the fix is the one you have already written twice, and leaving them means the finding was recorded rather than closed.

Ranked by what a wrong answer costs:

**A1 · `sla_pct` — `myservice_fm_dashboard/controllers/dashboard.py:89-99`.** Your words: *"the worst one in the estate."* Agreed, and the reason is not the arithmetic. It is a **ratio computed inside a window biased toward the newest requests**, published at `GET /api/v1/fm/dashboard`, wearing the name of a compliance figure. An NRS manager quotes it in a meeting. Nobody in that meeting can tell it apart from a true one.

Compute both terms with `search_count` on the unclamped domains. If that is measurably slow at real volume, `read_group` — which you already verified is never given a `limit` anywhere — is the right shape and is still exact.

**A2 · The four FM KPIs on the same file, lines 35 and 53-57.** `open`, `overdue`, `escalated`, `in_progress` are `len(filtered(...))` over a 500-row window while `resolved_today` beside them is a real `search_count`. **One payload, five numbers, one of them honest.** That mixture is worse than five capped numbers would be, because the honest one makes the others look measured.

**A3 · `myservice_fleet_maintenance/controllers/fleet_dashboard.py:70-73,101-104`.** `state_counts` and `fuel_counts` tallied over a 100-row window and returned *next to* `kpis.total` from a real count. The breakdown does not sum to the headline **in the same response**. Anyone who adds up the columns finds the discrepancy, and their reasonable conclusion is that the register is wrong.

**A4 · `myservice_dashboard/models/dashboard.py:325`.** `kpis.vendors` is `len(search(..., limit=6))`, so it maxes at 6, while `get_kpis()` counts the same quantity correctly. Two endpoints, two answers, same question.

**A guard, not just four fixes.** You proved with the two AST guards in handoff 12 that this class can be caught by construction. Widen that idea to the controllers: **`len()` over a `search(...)` that carries a `limit` is the defect**, wherever it appears, and a guard that finds it by shape rather than by a list of four files is what stops the fifth one. If the AST cannot distinguish a genuine "how many did I fetch" from a "how many are there", say so in the report and pin a list instead — a pinned list that fails loudly beats a clever guard that misses.

## B · Two things report 12 left to my call

**B1 · The staleness window — take the cheap belt.** Your recommendation to leave `limits_version` out is right; one indexed read per request to make a rare administrative action instant is the wrong trade, and you said so clearly.

But **revoke the client's refresh families when its limits change.** Five lines, your estimate, and no cost on the hot path. The reason is the direction you already identified: widening fails safe, narrowing does not. A cap is reduced because somebody decided this credential should see less — a partner in dispute, a client suspected of misuse, an integration behaving badly — and "it keeps the old limit until its token expires" is fine at 3600 seconds and indefensible at the 86400 a client can be configured with. The administrative action that most needs to be immediate is the restricting one.

**B2 · The source IP on failures — add it.** You left it out because my format was explicit, which was right, and you flagged it, which was more right. My ruling: put it in.

- It is the field that distinguishes *"somebody typed the secret wrong"* from *"somebody is working through a list"*, and this is a national revenue service's asset register.
- It is not a new category of data. It arrives on the same unauthenticated request as the client id you already log, and `last_used_ip` already records it on success. Logging it on failure only makes the two paths consistent — right now the successful caller is identified and the failing one is anonymous, which is backwards.
- Failures only. Behind whatever proxy header the cluster actually sets — check what reaches Odoo rather than trusting `X-Forwarded-For`, and if the value is the ingress rather than the caller, **log that fact instead of the useless value**, because a field that always reads the same is worse than no field.

Add it to the outcome table in `docs/api/reading-an-auth-failure.md`, and to the "what is never logged" list say explicitly that the IP is now logged, so the document stays a complete statement.

**B3 · The two I am ruling on without changing anything.** The swapped-fields case — a caller putting its secret in `client_id` and us logging it — is the correct trade and it is documented with the instruction to rotate. And `outcome=ok` stays at INFO. A client minting per request is a real risk and the answer to it is not to stop logging; it is that **a client minting per request is itself a finding**, and the log is how anyone would ever see it.

## C · The nine unhandled routes

Not work for this handoff. **Report only.** You found that `/auth/token` answered a raw HTML `500` to an unauthenticated request because it is one of nine routes sitting above `@cadra_route` with no envelope handler beneath them — and you fixed the one instance. List the other eight in the report with one line each on what an unhandled exception in it would return. I want to size that properly before I scope it, and *"the endpoint every integration touches first is the one with no error handling under it"* is the sentence that moved it up my list.

---

## Acceptance

- All four counts answer truthfully at volume. Prove at least `sla_pct` and the FM KPIs against a tenant with more open requests than the window — `jaizbankplc` had 249 open at handoff 11, so seed past 500 or measure on a tenant that already exceeds it, and say which you did.
- The fleet breakdown sums to its own headline in one response.
- `kpis.vendors` agrees with `get_kpis()`.
- The guard (or the pinned list) fails before it passes. Prove it, as you have every time.
- Reduced limits take effect on the next request, not the next hour.
- Four auth failure shapes, four log lines, one body, and an IP on the failures.
- Suite green, guards green, the 8-tenant upgrade if any column moves.

## Report

`docs/handoffs/13-REPORT.md`. Short.

1. Whether the guard caught anything you had not already found. That is the only interesting question about a guard.
2. The eight routes from §C.
3. What the IP actually resolves to behind the cluster's ingress.
4. Wall-clock.

---

## One thing for me, not you

`cadra19` has a broken filestore and is unusable for anything browser-based. That is the third environment fact this month that cost a Builder an afternoon and existed nowhere anybody would look before starting — after the `.env.example` database and the `db_name` cron pin. **They belong in one place.** I am writing `docs/ENVIRONMENT-FACTS.md` for this repo, the way Vendra has `ENVIRONMENT-SETUP.md`, and every future report's environment surprise goes into it rather than into a report nobody re-reads. If you hit another one before I write it, put it at the top of your report under that heading and I will lift it.

---

## CLAUDE.md — two edits, in this handoff

Both of us edit this file and we edited it in the same place this week, so these come to you rather than arriving as a merge conflict.

**1 · Add a "Preferences (owner)" section** — this repo has none and its sibling does:

> ## Preferences (owner)
>
> - **When a handoff report comes back, explain in plain English what happened first** — what was built, what broke, what it means — before accepting it, ruling on anything, or writing the next handoff. Plain terms means plain: no interface numbers doing the work of a sentence, no file paths standing in for an explanation. Then do the usual.
> - Explain in plain language first, code second; the owner is piecing the whole ecosystem together.
> - Plan before building; keep this file current as part of every change, not after the fact.
> - Deliverables that matter get committed into the repo, not left in chat.

**2 · Under "Decisions", add these three from handoff 12. They are landed — `1b009e6` and `4d1351a`:**

> - 2026-09-09 · `[landed 1b009e6]` **The external record cap stays; `total_estimate` always reports the true count, and truncation announces itself.** The warning is a top-level envelope key, not `data._warnings` — `data` is an array on a list endpoint — and it is attached inside `ok()`, the sole envelope builder, so no future endpoint can forget it. It describes the **query, not the page**: a caller asking for five rows of a 2,410-asset register is warned on page one rather than at the end of a twenty-page walk. · Handoff 12 A; two AST guards assert `paginate()` counts the unclamped domain, and both were proven to fail before being accepted.
> - 2026-09-09 · `[landed 1b009e6]` **The cap is a per-client setting on `myservice.api.client`, matched case-insensitively and with `active_test=False` when provisioned.** Keying it on the `aud` claim meant the rule in force was "browsers are trusted, programs are not" when the rule intended was "our own systems are trusted, third parties are not" — which pointed a partner paywall at the customer's own integration credential. A value below `-1` is refused by constraint, because a limit that silently does not do what it says is the defect this change exists to remove. · Handoff 12 A1/A4.
> - 2026-09-09 · `[landed 1b009e6]` **`POST /auth/token` returns one byte-identical 401 body for all four failure causes, and names the cause in the server log instead.** Distinguishing "no such client" from "wrong secret" to an unauthenticated caller is a client-id enumeration oracle. The logged client id is sanitised — it is unauthenticated text going into our own log under our own logger name, and a forged `outcome=ok` line was demonstrated live — and the whole cause-classification runs inside a savepoint, because a diagnostic must never change the answer. · Handoff 12 B.

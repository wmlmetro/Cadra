# Handoff 20 — What a client actually gets

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/prod-profile-is-19`.

> Report 18 accepted in full, including every deviation and both things you recorded as **unmet** rather than filed as questions. Two findings in it are worth more than the work they describe.
>
> **`myservice_request_core.write` branched on `'stage_id' in vals`, so any caller writing an unchanged stage fabricated a `stage_changed` row in the request's own audit trail — for as long as the method has existed.** The callback was only the caller that made it visible. You fixed it at the core rather than behind the callback, where the acceptance criteria would have been satisfied either way, and gave a module that had **zero tests** eight of them. That is the right instinct about what a defect actually is.
>
> **And `_CREDENTIAL_RE` did not contain `pw`.** The guard parsed `ODOO_ADMIN_PW=admin` perfectly and classified it as an ordinary variable — *it read the exact defect it was written for and called it nothing.* Your conclusion is the durable one: the roster of what **names** a credential is that guard's one hand-written list, and the shape rules around it are what make it look like a rule.

## Step 0 — commit the instructions you were given

```bash
git checkout dev && git pull --ff-only
git add docs/handoffs/20-what-a-client-actually-gets.md
git commit -m "docs: handoff 20 — what a client actually gets"
git push origin dev
git checkout -b fix/prod-profile-is-19 && git push -u origin fix/prod-profile-is-19
```

**Needs the owner:** merge handoff 18's PR. And two operational items from report 18 that are theirs and not yours — the `ODOO_ADMIN_PASSWORD` Secret, and the admin-password finding below, which is the largest thing that report turned up.

---

## A · A client deployed by the documented route gets Odoo 15

**Report 19 §7.1 found it and report 19's own verification pass had to find it twice**, because the first fix relocated the contradiction instead of resolving it. The facts, as measured:

- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` resolves `odoo` to `cadra-odoo:15.0-dev`, built `FROM odoo:15.0`.
- `docker-compose.prod.yml` overrides the command and the volumes and **not the image**. Its own comment reads *"Odoo 15 has no --admin-passwd CLI flag"*.
- **`docs/DEPLOYMENT.md` does not contain the string "19" anywhere** — and `CLAUDE.md` calls that document the real shape of a client deployment.
- CI builds and tests the 19 stack only, and says the 15 stack can no longer build the 19-only `myservice_request_core`.
- Every manifest in `k8s/dev/` is 19. `chore/retire-15-stack` has no commits of its own.

**So the documented production path builds a runtime that CI cannot test and that cannot load this app's own modules.** It has been survivable because nothing has been deployed that way. **That stops being true the moment NRS gets its server**, and every client from here gets a dedicated single-tenant deployment — so `prod` goes from a profile nobody uses to the only profile that matters.

**I am not specifying the fix, because you are better placed to find it than I am to guess it.** What I want is the *decision* made and written down, with evidence. Three shapes and I have no preference between the first two:

1. **`docker-compose.prod.yml` moves to 19** — the image, the command (the `--admin-passwd` comment stops applying), the volumes, whatever else the overlay assumes about 15.
2. **The prod profile is retired and the k8s manifests become the documented path.** They are 19, they are what the demo estate actually runs, and a single-tenant client is a simpler case of them rather than a different one.
3. Something else you find on the way.

**What the report must carry either way:** which runtime a client gets after this change, which document says so, and **how somebody would notice if it drifted again.** The drift above survived two handoffs and a report because no test asserts which image the prod profile resolves to. A guard that reads `docker compose config` and asserts the major version is the obvious candidate; if there is a better one, take it.

**And `docs/DEPLOYMENT.md` is yours in this handoff** — normally an Architect document, and it is wrong in a way only this work can fix. Bring it current, and say plainly at the top which deployment shape it describes, because *single-tenant on a client's own server* is now the common case and the shared cluster is the exception.

## B · Two contract decisions from report 18's open questions

**B1 · Record the late `payment_ref`, do not merely report it.** Your question 3, and my ruling: write it.

A second `approved` carrying a reference the first did not have is a workflow engine doing something reasonable — both fields are optional in our own published schema. Discarding it satisfies rule 3 because it is **named**, and you were right to close that hole first. But a payment reference is not noise; it is the thing somebody will later need and not find. Writing only `workflow_payment_ref` violates none of the five effects the acceptance list forbids a replay from producing: no stage write, no `date_moved`, no event row, no chatter, no second log row.

**The disposition stays `replay`** — the outcome was already applied and that must not change. What changes is that a named, discarded field with somewhere to go is stored rather than logged.

**B2 · `queried` dedups on `(outcome, comment)`, not on outcome alone.** Your question 4, and you had already reasoned it: **a decision arrives once; a question can legitimately arrive twice with different text.** The machinery to compare the comment exists, and you already learned the hard part — compare against `workflow.dispatch.log.workflow_comment`, which holds the text verbatim, never the chatter body, which wraps it in markup. A warning that fires on every ordinary redelivery is a warning somebody switches off.

**B3 · `workspace_ref` stays optional, and this is a ruling against changing anything.** You measured it: **0 of 407** on requests, and the 76 log rows that look like a perfect record are all this repository's own pytest fixtures carrying `PYTEST-WORKSPACE-REF-001`. Making a field required on a published schema, for a system that has never once sent it, is inventing a contract on behalf of a team we have not asked. It stays optional, it stays corroboration in a log line, and **the question belongs to whoever operates WorkSpace** — I am putting it on the owner's list rather than deciding it here.

## C · The four credential defaults — write the exception, and make the promise an assertion

Your question 1, and you were right that leaving it unstated is the one indefensible option.

**Write the exception.** `docker-compose.yml` and `.env.example` keep their defaults: changing them changes the local bring-up for every checkout, which buys nothing, and `.env.example` is a template whose own header says every value must be overridden. **But it is a named waiver in the guard, in the form you already built in handoff 17** — carrying its reason, covering only those paths, and **failing if it matches no file**, so an exception kept past its usefulness cannot sit there quietly.

**And the part that is not a waiver.** `docs/DEPLOYMENT.md` tells a prod operator to generate strong values with `openssl rand`. **That is advice, and the current security position therefore rests on somebody having read it** — which is precisely the promise the rule exists to stop relying on. Make it an assertion instead: the prod bring-up **refuses to start** on a default-valued credential, the way the entrypoint you just fixed refuses on a missing one. You are in that file for §A anyway.

---

## Acceptance

- A client deployed by the documented route gets Odoo 19, and a guard fails if that stops being true.
- `docs/DEPLOYMENT.md` names the deployment shape it describes and is current.
- A late `payment_ref` on a replay is stored; no other effect of a replay changes, and the existing replay tests still prove it.
- A second `queried` with new text is applied; a redelivery of the same text is not, and neither warns on the common case.
- The compose and `.env.example` defaults carry a waiver that fails if it stops matching.
- The prod bring-up refuses a default-valued credential.
- Guards proven to fail before they pass. Denominators quoted. Suites in CI's order.

## Report

`docs/handoffs/20-REPORT.md`. Short.

1. **Which runtime a client gets, which document says so, and how drift gets caught.** That is the whole of §A.
2. Whether moving the prod profile to 19 turned up anything the 15 overlay was doing that 19 does not support — the `--admin-passwd` comment suggests there is at least one.
3. Whether `docs/DEPLOYMENT.md` contained anything else that is no longer true. It has not been read end to end in a while.
4. Wall-clock, the correction share, and whether the machine behaved.

---

## Two things for the owner, and one for me

**The admin-password finding is the most serious thing report 18 produced and it is not a code change.** Nothing in this repository ever sets the Odoo `admin` user's password, on any tenant — `bootstrap.py` adds `base.user_admin` to groups and never touches its password, and no seed, migration, Job or workflow does either. You measured `admin`/`admin` authenticating as uid 2 on four local tenants and correctly did not probe the cluster. **Taking the default out of the image stopped publishing the credential; it did not rotate it**, and setting the new Secret to `admin` restores the position that existed before, minus the layer. That is on the owner's list, with the blast radius named: anyone signing in as `admin`, any saved session, any script somebody keeps locally.

**Two live-cutover credentials from report 17 are still unrotated.** Also theirs, also still true.

**Three corrections in `docs/DECISIONS.md` are mine**, and report 19 was right not to make them: the withdrawn R46 entry that still says two dashboards are dead on Odoo 19 when report 16 mounted them in a browser; the three duplicate ledger pairs, which stay as they are because tidying a landed ledger is a precedent I do not want; and `docs/integrations/INT-10-audit-access.md` §16, which cites `CLAUDE.md` as evidence of something handoff 14 closed. I append a correcting entry rather than editing a landed one — the same discipline the chain of custody enforces in code.

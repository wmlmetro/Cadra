# Handoff 56 — The name and the hat

**Branch:** `fix/the-name-and-the-hat`
**Report:** `docs/handoffs/56-REPORT.md` — short. One page.
**Freeze:** the demo is today. **Nothing else merges, nothing else deploys,
and this branch must be mergeable on its own.** Handoffs 53 and 55 are
paused where they stand; do not touch their branches, do not rebase anything.

**Base: the commit that is actually deployed, not `dev` HEAD.** Measure it
first — the deployed `myservice_api` version against `dev`'s manifest, or the
deploy Job's image tag — and print both in the report. If `dev` is ahead of
what is deployed, branch from the deployed commit and **say so in the first
line of the report**, because merging this into `dev` and deploying `dev`
would carry everything in between, and the owner has said no.

---

## 1 · What the owner asked for

In the top-right of the app, where the signed-in person's name and email
are, **show the role they hold** — *Auditor*, *Asset Manager*, *Tag-Issuing
Unit* — so a persona can be told apart at a glance during the demo.

## 2 · Why this is not purely a front-end change on Cadra, and the minimum

The top bar reads `GET /api/v1/auth/whoami`, which returns `id`, `login`,
`name`, `email`, `scopes` — **and no roles.** The only route that names a
person's roles is `GET /api/v1/users/<id>`, behind `access:read`, which a
storekeeper does not hold. So there is no response a non-administrator can
read today that says what role they hold.

Two ways to put a role on the screen:

- **Derive it from `scopes` in the browser.** Rejected. A scope set maps to
  a role only approximately — Asset Officer is Asset User plus one scope,
  an admin is a wildcard — and the label would be a guess that is wrong
  exactly for the persona it matters for. We do not put guesses next to
  people's names.
- **Add `roles` to `whoami`.** Accepted — the minimum honest change. One
  additive key on one existing route, no stored field, no view, no fan-out
  beyond the manifest bump the deploy Job expects.

So:

### 2a · Server

`whoami` gains `"roles": [{"key": ..., "name": ...}]` — the roles the user
holds that the Users page already publishes, from the **same**
`PUBLISHED_ROLE_NAMES` vocabulary and the same `role_key`, in `GROUP_SCOPES`
order. The same user's `/users/<id>` roles and their `whoami` roles must be
the same list — assert that in the test. Additive; `docs/api/CHANGELOG.md`
one line; the OpenAPI response schema for the route updated. Nothing else on
the server.

### 2b · Front end

`Topbar.tsx`: under the name, in the small text where the email sits, the
role name. One role: its name. Two: both, joined with a middle dot. Three or
more: the first two and *+N*, with every role listed in the dropdown. An
administrator (`base.group_system` → the `admin`/`system` key) shows
*Administrator*. **No roles returned: show nothing** — not "User", not a
dash. A blank is honest; an invented label is not. `WhoAmI` in
`dataProvider.ts` gains the field; a missing field (an old server) is an
empty list, so the bar degrades to today's behaviour rather than crashing
behind handoff 50's boundary.

## 3 · What must not change

Anything else. No nav change, no sidebar, no Users page, no scope, no
persona, no doc sweep beyond CHANGELOG and this report. If you find a defect
while here, write it in the report and leave it.

## 4 · Verification — the minimum that still proves it

1. The one pytest (`whoami.roles` equals `/users/<id>` roles for three
   personas; empty list for a credential with no groups).
2. Driven in the browser as **every Cadra persona** on `test19` — the top
   bar for each, one screenshot each, the role text read off the image.
   This is the whole point of the change and it takes five minutes.
3. `tsc --noEmit`; the browser specs that touch the top bar (41, 45, 46)
   green; the HTTP suite once.
4. The bundle rebuilt and served for the drive.

Report: the base commit measured, the screenshots, the suite lines. Nothing
else.

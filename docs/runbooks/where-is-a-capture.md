# Where is a capture?

**For:** the owner, and whoever is asked *"the phone says I submitted it, but
the reviewer can't find it."* **Since:** handoff 69 (28 October 2026).

A capture the reviewer cannot see is in one of two places. Either **the
server has it and the review page is not showing it** (H1–H4 below), or
**the server never got it** (H5–H7). Work down this page from the top: the
first three steps are in the web app and answer most cases; the last step is
one command for the cases the web app cannot see.

## What you need from the person

Any one of these identifies a capture:

- the **capture ID** the phone shows (a long code like
  `0d4b1c4d-bdbe-4839-ac59-6beb2d6203ea`);
- the **printed code** on the label (`NRS-AST-012001`);
- the **old FIRS tag** they confirmed on the item;
- failing all of those: the **time, the room, and who captured it**.

Also ask **which address the phone is connected to** (its server, e.g.
`staging.app.cadra.ng`). That is the tenant to look in.

## The seven reasons

| # | What is happening | What you see | What to do |
|---|---|---|---|
| H1 | The capture's campaign **names nobody as a reviewer**, or not this person. The review page lists only open campaigns that name the person signed in. | *Find a capture* finds it and says *"You are not a reviewer on …"*, naming who is. On **Audit review**: *"N captures wait in campaigns that don't name you as a reviewer."* On **Audit campaigns**: *"N captures wait and no reviewer is named."* | The Asset Controller opens the campaign on **Audit campaigns** and adds the reviewer. The captures appear at once. |
| H2 | The campaign is **closed**. The review page lists open campaigns only. | *Find a capture* shows the campaign as closed. | Nothing to review: a campaign closes only once every capture in it has been reviewed. Its result is on the capture. |
| H3 | More than **100** captures wait in that list. Before handoff 69 the review page showed the first 100 (oldest first) and said nothing about the rest. | The page now says *"Showing 100 of N waiting"*. | Press **Show the next 100**. |
| H4 | The reviewer is **looking at another campaign or room**. The campaign box opens on the *newest* open campaign naming them, which may be an empty one. | *Find a capture* shows it in a campaign the reviewer is on, just not the one selected. | Pick that campaign in the box at the top of **Audit review** (and *Every room*), or press **Review it** on the *Find a capture* result. |
| H5 | The server **refused** it — the device was not bound to the person, the code was not theirs, the scanned label was not the code, the room was outside the campaign, the capture was more than five working days old… Nothing is stored for a refused capture. | *Find a capture* finds nothing. Since handoff 69 the refusal is on **Devices and codes › Refused syncs** (last 7 days; kept 90): the time, the person, the device, and the sentence the phone was sent. | Read the sentence; it says what to fix. The person fixes it and sends the capture again. If the phone showed it as *submitted*, tell the mobile team: the phone must show the refusal and keep the capture (mobile guide §6.6). |
| H6 | The phone sent it to **another tenant** — a different server address from the one the reviewer uses. | Nothing on this tenant, nothing in Refused syncs. | Run the command below with the capture ID or code: it searches every tenant and says where it is. Point the phone at the right address. |
| H7 | It is **still on the phone** — never sent (no signal, the app closed, the queue stuck), or sent and lost on the way. | Nothing on any tenant, nothing in Refused syncs, and no `POST` for it in the server's log. | The mobile team's to look at: the phone's queue for that capture. The person should not re-capture until the queue is checked: a re-capture is a new capture, and the stuck one may still arrive (it is held as a duplicate only when both name the same asset, SAP record or old tag). |

## Step by step in the web app

1. **Audit review › Find a capture** (also on **Audit campaigns**). Paste the
   capture ID, the code or the old tag. If it is found, the answer names its
   campaign (open or closed), room, state, who captured it on which device,
   when the server received it, and who may review it — that is H1, H2 or
   H4, and the row says which. If it says *"No capture on this register has
   that ID or code"*, go on.
2. **Devices and codes › Refused syncs** (the Asset Controller). Look for the
   person and the device around the time. A row there is H5, with the
   reason in the server's own words.
3. **Audit campaigns.** A campaign with captures waiting and a warning that
   no reviewer is named is H1 for every capture in it.

## When the web app has no answer (H6, H7): one command

From a machine with the cluster's access (the owner's), in the repository:

```
scripts/audit_trace.sh staging --capture 0d4b1c4d-bdbe-4839-ac59-6beb2d6203ea
scripts/audit_trace.sh staging --code NRS-AST-012001
scripts/audit_trace.sh staging --device DEV-9FC2E414 --since 2026-10-20 --logs
scripts/audit_trace.sh staging                 # every capture of the last 14 days
```

It only reads — every query runs read-only — and prints ids, never names. It
uses the Cadra cluster by name, whatever cluster your terminal is pointed
at, and refuses to run anywhere else. It prints:

- every matching capture, with **`hidden_by`**: which of H1–H4 hides a
  waiting one;
- per campaign, how many wait, who the reviewers are (by id), and whose
  review page opens on it;
- the refused syncs kept on that tenant;
- photos the phone uploaded that are on **no** capture — an item that was
  photographed and then never sent (H5 or H7);
- with `--capture` or `--code` and nothing on this tenant: the same search
  on **every other tenant** (H6), and where it was found;
- with `--logs`: every `POST /api/v1/audit/captures` the server's log holds
  for the tenant, and their statuses. **The log only goes back to when the
  server last restarted** (the script says when). A capture with no row on
  any tenant, no refusal and no `POST` in the log never reached the server:
  H7.

`--local` runs the same against this machine's own stack (`test19f`, …).
`nrs19` is refused: it holds a real NRS staff extract and is not touched.

## The worked example: staging, 27 October 2026 (handoff 69 Part A)

The server held all 11 captures the phone had sent. **Campaign 1**: 5
captures waiting, and **no reviewer named** on the campaign, so no reviewer's
page could ever list them (H1). **Campaign 3**: 5 captures waiting, and its
reviewer named — but the review page opened on **campaign 4**, a newer
campaign naming the same reviewer and holding nothing, so they sat one pick
away in the campaign box (H4). The server's surviving log held two capture
`POST`s, both accepted; nothing had been refused.

# Handoff 64 — What the photo says

**Branch:** `feat/what-the-photo-says`
**Report:** `docs/handoffs/64-REPORT.md`
**Runs after:** 63 and 63b (the faster loop), merged. Branch from `dev`,
after pulling.

**Step 0, in one docs commit with this file:**

- **`CLAUDE.md`'s new section, *Progress you report while you work*,** if
  it isn't committed yet. Follow it from this handoff on.

- **Append ruling R11** (§0 below) to `docs/AI-CAPTURE-EVALUATION.md` §2.
- **Renumber its §4:**
  - 64 becomes *AI identification, server-side, web first*;
  - **65** becomes *the link*: Cadra's own NRS register linked to SAP's
    records (report 63 §6);
  - devices, code blocks and the audit-capture path become **66**.
- **Correct `docs/integrations/INT-05b-register-state.md`:** for a
  `grn_reference` Vendra doesn't hold, Vendra answers `202` and
  dead-letters on its side. It is **not** a 4xx (Vendra report 57, Cadra
  report 62 §4.2). Fix the sentence to match; no behaviour change.
- **Update `docs/integrations/mobile-ai-capture-endpoints.md`:**
  - the model manifest and download rows become *not needed: Cadra
    identifies the photo (R11)*;
  - add the new route from §2.

---

## 0 · The ruling: R11, Cadra identifies the photo

The AI addendum and the mobile team's endpoint list assumed a recognition
model **on the phone**: trained, packaged, downloaded through a model
manifest. The owner has ruled otherwise, on 18 October:

- **No model is trained or shipped.** Recognition uses an **existing,
  general-purpose vision model from an AI provider**, called **by Cadra's
  server**, never by the phone or the browser directly. Today's large
  vision models describe a photographed chair, desk or laptop, read the
  text on it, and choose among a list of classes they are given, without
  training.
- **Why server-side:**
  - **one feature for every client.** The owner wants it on **Cadra's web
    app** as well as the phone, and both call the same Cadra route;
  - the provider's key never leaves the server;
  - the provider can be changed without touching any client;
  - every suggestion is recorded where the audit trail lives (AI-NFR-05).
- **Offline:** a photo taken offline is identified **when it syncs**.
  Until then the person picks the class themselves. They confirm the
  suggestion anyway, so nothing depends on the AI being reachable.
- **What a photo can and can't do:** it identifies the **kind** of item
  (class, description, colour, material, condition) and reads **visible
  text** (a brand, a model, a serial plate, an old FIRS tag sticker). It
  can't tell **which** of 80,000 SAP furniture records a chair is. That
  is the matcher's job (63), fed with what the photo read.
- **The AI proposes, a person confirms.** No field is written from a
  suggestion without a person accepting it (addendum principle; handoff
  40's camera rule).
- **Data leaves our servers.** Photos go to the provider. This joins R7's
  hosting acceptance: NRS's written acceptance names the provider before
  production photos are sent. The owner's item.

## 1 · The provider, behind one adapter

- **An adapter interface** in one module: send an image, a prompt and a
  JSON schema; get validated JSON back, plus the model name, latency and
  token or cost counts.
- **Two implementations:**
  - **a fake**, deterministic and offline. Every test uses it.
  - **one real provider: Anthropic's Messages API (Claude) with image
    input.** This is the owner's choice, 18 October. The model id goes in
    configuration, not code.
- **Configuration**, per tenant, as `cadra.*` parameters on the
  configuration record:
  - `cadra.ai.identify` (on/off, **default off** everywhere);
  - the provider;
  - the model id;
  - a timeout (default 20 s);
  - a **daily call cap** per tenant (default 500), with the count shown on
    Settings.
- **The key is a secret, and it is the owner's.**
  - It never appears in the repo, a test, a log, an error, the
    configuration record or this report.
  - Find how existing server secrets reach a tenant (SMTP, Turnstile) and
    use the same way. Document the owner's one command to place it. **You
    don't place it, and you don't ask for it.**
  - Every test runs on the fake.
  - The live check (§5.5) is run by the owner, with a command you write.
- **What is sent:**
  - the photo (61 already caps it at 300 KB);
  - the tenant's categories (name, identification mode, mapped SAP class);
  - for each SAP class, its **twenty commonest descriptions** from the
    mirror, as examples. These are counts and words, not records.

  **Nothing else:** no asset ids, no people, no locations, no SAP numbers.

## 2 · The route

**`POST /api/v1/ai/identify`**, scope `assets:write`, behind the switch.

- **Takes** a photo id already stored (61's `POST /assets/{id}/photos`), or
  a photo upload not yet tied to an asset (the "add a new asset" case),
  stored the same way and pending until an asset claims it or it expires.
- **Returns:**
  - **category:** the tenant's category id and name, with confidence, and
    up to two alternatives;
  - **attributes:** `name` (a description in SAP's style, e.g. *HIGH BACK
    EXECUTIVE SWIVEL CHAIR*), `colour`, `material`, and `make` and
    `model_name` **only if legible**;
  - **condition:** one of the published enum values (R5: *unserviceable*
    is `poor`, with a note);
  - **text read:** each string with what it looks like: `brand`, `model`,
    `serial_like`, `firs_tag_like`, `other`;
  - **SAP candidates:** 63's matcher called with the old tag if one was
    read, plus the class and description. Up to five, each with its
    ranking reason. Only for callers holding `sap_mirror:read`; others get
    the count.
  - **`suggestion_id`.**
- **Dimensions are never guessed.** A photo has no scale. `dimensions`
  stays empty unless a label in the photo states them.
- **Refused in words:**
  - switch off;
  - daily cap reached (*"today's 500 identifications are used; fill the
    details by hand"*);
  - provider timeout or error (*"the photo could not be identified just
    now; fill the details by hand"*);
  - a non-image.

  Answers that fail the schema are discarded, counted, and never shown.
- **The record.** Each call writes an append-only `nrs.ai.suggestion`:
  - photo, provider, model, prompt version, the suggestion JSON, latency,
    cost counts, who, and when.
  - **When the person saves,** the save links the suggestion and records,
    per field, *accepted*, *changed (from → to)* or *ignored*. That is
    AI-NFR-05's audit trail, and the history shows it in one line: *"Details
    suggested from a photo; 4 accepted, 1 changed."*

## 3 · On the web app

**Identify from photo** in two places, using only the route above:

1. **Add asset** (the asset form):
   - take or upload a photo, get the suggestions, and see them **filled
     into the form, marked as suggested** until the person touches or
     accepts each one;
   - pick an SAP candidate to fill the SAP number, if the person may;
   - the photo becomes the asset's first photo on save.
2. **An asset's Photos tab:** *Identify* on any photo shows the
   suggestions **beside** the current values, with *Use this* per field. It
   never overwrites silently. Useful for cleaning legacy records with
   *Unknown* descriptions.

Both say on screen, once: *"Photograph the item, not people. The photo is
sent to <provider> to read it."*

## 3b · A Test Connection that tells the truth

The owner pressed **Test Connection** on staging's Vendra target and got
`HTTP 401 AuthenticationError`. The button GETs `<base URL>/ping` with
the bearer token. Vendra has no `/ping`, and Frappe answers `401` to any
bearer request on a path no auth hook covers. **So the button fails for
every Vendra target, whether or not delivery works.** A health check that
always says *failed* is worse than none.

- **For a target whose purpose is `asset_events`:** test what Cadra
  actually sends.
  - Make an authenticated request to the configured event endpoint and,
    if set, the register-state endpoint, with a body Vendra recognises as
    a probe. Agree the shape from Vendra's receivers. If they have none,
    send a request they will refuse *for its content*, not for auth: a
    `400` or `422` proves auth passed, and a `401` proves it didn't.
  - Report each endpoint in words: *"Tag events: reachable, token
    accepted. Register-state events: reachable, token accepted."* Or say
    which failed and why.
- **Other purposes:** keep the current behaviour. Say in DECISIONS whether
  SAP's target has the same false failure.

## 4 · What must not change

- **Switch off** (every tenant by default): no route answers except to
  refuse, and no screen shows the button.
- No suggestion writes a field by itself.
- 61's photo rules (cap, immutability, supersede) and 63's matcher
  ranking.
- The provider key: never in the repo, a log or this report.

## 5 · Verification

1. Per `CLAUDE.md`'s *Speed* rules: targeted tests while building; one
   final local pytest run (gates off is enough here: nothing in this
   handoff touches the gates); CI for the rest, cited by its run. All tests
   use the fake adapter.
2. **The route, on the fake:**
   - each field;
   - the SAP candidates for a holder of `sap_mirror:read` and the count for
     others;
   - each refusal;
   - a malformed provider answer discarded and counted;
   - the cap.
3. **The audit trail:** a save with 4 accepted and 1 changed, the record
   and the history line, and an unsaved suggestion leaving nothing on any
   asset.
4. **The web app** (browser suite): both places, with suggestions marked
   until accepted; nothing written on *Cancel*.
5. **The live check, for the owner to run**, once the key is placed on
   `test19` or `staging`: a script that sends **the owner's own photos**
   from a folder (the owner photographs 30–50 items around the office:
   chairs, desks, laptops, printers, an air conditioner, and two or three
   with an old FIRS tag visible). For each it prints:
   - the suggested category against the true one (from the file name, e.g.
     `chair-01.jpg`);
   - the text read;
   - the top SAP candidate's reason;
   - the time and cost.

   Then totals: category right first time, right in the top three, average
   seconds, cost per photo. **Write the script and its instructions; the
   owner runs it**, and pastes the totals into this report as an
   addendum.
6. The fan-out, readiness, and the deploy steps; the switch stays off on
   every tenant until the owner turns it on.

And the standing sentence check.

## 6 · The question for the report

**What would it cost to identify a whole office?** Take the provider's
published per-image cost, or the fake's token counts against the
provider's published prices, and NRS's numbers: 161,647 active assets, and
80,370 furniture. Price:

- one photo per asset for the whole register;
- one Lot 4 audit of the headquarters (use the share of SAP records whose
  old tag carries an HQ office code).

Also say what reduces it: smaller images, or identifying only when the
person asks.

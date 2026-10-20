#!/usr/bin/env python3
"""The live check of *Identify from photo* — handoff 64 §5.5, 65 §0a.2. THE OWNER RUNS IT.

It sends the owner's own photos, one at a time, to a tenant's
`POST /api/v1/ai/identify` — the same route the web app calls — and prints,
for each, the suggested class against the true one, the text read, the top
SAP candidate's reason, the time and the cost. Then one TABLE PER MODEL:
right first time, right in the top three, seconds per photo (mean and
median) and cost per photo.

CHOOSING THE MODEL (handoff 65 §0a.2): `--models a,b,c` runs the SAME folder
through each model in turn — the tenant's model is set to each with
`PATCH /api/v1/settings/ai-identify` and put back afterwards, whatever
happens — so the owner can pick the cheapest model that is right often
enough. Without `--models` it runs once, on the model the tenant already has
(Opus by default, `claude-opus-5-5`, until the owner chooses otherwise).

CHOOSING THE PROVIDER (handoff 68): an entry may be `provider:model` —
`--models openai:gpt-6.1-sol,anthropic:claude-opus-5-5` — so one folder
compares providers in one run; the tenant's provider is switched for that
entry and, like its model, put back afterwards. A bare model is asked of the
tenant's own provider. The server needs THAT provider's key
(`CADRA_AI_API_KEY` for Anthropic, `CADRA_OPENAI_API_KEY` for OpenAI); a
provider whose key is absent is refused at the switch, in words.

BEFORE YOU RUN IT
-----------------
1. Set the provider key ON THE SERVER (the key never goes in this script, and
   since handoff 65 never in a database): the server reads `CADRA_AI_API_KEY`
   (Anthropic) and `CADRA_OPENAI_API_KEY` (OpenAI) from its environment.
       scripts/set_ai_key.sh               # local; prompts, nothing echoed,
       scripts/set_ai_key.sh openai        # writes .env — then recreate odoo
   On staging: the GitHub secrets of the same names, which deploy-dev syncs
   into the `cadra-odoo` secret, then a rollout of the Odoo Deployment
   (docs/DEPLOYMENT.md).
2. Switch it on, on THAT tenant only: Settings → Identify from photo → on,
   provider `anthropic` or `openai`. (Photos leave our servers: R7 / R11.)
3. Photograph 30–50 items around the office — chairs, desks, laptops,
   printers, an air conditioner, and two or three with an old FIRS tag
   visible — and name each file after what it is:
       chair-01.jpg  chair-02.jpg  desk-01.jpg  laptop-01.jpg
       air-conditioner-01.jpg  printer-firs-01.jpg
   The words before the first digit name the TRUE kind, shortened to the
   longest run `labels.json` names (`printer-firs-01.jpg` → `printer`).
4. Say which of the tenant's classes each kind belongs to, in `labels.json`
   in the same folder (otherwise a kind is "right" when the class's name
   contains it, which is rarely how classes are named):
       {"chair": "Office Furniture", "desk": "Office Furniture",
        "laptop": "IT Equipment", "printer": "IT Equipment",
        "air-conditioner": "Electrical Equipment"}

RUN
---
    tests/.venv/bin/python scripts/ai_live_check.py \\
        --base http://test19.localhost:8069 --folder ~/Desktop/office-photos \\
        --models claude-opus-5-5,claude-sonnet-5-5,claude-haiku-5-5

    # two providers, one table each, the same photos:
        --models openai:gpt-6.1-sol,openai:gpt-6-luna,anthropic:claude-opus-5-5

It signs in as an account you name (`--login`, the password is asked for and
never echoed) — an administrator sees the SAP candidates; an account without
`sap_mirror:read` sees only their count. `--models` with more than one model
needs `settings:write` (it changes the tenant's model for the run). Every
photo is one identification against the tenant's daily cap — so N photos
across M models is N × M — and is held 24 hours for an asset that is never
saved (the cron then deletes it). Nothing is written on any asset.

THE COST is the provider's own token counts (the `usage` on each answer)
times `PRICES_PER_MTOK` below — this script's table, so the comparison does
not depend on which models the server has a price for. A model with no
price prints "price not set" rather than a number made up.

Paste the TABLES into the handoff's report as the addendum.

Photos over 300 KB are made smaller first, the way the web app does — with
Pillow if it is installed, otherwise with macOS's `sips`.
"""
import argparse
import getpass
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import requests

MAX_BYTES = 300 * 1024
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

#: USD per million tokens: (input, output, cache read). A cache WRITE
#: (five-minute) is billed at 1.25 × input. OWNER: confirm these against
#: Anthropic's pricing page (https://www.anthropic.com/pricing) before you
#: quote a number from this script — they are the figures published as of
#: 2026-10-06, the same ones `ai_provider.PRICES_PER_MTOK` records cost with.
#: `None` means "not known": the table then says "price not set" for that
#: model (or that kind of token) instead of inventing one. Claude Haiku 5.5's
#: input/output prices hold for prompts up to 100K tokens, which a photo and
#: the class list are far below; its cache-read price was not published
#: with them, so it is None here.
#: OpenAI's (handoff 68) — OWNER: confirm these against OpenAI's pricing
#: page (https://developers.openai.com/api/docs/pricing) too. Read from its
#: model pages on 2026-10-20, standard tier, prompts under 272K tokens. Its
#: cache writes are also 1.25 × input, and OpenAI's `input_tokens` includes
#: cached tokens — Cadra's server records the uncached part apart, as it
#: does for Anthropic, so the same arithmetic serves both. GPT-6 Luna's
#: cache-write price was not published beside the others; the 1.25 × rule
#: is assumed for it.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, None),
    "gpt-6-astra": (10.00, 50.00, 1.00),
    "gpt-6.1-sol": (2.00, 10.00, 0.10),
    "gpt-6-sol": (2.00, 10.00, 0.20),
    "gpt-6-luna": (0.10, 0.50, 0.01),
}


def price_of(model: str):
    """The table's row for `model`, or for the model a dated snapshot id
    belongs to (OpenAI answers `gpt-6.1-sol-2026-09-29`)."""
    model = model or ""
    if model in PRICES_PER_MTOK:
        return PRICES_PER_MTOK[model]
    snap = re.match(r"^(.+?)-\d{4}-\d{2}-\d{2}$", model)
    return PRICES_PER_MTOK.get(snap.group(1)) if snap else None


def parse_models(arg: str, providers=("anthropic", "openai")):
    """`--models` as `[(provider or None, model)]`. `provider:model` names
    the provider; a bare model id is asked of the tenant's own."""
    out = []
    for entry in (arg or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        provider, sep, model = entry.partition(":")
        if not sep:
            provider, model = None, entry
        provider = provider and provider.strip().lower()
        model = model.strip()
        if provider is not None and provider not in providers:
            sys.exit(f"--models: '{entry}' names provider '{provider}'; "
                     f"one of: {', '.join(providers)}.")
        if not model:
            sys.exit(f"--models: '{entry}' names no model.")
        out.append((provider, model))
    if len(set(out)) != len(out):
        sys.exit("--models names a model twice.")
    return out


def shrink(path: pathlib.Path) -> tuple[bytes, str]:
    """The photo as a JPEG under 300 KB, and the name to send it under."""
    data = path.read_bytes()
    name = path.stem + ".jpg"
    if len(data) <= MAX_BYTES and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
        return data, path.name
    try:
        from PIL import Image, ImageOps
        import io
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        side = 1600
        while side >= 320:
            copy = img.copy()
            copy.thumbnail((side, side))
            for q in (86, 76, 66, 56):
                out = io.BytesIO()
                copy.save(out, "JPEG", quality=q)
                if out.tell() <= MAX_BYTES:
                    return out.getvalue(), name
            side = int(side * 0.75)
    except ImportError:
        if not shutil.which("sips"):
            sys.exit("A photo is over 300 KB and neither Pillow nor macOS sips "
                     "is available to make it smaller.")
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / name
            for side, q in ((1600, 70), (1280, 60), (1024, 55), (800, 50)):
                subprocess.run(["sips", "-Z", str(side), "-s", "format", "jpeg",
                                "-s", "formatOptions", str(q), str(path),
                                "--out", str(out)], check=True,
                               capture_output=True)
                if out.stat().st_size <= MAX_BYTES:
                    return out.read_bytes(), name
    sys.exit(f"{path.name} could not be made smaller than 300 KB.")


def true_kind(path: pathlib.Path, labels: dict) -> str:
    """The TRUE kind from the file name: the words before the first digit,
    shortened to the longest run `labels.json` names — so
    `printer-firs-01.jpg` is `printer` when the labels say what a printer
    is. With no labels, the first word."""
    m = re.match(r"([a-z][a-z-]*?)-?\d", path.stem.lower())
    words = (m.group(1) if m else path.stem.lower()).strip("-").split("-")
    for n in range(len(words), 0, -1):
        if "-".join(words[:n]) in labels:
            return "-".join(words[:n])
    return words[0]


def is_right(kind: str, category_name: str | None, labels: dict) -> bool:
    if not category_name:
        return False
    want = labels.get(kind)
    if want is not None:
        return category_name.strip().casefold() == str(want).strip().casefold()
    return kind.replace("-", " ").casefold() in category_name.casefold()


def cost_usd(model: str, usage: dict):
    """USD for one answer at `PRICES_PER_MTOK`, or None when a price this
    answer needs is not set (a model not in the table, or a kind of token
    whose price is None)."""
    price = price_of(model)
    if not price:
        return None
    p_in, p_out, p_read = price
    n_in = usage.get("input_tokens") or 0
    n_out = usage.get("output_tokens") or 0
    n_read = usage.get("cache_read_tokens") or 0
    n_write = usage.get("cache_write_tokens") or 0
    if p_in is None and (n_in or n_write) or p_out is None and n_out \
            or p_read is None and n_read:
        return None
    return ((n_in * (p_in or 0)) + (n_out * (p_out or 0))
            + (n_read * (p_read or 0)) + (n_write * (p_in or 0) * 1.25)
            ) / 1_000_000


def run_folder(base, auth, photos, labels, out, model, provider=None):
    """Every photo through the route once, on whatever model the tenant is
    set to now. One row per photo."""
    rows = []
    for path in photos:
        kind = true_kind(path, labels)
        data, name = shrink(path)
        started = time.monotonic()
        r = requests.post(f"{base}/api/v1/ai/identify", headers=auth,
                          files={"file": (name, data, "image/jpeg")},
                          data={"source": "web"}, timeout=90)
        seconds = time.monotonic() - started
        body = r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {}
        if r.status_code != 201:
            msg = (body.get("error") or {}).get("message") or r.text[:120]
            print(f"{path.name:<28} {kind:<18} REFUSED {r.status_code}: {msg}")
            rows.append({"file": path.name, "ok": False, "seconds": seconds})
            continue
        sg = body["data"]
        if out:
            out.write(json.dumps({"file": path.name, "true": kind,
                                  "provider": provider, "model": model,
                                  "answer": sg}) + "\n")
        top = sg["category"]
        names = [top["name"]] + [a["name"] for a in top["alternatives"]]
        first = is_right(kind, top["name"], labels)
        top3 = any(is_right(kind, n, labels) for n in names)
        reads = "; ".join(f"{t['text']} ({t['looks_like']})"
                          for t in sg["text_read"]) or "—"
        sap = sg["sap_candidates"]
        sap_line = (sap["items"][0]["reason"] if sap.get("items")
                    else (sap.get("note") or "—"))
        usage = sg.get("usage") or {}
        # Priced by the model that ANSWERED (the server's fallback on a
        # decline can be another), at this script's table.
        answered = sg.get("model") or model
        cost = cost_usd(answered, usage)
        print(f"{path.name:<28} true {kind:<16} → {top['name']} "
              f"({top['confidence']:.0%}) {'✓' if first else ('~' if top3 else '✗')}")
        print(f"{'':<28} read: {reads}")
        print(f"{'':<28} SAP: {sap_line}")
        print(f"{'':<28} {seconds:.1f} s, "
              f"{'$%.4f' % cost if cost is not None else 'price not set'}, "
              f"{usage.get('input_tokens')} in / "
              f"{usage.get('output_tokens')} out tokens"
              f"{'' if answered == model else f' (answered by {answered})'}\n")
        rows.append({"file": path.name, "ok": True, "first": first,
                     "top3": top3, "seconds": seconds, "cost": cost,
                     "server_ms": sg.get("latency_ms")})
    return rows


def table(model, rows, labels, provider=None):
    """One model's totals, in the shape the owner pastes into the report."""
    done = [x for x in rows if x["ok"]]
    n = len(done)
    lines = [f"MODEL {provider + ':' if provider else ''}{model}",
             f"  photos sent              {len(rows)}  (identified {n}, "
             f"refused {len(rows) - n})"]
    if n:
        secs = [x["seconds"] for x in done]
        server = [(x["server_ms"] or 0) / 1000 for x in done]
        costs = [x["cost"] for x in done if x["cost"] is not None]
        lines += [
            f"  class right first time   {sum(x['first'] for x in done)} of {n}",
            f"  class right in top three {sum(x['top3'] for x in done)} of {n}",
            f"  seconds per photo        mean {statistics.mean(secs):.1f}, "
            f"median {statistics.median(secs):.1f}  (the server's provider "
            f"call: mean {statistics.mean(server):.1f}, median "
            f"{statistics.median(server):.1f})",
        ]
        if len(costs) == n:
            lines.append(f"  cost per photo           ${sum(costs) / n:.4f}"
                         f"  (total ${sum(costs):.4f} over {n})")
        elif costs:
            lines.append(f"  cost per photo           ${sum(costs) / len(costs):.4f}"
                         f" over the {len(costs)} of {n} priced — price not "
                         f"set for the rest")
        else:
            lines.append("  cost per photo           price not set "
                         "(PRICES_PER_MTOK)")
    lines.append(f"  labels                   "
                 f"{'labels.json' if labels else 'none (class name contains the kind)'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True,
                    help="the tenant, e.g. http://test19.localhost:8069")
    ap.add_argument("--folder", required=True, type=pathlib.Path)
    ap.add_argument("--login", help="the account to sign in as")
    ap.add_argument("--models",
                    help="comma-separated model ids, or provider:model pairs, "
                         "to compare on the same folder, e.g. "
                         "openai:gpt-6.1-sol,anthropic:claude-opus-5-5 "
                         "(default: the tenant's provider and model)")
    ap.add_argument("--out", type=pathlib.Path,
                    help="also write every answer as JSON lines here")
    args = ap.parse_args()

    wanted = parse_models(args.models)
    folder = args.folder.expanduser()
    photos = sorted(p for p in folder.iterdir()
                    if p.suffix.lower() in IMAGE_SUFFIXES)
    if not photos:
        sys.exit(f"No photos in {folder}.")
    labels_file = folder / "labels.json"
    labels = json.loads(labels_file.read_text()) if labels_file.exists() else {}
    if not labels:
        print("No labels.json: a kind counts as right when the class's name "
              "contains it.\n")

    base = args.base.rstrip("/")
    login = args.login or input("Sign in as (login): ").strip()
    password = os.environ.get("CADRA_PASSWORD") or getpass.getpass(
        f"Password for {login} (hidden): ")
    r = requests.post(f"{base}/api/v1/auth/login",
                      json={"login": login, "password": password}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Sign-in refused: HTTP {r.status_code} {r.text[:200]}")
    token = r.json()["data"]["access_token"]
    auth = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    settings_url = f"{base}/api/v1/settings/ai-identify"

    s = requests.get(settings_url, headers=auth, timeout=30)
    if s.status_code != 200:
        sys.exit(f"Could not read the tenant's settings: HTTP {s.status_code} "
                 f"{s.text[:200]}")
    st = s.json()["data"]
    tenant_model = st["model"]
    tenant_provider = st["provider"]
    # Every entry resolved to (provider, model): a bare model is the
    # tenant's provider's.
    runs = [(p or tenant_provider, m) for p, m in wanted] or [
        (tenant_provider, tenant_model)]
    keys = st.get("keys") or {}
    print(f"Tenant: {base}  provider {tenant_provider}  model {tenant_model}"
          f"  effort {st['effort']}  today {st['today']['calls']} of "
          f"{st['daily_cap']} used  server keys: "
          + (", ".join(f"{p} {'present' if k.get('placed') else 'ABSENT'}"
                       for p, k in keys.items())
             or ('present' if st.get('key_placed') else 'ABSENT')) + "\n")
    if any(p == "fake" for p, _m in runs):
        print("WARNING: a run is on the test stand-in, not a real "
              "provider — its numbers mean nothing.\n")
    for p in sorted({p for p, _m in runs if p in keys}):
        if not keys[p].get("placed"):
            print(f"WARNING: the server holds no {p} key "
                  f"({keys[p].get('variable')}); its photos will be "
                  "refused (the switch to it is refused first).\n")
    models = [m for _p, m in runs]
    needed = len(photos) * len(runs)
    if st["today"]["remaining"] < needed:
        print(f"WARNING: {len(photos)} photos × {len(models)} model(s) = "
              f"{needed} identifications and only "
              f"{st['today']['remaining']} left today.\n")
    unpriced = [m for m in models if not price_of(m)]
    if unpriced:
        print(f"Note: price not set for {', '.join(unpriced)} — its cost "
              "will say so.\n")

    out = args.out.open("w") if args.out else None
    tables = []
    touched = set()     # the providers this run set a model on
    try:
        for provider, model in runs:
            if (provider, model) != (tenant_provider, tenant_model) \
                    or len(runs) > 1:
                body = {"model": model}
                if provider != tenant_provider or len(
                        {p for p, _m in runs}) > 1:
                    body["provider"] = provider
                p = requests.patch(settings_url, headers=auth,
                                   json=body, timeout=30)
                if p.status_code != 200:
                    msg = ((p.json().get("error") or {}).get("message")
                           if p.headers.get("content-type", "").startswith(
                               "application/json") else p.text[:200])
                    sys.exit(f"Could not set the tenant to {provider}:"
                             f"{model}: HTTP {p.status_code} {msg} (choosing "
                             "a model needs settings:write).")
            print("=" * 72)
            print(f"{provider}:{model}\n")
            touched.add(provider)
            rows = run_folder(base, auth, photos, labels, out, model,
                              provider=provider)
            tables.append(table(model, rows, labels, provider=provider))
    finally:
        if out:
            out.close()
        # Put the tenant's model back, whatever happened above.
        if runs != [(tenant_provider, tenant_model)]:
            # Every provider's model the run touched, then the provider: each
            # provider keeps its own model (handoff 68), so each is put back
            # under its own provider before the tenant's is restored.
            failed = []
            for prov in sorted(touched):
                was = next((o.get("model") for o in st.get(
                    "provider_options") or () if o.get("value") == prov),
                    tenant_model if prov == tenant_provider else None)
                if was:
                    r = requests.patch(settings_url, headers=auth, json={
                        "provider": prov, "model": was}, timeout=30)
                    if r.status_code != 200:
                        failed.append(f"{prov}:{was}")
            back = requests.patch(settings_url, headers=auth, json={
                "provider": tenant_provider, "model": tenant_model},
                timeout=30)
            if back.status_code != 200:
                failed.append(f"{tenant_provider}:{tenant_model}")
            print(f"\nThe tenant is back to {tenant_provider}:{tenant_model}"
                  if not failed else
                  f"\nWARNING: could not put back {', '.join(failed)} — set "
                  "them in Settings → Identify from photo.")

    print("=" * 72)
    print("TABLES (paste into the handoff's report, addendum)\n")
    print("\n\n".join(tables))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The live check of *Identify from photo* — handoff 64 §5.5. THE OWNER RUNS IT.

It sends the owner's own photos, one at a time, to a tenant's
`POST /api/v1/ai/identify` — the same route the web app calls — and prints,
for each, the suggested class against the true one, the text read, the top
SAP candidate's reason, the time and the cost. Then the totals: right first
time, right in the top three, average seconds, cost per photo.

BEFORE YOU RUN IT
-----------------
1. Place the provider key on the tenant (the key never goes in this script):
       scripts/set_ai_key.sh test19        # local; prompts, nothing echoed
   On staging: the `CADRA_AI_API_KEY` key of the `cadra-odoo` secret, then
   the bootstrap job (docs/DEPLOYMENT.md).
2. Switch it on, on THAT tenant only: Settings → Identify from photo → on,
   provider `anthropic`. (Photos leave our servers: R7 / R11.)
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
        --base http://test19.localhost:8069 --folder ~/Desktop/office-photos

It signs in as an account you name (`--login`, the password is asked for and
never echoed) — an administrator sees the SAP candidates; an account without
`sap_mirror:read` sees only their count. Every photo is one identification
against the tenant's daily cap, and is held 24 hours for an asset that is
never saved (the cron then deletes it). Nothing is written on any asset.

Paste the TOTALS block into docs/handoffs/64-REPORT.md as the addendum.

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
import subprocess
import sys
import tempfile
import time

import requests

MAX_BYTES = 300 * 1024
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True,
                    help="the tenant, e.g. http://test19.localhost:8069")
    ap.add_argument("--folder", required=True, type=pathlib.Path)
    ap.add_argument("--login", help="the account to sign in as")
    ap.add_argument("--out", type=pathlib.Path,
                    help="also write every answer as JSON lines here")
    args = ap.parse_args()

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

    s = requests.get(f"{base}/api/v1/settings/ai-identify", headers=auth,
                     timeout=30)
    if s.status_code == 200:
        st = s.json()["data"]
        print(f"Tenant: {base}  provider {st['provider']}  model {st['model']}"
              f"  effort {st['effort']}  today {st['today']['calls']} of "
              f"{st['daily_cap']} used\n")
        if st["provider"] != "anthropic":
            print("WARNING: this tenant is on the test stand-in, not the real "
                  "provider — the numbers below mean nothing.\n")
        if st["today"]["remaining"] < len(photos):
            print(f"WARNING: {len(photos)} photos and only "
                  f"{st['today']['remaining']} identifications left today.\n")

    out = args.out.open("w") if args.out else None
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
        cost = (sg.get("usage") or {}).get("cost_usd")
        print(f"{path.name:<28} true {kind:<16} → {top['name']} "
              f"({top['confidence']:.0%}) {'✓' if first else ('~' if top3 else '✗')}")
        print(f"{'':<28} read: {reads}")
        print(f"{'':<28} SAP: {sap_line}")
        print(f"{'':<28} {seconds:.1f} s, "
              f"{'$%.4f' % cost if cost is not None else 'cost unknown'}, "
              f"{sg['usage']['input_tokens']} in / "
              f"{sg['usage']['output_tokens']} out tokens\n")
        rows.append({"file": path.name, "ok": True, "first": first,
                     "top3": top3, "seconds": seconds, "cost": cost,
                     "server_ms": sg.get("latency_ms")})
    if out:
        out.close()

    done = [x for x in rows if x["ok"]]
    n = len(done)
    print("=" * 72)
    print("TOTALS (paste into docs/handoffs/64-REPORT.md, addendum)")
    print(f"  photos sent              {len(rows)}  (identified {n}, refused "
          f"{len(rows) - n})")
    if n:
        costs = [x["cost"] for x in done if x["cost"] is not None]
        print(f"  class right first time   {sum(x['first'] for x in done)} of {n}")
        print(f"  class right in top three {sum(x['top3'] for x in done)} of {n}")
        print(f"  average seconds          {sum(x['seconds'] for x in done) / n:.1f}"
              f" (server's provider call "
              f"{sum((x['server_ms'] or 0) for x in done) / n / 1000:.1f})")
        if costs:
            print(f"  cost per photo           ${sum(costs) / len(costs):.4f}"
                  f"  (total ${sum(costs):.4f} over {len(costs)})")
    print(f"  labels                   "
          f"{'labels.json' if labels else 'none (class name contains the kind)'}")


if __name__ == "__main__":
    main()

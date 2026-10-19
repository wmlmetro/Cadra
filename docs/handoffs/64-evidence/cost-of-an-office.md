# What it would cost to identify a whole office (handoff 64 §6)

An ESTIMATE from published prices and the published token rules, until the
owner's live check (§5.5) measures the real thing. Model: the configured
default, `claude-opus-5-5` — $4.00 / MTok input, $20.00 / MTok output,
$0.20 / MTok cache read, $5.00 / MTok cache write (prices as cached
2026-10-06).

## One photo

| Part | Tokens | How |
|---|---|---|
| The image | 2,560 | the web app redraws to at most 1,600 px on the long side; a phone's 4:3 → 1,600 × 1,200 px ÷ 750 |
| The system prompt, today on `nrs19` | ~710 | 2,834 characters ÷ 4 (22 classes; 1 carries a SAP class, and that class has no SAP descriptions — GO-LIVE §33.4) |
| The system prompt, once classes are mapped | ~2,200 | + about ten SAP classes × twenty descriptions; the same on every call, so cached |
| Schema + instruction | ~420 | 1,624 + ~60 characters ÷ 4 |
| Output | ~600 | ~250 for the JSON answer, the rest thinking at effort `low` (assumed) |

- **Today's prompt (not cached):** 3,690 in × $4 + 600 out × $20 = **$0.027**.
- **Mapped prompt, system cached:** 2,980 in × $4 + 2,200 cache-read × $0.20 + 600 out × $20 = **$0.024**.
- Call it **2½ US cents a photo**, about half of it the answer (output).

## The register, and an HQ audit

NRS's numbers: 161,647 active SAP assets, 80,370 of them furniture
(classes `2xxx`). HQ, read off `nrs19`'s mirror: **57,059 of 161,647
active records (35.3 %) carry an old tag with an HQ office code** — 74
codes beginning `HQ` (largest HQFM 8,046, HQHC 6,061, HQIA 3,698), every one
read from the tag; 37,831 records have no office at all, so the share of
records whose office is KNOWN is 57,059 of 123,816 (46.1 %).

| | Photos | At $0.024 | At $0.027 |
|---|---|---|---|
| One photo per asset, whole register | 161,647 | **$3,880** | $4,360 |
| Furniture only | 80,370 | $1,930 | $2,170 |
| One Lot 4 audit of HQ (HQ-coded records) | 57,059 | **$1,370** | $1,540 |

## What reduces it

1. **Identify only when the person asks** — which is how it is built: a
   button, never automatic. In a Lot 4 audit most items carry an old FIRS
   tag the matcher reads directly (typed or scanned), and need no photo
   read at all. If one item in three needs identifying, HQ is **~$460**.
2. **Smaller images.** At 1,024 px on the long side the image is 1,049
   tokens, not 2,560: **~$0.018 a photo (−25 %)**, HQ ~$1,030. At 768 px,
   590 tokens: ~$0.016. Whether a serial plate is still legible at that
   size is for the live check to say — it is the one thing a smaller image
   could cost.
3. **Effort stays `low`.** Output is half the bill; more thinking is more
   output.
4. **Photos identified at sync, not while somebody waits** (the offline
   phone) can go through the Batch API at half price — not built.
5. **The model is the owner's choice, not this report's.** For scale only:
   Sonnet 5.5 ($2 / $10) would halve the figures; Haiku 5.5 ($0.10 /
   $0.50) would be about 40 times cheaper. Neither has been measured on
   these photos; the live check is how to decide.

The daily cap (default 500 a tenant) bounds a day at about **$12** at
$0.024 a photo.

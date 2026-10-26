/**
 * Asset label composition + printing, client-side.
 *
 * Why not just open Odoo's PDF report? `/report/pdf/...` is a session-auth
 * route and the SPA authenticates with a JWT bearer token only — it has no
 * Odoo session cookie, so that URL redirects to the login page. (The
 * `/api/v1/barcode/print-url` endpoint hands back exactly that URL, which is
 * why nothing in the SPA has ever been able to use it.)
 *
 * So we compose the label here and let the browser's print dialog drive the
 * label printer. Layouts mirror the QWeb templates in
 * myservice_asset_register/views/asset_tag_report.xml so a label printed from
 * the SPA matches one printed from the Odoo backend.
 */

import { code128Svg, code128Modules } from "./code128";
import { getBrand, brandLogoSrc } from "./brand";
import { API_BASE } from "./api";

export type LabelSize = "small" | "2x1" | "standard" | "large" | "sheet";

export interface LabelData {
  /** The `nrs.asset.tag.label` id, when the caller has one — not printed;
   *  it is what the station sends to `POST /api/v1/tags/printed` so the
   *  print is recorded (handoff 61). */
  tag_id?: number | null;
  tag_number: string;
  asset_name?: string;
  asset_code?: string;
  location?: string;
  category?: string;
  custodian?: string;
  serial_number?: string;
  floor_room?: string;
}

/**
 * Floor and room read back off a tag code.
 *
 * Tags are generated as BUILDING-FLOOR-ROOM-CATEGORY-NNN (see _tag_prefix in
 * myservice_asset_register/models/asset_tag.py), so the two middle segments
 * are the floor and room codes the label prints bottom-left. Saves a round
 * trip — the barcode endpoints don't return floor_room, and the code the
 * client already holds carries it.
 *
 * Deliberately strict: only codes with that exact shape and a numeric tail
 * qualify. Legacy or imported tags return "" and the line is left off rather
 * than printing two arbitrary segments as if they were a location.
 */
export function floorRoomFromTag(tag: string): string {
  const parts = (tag || "").trim().split("-");
  if (parts.length !== 5) return "";
  const [building, floor, room, category, seq] = parts;
  if (!building || !floor || !room || !category) return "";
  if (!/^\d+$/.test(seq)) return "";
  return `${floor} - ${room}`;
}

export const LABEL_SIZES: Array<{ value: LabelSize; label: string; hint: string }> = [
  { value: "small",    label: "Small",    hint: "50 × 25 mm — code + barcode" },
  { value: "2x1",      label: "2 × 1 in", hint: "50.8 × 25.4 mm — 2″ × 1″ roll (Zebra ZT231)" },
  { value: "standard", label: "Standard", hint: "50 × 30 mm — the default asset tag" },
  { value: "large",    label: "Large",    hint: "100 × 60 mm — full detail" },
  { value: "sheet",    label: "A4 sheet", hint: "8 per page, plain paper — cut out" },
];

/** Page box per size, in mm. `sheet` prints on plain A4. */
const PAGE: Record<LabelSize, { css: string }> = {
  small:    { css: "@page { size: 50mm 25mm; margin: 0; }" },
  "2x1":    { css: "@page { size: 50.8mm 25.4mm; margin: 0; }" },
  standard: { css: "@page { size: 50mm 30mm; margin: 0; }" },
  large:    { css: "@page { size: 100mm 60mm; margin: 0; }" },
  sheet:    { css: "@page { size: A4; margin: 6mm; }" },
};

function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Resolve a possibly-relative URL against the current document. */
function absolute(url: string): string {
  try {
    return new URL(url, window.location.href).href;
  } catch {
    return url;
  }
}

/**
 * QR image URL. Odoo's `/report/barcode` controller is `auth="public"`, so this
 * needs no token — but it is the one part of the label that depends on the
 * server being reachable. Every QR <img> gets an error handler that hides it,
 * so a label still prints (with its Code128) if the route is unavailable.
 */
function qrUrl(value: string, px: number): string {
  const base = API_BASE || "";
  return absolute(
    `${base}/report/barcode?barcode_type=QR&value=${encodeURIComponent(value)}` +
    `&width=${px}&height=${px}`,
  );
}

/** Code128 as a data URI so it drops straight into an <img>. */
function code128Img(value: string, className: string, style = ""): string {
  const svg = code128Svg(value);
  if (!svg) {
    // Unencodable code — print it big as text rather than emit a blank space.
    return `<div class="${className} bc-fallback">${esc(value)}</div>`;
  }
  const src = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  return `<img class="${className}" src="${src}" alt="${esc(value)}"${style ? ` style="${style}"` : ""}/>`;
}

/**
 * One layout at every size:
 *
 *   ┌───────────────────────────────────────┐
 *   │ ▓▓▓▓▓▓▓   Apple M4                    │
 *   │ ▓▓ QR ▓   (GWSRW0S14)                 │
 *   │ ▓▓▓▓▓▓▓   NRS-AST-011933              │
 *   │ ‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖ │
 *   │      [logo] Nigeria Revenue Service   │
 *   └───────────────────────────────────────┘
 *
 * The QR on the left with the name, the serial in brackets (left off when the
 * asset has none — a `tag_id` or `record_only` class) and the tag number
 * beside it; the Code 128 on its own row across the label; the tenant's logo
 * and name in a footer. The barcode's width is the point: beside the QR on
 * 50 mm stock a module printed at ~0.14 mm, below what a phone camera reads.
 * Across the label it is sized by `barcodeWidthMm`. Sizes differ only in the
 * root font-size and the barcode/QR boxes — everything else is in `em`.
 */
/** One dot of a 203 dpi label printer (the Zebra ZT231's standard head),
 *  in mm. */
const DOT_MM = 25.4 / 203;

/** Width the barcode may take at each size: the label less its side
 *  padding (`.lbl` padding-inline, .5em of the root font-size). */
const BARCODE_ROOM_MM: Record<Exclude<LabelSize, "sheet">, number> = {
  small: 50 - 2 * 0.5 * 6 * 0.3528,
  "2x1": 50.8 - 2 * 0.5 * 6 * 0.3528,
  standard: 50 - 2 * 0.5 * 7 * 0.3528,
  large: 100 - 2 * 0.5 * 13 * 0.3528,
};

/**
 * The barcode's printed width, in mm, or null to stretch it across the room.
 *
 * A thermal head prints whole dots, so a module of 1.8 dots comes out as a
 * mix of one-dot and two-dot bars and the decoder reads widths that are wrong
 * by up to half a module. When the symbol fits at a whole number of dots per
 * module — at least two, 0.25 mm, which a phone reads — it is printed at
 * exactly that, the most dots that fit, and centred. `NRS-AST-011933` (187
 * modules) fits at two dots on every 50 mm size. A tag too long for that
 * (`HQ-GF-MR-FF-001`, 220 modules) is stretched across the room as before.
 * On a 300 dpi head the same widths are within a few percent of whole dots.
 */
function barcodeWidthMm(tag: string, size: Exclude<LabelSize, "sheet">): number | null {
  const modules = code128Modules(tag);
  if (!modules) return null;
  const dots = Math.floor(BARCODE_ROOM_MM[size] / (modules * DOT_MM));
  return dots >= 2 ? modules * dots * DOT_MM : null;
}

/** How many characters of the tag fit the text column at full size. A longer
 *  tag is shrunk to fit, never clipped or wrapped: the printed number must
 *  agree with the bars under it. Kept in step with `tagmax` in
 *  asset_tag_report.xml. */
const TAG_MAX: Record<Exclude<LabelSize, "sheet">, number> = {
  small: 23, "2x1": 23, standard: 19, large: 21,
};

function labelMarkup(d: LabelData, size: Exclude<LabelSize, "sheet">, footer: string): string {
  // Trim once so the printed text and the encoded barcode can't disagree —
  // code128Svg trims internally.
  const tag = (d.tag_number || "").trim();
  const serial = (d.serial_number || "").trim();
  const qrPx = size === "large" ? 360 : 200;
  const tagScale = tag.length > TAG_MAX[size] ? TAG_MAX[size] / tag.length : 1;
  const bcMm = barcodeWidthMm(tag, size);
  const bcStyle = bcMm ? `width:${bcMm.toFixed(3)}mm` : "";

  return `
    <div class="lbl lbl-${size}">
      <div class="top">
        <div class="col-qr">
          <img class="qr" data-qr="1" src="${qrUrl(tag, qrPx)}" alt=""/>
        </div>
        <div class="col-txt">
          <div class="asset-name">${esc((d.asset_name || "").slice(0, 40))}</div>
          ${serial ? `<div class="serial">(${esc(serial)})</div>` : ""}
          <div class="tag-code" style="font-size:${(1.1 * tagScale).toFixed(3)}em">${esc(tag)}</div>
        </div>
      </div>
      ${code128Img(tag, "bc", bcStyle)}
      ${footer}
    </div>`;
}

/** The tenant's logo and name, the same on every label of a print run. A
 *  thermal head prints the logo in black dots, so a colour logo comes out
 *  dithered; a logo that fails to load is hidden and the name stays. */
function footerMarkup(): string {
  const brand = getBrand();
  const name = brand.name || brand.short_name;
  const logo = absolute(brandLogoSrc());
  if (!name && !logo) return "";
  return `<div class="foot">${logo ? `<img class="foot-logo" data-logo="1" src="${esc(logo)}" alt=""/>` : ""}` +
    `${name ? `<span class="foot-name">${esc(name)}</span>` : ""}</div>`;
}

const STYLES = `
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; }
  body { font-family: Arial, Helvetica, sans-serif; color: #000; -webkit-print-color-adjust: exact; print-color-adjust: exact; }

  /* One label per page, edge to edge — roll/label stock. */
  .page { page-break-after: always; break-after: page; overflow: hidden; }
  .page:last-child { page-break-after: auto; break-after: auto; }

  /* Everything scales off .lbl's font-size. */
  .lbl { display: flex; flex-direction: column; justify-content: center; padding: .4em .5em;
         overflow: hidden; background: #fff; line-height: 1.2; }
  .top { display: flex; align-items: center; gap: .9em; }
  .col-qr { flex: 0 0 auto; }
  .qr { display: block; }
  .col-txt { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  .asset-name { font-size: 1em;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .serial { font-size: .8em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag-code { letter-spacing: .3px; white-space: nowrap; margin-top: .1em; }
  /* Stretched across the label unless barcodeWidthMm gives it an exact
     width, then centred. */
  .bc { display: block; width: 100%; flex: 0 0 auto; margin: .5em auto 0; }
  .foot { flex: 0 0 auto; height: 1.25em; margin-top: .35em; display: flex; align-items: center;
          justify-content: center; gap: .4em; overflow: hidden; }
  .foot-logo { height: 100%; width: auto; max-width: 30%; object-fit: contain; }
  .foot-name { font-size: .75em; font-weight: 700; white-space: nowrap; overflow: hidden;
               text-overflow: ellipsis; min-width: 0; }
  .bc-fallback { font-family: "Courier New", monospace; font-weight: 700; letter-spacing: 1px; }

  /* Per-size scale. Only the type scale and the barcode/QR boxes change. */
  .lbl-small    { width: 50mm;  height: 25mm; font-size: 6pt; }
  .lbl-small    .qr { width: 11mm; height: 11mm; }
  .lbl-small    .bc { height: 7mm; }

  /* 2" x 1" roll — the ZT231's stock. The small label's metrics; the extra
     .8 x .4 mm is slack, not scale. */
  .lbl-2x1      { width: 50.8mm; height: 25.4mm; font-size: 6pt; }
  .lbl-2x1      .qr { width: 11mm; height: 11mm; }
  .lbl-2x1      .bc { height: 7mm; }

  .lbl-standard { width: 50mm;  height: 30mm; font-size: 7pt; }
  .lbl-standard .qr { width: 13mm; height: 13mm; }
  .lbl-standard .bc { height: 9mm; }

  .lbl-large    { width: 100mm; height: 60mm; font-size: 13pt; }
  .lbl-large    .qr { width: 26mm; height: 26mm; }
  .lbl-large    .bc { height: 18mm; }

  /* A4 sheet — 2 x 4 grid with a dashed cut border. Inside a 6mm page margin
     that leaves 198 x 285mm, so 97 x 68mm cells: near enough the large label's
     own 100 x 60mm that it needs no reflow. */
  .sheet { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 68mm; gap: 4mm; }
  .sheet .cell { border: .3mm dashed #c8c8c8; display: flex; align-items: stretch; overflow: hidden; }
  .sheet .lbl-large { width: 100%; height: 100%; }
`;

function buildDocument(labels: LabelData[], size: LabelSize): string {
  const footer = footerMarkup();
  let content: string;
  if (size === "sheet") {
    // 8 per page — a page break every 8 cells keeps the grid aligned.
    const pages: string[] = [];
    for (let i = 0; i < labels.length; i += 8) {
      const cells = labels
        .slice(i, i + 8)
        .map((d) => `<div class="cell">${labelMarkup(d, "large", footer)}</div>`)
        .join("");
      pages.push(`<div class="page"><div class="sheet">${cells}</div></div>`);
    }
    content = pages.join("");
  } else {
    content = labels
      .map((d) => `<div class="page">${labelMarkup(d, size, footer)}</div>`)
      .join("");
  }

  return `<!doctype html><html><head><meta charset="utf-8">
<title>Labels</title>
<style>${PAGE[size].css}${STYLES}</style>
</head><body>${content}</body></html>`;
}

/** Resolve once every <img> has loaded or failed — never hang the print. */
function waitForImages(doc: Document, timeoutMs: number): Promise<void> {
  const imgs = Array.from(doc.images);
  const pending = imgs.filter((img) => !img.complete);
  if (!pending.length) return Promise.resolve();

  return new Promise((resolve) => {
    let left = pending.length;
    const done = () => { if (--left <= 0) resolve(); };
    for (const img of pending) {
      img.addEventListener("load", done, { once: true });
      img.addEventListener("error", done, { once: true });
    }
    setTimeout(resolve, timeoutMs);
  });
}

export interface PrintResult {
  /** True when at least one QR failed to load — the Code128 still printed. */
  qrUnavailable: boolean;
}

/**
 * Open the browser print dialog for `labels`. Renders into an offscreen
 * same-origin iframe rather than a popup so it can't be blocked, and cleans
 * the iframe up once printing finishes.
 */
export async function printLabels(labels: LabelData[], size: LabelSize): Promise<PrintResult> {
  if (!labels.length) return { qrUnavailable: false };

  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  // Offscreen rather than display:none — a zero-size frame won't lay out, and
  // some browsers refuse to print a frame that was never laid out.
  iframe.style.cssText =
    "position:fixed;left:-10000px;top:0;width:250mm;height:300mm;border:0;visibility:hidden;";
  document.body.appendChild(iframe);

  const cleanup = () => {
    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
  };

  try {
    const html = buildDocument(labels, size);

    await new Promise<void>((resolve) => {
      iframe.addEventListener("load", () => resolve(), { once: true });
      iframe.srcdoc = html;
      // srcdoc is same-origin, so a missed load event would strand us —
      // resolve anyway after a moment and let the image wait catch up.
      setTimeout(resolve, 3000);
    });

    const doc = iframe.contentDocument;
    if (!doc) throw new Error("Could not open the print view.");

    // Hide any server-fetched image that fails to load, so a broken-image glyph
    // never prints. Set from here (not an inline onerror) to stay CSP-safe.
    let qrFailed = false;
    for (const img of Array.from(doc.querySelectorAll<HTMLImageElement>("img[data-qr], img[data-logo]"))) {
      const isQr = img.hasAttribute("data-qr");
      const markFailed = () => {
        if (isQr) qrFailed = true;
        img.style.visibility = "hidden";
      };
      if (img.complete && img.naturalWidth === 0) markFailed();
      else img.addEventListener("error", markFailed, { once: true });
    }

    await waitForImages(doc, 5000);

    const win = iframe.contentWindow;
    if (!win) throw new Error("Could not open the print view.");
    win.focus();
    win.print();

    // Print is synchronous in most browsers but not all; give the dialog a
    // moment to take its snapshot before the iframe goes away.
    setTimeout(cleanup, 1000);
    return { qrUnavailable: qrFailed };
  } catch (e) {
    cleanup();
    throw e;
  }
}

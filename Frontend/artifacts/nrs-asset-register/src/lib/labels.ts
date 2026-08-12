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

import { code128Svg } from "./code128";
import { getBrand, brandLogoSrc } from "./brand";
import { API_BASE } from "./api";

export type LabelSize = "small" | "standard" | "large" | "sheet";

export interface LabelData {
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
  { value: "standard", label: "Standard", hint: "50 × 30 mm — the default asset tag" },
  { value: "large",    label: "Large",    hint: "100 × 60 mm — full detail" },
  { value: "sheet",    label: "A4 sheet", hint: "8 per page, plain paper — cut out" },
];

/** Page box per size, in mm. `sheet` prints on plain A4. */
const PAGE: Record<LabelSize, { css: string }> = {
  small:    { css: "@page { size: 50mm 25mm; margin: 0; }" },
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
function code128Img(value: string, className: string): string {
  const svg = code128Svg(value);
  if (!svg) {
    // Unencodable code — print it big as text rather than emit a blank space.
    return `<div class="${className} bc-fallback">${esc(value)}</div>`;
  }
  const src = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  return `<img class="${className}" src="${src}" alt="${esc(value)}"/>`;
}

/**
 * One layout at every size (the approved "Option 1" artwork):
 *
 *   ┌──────┬─────────────────────────────────┐
 *   │      │ ███ NRS FACILITIES MANAGEMENT   │
 *   │      │ Workstation Desk                │
 *   │ logo │ HQ-GF-MR-FF-001                 │
 *   │      │ NRS-FF-DSK-00001                │
 *   │      │ ‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖‖       ▓▓▓     │
 *   │ GF-MR│  HQ-GF-MR-FF-001        ▓▓▓     │
 *   └──────┴─────────────────────────────────┘
 *
 * The colour band is inset from the left so the brand mark sits in its own
 * column, and the human-readable code repeats under the barcode so a tag
 * stays usable once the bars scuff. Sizes differ only in the root font-size
 * and the barcode/QR dimensions — everything else is in `em`.
 */
function labelMarkup(d: LabelData, size: LabelSize, brandPrimary: string, logo: string): string {
  // Trim once so the printed text and the encoded barcode can't disagree —
  // code128Svg trims internally.
  const tag = (d.tag_number || "").trim();
  const qrPx = size === "small" ? 120 : 200;
  const brand = getBrand();
  const brandName = brand.short_name || brand.name;

  return `
    <div class="lbl lbl-${size}">
      <div class="side">
        ${logo ? `<img class="side-logo" data-logo="1" src="${esc(logo)}" alt=""/>`
               : `<span class="side-name" style="color:${esc(brandPrimary)}">${esc(brandName)}</span>`}
        <div class="side-room">${esc(d.floor_room || "")}</div>
      </div>
      <div class="content">
        <div class="hdr" style="background:${esc(brandPrimary)}">
          <span class="hdr-brand">${esc(brandName)}</span>
          <span class="hdr-sub">FACILITIES MANAGEMENT</span>
        </div>
        <div class="body">
          <div class="asset-name">${esc((d.asset_name || "").slice(0, 40))}</div>
          <div class="tag-code">${esc(tag)}</div>
          <div class="asset-code">${esc(d.asset_code || "")}</div>
          <div class="row">
            <div class="col-bc">
              ${code128Img(tag, "bc-wide")}
              <div class="bc-text">${esc(tag)}</div>
            </div>
            <div class="col-qr">
              <img class="qr" data-qr="1" src="${qrUrl(tag, qrPx)}" alt=""/>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

const STYLES = `
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; }
  body { font-family: Arial, Helvetica, sans-serif; color: #000; -webkit-print-color-adjust: exact; print-color-adjust: exact; }

  /* One label per page, edge to edge — roll/label stock. */
  .page { page-break-after: always; break-after: page; overflow: hidden; }
  .page:last-child { page-break-after: auto; break-after: auto; }

  /* ── Option 1 layout. Everything scales off .lbl's font-size. ── */
  .lbl { display: flex; overflow: hidden; background: #fff; line-height: 1; }
  /* Brand mark centred in its own column; the floor/room pair is positioned
     rather than flowed, so pinning it to the bottom can't shove the mark up. */
  .side { flex: 0 0 auto; position: relative; display: flex; align-items: center;
          justify-content: center; padding: .8em .4em 2em; }
  .side-logo { width: 100%; max-height: 4.2em; object-fit: contain; }
  .side-name { font-weight: 900; font-size: 1.4em; }
  /* The floor/room pair a walking auditor reads first, without having to parse
     the full tag code. */
  .side-room { position: absolute; left: 0; right: 0; bottom: .6em; text-align: center;
               font-size: .85em; color: #888; letter-spacing: .3px; white-space: nowrap; }

  .content { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  .hdr { flex: 0 0 auto; color: #fff; display: flex; align-items: baseline; gap: .5em;
         padding: .35em .8em; }
  .hdr-brand { font-weight: 900; font-size: 1.15em; letter-spacing: .2px; }
  .hdr-sub { font-weight: 600; font-size: .95em; letter-spacing: .4px; }

  .body { flex: 1 1 auto; min-height: 0; padding: .35em .8em .3em; display: flex; flex-direction: column; }
  .asset-name { font-weight: 700; font-size: 1.15em; line-height: 1.15;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag-code { font-family: "Courier New", monospace; font-weight: 700; font-size: 1.95em;
              letter-spacing: .5px; line-height: 1.15; }
  .asset-code { font-family: "Courier New", monospace; font-size: .95em; color: #777;
                line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* Follows the codes directly. Left flexible it would be shoved to the very
     bottom edge, which reads as a mistake on a 60mm label. */
  .row { flex: 0 0 auto; display: flex; align-items: flex-end; gap: .8em; margin-top: .5em; }
  .col-bc { flex: 1 1 auto; min-width: 0; }
  .col-qr { flex: 0 0 auto; }
  .qr { display: block; }
  .bc-wide { width: 100%; display: block; }
  .bc-text { font-family: "Courier New", monospace; font-weight: 700; font-size: 1.15em;
             letter-spacing: 1.5px; text-align: center; line-height: 1.1; }
  .bc-fallback { font-family: "Courier New", monospace; font-weight: 700; letter-spacing: 1px;
                 text-align: center; }

  /* Per-size scale. Only the type scale and the barcode/QR boxes change. */
  .lbl-small    { width: 50mm;  height: 25mm; font-size: 4pt; }
  .lbl-small    .side { width: 8mm; }
  .lbl-small    .bc-wide { height: 6.5mm; }
  .lbl-small    .qr { width: 8mm; height: 8mm; }

  .lbl-standard { width: 50mm;  height: 30mm; font-size: 4.6pt; }
  .lbl-standard .side { width: 9mm; }
  .lbl-standard .bc-wide { height: 8mm; }
  .lbl-standard .qr { width: 10mm; height: 10mm; }

  .lbl-large    { width: 100mm; height: 60mm; font-size: 8.5pt; }
  .lbl-large    .side { width: 17mm; }
  .lbl-large    .bc-wide { height: 21mm; }
  .lbl-large    .qr { width: 24mm; height: 24mm; }

  /* A4 sheet — 2 x 4 grid with a dashed cut border. Inside a 6mm page margin
     that leaves 198 x 285mm, so 97 x 68mm cells: near enough the large label's
     own 100 x 60mm that it needs no reflow. */
  .sheet { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 68mm; gap: 4mm; }
  .sheet .cell { border: .3mm dashed #c8c8c8; display: flex; align-items: stretch; overflow: hidden; }
  .sheet .lbl-large { width: 100%; height: 100%; }
`;

function buildDocument(labels: LabelData[], size: LabelSize): string {
  const brand = getBrand();
  const logo = absolute(brandLogoSrc());
  const primary = brand.primary || "#C8102E";

  let content: string;
  if (size === "sheet") {
    // 8 per page — a page break every 8 cells keeps the grid aligned.
    const pages: string[] = [];
    for (let i = 0; i < labels.length; i += 8) {
      const cells = labels
        .slice(i, i + 8)
        .map((d) => `<div class="cell">${labelMarkup(d, "large", primary, logo)}</div>`)
        .join("");
      pages.push(`<div class="page"><div class="sheet">${cells}</div></div>`);
    }
    content = pages.join("");
  } else {
    content = labels
      .map((d) => `<div class="page">${labelMarkup(d, size, primary, logo)}</div>`)
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

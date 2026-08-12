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

function labelMarkup(d: LabelData, size: LabelSize, brandPrimary: string, logo: string): string {
  // Trim once so the printed text and the encoded barcode can't disagree —
  // code128Svg trims internally.
  const tag = (d.tag_number || "").trim();
  const qrPx = size === "large" ? 200 : 120;

  if (size === "small") {
    return `
      <div class="lbl lbl-small">
        ${code128Img(tag, "bc-wide")}
        <div class="code-strong">${esc(tag)}</div>
      </div>`;
  }

  if (size === "large") {
    return `
      <div class="lbl lbl-large">
        <div class="hdr" style="background:${esc(brandPrimary)}">
          ${logo ? `<img class="hdr-logo" data-logo="1" src="${esc(logo)}" alt=""/>` : ""}
          <span class="hdr-name">${esc(getBrand().short_name || getBrand().name)}</span>
          <span class="hdr-sub">ASSET REGISTER</span>
        </div>
        <div class="body">
          <div class="asset-name">${esc((d.asset_name || "").slice(0, 55))}</div>
          <div class="row">
            <div class="col-bc">
              ${code128Img(tag, "bc-wide")}
              <div class="code-strong">${esc(tag)}</div>
            </div>
            <div class="col-qr">
              <img class="qr" data-qr="1" src="${qrUrl(tag, qrPx)}" alt=""/>
            </div>
          </div>
          <table class="meta">
            <tr><td class="k">Asset code</td><td class="v mono">${esc(d.asset_code)}</td>
                <td class="k">Serial</td><td class="v mono">${esc(d.serial_number)}</td></tr>
            <tr><td class="k">Location</td><td class="v" colspan="3">${esc((d.location || "").slice(0, 45))}${d.floor_room ? ` <span class="dim">/</span> ${esc(d.floor_room)}` : ""}</td></tr>
            <tr><td class="k">Custodian</td><td class="v" colspan="3">${esc((d.custodian || "").slice(0, 40))}</td></tr>
          </table>
        </div>
      </div>`;
  }

  // "standard" (50 x 30 mm) and each cell of the A4 sheet.
  return `
    <div class="lbl lbl-standard">
      <div class="bar" style="background:${esc(brandPrimary)}"></div>
      <div class="body">
        <div class="brandline">
          ${logo ? `<img class="mini-logo" data-logo="1" src="${esc(logo)}" alt=""/>` : `<span class="mini-name" style="color:${esc(brandPrimary)}">${esc(getBrand().short_name || getBrand().name)}</span>`}
        </div>
        <div class="k">TAG CODE</div>
        <div class="code-strong">${esc(tag)}</div>
        <div class="k">ASSET CODE</div>
        <div class="code-weak">${esc(d.asset_code || d.asset_name || "")}</div>
        <div class="row">
          <div class="col-bc">${code128Img(tag, "bc-wide")}</div>
          <div class="col-qr"><img class="qr" data-qr="1" src="${qrUrl(tag, qrPx)}" alt=""/></div>
        </div>
      </div>
    </div>`;
}

const STYLES = `
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; }
  body { font-family: Arial, Helvetica, sans-serif; color: #000; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .bc-fallback { font-family: "Courier New", monospace; font-weight: 700; letter-spacing: 1px; text-align: center; }
  .code-strong { font-family: "Courier New", monospace; font-weight: 700; letter-spacing: 1px; line-height: 1.05; }
  .code-weak { font-family: "Courier New", monospace; color: #666; line-height: 1.05; }
  .k { font-size: 5.5pt; color: #999; text-transform: uppercase; letter-spacing: .5px; line-height: 1.1; }
  .qr { display: block; }
  .row { display: flex; align-items: flex-end; gap: 1.5mm; }
  .col-bc { flex: 1 1 auto; min-width: 0; }
  .col-qr { flex: 0 0 auto; }

  /* One label per page, edge to edge — roll/label stock. */
  .page { page-break-after: always; break-after: page; overflow: hidden; }
  .page:last-child { page-break-after: auto; break-after: auto; }

  .lbl-small { width: 50mm; height: 25mm; padding: 2mm; text-align: center; }
  .lbl-small .bc-wide { width: 100%; height: 13mm; display: block; }
  .lbl-small .code-strong { font-size: 8pt; margin-top: .5mm; }

  .lbl-standard { width: 50mm; height: 30mm; display: flex; }
  .lbl-standard .bar { width: 1.4mm; flex: 0 0 auto; }
  .lbl-standard .body { flex: 1 1 auto; min-width: 0; padding: 1mm 1.5mm 1mm 1.2mm; }
  /* Flex, not a line box: an inline image in a short line box overflows it and
     collides with the TAG CODE line below. */
  .lbl-standard .brandline { height: 3.6mm; margin-bottom: .5mm; display: flex; align-items: center; }
  .lbl-standard .mini-logo { height: 3.4mm; width: auto; object-fit: contain; }
  .lbl-standard .mini-name { font-size: 8pt; font-weight: 900; line-height: 1; }
  .lbl-standard .code-strong { font-size: 10.5pt; }
  .lbl-standard .code-weak { font-size: 6.5pt; }
  .lbl-standard .bc-wide { width: 100%; height: 11mm; display: block; }
  .lbl-standard .qr { width: 11mm; height: 11mm; }
  .lbl-standard .row { margin-top: .6mm; }

  .lbl-large { width: 100mm; height: 60mm; display: flex; flex-direction: column; }
  .lbl-large .hdr { flex: 0 0 auto; color: #fff; padding: 1.6mm 2.5mm; display: flex; align-items: center; gap: 2mm; }
  .lbl-large .hdr-logo { height: 4.5mm; width: auto; object-fit: contain; }
  .lbl-large .hdr-name { font-size: 9pt; font-weight: 900; letter-spacing: .3px; }
  .lbl-large .hdr-sub { font-size: 6.5pt; font-weight: 400; letter-spacing: .5px; opacity: .9; }
  .lbl-large .body { flex: 1 1 auto; min-height: 0; padding: 2mm 3mm; }
  .lbl-large .asset-name { font-size: 11pt; font-weight: 700; line-height: 1.2; margin-bottom: 1.5mm;
                           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lbl-large .bc-wide { width: 100%; height: 15mm; display: block; }
  .lbl-large .code-strong { font-size: 10pt; text-align: center; margin-top: .5mm; }
  .lbl-large .qr { width: 17mm; height: 17mm; }
  .lbl-large .meta { width: 100%; border-collapse: collapse; margin-top: 1.5mm; font-size: 7pt; }
  .lbl-large .meta .k { width: 18%; padding: .2mm 0; }
  .lbl-large .meta .v { font-weight: 600; padding: .2mm 0; }
  .lbl-large .mono { font-family: "Courier New", monospace; font-weight: 400; }
  .lbl-large .dim { color: #999; }

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

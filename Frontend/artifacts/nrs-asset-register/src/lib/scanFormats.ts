/**
 * The published symbology vocabulary — handoff 54.
 *
 * Separate from `scanEngine.ts` ON PURPOSE: this module has no zxing
 * import, so a page that only needs to NAME a format (the station's "read
 * from QR code" chip, the affix dialog's `scanned_format` on the POST) can
 * import it statically without dragging the decoder into its chunk. The
 * engine, and its ~930 KB wasm, load only when a camera starts.
 *
 * These are the BarcodeDetector-style names, and they are API surface:
 * `POST /assets/<id>/tag-affixed` accepts exactly this set as
 * `scanned_format` / `serial_format`, and the refused-affix event records
 * them. Changing a name here is a breaking API change, not a rename.
 */

export const SCAN_FORMATS = [
  "code_128", "code_39", "code_93", "codabar",
  "ean_13", "ean_8", "upc_a", "upc_e", "itf",
  "qr_code", "data_matrix", "pdf417", "aztec",
] as const;
export type ScanFormat = (typeof SCAN_FORMATS)[number];

/** 1D formats have no error correction worth the name — a partial read can
 *  yield a valid, wrong string — so the scanner accepts a 1D value only
 *  when two consecutive decodes agree. 2D codes correct their own errors
 *  and are accepted on one. */
const TWO_D: ReadonlySet<ScanFormat> = new Set([
  "qr_code", "data_matrix", "pdf417", "aztec",
]);
export const isTwoDimensional = (f: ScanFormat) => TWO_D.has(f);

/** Shown to people ("Read from QR code"), and in the chooser. */
export const SCAN_FORMAT_LABELS: Record<ScanFormat, string> = {
  code_128: "Code 128", code_39: "Code 39", code_93: "Code 93",
  codabar: "Codabar", ean_13: "EAN-13", ean_8: "EAN-8",
  upc_a: "UPC-A", upc_e: "UPC-E", itf: "ITF",
  qr_code: "QR code", data_matrix: "Data Matrix",
  pdf417: "PDF417", aztec: "Aztec",
};

/** One decode's worth of answer: the value as printed, trimmed, and what
 *  kind of code it came off. */
export interface ScanHit {
  value: string;
  format: ScanFormat;
}

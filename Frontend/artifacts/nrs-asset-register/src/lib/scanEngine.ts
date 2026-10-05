/**
 * The one decoding engine — handoff 54.
 *
 * Before this, the station's camera used the platform's `BarcodeDetector`,
 * which exists on some phones and not others, honours an unknowable subset
 * of the formats it is asked for, and made "some barcodes scan and some do
 * not" a fact about whose phone it was. This module bundles ZXing compiled
 * to WebAssembly (`zxing-wasm`, the reader build) and makes it THE engine on
 * every device: the same label through the same lens produces the same
 * result everywhere, and a failure reproduces instead of depending on the
 * handset. The platform detector is deliberately not kept as an
 * acceleration — one engine is the point.
 *
 * This module is imported DYNAMICALLY by `BarcodeScanner` when the camera
 * starts, never from the app's boot path: the .wasm is ~930 KB and a person
 * who never opens the camera never fetches it. The wasm is served from our
 * own origin (the `?url` import below hands Vite the file), never from the
 * default jsDelivr CDN — a tagging station on a government network has no
 * business fetching its decoder from a third party. Code that only needs to
 * NAME a format imports `scanFormats.ts`, which carries none of this.
 *
 * The corpus script (`e2e/corpus/run54.mjs`) decodes with the same package,
 * the same version and the same `READER_OPTIONS`, so its offline table is a
 * measurement of this engine, not of a cousin.
 */

import {
  prepareZXingModule,
  readBarcodes,
  type ReaderOptions,
  type ReadResult,
} from "zxing-wasm/reader";
import wasmUrl from "zxing-wasm/reader/zxing_reader.wasm?url";
import {
  SCAN_FORMATS, SCAN_FORMAT_LABELS, isTwoDimensional,
  type ScanFormat, type ScanHit,
} from "@/lib/scanFormats";

export { SCAN_FORMATS, SCAN_FORMAT_LABELS, isTwoDimensional };
export type { ScanFormat, ScanHit };

prepareZXingModule({
  overrides: {
    locateFile: (path: string, prefix: string) =>
      path.endsWith(".wasm") ? wasmUrl : prefix + path,
  },
});

/** ZXing's names for the published thirteen, in the same order. */
const ZXING_FORMATS = [
  "Code128", "Code39", "Code93", "Codabar",
  "EAN13", "EAN8", "UPCA", "UPCE", "ITF",
  "QRCode", "DataMatrix", "PDF417", "Aztec",
] as const;

const ZXING_TO_SCAN: Record<string, ScanFormat> = Object.fromEntries(
  ZXING_FORMATS.map((z, i) => [z, SCAN_FORMATS[i]]),
);
// Variants ZXing may report when asked for the base symbology. An ITF read
// of 14 digits can come back "ITF14"; a UPC-A is an EAN-13 with a leading
// zero and some builds answer either way.
Object.assign(ZXING_TO_SCAN, {
  "ITF14": "itf",
  "Code39Std": "code_39",
  "Code39Ext": "code_39",
  "CompactPDF417": "pdf417",
  "AztecCode": "aztec",
  "QRCodeModel1": "qr_code",
  "QRCodeModel2": "qr_code",
});

/** The exact options the corpus measures with. `tryHarder`/`tryRotate`/
 *  `tryInvert` cost CPU per frame, which is why the scanner throttles to
 *  ~10 fps instead of decoding every animation frame. */
const READER_OPTIONS: ReaderOptions = {
  formats: [...ZXING_FORMATS],
  tryHarder: true,
  tryRotate: true,
  tryInvert: true,
  maxNumberOfSymbols: 4,
};

function toHit(r: ReadResult): ScanHit | null {
  const format = ZXING_TO_SCAN[r.format];
  const value = (r.text ?? "").trim();
  if (!format || !value) return null;
  return { value, format };
}

/** Decode one frame (an ImageData, usually a canvas crop). Returns the
 *  DISTINCT values in it: a Cadra label carries its number twice (Code 128
 *  and QR), and two copies of one value are one answer, not two. When one
 *  value was read as both a 1D and a 2D code, the 2D read is the one kept —
 *  it is the one a single decode may accept. */
export async function decodeFrame(image: ImageData): Promise<ScanHit[]> {
  const results = await readBarcodes(image, READER_OPTIONS);
  const byValue = new Map<string, ScanHit>();
  for (const r of results) {
    const hit = toHit(r);
    if (!hit) continue;
    const prev = byValue.get(hit.value);
    if (!prev || (!isTwoDimensional(prev.format) && isTwoDimensional(hit.format))) {
      byValue.set(hit.value, hit);
    }
  }
  return [...byValue.values()];
}

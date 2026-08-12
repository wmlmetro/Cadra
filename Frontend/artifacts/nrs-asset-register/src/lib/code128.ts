/**
 * Code 128 (subset B) → inline SVG.
 *
 * Labels are printed by the browser from the Barcode Station, so the barcode
 * has to be generated client-side. Drawing it as vector SVG (rather than
 * pulling a raster PNG from Odoo's /report/barcode route) means the bars stay
 * crisp at any label size — a 600x100 PNG squeezed onto a 40mm-wide label is
 * the classic cause of "the scanner won't read our tags".
 *
 * Subset B covers ASCII 32..126, which is every character an asset tag code
 * uses (uppercase letters, digits, dashes). Values outside that range are
 * dropped rather than mis-encoded.
 */

/**
 * The 107 Code 128 element-width patterns, indexed by code value.
 * Each character is a run length in modules, alternating bar/space starting
 * with a bar. 103/104/105 are Start A/B/C; 106 is Stop (7 elements).
 */
const PATTERNS = [
  // 0-9
  "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
  // 10-19
  "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
  // 20-29
  "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
  // 30-39
  "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
  // 40-49
  "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
  // 50-59
  "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
  // 60-69
  "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
  // 70-79
  "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
  // 80-89
  "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
  // 90-99
  "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
  // 100-102, 103=StartA, 104=StartB, 105=StartC, 106=Stop
  "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
];

const START_B = 104;
const STOP = 106;

/** Characters Code 128 subset B can encode. */
export function isCode128Encodable(value: string): boolean {
  if (!value) return false;
  for (let i = 0; i < value.length; i++) {
    const c = value.charCodeAt(i);
    if (c < 32 || c > 126) return false;
  }
  return true;
}

/**
 * Code values for `value` in subset B, including the start code and the mod-103
 * check character, terminated by the stop pattern.
 */
function encodeB(value: string): number[] {
  const codes = [START_B];
  let sum = START_B;
  for (let i = 0; i < value.length; i++) {
    const v = value.charCodeAt(i) - 32;
    codes.push(v);
    // Weight is the 1-based position of the character after the start code.
    sum += v * (i + 1);
  }
  codes.push(sum % 103);
  codes.push(STOP);
  return codes;
}

export interface Code128Options {
  /** Bar height as a fraction of the SVG viewBox height. Default 1 (full). */
  barHeightRatio?: number;
  /** Quiet-zone width in modules on each side. The spec minimum is 10. */
  quietModules?: number;
  /** Bar colour. Default black — never use a mid-grey, scanners need contrast. */
  color?: string;
}

/**
 * Render `value` as a Code 128-B barcode SVG that stretches to fill its box.
 * Returns "" when the value can't be encoded, so callers can fall back to
 * printing the code as text rather than emitting a broken label.
 */
export function code128Svg(value: string, opts: Code128Options = {}): string {
  const code = (value || "").trim();
  if (!isCode128Encodable(code)) return "";

  const quiet = opts.quietModules ?? 10;
  const heightRatio = opts.barHeightRatio ?? 1;
  const color = opts.color ?? "#000";

  const codes = encodeB(code);
  const widths: number[] = [];
  for (const c of codes) {
    for (const ch of PATTERNS[c]) widths.push(Number(ch));
  }

  // Alternating bar/space, starting with a bar. Merge nothing — each run is
  // emitted at its exact module width so the printer rounds consistently.
  const totalModules = widths.reduce((a, b) => a + b, 0) + quiet * 2;
  const barHeight = 100 * heightRatio;
  let x = quiet;
  let rects = "";
  for (let i = 0; i < widths.length; i++) {
    const w = widths[i];
    if (i % 2 === 0) {
      rects += `<rect x="${x}" y="0" width="${w}" height="${barHeight}" fill="${color}"/>`;
    }
    x += w;
  }

  // preserveAspectRatio="none" lets the label CSS set width and height
  // independently — label stock is rarely the barcode's natural aspect ratio.
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalModules} 100" ` +
    `preserveAspectRatio="none" shape-rendering="crispEdges">${rects}</svg>`
  );
}

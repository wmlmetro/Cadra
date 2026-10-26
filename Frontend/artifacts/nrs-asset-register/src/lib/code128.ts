/**
 * Code 128 (subset B, with runs of digits packed in subset C) → inline SVG.
 *
 * Labels are printed by the browser from the Barcode Station, so the barcode
 * has to be generated client-side. Drawing it as vector SVG (rather than
 * pulling a raster PNG from Odoo's /report/barcode route) means the bars stay
 * crisp at any label size — a 600x100 PNG squeezed onto a 40mm-wide label is
 * the classic cause of "the scanner won't read our tags".
 *
 * Subset B covers ASCII 32..126, which is every character an asset tag code
 * uses (uppercase letters, digits, dashes). Values outside that range are
 * dropped rather than mis-encoded. A run of digits long enough to pay for the
 * switch is packed two to a symbol in subset C, the way a label printer's own
 * firmware encodes it: `NRS-AST-011933` is 167 modules instead of 189, which
 * is what lets it print at a whole two dots per module across 2-inch stock on
 * a 203 dpi printer (see labels.ts).
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
const START_C = 105;
/** Switch codes: CODE C read in subset B, CODE B read in subset C. */
const CODE_C = 99;
const CODE_B = 100;
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

const isDigit = (c: string) => c >= "0" && c <= "9";

/** Length of the run of digits starting at `i`. */
function digitRun(value: string, i: number): number {
  let n = 0;
  while (i + n < value.length && isDigit(value[i + n])) n++;
  return n;
}

/**
 * Code values for `value`, including the start code and the mod-103 check
 * character, terminated by the stop pattern.
 *
 * Subset B throughout, except that a run of digits is packed in subset C when
 * the switch saves modules: four or more at the start or the end of the value
 * (one switch), six or more in the middle (a switch in and one back). An odd
 * run leaves its first digit in B so the rest pair up.
 */
function encode(value: string): number[] {
  const symbols: number[] = [];
  let i = 0;
  let inC = false;

  if (digitRun(value, 0) >= 4) {
    // Start in C with the even part of the leading run; an odd last digit
    // drops back to B below.
    symbols.push(START_C);
    inC = true;
  } else {
    symbols.push(START_B);
  }

  while (i < value.length) {
    const run = digitRun(value, i);
    const atEnd = i + run === value.length;
    if (inC) {
      if (run >= 2) {
        symbols.push(Number(value.slice(i, i + 2)));
        i += 2;
        continue;
      }
      symbols.push(CODE_B);
      inC = false;
      continue;
    }
    if (run >= 6 || (run >= 4 && atEnd)) {
      if (run % 2 === 1) {
        symbols.push(value.charCodeAt(i) - 32);
        i += 1;
      }
      symbols.push(CODE_C);
      inC = true;
      continue;
    }
    symbols.push(value.charCodeAt(i) - 32);
    i += 1;
  }

  // Weight is the 1-based position of the symbol after the start code; the
  // start code itself carries weight 1.
  let sum = symbols[0];
  for (let k = 1; k < symbols.length; k++) sum += symbols[k] * k;
  return [...symbols, sum % 103, STOP];
}

/** Module widths of `value`'s bars and spaces, quiet zones excluded. */
function elementWidths(value: string): number[] {
  const widths: number[] = [];
  for (const c of encode(value)) {
    for (const ch of PATTERNS[c]) widths.push(Number(ch));
  }
  return widths;
}

/**
 * The symbol's total width in modules, quiet zones included — what a label
 * needs to size the barcode to a whole number of printer dots per module.
 * 0 when the value can't be encoded.
 */
export function code128Modules(value: string, quietModules = 10): number {
  const code = (value || "").trim();
  if (!isCode128Encodable(code)) return 0;
  return elementWidths(code).reduce((a, b) => a + b, 0) + quietModules * 2;
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
 * Render `value` as a Code 128 barcode SVG that stretches to fill its box.
 * Returns "" when the value can't be encoded, so callers can fall back to
 * printing the code as text rather than emitting a broken label.
 */
export function code128Svg(value: string, opts: Code128Options = {}): string {
  const code = (value || "").trim();
  if (!isCode128Encodable(code)) return "";

  const quiet = opts.quietModules ?? 10;
  const heightRatio = opts.barHeightRatio ?? 1;
  const color = opts.color ?? "#000";

  const widths = elementWidths(code);

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

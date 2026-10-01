import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Today, as a LAGOS calendar date (`YYYY-MM-DD`).
 *
 * The server's definition, not the browser's: Nigeria keeps no daylight
 * saving, so Lagos is UTC+1 all year, and the server's `snapshot_today` is
 * exactly this. A UTC date is wrong for one hour every night — between
 * midnight and 01:00 in Lagos it still says yesterday — which is what report
 * 29 found in the register snapshot. The browser's own zone is not used
 * either: a screen that names a window of dates must name the same window the
 * server filtered on, wherever the viewer happens to be sitting.
 */
export function lagosToday(): string {
  return new Date(Date.now() + 3600_000).toISOString().slice(0, 10);
}

/**
 * `YYYY-MM-DD` plus `days` calendar days, as a `YYYY-MM-DD`. Pure date
 * arithmetic in UTC, so no zone can move the answer by a day.
 */
export function addDaysIso(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/**
 * `YYYY-MM-DD` plus `months` calendar months, clamped to the end of the
 * target month — the same answer as python-dateutil's `relativedelta`, which
 * is what the server derives a warranty's expiry with: 31 Jan + 1 month is
 * 28 Feb (29 in a leap year), not 3 March. Returns null for anything that is
 * not a date and a whole number of months.
 */
export function addMonthsIso(iso: string, months: number): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m || !Number.isInteger(months)) return null;
  const y = Number(m[1]), mo = Number(m[2]) - 1, d = Number(m[3]);
  const total = y * 12 + mo + months;
  const ty = Math.floor(total / 12), tm = total - ty * 12;
  const lastDay = new Date(Date.UTC(ty, tm + 1, 0)).getUTCDate();
  return new Date(Date.UTC(ty, tm, Math.min(d, lastDay))).toISOString().slice(0, 10);
}

/** `2026-09-22` → `22 Sep 2026`. Formatted in UTC so the date printed is the
 *  date given, never the day before in a browser west of Greenwich. */
export function formatIsoDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

/** `2026-10-01T11:32:07` → `1 Oct 2026, 12:32` in the viewer's zone.
 *
 *  The API's `*_at` datetimes are UTC with no zone suffix (`isoformat()` of a
 *  naive Odoo datetime), so one is appended before parsing; a value that
 *  already carries a zone is left alone. A bare date falls back to
 *  `formatIsoDate`, and anything unparseable comes back as given rather than
 *  as "Invalid Date". */
export function formatIsoDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  if (!iso.includes("T")) return formatIsoDate(iso);
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const t = new Date(zoned);
  if (Number.isNaN(t.getTime())) return iso;
  return t.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

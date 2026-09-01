// Runtime per-tenant branding.
//
// ONE static build serves every tenant; on startup we fetch the brand for the
// current host from the same-origin Cadra API (GET /api/v1/brand — Odoo's
// dbfilter resolves the tenant DB from the host), then apply colour, title and
// logo. So gtb.cadra.ng shows GTB's orange + logo and staging.app.cadra.ng
// shows NRS's red, from the same bundle. Falls back to bundled defaults if the
// API is unreachable.

export type Brand = {
  name: string;
  short_name: string;
  primary: string;       // hex, e.g. "#E04403"
  primary_dark: string;  // hex
  logo: string;          // data: URI (or "" → use bundled fallback)
  turnstile: boolean;    // this tenant enforces Turnstile on login
};

// Bundled fallback (the original NRS branding) — used if the API call fails.
const FALLBACK_LOGO = `${import.meta.env.BASE_URL}nrs-logo.png`;
const DEFAULT_BRAND: Brand = {
  name: "Cadra",
  short_name: "",
  primary: "#E01F26",
  primary_dark: "#C2181E",
  logo: "",
  // Assume unprotected. The API is the real gate — guessing `true` here would
  // block the login form on tenants that never asked for a challenge.
  turnstile: false,
};

let current: Brand = DEFAULT_BRAND;

export function getBrand(): Brand {
  return current;
}

/** Logo to render: the tenant's logo if provided, else the bundled NRS mark. */
export function brandLogoSrc(): string {
  return current.logo || FALLBACK_LOGO;
}

/** "#E04403" -> "20 96% 45%" (the "H S% L%" form Tailwind/shadcn CSS vars use). */
function hexToHslParts(hex: string): string | null {
  const m = hex.replace("#", "").match(/^([0-9a-fA-F]{6})$/);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  let h = 0;
  let s = 0;
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

const CACHE_KEY = "cadra.brand.v2";

/** Last successfully-fetched brand for this host, if any. Lets the app render
 *  the correct brand instantly on every page load and avoids flashing the NRS
 *  fallback when a later fetch is slow or fails. */
export function getCachedBrand(): Brand | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as Brand) : null;
  } catch {
    return null;
  }
}

export async function fetchBrand(): Promise<Brand> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 6000);
    const res = await fetch("/api/v1/brand", {
      headers: { Accept: "application/json" },
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!res.ok) throw new Error(`brand ${res.status}`);
    const json = await res.json();
    const d = (json && json.data) || {};
    const brand: Brand = {
      name: d.name || DEFAULT_BRAND.name,
      short_name: d.short_name || "",
      primary: d.primary || DEFAULT_BRAND.primary,
      primary_dark: d.primary_dark || DEFAULT_BRAND.primary_dark,
      logo: d.logo || "",
      turnstile: d.turnstile === true,
    };
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(brand)); } catch { /* ignore */ }
    return brand;
  } catch {
    // Prefer a previously-cached brand over the NRS default on a transient fail.
    return getCachedBrand() ?? DEFAULT_BRAND;
  }
}

/** Apply brand to the document: theme CSS vars, accent, and tab title. */
export function applyBrand(brand: Brand): void {
  current = brand;
  const root = document.documentElement;
  const hsl = hexToHslParts(brand.primary);
  if (hsl) {
    // shadcn/Tailwind primary tokens (all the red "358 76% 50%" spots).
    for (const v of ["--primary", "--sidebar-primary", "--sidebar-ring", "--ring"]) {
      root.style.setProperty(v, hsl);
    }
  }
  // Raw-hex accent token used directly in a few places.
  root.style.setProperty("--nrs-red", brand.primary);
  document.title = brand.name ? `${brand.name} · Cadra` : "Cadra";

  // Per-tenant favicon: point the icon at the tenant logo (data URI). The
  // bundled NRS favicon.svg / nrs-logo.png in index.html stay as the fallback
  // when brand.logo is empty. Remove the bundled alternates so they can't
  // out-rank the data URI in the browser's favicon selection.
  if (brand.logo) {
    let icon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    icon.type = brand.logo.startsWith("data:image/svg") ? "image/svg+xml" : "image/png";
    icon.href = brand.logo;
    document.head
      .querySelectorAll("link[rel='alternate icon'], link[rel='apple-touch-icon']")
      .forEach((el) => el.remove());
  }
}

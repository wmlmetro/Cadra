import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { fetchBrand, applyBrand, getCachedBrand } from "@/lib/brand";

// Resolve + apply per-tenant branding before first paint so the UI renders in
// the correct colour/logo (no NRS→GTB flash). A sessionStorage cache makes every
// reload after the first instant and immune to a slow/failed brand fetch (which
// would otherwise flash the NRS fallback). Only the very first load blocks on
// the network; thereafter we render from cache and refresh in the background.
async function boot() {
  const cached = getCachedBrand();
  applyBrand(cached ?? (await fetchBrand()));
  createRoot(document.getElementById("root")!).render(<App />);
  if (cached) void fetchBrand().then(applyBrand);
}

void boot();

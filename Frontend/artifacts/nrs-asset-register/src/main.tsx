import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { fetchBrand, applyBrand } from "@/lib/brand";

// Resolve + apply per-tenant branding before first paint so the UI renders in
// the correct colour/logo (no NRS→GTB flash). fetchBrand() is fast, same-origin,
// cached, and self-times-out, so render is never blocked for long.
async function boot() {
  applyBrand(await fetchBrand());
  createRoot(document.getElementById("root")!).render(<App />);
}

void boot();

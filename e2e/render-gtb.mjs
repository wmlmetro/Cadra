/**
 * Render check for the Depreciation report + asset Depreciation card.
 * Logs in through the REST API, seeds the SPA's localStorage session, then
 * loads the pages and reports what actually rendered.
 */
import { chromium } from "playwright";

const ORIGIN = process.env.ORIGIN ?? "http://localhost:8269";

const res = await fetch(`${ORIGIN}/api/v1/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ login: "admin", password: "admin" }),
});
const body = await res.json();
const d = body.data;
const token = d.access_token;
if (!token) throw new Error("no token: " + JSON.stringify(body).slice(0, 300));

const browser = await chromium.launch();
const page = await browser.newPage();

const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

await page.goto(`${ORIGIN}/app/`, { waitUntil: "domcontentloaded" });
await page.evaluate(([t, exp, scope]) => {
  localStorage.setItem("cadra.token", t);
  localStorage.setItem("cadra.tokenExpiresAt", String(exp));
  localStorage.setItem("cadra.tokenScope", scope);
  localStorage.removeItem("cadra.loggedOut");
}, [token, Date.now() + (d.expires_in ?? 3600) * 1000, d.scope ?? "*"]);

// ── Report page ────────────────────────────────────────────────────────────
await page.goto(`${ORIGIN}/app/reports/depreciation`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

const heading = await page.getByRole("heading", { name: /depreciation/i }).first()
  .textContent().catch(() => null);
console.log("HEADING:", heading);

for (const label of ["Depreciable cost", "Accumulated", "Net book value", "Needs start date"]) {
  const seen = await page.getByText(label, { exact: false }).first().isVisible().catch(() => false);
  console.log(`TILE ${label}: ${seen ? "visible" : "MISSING"}`);
}
console.log("has 404:", await page.getByText(/^404$/).count());
console.log("status sections:",
  await page.getByText("Assets by depreciation status").count(),
  await page.getByText("Assets by method").count());

await page.screenshot({ path: "/private/tmp/claude-502/-Users-macbookprom1-Desktop-WML-myservicenrs/5c41f266-c148-4b84-95d6-b88d0b592bf0/scratchpad/gtb-report.png", fullPage: true });

// Refresh control must work (this is what the e2e loop asserts).
const refresh = page.getByRole("button", { name: /refresh/i }).first();
if (await refresh.count()) { await refresh.click(); await page.waitForTimeout(1200); }
console.log("after refresh, heading still present:",
  await page.getByRole("heading", { name: /depreciation/i }).first().isVisible().catch(() => false));

// ── Asset detail card ──────────────────────────────────────────────────────
const list = await (await fetch(`${ORIGIN}/api/v1/assets?limit=1`, {
  headers: { Authorization: `Bearer ${token}` },
})).json();
const assetId = list.data?.[0]?.id;
if (assetId) {
  await page.goto(`${ORIGIN}/app/assets/${assetId}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  const card = await page.getByText("Depreciation", { exact: true }).count();
  console.log(`ASSET ${assetId} depreciation card headings:`, card);
  await page.screenshot({ path: "/private/tmp/claude-502/-Users-macbookprom1-Desktop-WML-myservicenrs/5c41f266-c148-4b84-95d6-b88d0b592bf0/scratchpad/gtb-asset.png", fullPage: true });
}

console.log("PAGE ERRORS:", errors.length ? errors.slice(0, 5) : "none");
await browser.close();

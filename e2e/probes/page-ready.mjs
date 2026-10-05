/**
 * Probe: what a reload costs on three screens — handoff 52 §5.
 *
 * The §5 ruling makes every query restored from the persisted cache stale on
 * restore, so a reload paints from cache and refetches at once. The cost is
 * a refetch burst on every reload, and the ruling asks for it measured, not
 * asserted: page-ready times and API request counts, before and after, on
 * three screens. Run this against the SERVED bundle (rebuild first), once on
 * the pre-ruling bundle and once on the post-ruling one.
 *
 * Per screen, with a WARM persisted cache (the screen was visited, and the
 * persister's 1 s write throttle was given time to flush):
 *   - t_content  — reload → the screen's own content marker visible
 *   - t_quiet    — reload → no /api/v1 request for 1.5 s
 *   - api_calls  — /api/v1 requests between reload and quiet
 *
 * Run (from repo root):
 *   E2E_ORIGIN=http://test19.localhost:8069 node e2e/probes/page-ready.mjs
 */
import { chromium } from '../node_modules/playwright/index.mjs';

const ORIGIN = process.env.E2E_ORIGIN ?? 'http://test19.localhost:8069';
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'admin';
const RUNS = Number(process.env.RUNS ?? 3);

// Screen → the marker that says its own content (not just the shell) is up.
const SCREENS = [
  { path: '/app/assets', name: 'asset-dashboard', marker: 'main h1, main h2, [data-testid="register-total"]' },
  { path: '/app/assets/list', name: 'asset-register-list', marker: '[data-testid="table-asset-list"] tbody tr, [data-testid^="card-asset-"]' },
  { path: '/app/approvals', name: 'approvals', marker: '[data-testid="approval-count"]' },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL: ORIGIN });

  // Sign in through the real form once.
  await page.goto('/app/', { waitUntil: 'domcontentloaded' });
  const username = page.locator('input[autocomplete="username"]');
  await username.waitFor({ state: 'visible', timeout: 20000 });
  await username.fill(USER);
  await page.locator('input[autocomplete="current-password"]').fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByTestId('nav-facility-command-center').waitFor({ state: 'visible', timeout: 20000 });

  const results = [];
  for (const screen of SCREENS) {
    // Warm the cache: visit, let content land, let the write throttle flush.
    await page.goto(screen.path, { waitUntil: 'domcontentloaded' });
    await page.locator(screen.marker).first().waitFor({ state: 'visible', timeout: 30000 });
    await sleep(2000);

    for (let run = 1; run <= RUNS; run++) {
      let apiCalls = 0;
      let lastApiAt = 0;
      const onReq = (req) => {
        if (req.url().includes('/api/v1/')) { apiCalls += 1; lastApiAt = Date.now(); }
      };
      page.on('request', onReq);
      const t0 = Date.now();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.locator(screen.marker).first().waitFor({ state: 'visible', timeout: 30000 });
      const tContent = Date.now() - t0;
      // Quiet = 1.5 s with no /api/v1 request (cap the wait at 20 s).
      lastApiAt = Math.max(lastApiAt, Date.now());
      while (Date.now() - lastApiAt < 1500 && Date.now() - t0 < 20000) await sleep(100);
      const tQuiet = (lastApiAt - t0);
      page.off('request', onReq);
      results.push({ screen: screen.name, run, t_content_ms: tContent, t_quiet_ms: tQuiet, api_calls: apiCalls });
      await sleep(1800); // let the persister flush before the next reload
    }
  }

  console.log(JSON.stringify({ origin: ORIGIN, at: new Date().toISOString(), results }, null, 2));
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });

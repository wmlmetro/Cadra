/**
 * Probe: the sidebar badge counts BOTH kinds of waiting work — handoff 52 §1.
 *
 * Driven as the Asset Manager persona on a tenant where they have ZERO
 * pending movement approvals, with exactly one pending tag replacement
 * naming them (created just before by the caller). So the badge's whole
 * value is the replacement: before the fix it was invisible (the badge
 * read only `/approvals`), after it the badge reads 1 — and approving the
 * replacement from the Approvals page takes it back off without a reload
 * (`invalidateTagQueries` now invalidates `approval-count`).
 *
 * Run (from repo root), after creating the one pending replacement:
 *   E2E_ORIGIN=http://test19.localhost:8069 \
 *   PERSONA_USER=... PERSONA_PASS=... TAG_NUMBER=NRS-GEN-xxxxx \
 *   node e2e/probes/badge-counts-both.mjs
 */
import { chromium } from '../node_modules/playwright/index.mjs';

const ORIGIN = process.env.E2E_ORIGIN ?? 'http://test19.localhost:8069';
const USER = process.env.PERSONA_USER;
const PASS = process.env.PERSONA_PASS;
const TAG = process.env.TAG_NUMBER;
const SHOTS = process.env.E2E_EVIDENCE ?? 'docs/handoffs/52-evidence';
if (!USER || !PASS || !TAG) { console.error('need PERSONA_USER, PERSONA_PASS, TAG_NUMBER'); process.exit(2); }

async function badge(page) {
  const b = page.getByTestId('nav-approvals-badge');
  return (await b.count()) ? (await b.textContent()).trim() : '(not drawn)';
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL: ORIGIN });
  await page.goto('/app/', { waitUntil: 'domcontentloaded' });
  const username = page.locator('input[autocomplete="username"]');
  await username.waitFor({ state: 'visible', timeout: 20000 });
  await username.fill(USER);
  await page.locator('input[autocomplete="current-password"]').fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByTestId('nav-facility-command-center').waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForTimeout(2500); // the badge query settles
  const before = await badge(page);
  await page.screenshot({ path: `${SHOTS}/badge-before.png` });

  // Approve the one replacement from the Approvals page (spec 51's path).
  await page.goto('/app/approvals', { waitUntil: 'domcontentloaded' });
  const row = page.locator(`[data-testid="replacement-row"]:has-text("${TAG}")`).first()
    .or(page.locator(`tr:has-text("${TAG}")`).first());
  await row.waitFor({ state: 'visible', timeout: 20000 });
  await row.getByTestId('button-approve-replacement').click();
  const dialog = page.getByTestId('dialog-approve-replacement');
  await dialog.waitFor({ state: 'visible', timeout: 10000 });
  await dialog.getByTestId('button-confirm-approve-replacement').click();
  await dialog.waitFor({ state: 'hidden', timeout: 30000 });
  await page.waitForTimeout(2500); // invalidation → badge refetch
  const after = await badge(page);
  await page.screenshot({ path: `${SHOTS}/badge-after.png` });

  console.log(JSON.stringify({ origin: ORIGIN, persona: USER, tag: TAG,
    badge_before: before, badge_after: after }, null, 2));
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });

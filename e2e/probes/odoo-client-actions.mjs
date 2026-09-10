/**
 * Probe: does an `ir.actions.client` MOUNT in the Odoo 19 backend web client?
 *
 * This exists because the same question has now been answered wrongly in BOTH
 * directions across five handoffs, from the source tree, by people reading
 * Odoo core and concluding that `odoo.define` modules requiring
 * `web.AbstractAction` cannot load on 19. They can: `myservice_nrs_base`
 * ships `static/src/js/legacy_compat.js`, which re-provides those module
 * names backed by real Odoo 19 services. The shim is invisible from Odoo's
 * source and decisive for ours — so the only sound evidence is a browser.
 *
 * Report 11 measured exactly this and never committed the probe, which is
 * why report 15 had to guess and guessed wrong. It is committed now.
 *
 * Run (from repo root):
 *   node e2e/probes/odoo-client-actions.mjs
 *   E2E_ORIGIN=http://nrs19.localhost:8069 node e2e/probes/odoo-client-actions.mjs
 *
 * Logs into Odoo's OWN backend (`/web/login`) — not the SPA, whose token the
 * rest of `e2e/` uses and which cannot reach a client action.
 */
import { chromium } from '../node_modules/playwright/index.mjs';

const ORIGIN = process.env.E2E_ORIGIN ?? 'http://jaizbankplc.localhost:8069';
const USER = process.env.E2E_USER ?? 'admin';
const PASS = process.env.E2E_PASS ?? 'admin';

// Every client action tag this repo registers, alive or retired. The retired
// ones are in the list deliberately: a probe that only looks at what it
// expects to work cannot tell "still dead" from "not checked".
const TAGS = [
  'myservice_dashboard',              // Operations Dashboard — carries the Fleet Command tab
  'barcode_station',
  'nrs_asset_dashboard',
  'myservice_fm_dashboard',
  'bus_dashboard',
  'myservice_fleet_dashboard',        // retired, handoff 11
  'nrs_security_command_center',      // retired
  'nrs_case_management',              // retired
  'myservice_security_dashboard',     // retired
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const errors = [];
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });

await page.goto(`${ORIGIN}/web/login`, { waitUntil: 'domcontentloaded' });
// Scope to the login FORM. `button[type=submit]` alone also matches the
// website theme's search button, which is present and invisible on this page.
const form = page.locator('form.oe_login_form, form:has(input[name="login"])').first();
await form.locator('input[name="login"]').fill(USER);
await form.locator('input[name="password"]').fill(PASS);
await Promise.all([
  page.waitForURL(/\/(odoo|web)/, { timeout: 30000 }),
  form.locator('button[type="submit"]').first().click(),
]);
console.log(`logged in at ${page.url()}`);

// `odoo.loader` is populated as the backend bundle executes, which is AFTER
// the navigation resolves. Evaluating too early reads `undefined`.
await page.waitForFunction(() => window.odoo && window.odoo.loader
  && window.odoo.loader.modules.has('@web/core/registry'), null, { timeout: 30000 });

// Which tags the OWL action registry actually knows about. This is the
// registration half; mounting is the other half and they fail separately.
const registered = await page.evaluate(async (tags) => {
  const reg = odoo.loader.modules.get('@web/core/registry').registry;
  const actions = reg.category('actions');
  return Object.fromEntries(tags.map((t) => [t, actions.contains(t)]));
}, TAGS);

const results = [];
for (const tag of TAGS) {
  errors.length = 0;
  let legacyBytes = 0, amBytes = 0, mounted = false, note = '';
  try {
    await page.goto(`${ORIGIN}/odoo/action-${tag}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);
    // THE discriminator. `legacy_compat.js`'s `LegacyAction` template is
    //   <div t-ref="root" class="o_client_action o_nrs_legacy_action"/>
    // so that class in the DOM means a legacy `odoo.define` client action
    // really mounted through the shim. Measuring `.o_action_manager` alone
    // does NOT work: an unresolvable tag still renders ~22 KB of Odoo's own
    // error surface there, which reads as a mount and is not one.
    const legacy = await page.$('.o_nrs_legacy_action');
    legacyBytes = legacy ? await legacy.evaluate((n) => n.outerHTML.length) : 0;
    const am = await page.$('.o_action_manager');
    amBytes = am ? await am.evaluate((n) => n.outerHTML.length) : 0;
    const dialog = await page.$('.o_dialog');
    if (dialog) note = (await dialog.innerText()).split('\n')[0].slice(0, 60);
    mounted = legacyBytes > 1000 && !dialog;
  } catch (e) {
    note = `navigation: ${e.message.split('\n')[0]}`;
  }
  results.push({ tag, registered: registered[tag], mounted, legacyBytes, amBytes,
                 errors: errors.length, sample: errors.slice(0, 2), note });
}

console.log('\ntag                              registered  mounted  legacy DOM  action-mgr  errors  note');
console.log('-'.repeat(104));
for (const r of results) {
  console.log(
    `${r.tag.padEnd(32)} ${String(r.registered).padEnd(11)} ${String(r.mounted).padEnd(8)} ` +
    `${String(r.legacyBytes).padStart(10)}  ${String(r.amBytes).padStart(10)}  ${String(r.errors).padStart(6)}  ${r.note}`);
  for (const s of r.sample) console.log(`    ${s.slice(0, 140)}`);
}

// The Fleet Command tab is a PANEL inside `myservice_dashboard`, not an
// action of its own, so mounting the host is necessary and not sufficient.
// Click the tab and measure what it renders.
console.log('\n--- Fleet Command tab, inside myservice_dashboard ---');
await page.goto(`${ORIGIN}/odoo/action-myservice_dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(4000);
errors.length = 0;
const tabBefore = await page.$('.ms-tab[data-tab="fleet"]');
console.log(`Fleet Command tab button present: ${!!tabBefore}`);
if (tabBefore) {
  await tabBefore.click();
  await page.waitForTimeout(4000);
  const panel = await page.$('[data-panel="fleet"]');
  const html = panel ? await panel.evaluate((n) => n.outerHTML.length) : 0;
  const visible = panel ? await panel.isVisible() : false;
  const kpis = await page.$$eval('[data-panel="fleet"] .ms-fleet-kval',
                                 (ns) => ns.map((n) => n.textContent.trim()));
  const loading = await page.$$eval('[data-panel="fleet"] .ms-fleet-empty',
                                    (ns) => ns.map((n) => n.textContent.trim()));
  console.log(`panel visible: ${visible}   DOM bytes: ${html}   console errors after click: ${errors.length}`);
  console.log(`KPI strip: ${JSON.stringify(kpis)}`);
  console.log(`still-loading placeholders: ${JSON.stringify(loading)}`);
  for (const s of errors.slice(0, 5)) console.log(`    ${s.slice(0, 160)}`);
}

await browser.close();

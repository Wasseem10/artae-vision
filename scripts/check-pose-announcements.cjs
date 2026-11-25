// Local accessibility DOM check with controlled missing poses, then real poses.
// Does not measure detection accuracy or speech output of a screen reader.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3343/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');
async function main() {
  const output = path.resolve(__dirname, '../artifacts/pose-announcements');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    await context.route('**/*', route => {
      const target = new URL(route.request().url());
      return target.origin !== origin || target.pathname.startsWith('/api/')
        ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }) : route.continue();
    });
    await context.addInitScript(() => {
      const Native = window.Worker;
      window.Worker = new Proxy(Native, { construct(Target, args) {
        const worker = new Target(...args);
        if (!String(args[0]).includes('pose-worker')) return worker;
        let results = 0;
        return new Proxy(worker, {
          get(target, prop) { const value = Reflect.get(target, prop, target); return typeof value === 'function' ? value.bind(target) : value; },
          set(target, prop, value) {
            if (prop === 'onmessage' && typeof value === 'function') target.onmessage = event => {
              if (event.data.type === 'result' && ++results <= 30) value(new MessageEvent('message', {
                data: { ...event.data, poses: [], primaryLandmarks: [], landmarks: [] },
              }));
              else value(event);
            };
            else Reflect.set(target, prop, value, target);
            return true;
          },
        });
      } });
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function() { if (!this.controls) this.playbackRate = .5; return play.call(this); };
    });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByLabel('Sample scenario').selectOption('sitting');
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    const warning = page.getByRole('status').filter({ hasText: 'Detection may miss a fall.' });
    await warning.waitFor({ timeout: 60000 });
    assert.equal((await warning.innerText()).includes('Body pose visible'), false, 'Changing percentage must be outside the live region');
    await warning.evaluate(hint => {
      const paragraph = hint.parentElement;
      window.__poseAnnouncements = { guidance: [hint.textContent], percentages: [] };
      new MutationObserver(() => {
        const state = window.__poseAnnouncements;
        if (state.guidance.at(-1) !== hint.textContent) state.guidance.push(hint.textContent);
        const percentage = Number(paragraph.textContent.match(/visible in (\d+)%/)?.[1]);
        if (Number.isFinite(percentage) && state.percentages.at(-1) !== percentage) state.percentages.push(percentage);
      }).observe(paragraph, { subtree: true, childList: true, characterData: true });
    });
    const recovered = page.getByRole('status').filter({ hasText: 'Keep each full body in view.' });
    await recovered.waitFor({ timeout: 30000 });
    const paragraph = recovered.locator('..');
    assert.equal(await paragraph.evaluate(el => !!el.closest('[aria-live], [role="status"], [role="alert"]')), false);
    const observations = await page.evaluate(() => window.__poseAnnouncements);
    assert.equal(observations.guidance.length, 2, 'Only the guidance transition changes announced text');
    assert.ok(observations.percentages.filter(n => n > 0 && n < 70).length >= 3, 'Exercise changing percentages within one guidance state');
    assert.equal(await page.locator('aside [aria-live="polite"]').count(), 1, 'Incident announcements remain enabled');
    await paragraph.screenshot({ path: path.join(output, 'desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await paragraph.screenshot({ path: path.join(output, 'mobile.png') });
    await page.getByRole('button', { name: 'Stop agent', exact: true }).click();
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ ...observations, pageErrors: errors, screenReaderSpeechVerified: false }, null, 2));
    console.log(JSON.stringify({ guidanceStates: observations.guidance.length, percentageUpdates: observations.percentages.length, pageErrors: errors.length }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

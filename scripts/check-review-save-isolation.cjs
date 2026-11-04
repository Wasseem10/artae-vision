// Local QA with real inference/recording and one deliberately failed database open.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3336/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const output = path.resolve(__dirname, '../artifacts/review-save-isolation');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.ARTAE_TEST_BROWSER || 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const results = [];
  try {
    for (const previousOutcome of [null, 'acknowledged']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        await context.route('**/*', route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
          return route.continue();
        });
        await context.addInitScript(() => {
          const openDatabase = indexedDB.open.bind(indexedDB);
          window.__reviewIsolation = { armReview: false, holdNext: false, held: false, fail: null, backgroundCommits: 0 };
          // Arm within this click's synchronous dispatch. Arming before Playwright
          // locates/clicks the button could intercept a recorder save instead.
          document.addEventListener('click', event => {
            if (window.__reviewIsolation.armReview && event.target.closest('button')?.textContent === 'Mark reviewed') {
              window.__reviewIsolation.armReview = false;
              window.__reviewIsolation.holdNext = true;
            }
          }, true);
          indexedDB.open = (...args) => {
            const request = openDatabase(...args);
            if (window.__reviewIsolation.holdNext) {
              window.__reviewIsolation.holdNext = false;
              Object.defineProperty(request, 'onsuccess', { configurable: true, set() {
                request.addEventListener('success', () => {
                  window.__reviewIsolation.held = true;
                  window.__reviewIsolation.fail = () => {
                    request.result.close();
                    window.__reviewIsolation.held = false;
                    Object.defineProperty(request, 'error', {
                      value: new DOMException('Injected review storage failure', 'UnknownError'),
                    });
                    request.onerror(new Event('error'));
                  };
                }, { once: true });
              } });
            }
            return request;
          };
          const transaction = IDBDatabase.prototype.transaction;
          IDBDatabase.prototype.transaction = function(stores, mode, ...rest) {
            const tx = transaction.call(this, stores, mode, ...rest);
            if (this.name === 'artae-browser-sessions' && mode === 'readwrite' && window.__reviewIsolation.held) {
              tx.addEventListener('complete', () => { window.__reviewIsolation.backgroundCommits++; });
            }
            return tx;
          };
        });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        await page.getByRole('button', { name: 'Start agent', exact: true }).click();
        await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
        // Give review setup time before the short source ends. Once evidence is
        // available, pause the source briefly while native recording stays active.
        const inputVideo = page.locator('video').first();
        await inputVideo.evaluate(video => { video.playbackRate = 0.5; });
        const reviewButton = page.getByRole('button', { name: 'Review footage', exact: true }).first();
        await reviewButton.waitFor({ timeout: 45000 });
        await inputVideo.evaluate(video => video.pause());
        assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 1,
          'The overlap fixture requires active recording');
        await reviewButton.click();
        const dialog = page.getByRole('dialog');
        if (previousOutcome) {
          await dialog.getByRole('button', { name: 'Acknowledge', exact: true }).click();
          await page.getByText('Review saved on this device', { exact: true }).waitFor();
        }
        await dialog.getByText('Reviewer note and response steps', { exact: true }).click();
        const note = page.getByLabel('Reviewer note (optional)');
        await note.fill('Review draft must survive a failed save.');
        await page.evaluate(() => { window.__reviewIsolation.armReview = true; });
        await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
        await page.waitForFunction(() => window.__reviewIsolation.held);
        await dialog.getByRole('status').filter({ hasText: 'Saving review…' }).waitFor();
        await dialog.press('Escape');
        // Stopping finalizes real recording segments and persists the shared session
        // while the separate review save is still waiting for its database open.
        const stop = page.getByRole('button', { name: 'Stop agent', exact: true });
        await stop.click();
        await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
        await page.waitForFunction(() => window.__reviewIsolation.backgroundCommits > 0);
        await page.evaluate(() => window.__reviewIsolation.fail());
        await page.getByRole('button', { name: 'Review footage', exact: true }).first().click();
        await dialog.getByRole('alert').filter({ hasText: 'Injected review storage failure' }).waitFor();
        assert.equal(await note.inputValue(), 'Review draft must survive a failed save.');
        assert.equal(await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).isEnabled(), true);
        assert.equal(await page.getByText('Closed · reviewed', { exact: true }).count(), 0);
        const persisted = await page.evaluate(async () => {
          const db = await new Promise((resolve, reject) => {
            const open = indexedDB.open('artae-browser-sessions', 2);
            open.onsuccess = () => resolve(open.result);
            open.onerror = () => reject(open.error);
          });
          try {
            const rows = await new Promise((resolve, reject) => {
              const get = db.transaction('sessions').objectStore('sessions').getAll();
              get.onsuccess = () => resolve(get.result);
              get.onerror = () => reject(get.error);
            });
            const session = rows.find(row => row.events.length);
            return { review: session.events[0].review ?? null, clips: session.clips.length,
              commits: window.__reviewIsolation.backgroundCommits };
          } finally { db.close(); }
        });
        assert.equal(persisted.review?.outcome ?? null, previousOutcome,
          'Background recording saves must not commit the failed review');
        assert.ok(persisted.clips > 0, 'Recording evidence must still be saved');
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await dialog.evaluate(element => element.scrollWidth > element.clientWidth + 1), false);
        await dialog.screenshot({ path: path.join(output, `failed-${previousOutcome || 'open'}.png`) });
        // The retained draft can be retried explicitly and must then survive reload.
        await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
        await page.getByText('Closed · reviewed', { exact: true }).waitFor();
        await page.getByText('Review saved on this device', { exact: true }).waitFor();
        await page.reload();
        await page.locator('#history').getByRole('button').filter({ hasText: 'Sample: fall-lateral' }).first().click();
        await page.getByRole('button', { name: 'Review footage', exact: true }).first().click();
        assert.equal(await note.inputValue(), 'Review draft must survive a failed save.');
        assert.equal(await dialog.getByRole('button', { name: 'Download incident report', exact: true }).isEnabled(), true);
        assert.deepEqual(errors, []);
        results.push({ previousOutcome, backgroundCommits: persisted.commits, savedClips: persisted.clips,
          failedReviewIsolated: true, draftRetained: true, retrySurvivedReload: true, pageErrors: errors.length });
        console.log(JSON.stringify(results.at(-1)));
      } finally { await context.close(); }
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

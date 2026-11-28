// Local QA: native IndexedDB with one delayed read, synthetic saved incidents,
// and a real model startup. External services and account APIs are unavailable.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3338/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const output = path.resolve(__dirname, '../artifacts/history-load-order');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.ARTAE_TEST_BROWSER || 'chromium', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const results = [];
  try {
    for (const mode of ['newer-history', 'stale-error', 'new-live-session', 'current-error']) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 950 } });
      let page;
      let releaseModel;
      const modelGate = new Promise(resolve => { releaseModel = resolve; });
      try {
        await context.route('**/*', async route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
          if (mode === 'new-live-session' && target.pathname.endsWith('.task')) await modelGate;
          return route.continue();
        });
        await context.addInitScript(() => {
          window.__historyQA = { held: false, release: null };
          const get = IDBObjectStore.prototype.get;
          IDBObjectStore.prototype.get = function(key) {
            const request = get.call(this, key);
            if (this.name === 'sessions' && key === 'guest/slow-a') {
              Object.defineProperty(request, 'onsuccess', { configurable: true, set(callback) {
                request.addEventListener('success', event => {
                  window.__historyQA.held = true;
                  window.__historyQA.release = fail => {
                    if (fail) {
                      Object.defineProperty(request, 'error', { value: new DOMException('Injected history read failure', 'UnknownError') });
                      request.onerror(new Event('error'));
                    } else callback.call(request, event);
                  };
                }, { once: true });
              } });
            }
            return request;
          };
        });
        page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
        await page.evaluate(async () => {
          const db = await new Promise((resolve, reject) => {
            const open = indexedDB.open('artae-browser-sessions', 2);
            open.onsuccess = () => resolve(open.result);
            open.onerror = () => reject(open.error);
          });
          try {
            await new Promise((resolve, reject) => {
              const tx = db.transaction('sessions', 'readwrite');
              for (const [id, name] of [['slow-a', 'Fixture A'], ['fast-b', 'Fixture B']]) {
                tx.objectStore('sessions').put({ key: `guest/${id}`, id, scope: 'guest', name, job: 'fall',
                  createdAt: '2026-11-08T12:00:00Z', clips: [],
                  events: [{ id: `${id}-event`, at: 1, title: `${name} incident`, visibility: .8 }] });
              }
              tx.oncomplete = resolve;
              tx.onerror = () => reject(tx.error);
            });
          } finally { db.close(); }
        });
        await page.reload();
        const history = page.locator('#history');
        await history.getByRole('button').filter({ hasText: 'Fixture A' }).click();
        await page.waitForFunction(() => window.__historyQA.held);
        if (mode === 'new-live-session') {
          await page.getByRole('button', { name: 'Start agent', exact: true }).click();
          await page.getByText('Loading pose model…', { exact: true }).waitFor();
        } else if (mode !== 'current-error') {
          await history.getByRole('button').filter({ hasText: 'Fixture B' }).click();
          await page.getByText('Fixture B incident', { exact: true }).waitFor();
        }
        await page.evaluate(fail => window.__historyQA.release(fail), mode.endsWith('error'));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const currentError = mode === 'current-error';
        assert.equal(await page.getByText('Fixture A incident', { exact: true }).count(), currentError ? 1 : 0,
          'A superseded load must not replace the current incident feed');
        assert.equal(await page.getByText('Local footage could not load. Trying the account copy if available.', { exact: true }).count(), currentError ? 1 : 0,
          'Only a current load error may change the current save status');
        if (mode === 'new-live-session') {
          assert.equal(await page.getByText('Loading pose model…', { exact: true }).count(), 1);
          releaseModel();
          await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
          await page.getByRole('button', { name: 'Stop agent', exact: true }).click();
          await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
        } else if (!currentError) {
          assert.equal(await page.getByText('Fixture B incident', { exact: true }).count(), 1);
        }
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.screenshot({ path: path.join(output, `${mode}.png`), fullPage: true });
        assert.deepEqual(errors, []);
        results.push({ mode, supersededLoadIgnored: !currentError, currentErrorShown: currentError, pageErrors: errors.length });
        console.log(JSON.stringify(results.at(-1)));
      } catch (error) {
        if (page) await page.screenshot({ path: path.join(output, `${mode}-failure.png`), fullPage: true });
        throw error;
      } finally { releaseModel(); await context.close(); }
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

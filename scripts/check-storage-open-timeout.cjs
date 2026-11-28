// Synthetic saved incident; hold one native IndexedDB open success callback.
// Verify timeout, late-connection cleanup and explicit retry without inference.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3344/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');
async function main() {
  const output = path.resolve(__dirname, '../artifacts/storage-open-timeout');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    await context.route('**/*', route => {
      const target = new URL(route.request().url());
      return target.origin !== origin || target.pathname.startsWith('/api/')
        ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }) : route.continue();
    });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
    await page.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const open = indexedDB.open('artae-browser-sessions', 2);
        open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
      });
      try {
        await new Promise((resolve, reject) => {
          const tx = db.transaction('sessions', 'readwrite');
          tx.objectStore('sessions').put({ key: 'guest/timeout-fixture', id: 'timeout-fixture', scope: 'guest',
            name: 'Storage timeout fixture', job: 'fall', createdAt: '2026-11-27T12:00:00Z', clips: [],
            events: [{ id: 'event-timeout', at: 5, title: 'Synthetic timeout incident', visibility: .8 }] });
          tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
        });
      } finally { db.close(); }
    });
    await page.reload();
    const openReview = async () => {
      await page.locator('#history').getByRole('button').filter({ hasText: 'Storage timeout fixture' }).click();
      await page.getByRole('button', { name: 'Review incident', exact: true }).click();
    };
    await openReview();
    const dialog = page.getByRole('dialog');
    await dialog.getByText('Reviewer note and response steps', { exact: true }).click();
    const note = dialog.getByLabel('Reviewer note (optional)');
    await note.fill('Keep this draft through a storage timeout.');
    await page.evaluate(() => {
      const nativeOpen = indexedDB.open.bind(indexedDB);
      window.__openTimeout = { arm: true, held: false, closes: 0, release: null };
      indexedDB.open = (...args) => {
        const request = nativeOpen(...args);
        if (window.__openTimeout.arm) {
          window.__openTimeout.arm = false;
          Object.defineProperty(request, 'onsuccess', { configurable: true, set(callback) {
            request.addEventListener('success', event => {
              const db = request.result, nativeClose = db.close.bind(db);
              db.close = () => { window.__openTimeout.closes++; nativeClose(); };
              window.__openTimeout.held = true;
              window.__openTimeout.release = () => callback.call(request, event);
            }, { once: true });
          } });
        }
        return request;
      };
    });
    await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
    await page.waitForFunction(() => window.__openTimeout.held);
    await dialog.getByRole('status').filter({ hasText: 'Saving review…' }).waitFor();
    const alert = dialog.getByRole('alert').filter({ hasText: 'Browser storage did not respond' });
    await alert.waitFor({ timeout: 20000 });
    assert.equal(await note.inputValue(), 'Keep this draft through a storage timeout.');
    assert.equal(await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).isEnabled(), true);
    assert.equal(await page.getByText('Closed · reviewed', { exact: true }).count(), 0);
    await page.evaluate(() => window.__openTimeout.release());
    assert.equal(await page.evaluate(() => window.__openTimeout.closes), 1, 'Close the abandoned connection');
    const storedReview = await page.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const open = indexedDB.open('artae-browser-sessions', 2);
        open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
      });
      try {
        return await new Promise((resolve, reject) => {
          const get = db.transaction('sessions').objectStore('sessions').get('guest/timeout-fixture');
          get.onsuccess = () => resolve(get.result.events[0].review ?? null); get.onerror = () => reject(get.error);
        });
      } finally { db.close(); }
    });
    assert.equal(storedReview, null, 'Late setup cannot commit the failed review');
    await dialog.screenshot({ path: path.join(output, 'desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await alert.scrollIntoViewIfNeeded();
    assert.equal(await dialog.evaluate(el => el.scrollWidth > el.clientWidth), false);
    await dialog.screenshot({ path: path.join(output, 'mobile.png') });
    await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
    await page.getByText('Closed · reviewed', { exact: true }).waitFor();
    await page.reload();
    await openReview();
    await dialog.getByText('Review complete. Your saved outcome is reflected in the event log.', { exact: true }).waitFor();
    await dialog.getByText('Reviewer note and response steps', { exact: true }).click();
    assert.equal(await note.inputValue(), 'Keep this draft through a storage timeout.');
    assert.deepEqual(errors, []);
    const result = { browser: browser.version(), timedOut: true, lateConnectionClosed: true,
      lateReviewNotCommitted: true, retrySurvivedReload: true, pageErrors: errors };
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

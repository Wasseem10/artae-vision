// Inject device write failures only. Use a real local model and native recorder.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3334/live';
const origin = new URL(url).origin;
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const browser = await chromium.launch({ channel: process.env.ARTAE_TEST_BROWSER || 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const output = path.resolve(__dirname, '../artifacts/storage-failure-replay');
  await fs.mkdir(output, { recursive: true });
  await fs.copyFile(path.resolve(__dirname, '../apps/web/public/vision/NOTICE.md'), path.join(output, 'NOTICE.md'));
  const results = [];
  try {
    for (const mode of ['blocked-writes', 'healthy']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        await context.route('**/*', route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
          return route.continue();
        });
        await context.addInitScript(mode => {
          const transaction = IDBDatabase.prototype.transaction;
          window.__storageFailures = 0;
          IDBDatabase.prototype.transaction = function(stores, access, ...rest) {
            if (mode === 'blocked-writes' && this.name === 'artae-browser-sessions' && access === 'readwrite') {
              window.__storageFailures++;
              throw new DOMException('Injected device write failure', 'QuotaExceededError');
            }
            return transaction.call(this, stores, access, ...rest);
          };
        }, mode);
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        await page.getByRole('button', { name: 'Start agent', exact: true }).click();
        await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
        await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
        await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
        const events = await page.getByRole('button', { name: 'Review footage', exact: true }).count();
        const warning = page.getByRole('alert').filter({ hasText: 'Local history could not be saved' });
        if (mode === 'blocked-writes') {
          await warning.waitFor();
          assert.ok(await page.evaluate(() => window.__storageFailures > 0));
        }
        const history = page.locator('#history').getByRole('button').filter({ hasText: 'Sample: fall-lateral' });
        await history.click();
        await page.getByText('Guest session · this browser only', { exact: true }).waitFor();
        await page.getByText('Session history · monitoring stopped', { exact: true }).waitFor();
        const playable = async () => page.waitForFunction(() => {
          const video = document.querySelector('video[aria-label="Recorded footage playback"]');
          return video?.readyState >= 2 && video.videoWidth > 0 && !video.error;
        }, null, { timeout: 15000 });
        await playable();
        assert.equal(await page.getByRole('button', { name: 'Review footage', exact: true }).count(), events);
        if (mode === 'blocked-writes') await warning.waitFor();
        const downloaded = page.waitForEvent('download');
        await page.getByRole('link', { name: 'Download this segment', exact: true }).click();
        const saved = path.join(output, `${mode}.webm`);
        await (await downloaded).saveAs(saved);
        assert.ok((await fs.stat(saved)).size > 1000);
        // A second click must not turn the retained full session into metadata.
        await history.click(); await playable();
        if (mode === 'blocked-writes') await warning.waitFor();
        await page.screenshot({ path: path.join(output, `${mode}.png`), fullPage: true });
        if (mode === 'blocked-writes') {
          await page.setViewportSize({ width: 390, height: 844 });
          await warning.scrollIntoViewIfNeeded();
          await page.screenshot({ path: path.join(output, 'blocked-writes-mobile.png') });
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        } else {
          // Another session must still load its own disk data, not the current run's memory.
          await page.getByLabel('Sample scenario').selectOption('sitting');
          await page.getByRole('button', { name: 'Start agent', exact: true }).click();
          await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
          await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
          await history.click(); await playable();
          assert.equal(await page.getByRole('button', { name: 'Review footage', exact: true }).count(), events);
        }
        await page.reload();
        if (mode === 'healthy') {
          await history.click(); await playable();
        } else {
          await page.getByText('No saved sessions yet. Your completed runs will appear here.', { exact: true }).waitFor();
          assert.equal(await history.count(), 0);
        }
        assert.deepEqual(errors, []);
        results.push({ mode, replayedTwice: true, retainedEvents: events, downloadBytes: (await fs.stat(saved)).size,
          survivesReload: mode === 'healthy', pageErrors: errors.length });
        console.log(`${mode}: passed`);
      } finally { await context.close(); }
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

// Local QA with synthetic session intervals and real sample-video playback.
// This verifies review disclosure, not inference or recorded-frame coverage.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3341/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');
async function main() {
  const output = path.resolve(__dirname, '../artifacts/review-recording-gap');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    await context.route('**/*', route => {
      const target = new URL(route.request().url());
      return target.origin !== origin || target.pathname.startsWith('/api/')
        ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }) : route.continue();
    });
    const page = await context.newPage();
    const errors = [];
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
          for (const [id, start, duration] of [['after', 5.03, 3], ['before', 0, 4.96], ['contained', 0, 8], ['missing', 0, 4]]) {
            tx.objectStore('sessions').put({ key: `guest/gap-${id}`, id: `gap-${id}`, scope: 'guest', name: `Gap fixture ${id}`,
              job: 'fall', createdAt: '2026-11-15T12:00:00Z',
              events: [{ id: `event-${id}`, at: 5, title: `Synthetic ${id} incident`, visibility: .8 }],
              clips: [{ id: `clip-${id}`, start, duration, width: 640, height: 480,
                url: `${location.origin}/vision/samples/fall-lateral.mp4` }] });
          }
          tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
        });
      } finally { db.close(); }
    });
    await page.reload();
    const results = [];
    for (const [id, gap] of [['after', 30], ['before', 40], ['contained', 0], ['missing', null]]) {
      await page.locator('#history').getByRole('button').filter({ hasText: `Gap fixture ${id}` }).click();
      await page.getByText(`Synthetic ${id} incident`, { exact: true }).waitFor();
      const review = page.getByRole('button', { name: 'Review footage', exact: true });
      if (gap === null) {
        assert.equal(await review.isDisabled(), true);
        await page.getByText('No recording is available for this event.', { exact: true }).waitFor();
        results.push({ id, reviewDisabled: true });
        continue;
      }
      await review.click();
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      const notice = dialog.getByRole('status').filter({ hasText: 'Nearby recording only.' });
      assert.equal(await notice.count(), gap > 0 ? 1 : 0, `${id}: disclose only a nearby interval`);
      if (gap) {
        assert.ok((await notice.innerText()).includes(`about ${gap} ms gap`));
        assert.equal(await dialog.getByText(/Playback starts up to three seconds/).count(), 0);
      }
      await page.waitForFunction(seek => {
        const video = document.querySelector('video[aria-label="Incident evidence playback"]');
        return video?.readyState >= 2 && video.videoWidth > 0 && !video.error && !video.seeking && Math.abs(video.currentTime - seek) < .15;
      }, id === 'after' ? 0 : 2);
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await dialog.evaluate(el => el.scrollWidth > el.clientWidth), false);
      await dialog.screenshot({ path: path.join(output, `${id}-mobile.png`) });
      await page.setViewportSize({ width: 1400, height: 1000 });
      await dialog.screenshot({ path: path.join(output, `${id}-desktop.png`) });
      // Complete review on mobile as well: actions below the fold must remain reachable.
      await page.setViewportSize({ width: 390, height: 844 });
      await dialog.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
      const downloaded = page.waitForEvent('download');
      await dialog.getByRole('button', { name: 'Download incident report', exact: true }).click();
      const reportPath = path.join(output, `${id}-report.html`);
      await (await downloaded).saveAs(reportPath);
      const report = await fs.readFile(reportPath, 'utf8');
      assert.equal(report.includes('does not contain the event timestamp'), gap > 0);
      if (gap) assert.ok(report.includes(`approximately ${gap} ms`));
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      results.push({ id, gapMilliseconds: gap, reportAgrees: true, decodedPlayback: true });
    }
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), results, pageErrors: errors }, null, 2));
    console.log(JSON.stringify({ results, pageErrors: errors.length }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

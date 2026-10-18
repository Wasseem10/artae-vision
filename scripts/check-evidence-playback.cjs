// Local production-build QA: real detection/recording plus corrupt bytes,
// a missing HTTP recording, and a held media response. No production API calls.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3320/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const fixture = await fs.readFile(path.resolve(__dirname, '../apps/web/public/vision/samples/fall-lateral.mp4'));
  const output = path.resolve(__dirname, '../artifacts/evidence-playback');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  let releaseSlow;
  const slowGate = new Promise((resolve) => { releaseSlow = resolve; });
  let networkRequests = 0, slowRequests = 0;
  const serveVideo = async (route) => {
    const headers = { 'accept-ranges': 'bytes' };
    const range = route.request().headers().range;
    if (!range) return route.fulfill({ status: 200, contentType: 'video/mp4', headers, body: fixture });
    const match = /^bytes=(\d+)-(\d*)$/.exec(range);
    assert.ok(match, 'Unexpected test range');
    const start = Number(match[1]);
    const end = match[2] ? Math.min(Number(match[2]), fixture.length - 1) : fixture.length - 1;
    assert.ok(start >= 0 && start <= end, 'Invalid test range');
    await route.fulfill({ status: 206, contentType: 'video/mp4',
      headers: { ...headers, 'content-range': `bytes ${start}-${end}/${fixture.length}` },
      body: fixture.subarray(start, end + 1) });
  };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route('**/*', async (route) => {
      const request = new URL(route.request().url());
      if (request.pathname === '/__playback-test/network.mp4') {
        networkRequests++;
        if (networkRequests === 1) await route.fulfill({ status: 404, body: 'Missing test recording' });
        else await serveVideo(route);
      } else if (request.pathname === '/__playback-test/slow.mp4') {
        slowRequests++;
        if (slowRequests === 1) {
          await slowGate;
          // The original request may be cancelled when Retry removes its player.
          await route.fulfill({ status: 404, body: 'Late failed response' }).catch(() => {});
        } else await serveVideo(route);
      } else if (request.origin !== origin || request.pathname.startsWith('/api/v1/')) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Local QA only"}' });
      } else await route.continue();
    });
    await context.addInitScript(() => {
      const create = URL.createObjectURL.bind(URL);
      window.__playbackFault = 'none';
      URL.createObjectURL = (blob) => {
        if (blob.type.startsWith('video/') && window.__playbackFault !== 'none') {
          const mode = window.__playbackFault;
          window.__playbackFault = 'none';
          if (mode === 'corrupt') return create(new Blob(['Invalid recording bytes'], { type: 'video/webm' }));
          return `${location.origin}/__playback-test/${mode}.mp4`;
        }
        return create(blob);
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(url);
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
    const footage = page.getByRole('heading', { name: 'Recorded footage', exact: true }).locator('..');
    const clip = footage.getByRole('button').filter({ hasText: /^\d+:\d+–/ }).first();
    await clip.waitFor();
    const ready = async (label, seek) => {
      try { await page.waitForFunction(({ label, seek }) => {
      const video = document.querySelector(`video[aria-label="${label}"]`);
      return video?.readyState >= 2 && video.videoWidth > 0 && !video.error &&
        (seek === null || Math.abs(video.currentTime - seek) < 0.15);
      }, { label, seek }, { timeout: 15000 }); }
      catch (error) {
        console.error('PLAYBACK_DIAGNOSTIC', JSON.stringify(await page.evaluate(() =>
          [...document.querySelectorAll('video[controls]')].map((video) => ({ label: video.getAttribute('aria-label'),
            src: video.getAttribute('src'), readyState: video.readyState, time: video.currentTime,
            duration: video.duration, error: video.error?.code,
            seekable: [...Array(video.seekable.length)].map((_, index) => [video.seekable.start(index), video.seekable.end(index)]) })))), 'expectedSeek', seek,
        'requests', networkRequests, slowRequests);
        throw error;
      }
    };

    await page.evaluate(() => { window.__playbackFault = 'corrupt'; });
    await clip.click();
    await footage.getByRole('alert').filter({ hasText: 'cannot be decoded' }).waitFor();
    await footage.getByRole('button', { name: 'Retry playback', exact: true }).click();
    await footage.getByRole('alert').filter({ hasText: 'cannot be decoded' }).waitFor();
    // A retry cannot repair corrupt bytes. Selecting healthy saved footage can.
    await clip.click();
    await ready('Recorded footage playback', 0);
    assert.equal(await footage.getByRole('button', { name: 'Retry playback', exact: true }).count(), 0);
    console.log('CORRUPT_BYTES_OK: explicit error, failed retry stays honest, selecting healthy footage recovers');
    await page.evaluate(async () => {
      window.__playingPreview = document.querySelector('video[aria-label="Recorded footage playback"]');
      await window.__playingPreview.play();
    });

    const expectedSeek = await page.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const open = indexedDB.open('artae-browser-sessions', 2);
        open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
      });
      try {
        const sessions = await new Promise((resolve, reject) => {
          const read = db.transaction('sessions').objectStore('sessions').getAll();
          read.onsuccess = () => resolve(read.result); read.onerror = () => reject(read.error);
        });
        const session = sessions.find((row) => row.events.length && row.clips.length);
        const event = session.events[0];
        const clip = session.clips.find((row) => row.start <= event.at && row.start + row.duration >= event.at);
        if (!clip) throw new Error('Fixture incident must be inside one recorded segment');
        return Math.max(0, event.at - 3 - clip.start);
      } finally { db.close(); }
    });
    await page.evaluate(() => { window.__playbackFault = 'network'; });
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    assert.equal(await page.evaluate(() => window.__playingPreview.paused), true,
      'Opening incident playback must pause the removed recorded-footage player');
    await dialog.getByRole('alert').filter({ hasText: /recording.*(unavailable|downloaded)/ }).waitFor();
    await page.getByText('Reviewer note and response steps', { exact: true }).click();
    const note = page.getByLabel('Reviewer note (optional)');
    await note.fill('Draft retained through a recording load failure and retry.');
    assert.equal(networkRequests, 1, 'No automatic media retry loop');
    const retry = dialog.getByRole('button', { name: 'Retry playback', exact: true });
    await retry.focus(); await retry.press('Enter');
    await ready('Incident evidence playback', expectedSeek);
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('video[aria-label="Incident evidence playback"]')), true,
      'Keyboard retry must return focus to the replacement native player');
    assert.ok(networkRequests >= 2, 'Manual retry must fetch the recording again');
    assert.equal(await dialog.getByRole('alert').count(), 0);
    assert.equal(await note.inputValue(), 'Draft retained through a recording load failure and retry.');
    console.log('NETWORK_RETRY_OK: native missing-media error, keyboard retry, incident seek and draft preserved');

    await dialog.press('Escape');
    await page.evaluate(() => { window.__playbackFault = 'slow'; });
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().click();
    await dialog.getByRole('status').filter({ hasText: 'Loading recording…' }).waitFor();
    await dialog.getByRole('alert').filter({ hasText: 'taking too long' }).waitFor({ timeout: 20000 });
    assert.equal(slowRequests, 1);
    await dialog.screenshot({ path: path.join(output, 'desktop-timeout.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    assert.equal(await dialog.evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    await dialog.screenshot({ path: path.join(output, 'mobile-timeout.png') });
    await page.evaluate(() => { window.__previousPlayer = document.querySelector('video[aria-label="Incident evidence playback"]'); });
    await dialog.getByRole('button', { name: 'Retry playback', exact: true }).click();
    await ready('Incident evidence playback', expectedSeek);
    releaseSlow();
    await page.evaluate(async () => {
      window.__previousPlayer.dispatchEvent(new Event('error'));
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    assert.equal(await dialog.getByRole('alert').count(), 0, 'Late errors must not replace the new attempt');
    assert.equal(await note.inputValue(), 'Draft retained through a recording load failure and retry.');
    await page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
    await page.getByText('Closed · reviewed', { exact: true }).waitFor();
    await dialog.press('Escape');
    await page.reload();
    await page.getByRole('button').filter({ hasText: 'Sample: fall-lateral' }).first().click();
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().click();
    await ready('Incident evidence playback', expectedSeek);
    assert.equal(await note.inputValue(), 'Draft retained through a recording load failure and retry.');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ timeoutRecovery: true, staleErrorIgnored: true, reviewSurvivedReload: true,
      mobileWidth: 390, networkRequests, slowRequests, runtimeErrors: errors.length, browserVersion: browser.version() }));
    await context.close();
  } finally { releaseSlow(); await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });

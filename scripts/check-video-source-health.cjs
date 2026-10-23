// Real local model/recording, with paused video and Chrome's synthetic camera.
// No physical camera, account, cloud API, or external media access.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3330/live';
const origin = new URL(url).origin;
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
      '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const output = path.resolve(__dirname, '../artifacts/video-source-health');
  await fs.mkdir(output, { recursive: true });
  const results = [];
  try {
    for (const mode of ['frozen-video', 'brief-pause', 'camera-ended']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        await context.route('**/*', route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Local QA"}' });
          return route.continue();
        });
        await context.addInitScript(() => {
          window.__sourceQA = { terminated: 0, tracks: [], captureTracks: [] };
          const Native = window.Worker;
          window.Worker = new Proxy(Native, { construct(Target, args) {
            const worker = new Target(...args), terminate = worker.terminate.bind(worker);
            worker.terminate = () => { window.__sourceQA.terminated++; terminate(); };
            return worker;
          } });
          const get = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          navigator.mediaDevices.getUserMedia = async constraints => {
            const stream = await get(constraints);
            window.__sourceQA.tracks.push(...stream.getTracks());
            return stream;
          };
          const capture = HTMLCanvasElement.prototype.captureStream;
          HTMLCanvasElement.prototype.captureStream = function(...args) {
            const stream = capture.apply(this, args);
            window.__sourceQA.captureTracks.push(...stream.getTracks());
            return stream;
          };
        });
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        if (mode === 'camera-ended') await page.getByLabel('2. Connect video').selectOption('webcam');
        else if (mode === 'brief-pause') await page.getByLabel('Sample scenario').selectOption('sitting');
        const start = () => page.getByRole('button', { name: 'Start agent', exact: true }).click();
        const analyzed = () => page.evaluate(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]));
        await start();
        await page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 5, null, { timeout: 60000 });
        let eventsBefore = 0;
        if (mode === 'frozen-video') {
          await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
          eventsBefore = await page.getByRole('button', { name: 'Review footage', exact: true }).count();
          await page.locator('video:not([controls])').evaluate(video => video.pause());
        } else if (mode === 'camera-ended') {
          const labels = await page.evaluate(() => window.__sourceQA.tracks.map(track => track.label));
          assert.ok(labels.length && labels.every(label => /fake/i.test(label)), 'Only synthetic camera input permitted');
          await page.evaluate(() => window.__sourceQA.tracks.forEach(track => track.stop()));
        } else {
          await page.locator('video:not([controls])').evaluate(video => video.pause());
          await page.waitForTimeout(3000);
          assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 1);
          const before = await analyzed();
          await page.locator('video:not([controls])').evaluate(video => video.play());
          await page.waitForFunction(before => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= before + 5, before, { timeout: 15000 });
          await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
          assert.equal(await page.getByRole('alert').filter({ hasText: 'video source stopped advancing' }).count(), 0);
        }
        if (mode !== 'brief-pause') {
          const reason = mode === 'camera-ended' ? 'camera disconnected' : 'video source stopped advancing for 15 seconds';
          await page.getByRole('alert').filter({ hasText: reason }).waitFor({ timeout: 22000 });
          await page.getByText('Monitoring stopped', { exact: true }).waitFor();
          assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 0);
          assert.ok(await page.evaluate(() => window.__sourceQA.terminated > 0));
          assert.ok(await page.evaluate(() => window.__sourceQA.captureTracks.length > 0 && window.__sourceQA.captureTracks.every(track => track.readyState === 'ended')));
          const stoppedFrames = await analyzed();
          await page.waitForTimeout(500);
          assert.equal(await analyzed(), stoppedFrames);
          assert.equal(await page.getByRole('button', { name: 'Review footage', exact: true }).count(), eventsBefore);
          if (mode === 'frozen-video') {
            const footage = page.getByRole('heading', { name: 'Recorded footage', exact: true }).locator('..');
            await footage.getByRole('button').filter({ hasText: /^\d+:\d+–/ }).first().click();
            await page.waitForFunction(() => {
              const video = document.querySelector('video[aria-label="Recorded footage playback"]');
              return video?.readyState >= 2 && video.videoWidth > 0 && !video.error;
            });
          }
          await page.screenshot({ path: path.join(output, `${mode}-desktop.png`), fullPage: true });
          await page.setViewportSize({ width: 390, height: 844 });
          await page.getByRole('alert').filter({ hasText: reason }).scrollIntoViewIfNeeded();
          await page.screenshot({ path: path.join(output, `${mode}-mobile.png`) });
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          // Fresh source/session works without reloading; normal EOF isn't reported as a source failure.
          await page.getByLabel('2. Connect video').selectOption('sample');
          await page.getByLabel('Sample scenario').selectOption('sitting');
          await start();
          await page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 5, null, { timeout: 60000 });
          assert.equal(await page.getByRole('alert').filter({ hasText: reason }).count(), 0);
          await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
          assert.equal(await page.getByRole('alert').filter({ hasText: 'video source stopped advancing' }).count(), 0);
        }
        assert.deepEqual(errors, []);
        results.push({ mode, passed: true, browserErrors: errors.length, eventsRetained: eventsBefore });
        console.log(`${mode}: passed`);
      } finally { await context.close(); }
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

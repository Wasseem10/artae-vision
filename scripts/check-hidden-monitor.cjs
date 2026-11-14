// Controlled Page Visibility signals with real local pose inference/recording.
// This exercises app cleanup, not OS sleep or real background timer throttling.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3336/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const output = path.resolve(__dirname, '../artifacts/hidden-monitor');
  await fs.mkdir(output, { recursive: true });
  await fs.copyFile(path.resolve(__dirname, '../apps/web/public/vision/NOTICE.md'), path.join(output, 'NOTICE.md'));
  const browser = await chromium.launch({ channel: process.env.ARTAE_TEST_BROWSER || 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
      '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const results = [];
  try {
    for (const mode of ['loading', 'sample', 'camera']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        await context.route('**/*', route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
          return route.continue();
        });
        await context.addInitScript(mode => {
          const qa = window.__visibilityQA = { hidden: false, holdInit: mode === 'loading',
            initRequests: 0, terminated: 0, camera: [], capture: [] };
          Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => qa.hidden ? 'hidden' : 'visible' });
          Object.defineProperty(document, 'hidden', { configurable: true, get: () => qa.hidden });
          const Native = window.Worker;
          window.Worker = new Proxy(Native, { construct(Target, args) {
            const worker = new Target(...args), post = worker.postMessage.bind(worker), terminate = worker.terminate.bind(worker);
            worker.postMessage = (...args) => {
              if (args[0]?.type === 'init') { qa.initRequests++; if (qa.holdInit) return; }
              return post(...args);
            };
            worker.terminate = () => { qa.terminated++; terminate(); };
            return worker;
          } });
          const get = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          navigator.mediaDevices.getUserMedia = async constraints => {
            const stream = await get(constraints); qa.camera.push(...stream.getTracks()); return stream;
          };
          const capture = HTMLCanvasElement.prototype.captureStream;
          HTMLCanvasElement.prototype.captureStream = function(...args) {
            const stream = capture.apply(this, args); qa.capture.push(...stream.getTracks()); return stream;
          };
        }, mode);
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        const visibility = hidden => page.evaluate(hidden => {
          window.__visibilityQA.hidden = hidden;
          document.dispatchEvent(new Event('visibilitychange'));
        }, hidden);
        const start = page.getByRole('button', { name: 'Start agent', exact: true });
        const frames = () => page.evaluate(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]));
        const analyzed = () => page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 5, null, { timeout: 60000 });
        if (mode === 'loading') {
          // A start while already hidden must not create a worker or session.
          await visibility(true); await start.click();
          await page.getByRole('alert').filter({ hasText: 'Keep this tab visible before starting' }).waitFor();
          assert.equal(await page.evaluate(() => window.__visibilityQA.initRequests), 0);
          await visibility(false);
        }
        if (mode === 'camera') await page.getByLabel('2. Connect video').selectOption('webcam');
        await start.click();
        let events = 0;
        if (mode === 'loading') {
          await page.waitForFunction(() => window.__visibilityQA.initRequests === 1);
        } else {
          await analyzed();
          if (mode === 'sample') {
            await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
            events = await page.getByRole('button', { name: 'Review footage', exact: true }).count();
          } else {
            const labels = await page.evaluate(() => window.__visibilityQA.camera.map(t => t.label));
            assert.ok(labels.length && labels.every(label => /fake/i.test(label)), 'Synthetic camera only');
          }
        }
        await visibility(true);
        const warning = page.getByRole('alert').filter({ hasText: 'Monitoring stopped because this tab was hidden' });
        await warning.waitFor(); await start.waitFor();
        await page.getByText('Monitoring stopped', { exact: true }).waitFor();
        assert.equal(await page.evaluate(() => window.__visibilityQA.terminated), 1);
        await page.waitForFunction(() => [...window.__visibilityQA.camera, ...window.__visibilityQA.capture].every(t => t.readyState === 'ended'));
        const stoppedFrames = await frames();
        await visibility(false);
        await page.waitForTimeout(750);
        assert.equal(await frames(), stoppedFrames);
        await warning.waitFor();
        assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 0);
        assert.equal(await page.getByRole('button', { name: 'Review footage', exact: true }).count(), events);
        if (mode === 'sample') {
          const footage = page.getByRole('heading', { name: 'Recorded footage', exact: true }).locator('..');
          await footage.getByRole('button').filter({ hasText: /^\d+:\d+–/ }).first().click();
          await page.waitForFunction(() => {
            const v = document.querySelector('video[aria-label="Recorded footage playback"]');
            return v?.readyState >= 2 && v.videoWidth > 0 && !v.error;
          });
        }
        await page.screenshot({ path: path.join(output, `${mode}.png`), fullPage: true });
        if (mode === 'sample') {
          await page.setViewportSize({ width: 390, height: 844 });
          await warning.scrollIntoViewIfNeeded();
          await page.screenshot({ path: path.join(output, 'sample-mobile.png') });
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        }
        // No automatic resume, but explicit restart uses a fresh worker/session.
        await page.evaluate(() => { window.__visibilityQA.holdInit = false; });
        await page.getByLabel('2. Connect video').selectOption('sample');
        await page.getByLabel('Sample scenario').selectOption('sitting');
        await start.click(); await analyzed();
        assert.equal(await warning.count(), 0);
        // A redundant visible event must not stop a healthy foreground session.
        await visibility(false);
        assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 1);
        await page.getByRole('button', { name: 'Stop agent', exact: true }).click();
        await page.getByText('Monitoring stopped', { exact: true }).waitFor();
        await visibility(true);
        assert.equal(await warning.count(), 0, 'Stopped sessions must remove their visibility listener');
        assert.equal(await page.evaluate(() => window.__visibilityQA.terminated), 2);
        assert.deepEqual(errors, []);
        results.push({ mode, eventsRetained: events, stoppedFrames, restarted: true, pageErrors: 0 });
        console.log(`${mode}: passed`);
      } finally { await context.close(); }
    }
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ browser: browser.version(), simulatedVisibility: true, results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

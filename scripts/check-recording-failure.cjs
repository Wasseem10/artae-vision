// Local production-build QA. Real MediaPipe and native recording, with explicit
// capture/encoder fault injection. Blocks all nonlocal requests and API calls.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3320/live';
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const output = path.resolve(__dirname, '../artifacts/recording-failure');
  await fs.mkdir(output, { recursive: true });
  try {
    for (const mode of ['capture', 'constructor', 'start', 'runtime', 'healthy']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const errors = [];
      try {
        await context.route('**/*', async (route) => {
          const requestUrl = new URL(route.request().url());
          if (requestUrl.origin !== new URL(url).origin || requestUrl.pathname.startsWith('/api/v1/')) {
            await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Local recording fault test: API unavailable' }) });
          } else await route.continue();
        });
        await context.addInitScript((mode) => {
          const originalCapture = HTMLCanvasElement.prototype.captureStream;
          const NativeRecorder = window.MediaRecorder;
          window.__recordingTest = { creates: 0, recorders: [], streams: [] };
          HTMLCanvasElement.prototype.captureStream = function(...args) {
            if (mode === 'capture') throw new DOMException('Injected capture failure', 'NotSupportedError');
            const stream = originalCapture.apply(this, args);
            window.__recordingTest.streams.push(stream);
            return stream;
          };
          window.MediaRecorder = new Proxy(NativeRecorder, { construct(Target, args) {
            window.__recordingTest.creates++;
            if (mode === 'constructor') throw new DOMException('Injected encoder failure', 'NotSupportedError');
            const recorder = new Target(...args);
            if (mode === 'start') recorder.start = () => { throw new DOMException('Injected start failure', 'NotSupportedError'); };
            window.__recordingTest.recorders.push(recorder);
            return recorder;
          } });
          // Give the runtime fault a longer post-failure observation window.
          if (mode === 'runtime') {
            const play = HTMLMediaElement.prototype.play;
            HTMLMediaElement.prototype.play = function() { if (!this.controls) this.playbackRate = 0.5; return play.call(this); };
          }
        }, mode);
        const page = await context.newPage();
        page.on('pageerror', (error) => errors.push(error.message));
        await page.goto(url);
        await page.getByLabel('Sample scenario').selectOption(mode === 'healthy' || mode === 'runtime' ? 'sitting' : 'fall-lateral');
        await page.getByRole('button', { name: 'Start agent', exact: true }).click();
        await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
        await page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 5, null, { timeout: 30000 });
        const footage = page.getByRole('heading', { name: 'Recorded footage', exact: true }).locator('..');
        if (mode === 'runtime' || mode === 'healthy') {
          await footage.getByRole('button').first().waitFor({ timeout: 15000 });
        }
        if (mode === 'runtime') {
          await page.evaluate(() => window.__recordingTest.recorders.at(-1).dispatchEvent(new Event('error')));
        }
        if (mode !== 'healthy') {
          await footage.getByRole('alert').filter({ hasText: 'Recording stopped.' }).waitFor();
          assert.equal(await page.getByText('Recording the first segment. Evidence becomes playable in about 10 seconds.', { exact: true }).count(), 0);
          const before = await page.evaluate(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]));
          await page.waitForFunction((before) => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= before + 5,
            before, { timeout: 10000 });
          if (mode !== 'runtime') {
            await page.getByText('No recording is available for this event.', { exact: true }).first().waitFor({ timeout: 30000 });
            assert.equal(await page.getByText('Recording this event’s evidence…', { exact: true }).count(), 0);
          }
        }
        if (mode === 'healthy') {
          const before = await page.evaluate(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]));
          await page.waitForFunction((before) => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= before + 5,
            before, { timeout: 10000 });
        }
        const stop = page.getByRole('button', { name: 'Stop agent', exact: true });
        if (await stop.count()) await stop.click();
        await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
        await page.waitForFunction(() => window.__recordingTest.streams.every((stream) => stream.getTracks().every((track) => track.readyState === 'ended')));
        if (mode === 'healthy' || mode === 'runtime') {
          await footage.getByRole('button').first().click();
          await page.waitForFunction(() => {
            const video = document.querySelector('video[aria-label="Recorded footage playback"]');
            return video?.readyState >= 1 && video.videoWidth > 0;
          });
        }
        if (mode === 'runtime') {
          await footage.screenshot({ path: path.join(output, 'desktop-runtime-failure.png') });
          await page.setViewportSize({ width: 390, height: 844 });
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
          await footage.screenshot({ path: path.join(output, 'mobile-runtime-failure.png') });
        }
        const evidence = await page.evaluate(() => ({
          constructors: window.__recordingTest.creates,
          recordingTracksEnded: window.__recordingTest.streams.every((stream) => stream.getTracks().every((track) => track.readyState === 'ended')),
        }));
        if (mode === 'capture') assert.equal(evidence.constructors, 0);
        else if (['constructor', 'start'].includes(mode)) assert.equal(evidence.constructors, 1);
        else assert.equal(evidence.constructors, 2, 'Exactly one normal rotation; no failure retry loop');
        assert.deepEqual(errors, [], 'No uncaught browser errors');
        console.log(JSON.stringify({ mode, ...evidence, playableFootage: mode === 'healthy' || mode === 'runtime', runtimeErrors: errors.length }));
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });

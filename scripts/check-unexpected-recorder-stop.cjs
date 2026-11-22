// Controlled native-recorder stop; real local inference and recording bytes.
// This does not simulate or validate a particular OS/hardware failure.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3342/live';
const origin = new URL(url).origin;
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const output = path.resolve(__dirname, '../artifacts/unexpected-recorder-stop');
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
      const NativeRecorder = window.MediaRecorder;
      window.__recorderQA = [];
      window.MediaRecorder = class extends NativeRecorder {
        constructor(...args) {
          super(...args);
          window.__recorderQA.push({ recorder: this, createdAt: performance.now() });
        }
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.waitForFunction(() => window.__recorderQA[0]?.recorder.state === 'recording' &&
      performance.now() - window.__recorderQA[0].createdAt > 1500, null, { timeout: 60000 });
    await page.evaluate(() => window.__recorderQA[0].recorder.stop());
    const warning = page.getByRole('alert').filter({ hasText: 'Recording stopped. New footage is unavailable.' });
    await warning.waitFor({ timeout: 5000 });
    assert.match(await warning.innerText(), /Detection continues/);
    const footage = page.getByRole('heading', { name: 'Recorded footage', exact: true }).locator('..');
    const clip = footage.getByRole('button').filter({ hasText: /^\d+:\d+–/ }).first();
    await clip.click();
    await page.waitForFunction(() => {
      const video = document.querySelector('video[aria-label="Recorded footage playback"]');
      return video?.readyState >= 2 && video.videoWidth > 0 && !video.error;
    });
    // A later real sample incident proves inference survives recording failure.
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
    assert.equal(await page.getByRole('button', { name: 'Review footage', exact: true }).first().isDisabled(), true);
    await page.getByText('No recording is available for this event.', { exact: true }).first().waitFor();
    assert.equal(await page.evaluate(() => window.__recorderQA.length), 1, 'No automatic recorder restart');
    assert.equal(await page.evaluate(() => window.__recorderQA[0].recorder.stream.getTracks().every(t => t.readyState === 'ended')), true);
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
    await footage.screenshot({ path: path.join(output, 'desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await footage.screenshot({ path: path.join(output, 'mobile.png') });
    // Explicit restart creates a fresh recording; the old failure does not stick.
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.waitForFunction(() => window.__recorderQA.length === 2 && window.__recorderQA[1].recorder.state === 'recording');
    assert.equal(await warning.count(), 0);
    await page.getByRole('button', { name: 'Review footage', exact: true }).first().waitFor({ timeout: 30000 });
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === 'Review footage' && !b.disabled));
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
    assert.deepEqual(errors, []);
    const result = { retainedDecodedFootage: true, detectionContinued: true, missingIncidentEvidenceDisclosed: true,
      noAutomaticRestart: true, explicitRestartRecovered: true, pageErrors: errors };
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

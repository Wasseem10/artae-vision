// Record the actual local staged-sample workflow at normal playback speed.
// No fake detections, injected model outputs, microphone, or cloud service.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3320/live';
const origin = new URL(url).origin;
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname), 'Local capture only');
async function main() {
  const root = path.resolve(__dirname, '..');
  const outputBase = path.join(root, 'artifacts/recruiter-demo');
  await fs.mkdir(outputBase, { recursive: true });
  const output = await fs.mkdtemp(path.join(outputBase, 'take-'));
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
    recordVideo: { dir: output, size: { width: 1440, height: 1000 } } });
  let video;
  const steps = [], errors = [];
  const began = Date.now();
  const mark = step => steps.push({ step, elapsedSeconds: (Date.now() - began) / 1000 });
  try {
    await context.route('**/*', route => {
      const target = new URL(route.request().url());
      if (target.origin !== origin || target.pathname.startsWith('/api/'))
        return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Offline demonstration"}' });
      return route.continue();
    });
    const page = await context.newPage();
    video = page.video();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByLabel('Sample scenario').selectOption('fall-lateral');
    mark('Staged sample selected');
    await page.waitForTimeout(1500);
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    mark('Start requested');
    await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
    mark('Real inference started');
    const review = page.getByRole('button', { name: 'Review footage', exact: true });
    await review.waitFor({ timeout: 30000 });
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Review footage' && !b.disabled), null, { timeout: 30000 });
    mark('Possible fall with playable evidence');
    await page.screenshot({ path: path.join(output, 'incident.png'), fullPage: true });
    await review.click();
    await page.getByRole('dialog').waitFor();
    const playback = page.getByRole('dialog').locator('video');
    await playback.evaluate(v => v.play());
    mark('Evidence replay');
    await page.waitForTimeout(4000);
    await page.getByText('Reviewer note and response steps', { exact: true }).click();
    await page.getByLabel('Reviewer note (optional)').fill('Staged demo footage reviewed. This demonstrates the review workflow; no real emergency occurred.');
    await page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
    await page.getByText('Review saved on this device', { exact: true }).waitFor();
    mark('Review saved locally');
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download incident report', exact: true }).click();
    const report = await pending;
    await report.saveAs(path.join(output, 'incident-report.html'));
    await page.screenshot({ path: path.join(output, 'review.png'), fullPage: true });
    mark('Incident report exported');
    await page.getByRole('button', { name: 'Close incident review' }).click();
    const stop = page.getByRole('button', { name: 'Stop agent', exact: true });
    if (await stop.count()) await stop.click();
    await page.reload();
    await page.getByRole('button').filter({ hasText: 'Sample: fall-lateral' }).first().click();
    await page.getByText('Closed · reviewed', { exact: true }).waitFor();
    mark('Saved review reopened after reload');
    await page.waitForTimeout(2000);
    assert.deepEqual(errors, []);
    await context.close();
    await video.saveAs(path.join(output, 'artae-demo.webm'));
    await fs.writeFile(path.join(output, 'NOTICE.txt'),
      'Artae Vision: automated walkthrough of real local inference on a staged sample. No real emergency; no audio. Cloud services were unavailable.\n' +
      'Footage: UMAFall, Eduardo Casilari and Jose A. Santoyo-Ramón. https://figshare.com/articles/dataset/UMA_ADL_FALL_Dataset_zip/4214283\n' +
      'CC BY 4.0: https://creativecommons.org/licenses/by/4.0/ . Footage excerpt trimmed, resized, re-encoded, and displayed with model overlays. No endorsement implied.\n' +
      'Keep this attribution with the recording when sharing. This demonstration does not establish detection accuracy or field reliability.\n');
    await fs.writeFile(path.join(output, 'capture.json'), JSON.stringify({
      codeRevision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
      codeDirty: !!execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(),
      browser: browser.version(), viewport: { width: 1440, height: 1000 },
      disclosure: 'Automated UI walkthrough, actual MediaPipe inference, staged UMAFall sample, normal video speed, cloud unavailable, no audio or fabricated detections; no accuracy or field reliability claim.',
      steps,
    }, null, 2) + '\n');
    console.log(output);
  } finally { await context.close(); await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

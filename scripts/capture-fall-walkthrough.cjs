// Record the public, no-account fall flow using the staged licensed sample.
// Start the web app first, then run: node scripts/capture-fall-walkthrough.cjs
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));

const url = process.env.ARTAE_CAPTURE_URL || 'http://127.0.0.1:3100/live';
const mediaDir = path.resolve(__dirname, '../apps/web/public/media');

async function caption(page, message) {
  await page.evaluate((text) => {
    let label = document.getElementById('walkthrough-caption');
    if (!label) {
      label = document.createElement('div');
      label.id = 'walkthrough-caption';
      Object.assign(label.style, {
        position: 'fixed', zIndex: '9999', right: '24px', bottom: '24px',
        maxWidth: '400px', padding: '13px 18px', borderRadius: '12px',
        background: 'rgba(9, 34, 43, .94)', color: '#fff',
        boxShadow: '0 10px 30px rgba(0, 0, 0, .24)',
        font: '700 15px/1.4 Arial, sans-serif', pointerEvents: 'none',
      });
      document.body.appendChild(label);
    }
    label.textContent = text;
  }, message);
}

(async () => {
  await fs.mkdir(mediaDir, { recursive: true });
  const browser = await chromium.launch({
    channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: mediaDir, size: { width: 1280, height: 800 } },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  const video = page.video();
  try {
    // The cloud API is unavailable in this recording. The detector, evidence,
    // and review remain functional locally; no signed-in data is used.
    await page.route('**/api/v1/**', (route) => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Cloud API disabled for this walkthrough.' }),
    }));
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => {
      const start = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Start agent');
      return start && !start.disabled;
    });
    await caption(page, 'Artae Vision · Fall monitoring prototype');
    await page.waitForTimeout(2500);
    await caption(page, '1. Analyze the staged clip on this device');
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.getByRole('button', { name: 'Review footage', exact: true }).waitFor({ timeout: 45000 });
    await caption(page, '2. A possible fall creates an incident and recorded evidence');
    const reviewFootage = page.getByRole('button', { name: 'Review footage', exact: true });
    await page.waitForFunction(() => {
      const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Review footage');
      return button && !button.disabled;
    }, null, { timeout: 30000 });
    await page.screenshot({ path: path.join(mediaDir, 'fall-monitor-walkthrough.png') });
    await page.waitForTimeout(2500);
    await reviewFootage.click();
    await page.waitForFunction(() => {
      const playback = document.querySelector('video[controls]');
      return playback && playback.readyState >= 1 && playback.videoWidth > 0;
    });
    await page.waitForTimeout(2500);
    await caption(page, '3. Replay the evidence and record a human review');
    await page.getByText('Reviewer note and response steps', { exact: true }).click();
    await page.waitForTimeout(1200);
    await page.getByLabel('Reviewer note (optional)').fill('Staged demonstration reviewed; the simulated fall is confirmed.');
    await page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
    await page.getByText('Closed · reviewed', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Download incident report', exact: true }).scrollIntoViewIfNeeded();
    await caption(page, '4. Export the incident record · no account required');
    const reportDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download incident report', exact: true }).click();
    await reportDownload;
    await page.waitForTimeout(3000);
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
    await page.getByLabel('Sample scenario').selectOption('sitting');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await caption(page, '5. Negative control: the sitting clip should not alert');
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
    await page.waitForTimeout(2500);
  } finally {
    await context.close();
    const recorded = await video.path();
    await fs.rename(recorded, path.join(mediaDir, 'fall-monitor-walkthrough.webm'));
    await browser.close();
  }
  console.log('Wrote apps/web/public/media/fall-monitor-walkthrough.webm and .png');
})().catch((error) => { console.error(error); process.exitCode = 1; });

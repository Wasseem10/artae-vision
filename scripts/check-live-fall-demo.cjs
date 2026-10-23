// Start the web app first, then run this script with Chrome installed.
// Example: node scripts/check-live-fall-demo.cjs
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));
const assert = require('node:assert/strict');

const TEST_URL = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3000/live';

async function demoPage(browser, awsMode = 'unavailable') {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  let rejectedCalls = 0;
  let rejectedPublicDemoStarts = 0;
  let mockedPublicDemoStarts = 0;
  let mockedAnalyses = 0;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (awsMode === 'mock-success' && request.method() === 'POST' && path.endsWith('/browser-sessions/public-demo')) {
      mockedPublicDemoStarts += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'mock-public-demo', token: 'mock-token', max_checks: 4 }),
      });
      return;
    }
    if (awsMode === 'mock-success' && request.method() === 'POST' && path.endsWith('/browser-sessions/public-demo/analyze')) {
      mockedAnalyses += 1;
      const frames = request.postDataJSON().frames;
      // A caregiver may finish local review before optional AWS enrichment returns.
      await new Promise((resolve) => setTimeout(resolve, 12000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'match',
          summary: 'Mock Nova confirmed the staged fall sequence.',
          frames_analyzed: frames.length,
          matched_frame_index: frames.length - 1,
          confirmed: true,
          match_streak: 1,
          confirmation_count: 1,
          cooldown: false,
          checks_remaining: 3,
          event: {
            source_event_id: '00000000-0000-4000-8000-000000000123',
            occurred_at_seconds: frames.at(-1).at_seconds,
            details: {
              summary: 'Mock Nova confirmed the staged fall sequence.',
              strands_agent: {
                status: 'completed',
                summary: 'Mock Strands prepared caregiver review.',
                tools_invoked: ['preserve_evidence', 'notify_responder', 'request_human_review'],
              },
              review: { status: 'open', outcome: null },
              notification: { channel: 'in_app', status: 'saved', message: 'Mock caregiver review requested.', priority: 'high' },
              evidence: { status: 'awaiting_recording', start_seconds: 0, end_seconds: 15, recording_ids: [] },
            },
          },
        }),
      });
      return;
    }
    rejectedCalls += 1;
    if (request.method() === 'POST' && path.endsWith('/browser-sessions/public-demo')) {
      rejectedPublicDemoStarts += 1;
    }
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'The API is unavailable during this local smoke test.' }),
    });
  });
  await page.goto(TEST_URL, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
  return {
    context, page,
    rejectedCalls: () => rejectedCalls,
    rejectedPublicDemoStarts: () => rejectedPublicDemoStarts,
    mockedPublicDemoStarts: () => mockedPublicDemoStarts,
    mockedAnalyses: () => mockedAnalyses,
  };
}

async function startSample(page, sample) {
  await page.getByLabel('Sample scenario').selectOption(sample);
  const start = page.getByRole('button', { name: 'Start agent', exact: true });
  await start.waitFor();
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Start agent');
    return button && !button.disabled;
  });
  await start.click();
  await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
  await page.waitForFunction(() => {
    const count = document.body.innerText.match(/(\d+) frames analyzed/);
    return count && Number(count[1]) >= 10;
  }, null, { timeout: 30000 });
}

(async () => {
  const browser = await chromium.launch({
    channel: process.env.ARTAE_TEST_BROWSER === 'chromium' ? undefined : 'chrome',
    headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const navigation = await demoPage(browser);
    try {
      const base = new URL('/', TEST_URL).href;
      await navigation.page.goto(base);
      await navigation.page.getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('link', { name: 'Engineering', exact: true }).click();
      await navigation.page.getByRole('heading', { name: 'The live pipeline', exact: true }).waitFor();
      await navigation.page.getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('link', { name: 'Data & privacy', exact: true }).click();
      await navigation.page.getByRole('heading', { name: 'Know where your video goes.', exact: true }).waitFor();
      await navigation.page.setViewportSize({ width: 390, height: 844 });
      await navigation.page.goto(base);
      const demoLink = navigation.page.getByRole('link', { name: 'Try the live demo', exact: true });
      const box = await demoLink.boundingBox();
      assert.ok(box && box.y >= 0 && box.y + box.height <= 844, 'Mobile sample action must be visible without scrolling');
      await navigation.page.getByRole('button', { name: 'Open menu', exact: true }).click();
      await navigation.page.getByRole('navigation', { name: 'Mobile navigation' })
        .getByRole('link', { name: 'Sign in', exact: true }).click();
      await navigation.page.getByRole('button', { name: 'Create account', exact: true }).click();
      assert.equal(await navigation.page.getByLabel('Password', { exact: true }).getAttribute('autocomplete'), 'new-password');
      for (const route of ['demo', 'app']) {
        await navigation.page.goto(new URL(route, base).href);
        await navigation.page.waitForURL('**/live');
      }
      console.log('NAVIGATION_OK: engineering, privacy, mobile demo action, signup semantics, and legacy entry points');
    } finally {
      await navigation.context.close();
    }
    const positive = await demoPage(browser);
    try {
      await startSample(positive.page, 'fall-lateral');
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).waitFor({ timeout: 30000 });
      await positive.page.waitForFunction(() => {
        const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Review footage');
        return button && !button.disabled;
      }, null, { timeout: 30000 });
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).click();
      await positive.page.getByRole('dialog').waitFor();
      await positive.page.waitForFunction(() => {
        const video = document.querySelector('video[controls]');
        return video && video.readyState >= 1 && video.videoWidth > 0;
      }, null, { timeout: 15000 });
      await positive.page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
      await positive.page.getByText('Reviewer note and response steps', { exact: true }).click();
      await positive.page.getByLabel('Reviewer note (optional)').fill('Caregiver checked the staged subject; no injury observed.');
      await positive.page.getByLabel('Organization response steps (optional)').fill('Check the person\nRecord the outcome');
      await positive.page.getByRole('dialog').press('Escape');
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).click();
      await positive.page.getByText('Reviewer note and response steps', { exact: true }).click();
      assert.equal(await positive.page.getByLabel('Reviewer note (optional)').inputValue(),
        'Caregiver checked the staged subject; no injury observed.', 'Closing and reopening review must retain the draft');
      await positive.page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
      await positive.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await positive.page.getByText('Review saved on this device', { exact: true }).waitFor();
      assert.ok(positive.rejectedCalls() > 0, 'The local fall demo must work while API calls return 503');
      assert.ok(positive.rejectedPublicDemoStarts() > 0, 'The AWS session request must receive 503 in this test');

      await positive.page.reload();
      await positive.page.getByRole('button').filter({ hasText: 'Sample: fall-lateral' }).first().click();
      await positive.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).waitFor();
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).click();
      assert.equal(await positive.page.getByLabel('Reviewer note (optional)').inputValue(),
        'Caregiver checked the staged subject; no injury observed.');
      assert.equal(await positive.page.getByLabel('Organization response steps (optional)').inputValue(),
        'Check the person\nRecord the outcome');
      const reportDownload = positive.page.waitForEvent('download');
      await positive.page.getByRole('button', { name: 'Download incident report', exact: true }).click();
      const downloaded = await reportDownload;
      const reportHtml = await fs.readFile(await downloaded.path(), 'utf8');
      assert.match(reportHtml, /Resolved — reviewed/);
      assert.match(reportHtml, /Caregiver checked the staged subject; no injury observed\./);
      assert.match(reportHtml, /Check the person/);
      assert.match(reportHtml, /Evidence metadata/);
      assert.doesNotMatch(reportHtml, /<video|blob:/i);
      await positive.page.getByRole('dialog').press('Escape');
      assert.equal(await positive.page.getByRole('dialog').isVisible(), false, 'Escape must close incident review');
      assert.equal(await positive.page.evaluate(() => document.activeElement?.textContent?.trim()), 'Review footage',
        'Closing review must return keyboard focus to the event trigger');
      console.log('FALL_OK: detection, playable clip, saved review details, and incident report survive reload with API 503');
    } finally {
      await positive.context.close();
    }

    const negative = await demoPage(browser);
    try {
      await startSample(negative.page, 'sitting');
      await negative.page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
      assert.equal(await negative.page.getByRole('button', { name: 'Review footage', exact: true }).count(), 0,
        'Sitting control must not create a fall incident');
      assert.ok(negative.rejectedCalls() > 0, 'Negative control must also run with API 503');
      console.log('SITTING_OK: frames processed without a false fall incident with API 503');
    } finally {
      await negative.context.close();
    }

    const upload = await demoPage(browser);
    try {
      await upload.page.getByLabel('2. Connect video').selectOption('file');
      await upload.page.getByLabel('Choose a video').setInputFiles(path.resolve(__dirname,
        '../apps/web/public/vision/samples/fall-lateral.mp4'));
      assert.equal(await upload.page.getByRole('checkbox', { name: /Allow event frames/ }).isChecked(), false);
      await upload.page.getByRole('button', { name: 'Start agent', exact: true }).click();
      await upload.page.getByRole('button', { name: 'Review footage', exact: true }).waitFor({ timeout: 60000 });
      await upload.page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
      assert.equal(upload.rejectedPublicDemoStarts(), 0, 'Guest upload must not request cloud analysis without consent');
      console.log('UPLOAD_PRIVACY_OK: real guest upload detection without a cloud-analysis session');
    } finally {
      await upload.context.close();
    }

    const enriched = await demoPage(browser, 'mock-success');
    try {
      await startSample(enriched.page, 'fall-lateral');
      await enriched.page.waitForFunction(() => {
        const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Review footage');
        return button && !button.disabled;
      }, null, { timeout: 30000 });
      await enriched.page.getByRole('button', { name: 'Review footage', exact: true }).click();
      await enriched.page.getByRole('button', { name: 'Mark reviewed', exact: true }).waitFor({ timeout: 30000 });
      await enriched.page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
      await enriched.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      assert.equal(await enriched.page.getByText('AWS coordinator: completed', { exact: true }).count(), 0,
        'Local review must complete before mocked cloud enrichment returns');
      await enriched.page.getByRole('button', { name: 'Close incident review' }).click();
      await enriched.page.getByRole('complementary').getByText(/Possible fall · person \d+ — please review/).waitFor({ timeout: 30000 });
      await enriched.page.getByText('AWS coordinator: completed', { exact: true }).waitFor();
      await enriched.page.getByText('Mock Nova confirmed the staged fall sequence.', { exact: true }).waitFor();
      await enriched.page.getByText('Nova reviewed the whole scene and prepared a caregiver response. Check the person shown in the local alert.', { exact: false }).waitFor();
      await enriched.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await enriched.page.getByText('On-screen alert · this device', { exact: true }).waitFor();
      assert.equal(enriched.mockedPublicDemoStarts(), 1, 'Mocked AWS session must be requested once');
      assert.ok(enriched.mockedAnalyses() > 0, 'A real local fall candidate must trigger mocked Nova review');
      console.log('ENRICHMENT_OK: late mocked Nova and Strands result preserves guest review and device-only status');
    } finally {
      await enriched.context.close();
    }
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

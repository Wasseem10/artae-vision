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
      await new Promise((resolve) => setTimeout(resolve, 5000));
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
    channel: 'chrome',
    headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const positive = await demoPage(browser);
    try {
      await startSample(positive.page, 'fall-lateral');
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).waitFor({ timeout: 30000 });
      await positive.page.waitForFunction(() => {
        const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Review footage');
        return button && !button.disabled;
      }, null, { timeout: 30000 });
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).click();
      await positive.page.waitForFunction(() => {
        const video = document.querySelector('video[controls]');
        return video && video.readyState >= 1 && video.videoWidth > 0;
      }, null, { timeout: 15000 });
      await positive.page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
      await positive.page.getByText('Reviewer note and response steps', { exact: true }).click();
      await positive.page.getByLabel('Reviewer note (optional)').fill('Caregiver checked the staged subject; no injury observed.');
      await positive.page.getByLabel('Organization response steps (optional)').fill('Check the person\nRecord the outcome');
      await positive.page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
      await positive.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await positive.page.getByText('Review saved on this device', { exact: true }).waitFor();
      assert.ok(positive.rejectedCalls() > 0, 'The local fall demo must work while API calls return 503');
      assert.ok(positive.rejectedPublicDemoStarts() > 0, 'The AWS session request must receive 503 in this test');

      await positive.page.reload();
      await positive.page.getByRole('button').filter({ hasText: 'Sample: fall-lateral' }).first().click();
      await positive.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await positive.page.getByRole('button', { name: 'Review footage', exact: true }).waitFor();
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

    const enriched = await demoPage(browser, 'mock-success');
    try {
      await startSample(enriched.page, 'fall-lateral');
      await enriched.page.getByRole('button', { name: 'Mark reviewed', exact: true }).waitFor({ timeout: 30000 });
      await enriched.page.getByRole('button', { name: 'Mark reviewed', exact: true }).click();
      await enriched.page.getByText('Closed · reviewed', { exact: true }).waitFor();
      await enriched.page.getByText(/Possible fall · person \d+ — please review/).waitFor({ timeout: 30000 });
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

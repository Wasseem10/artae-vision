// Start the web app first. This composes two licensed local sample videos in
// Chrome, then uploads the result through the same UI a visitor uses.
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));

const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3000/live';

async function combinedVideo(page, left, right) {
  const base64 = await page.evaluate(async ({ left, right }) => {
    const videos = await Promise.all([left, right].map(async (name) => {
      const video = document.createElement('video');
      video.src = `/vision/samples/${name}.mp4`;
      video.muted = true;
      await new Promise((resolve, reject) => {
        video.onloadeddata = resolve;
        video.onerror = reject;
      });
      await video.play();
      return video;
    }));
    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 360;
    const context = canvas.getContext('2d');
    const stream = canvas.captureStream(15);
    const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8' });
    const chunks = [];
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.start();
    await new Promise((resolve) => {
      const started = performance.now();
      const draw = () => {
        context.drawImage(videos[0], 0, 0, 640, 360);
        context.drawImage(videos[1], 640, 0, 640, 360);
        if (performance.now() - started < 11800) requestAnimationFrame(draw);
        else resolve();
      };
      draw();
    });
    await new Promise((resolve) => { recorder.onstop = resolve; recorder.stop(); });
    videos.forEach((video) => video.pause());
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(chunks, { type: 'video/webm' });
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }, { left, right });
  return Buffer.from(base64, 'base64');
}

(async () => {
  const browser = await chromium.launch({
    channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    for (const [left, right, expectedFall] of [
      ['fall-lateral', 'person', true],
      ['person', 'fall-lateral', true],
      ['sitting', 'person', false],
    ]) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
      const page = await context.newPage();
      await page.route('**/api/v1/**', (route) => route.fulfill({ status: 503,
        contentType: 'application/json', body: JSON.stringify({ detail: 'Offline smoke test' }) }));
      try {
        await page.goto(url);
        const buffer = await combinedVideo(page, left, right);
        assert.ok(buffer.length > 100000, 'The combined video must contain frames');
        await page.getByLabel('2. Connect video').selectOption('file');
        await page.getByLabel('Choose a video').setInputFiles({
          name: `${left}-and-${right}.webm`, mimeType: 'video/webm', buffer,
        });
        await page.getByRole('button', { name: 'Start agent', exact: true }).click();
        await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
        await page.waitForFunction(() => /[2-4] people/.test(document.body.innerText), null, { timeout: 30000 });
        await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 30000 });
        const titles = await page.locator('article strong').allTextContents();
        const falls = titles.filter((title) => title.includes('Possible fall'));
        assert.equal(falls.length > 0, expectedFall,
          `${left} + ${right}: unexpected fall alerts: ${JSON.stringify(titles)}`);
        if (expectedFall) assert.ok(falls.every((title) => /person \d+/.test(title)), 'Alert needs a person track number');
        if (left === 'person' && right === 'fall-lateral') {
          assert.ok(falls.some((title) => /person [2-9]\d*/.test(title)),
            'The additional-person path must alert when the right-hand person falls');
        }
        console.log(`${left.toUpperCase()}_WITH_${right.toUpperCase()}_OK: two bodies seen, alerts: ${JSON.stringify(falls)}`);
      } finally {
        await context.close();
      }
    }
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await context.newPage();
    let visualChecks = 0;
    await page.route('**/api/v1/**', (route) => {
      const apiPath = new URL(route.request().url()).pathname;
      if (apiPath.endsWith('/browser-sessions/public-demo')) return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 'custom-mock', token: 'mock-token', max_checks: 4 }),
      });
      if (apiPath.endsWith('/browser-sessions/public-demo/analyze')) {
        visualChecks += 1;
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          status: 'match', summary: 'A person is visible in the sampled frames.',
          frames_analyzed: 4, confirmed: true, match_streak: 1, confirmation_count: 1,
          cooldown: false, checks_remaining: 3,
          event: { source_event_id: '00000000-0000-4000-8000-000000000123',
            occurred_at_seconds: 4, details: { summary: 'A person is visible in the sampled frames.' } },
        }) });
      }
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
    });
    try {
      await page.goto(new URL('/demo', url).href);
      await page.waitForURL('**/live');
      await page.getByLabel('1. What should it watch for?').selectOption('custom');
      await page.getByLabel('What visible condition should trigger an in-app alert?').fill('A person is visible');
      await page.getByLabel(/Allow sampled video frames/).check();
      await page.getByRole('button', { name: 'Start agent', exact: true }).click();
      await page.getByText('Visual condition matched', { exact: true }).waitFor({ timeout: 60000 });
      assert.ok(visualChecks > 0, 'The unified guest monitor must call AWS visual checks');
      console.log('CUSTOM_OK: old demo redirects to the one monitor, and guest visual condition produces an alert');
    } finally {
      await context.close();
    }
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

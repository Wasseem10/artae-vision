// Local-app QA only. Real MediaPipe + MediaRecorder; a licensed Y4M clip supplies
// the isolated browser's fake camera. No user webcam or account credentials.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:4174/demo';
  assert.ok(['localhost', '127.0.0.1', '::1'].includes(new URL(url).hostname), 'Local QA only');
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: [
    '--use-fake-device-for-media-stream',
    `--use-file-for-fake-video-capture=${path.resolve('.runtime/qa-webcam.y4m')}`,
    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  ] });
  try {
    const context = await browser.newContext({ permissions: ['camera'], viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(url);
    await page.getByLabel('1. What should it watch for?').selectOption('fall');
    await page.getByLabel('2. Connect video').selectOption('webcam');
    await page.getByRole('button', { name: 'Start agent', exact: true }).click();
    await page.getByText('Analyzing real video', { exact: true }).waitFor({ timeout: 60000 });
    const started = Date.now();
    for (let minute = 1; minute <= 2; minute++) {
      await page.waitForTimeout(60000);
      console.log('RUN_PROGRESS', minute, 'minute(s)', (await page.locator('body').innerText()).match(/\d+ frames analyzed[^\n]*/)?.[0]);
    }
    await page.getByRole('button', { name: 'Start agent', exact: true }).waitFor({ timeout: 15000 });
    assert.ok(Date.now() - started >= 120000, 'This is a wall-clock run, not accelerated playback');
    await page.waitForTimeout(1500); // final recorder + IndexedDB transaction
    const stored = await page.evaluate(async () => {
      const db = await new Promise((resolve, reject) => { const r = indexedDB.open('artae-browser-sessions', 2); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
      const sessions = await new Promise(resolve => { const r = db.transaction('sessions').objectStore('sessions').getAll(); r.onsuccess = () => resolve(r.result); });
      const session = sessions.sort((a,b) => b.createdAt.localeCompare(a.createdAt))[0];
      const sizes = await Promise.all(session.clips.map(c => new Promise(resolve => { const r = db.transaction('clips').objectStore('clips').get(`${session.scope}/${session.id}/${c.id}`); r.onsuccess = () => resolve(r.result?.blob?.size || 0); })));
      db.close();
      return { clips: session.clips, events: session.events, sizes,
        cameraReleased: [...document.querySelectorAll('video')].every(v => !v.srcObject),
        overflow: document.documentElement.scrollWidth > innerWidth + 1 };
    });
    assert.ok(stored.cameraReleased, 'Stop must release camera tracks');
    assert.equal(stored.events.length, 0, 'Sitting must not create a fall alert');
    assert.ok(stored.clips.length >= 11, 'Two minutes must contain recording segments');
    assert.ok(stored.sizes.every(n => n > 1000), 'Every segment needs real video bytes');
    assert.ok(stored.clips.reduce((n,c) => n + c.duration, 0) > 115, 'Recording coverage must exceed 115 seconds');
    for (let i = 1; i < stored.clips.length; i++)
      assert.ok(stored.clips[i].start - (stored.clips[i-1].start + stored.clips[i-1].duration) < .5, 'No half-second gaps');
    assert.equal(stored.overflow, false, 'Mobile-width workspace must not overflow');
    assert.deepEqual(errors, [], 'No browser runtime exceptions');
    await page.reload();
    await page.getByRole('button').filter({ hasText: 'My webcam' }).first().click();
    await page.waitForFunction(() => [...document.querySelectorAll('video')].some(v => v.controls && v.readyState >= 1));
    console.log('LIFECYCLE_OK', JSON.stringify({ seconds: (Date.now()-started)/1000, segments: stored.clips.length,
      recordedSeconds: stored.clips.reduce((n,c) => n+c.duration,0), bytes: stored.sizes.reduce((a,b)=>a+b,0), mobileWidth:390 }));
    // Independent denied-camera run: display actionable error and restore Start.
    const denied = await browser.newContext();
    const deniedPage = await denied.newPage();
    await deniedPage.goto(url);
    await deniedPage.getByLabel('2. Connect video').selectOption('webcam');
    await deniedPage.getByRole('button', { name: 'Start agent', exact: true }).click();
    await deniedPage.getByText(/Camera permission denied/).waitFor({ timeout: 60000 });
    await deniedPage.getByRole('button', { name: 'Start agent', exact: true }).waitFor();
    console.log('CAMERA_DENIED_RECOVERY_OK');
    const blocked = await browser.newContext();
    await blocked.addInitScript(() => Object.defineProperty(window, 'indexedDB', {
      get() { throw new DOMException('Storage blocked for regression test', 'SecurityError'); },
    }));
    const blockedPage = await blocked.newPage();
    await blockedPage.goto(url);
    await blockedPage.getByText(/Device history is unavailable/).waitFor();
    await blockedPage.getByRole('button', { name: 'Start agent', exact: true }).click();
    await blockedPage.getByRole('button', { name: 'Review footage', exact: true }).waitFor({ timeout: 60000 });
    const blockedStop = blockedPage.getByRole('button', { name: 'Stop agent', exact: true });
    if (await blockedStop.count()) await blockedStop.click();
    await blockedPage.getByText(/Local history could not be saved/).waitFor();
    console.log('BLOCKED_STORAGE_DETECTION_OK');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

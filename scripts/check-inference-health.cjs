// Real model, local video, and native recorder. Only the named worker response
// faults are injected. No camera, account, API, or external media access.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(__dirname, '../apps/web')] }));
const url = process.env.ARTAE_TEST_URL || 'http://127.0.0.1:3320/live';
const origin = new URL(url).origin;
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname), 'Local QA only');

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const dir = path.resolve(__dirname, '../artifacts/inference-health');
  await fs.mkdir(dir, { recursive: true });
  const results = [];
  try {
    for (const mode of ['stall', 'wrong-timestamp', 'healthy']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        await context.route('**/*', route => {
          const target = new URL(route.request().url());
          if (target.origin !== origin || target.pathname.startsWith('/api/'))
            return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Offline QA"}' });
          return route.continue();
        });
        await context.addInitScript(mode => {
          const Native = window.Worker;
          window.__healthTest = { terminated: 0, injected: false };
          window.Worker = new Proxy(Native, { construct(Target, args) {
            const worker = new Target(...args);
            if (!String(args[0]).includes('pose-worker')) return worker;
            let count = 0;
            const shouldInject = mode !== 'healthy' && !window.__healthTest.injected;
            return new Proxy(worker, {
              get(target, prop) {
                if (prop === 'postMessage') return (data, transfer) => {
                  if (data.type === 'frame') {
                    count++;
                    if (shouldInject && mode === 'stall' && count === 11) {
                      window.__healthTest.injected = true; data.bitmap.close(); return;
                    }
                  }
                  target.postMessage(data, transfer);
                };
                if (prop === 'terminate') return () => { window.__healthTest.terminated++; target.terminate(); };
                const value = Reflect.get(target, prop, target);
                return typeof value === 'function' ? value.bind(target) : value;
              },
              set(target, prop, value) {
                if (prop === 'onmessage' && typeof value === 'function') {
                  target.onmessage = event => {
                    if (shouldInject && mode === 'wrong-timestamp' && event.data.type === 'result' && count === 11) {
                      window.__healthTest.injected = true;
                      value(new MessageEvent('message', { data: { ...event.data, timestamp: event.data.timestamp - 1000 } }));
                    } else value(event);
                  };
                } else Reflect.set(target, prop, value, target);
                return true;
              },
            });
          } });
          // Keep the sitting control playing through the 15-second stall deadline.
          const play = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function() {
            if (!this.controls) this.playbackRate = .5;
            return play.call(this);
          };
        }, mode);
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(url);
        await page.getByLabel('Sample scenario').selectOption('sitting');
        await page.getByText('Session diagnostics', { exact: true }).click();
        await page.getByText('Waiting for measured results', { exact: false }).waitFor();
        const start = () => page.getByRole('button', { name: 'Start agent', exact: true }).click();
        await start();
        await page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 5, null, { timeout: 60000 });
        const diagnostic = page.locator('details').filter({ has: page.getByText('Session diagnostics', { exact: true }) });
        assert.match(await diagnostic.innerText(), /Median inference: \d/);
        assert.match(await diagnostic.innerText(), /Processed: \d/);
        if (mode !== 'healthy') {
          const failure = mode === 'stall' ? 'model did not respond for 15 seconds' : 'video result could not be verified';
          await page.getByRole('alert').filter({ hasText: failure }).waitFor({ timeout: 25000 });
          await page.getByText('Monitoring stopped', { exact: true }).waitFor();
          assert.equal(await page.getByRole('button', { name: 'Stop agent', exact: true }).count(), 0);
          assert.ok(await page.evaluate(() => window.__healthTest.terminated >= 1));
          const before = await page.evaluate(() => document.body.innerText.match(/(\d+) frames analyzed/)?.[1]);
          await page.waitForTimeout(1000);
          assert.equal(await page.evaluate(() => document.body.innerText.match(/(\d+) frames analyzed/)?.[1]), before);
          await page.screenshot({ path: path.join(dir, `${mode}.png`), fullPage: true });
          // Explicit new session must recover without reloading the page.
          await start();
          await page.waitForFunction(() => Number(document.body.innerText.match(/(\d+) frames analyzed/)?.[1]) >= 12, null, { timeout: 60000 });
          assert.equal(await page.getByRole('alert').filter({ hasText: failure }).count(), 0);
        } else {
          await page.screenshot({ path: path.join(dir, 'desktop.png'), fullPage: true });
          await page.setViewportSize({ width: 390, height: 844 });
          await page.screenshot({ path: path.join(dir, 'mobile.png'), fullPage: true });
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        }
        await page.getByRole('button', { name: 'Stop agent', exact: true }).click();
        assert.deepEqual(errors, []);
        results.push({ mode, passed: true, measuredDiagnostics: true, recovered: mode !== 'healthy' });
        console.log(`${mode}: passed`);
      } finally { await context.close(); }
    }
    await fs.writeFile(path.join(dir, 'results.json'), JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

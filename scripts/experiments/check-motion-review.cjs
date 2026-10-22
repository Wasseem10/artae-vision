// Local packet smoke check. Downloads are test drafts, never published labels.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
async function main() {
  const [packetArg, dependencies] = process.argv.slice(2);
  assert.ok(packetArg && dependencies, 'Pass local-packet-directory web-dependencies-root');
  const directory = path.resolve(packetArg);
  const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(dependencies)] }));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [], network = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => { network.push(route.request().url()); return route.abort(); });
    await page.goto(pathToFileURL(path.join(directory, 'index.html')).href);
    await page.locator('.frame img').last().waitFor();
    const count = await page.locator('.frame').count();
    assert.equal(count, 21);
    assert.ok(await page.locator('.frame img').evaluateAll(images => images.every(i => i.complete && i.naturalWidth > 0)));
    await page.getByRole('button', { name: 'Export single review', exact: true }).click();
    assert.match(await page.locator('#status').innerText(), /reviewer/);
    await page.getByLabel('Reviewer name').fill('SMOKE TEST ONLY');
    await page.getByRole('button', { name: 'Export single review', exact: true }).click();
    assert.match(await page.locator('#status').innerText(), /Unreviewed/);
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export draft', exact: true }).click();
    const draftPath = path.join(directory, 'smoke-draft.json');
    await (await downloaded).saveAs(draftPath);
    const draft = JSON.parse(fs.readFileSync(draftPath));
    assert.equal(draft.status, 'draft'); assert.equal(draft.frames[0].visiblePeople, null);
    await page.reload();
    await page.locator('#import').setInputFiles(draftPath);
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Review restored'));
    assert.equal(await page.getByLabel('Reviewer name').inputValue(), 'SMOKE TEST ONLY');
    const wrong = { ...draft, packetId: 'wrong-packet' };
    await page.locator('#import').setInputFiles({ name: 'wrong.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(wrong)) });
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Import rejected'));
    // Capture the blank review state, not artificial test labels.
    await page.reload();
    await page.screenshot({ path: path.join(directory, 'desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(directory, 'mobile.png') });
    await page.locator('.frame').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(directory, 'mobile-frame.png') });
    assert.deepEqual(errors, []); assert.deepEqual(network, []);
    console.log(JSON.stringify({ frames: count, allImagesLoaded: true, draftRoundTrip: true,
      incompleteReviewRejected: true, wrongPacketRejected: true, mobileOverflow: false,
      pageErrors: errors.length, externalRequests: network.length }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

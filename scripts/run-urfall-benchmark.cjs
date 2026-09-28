// Start the local web app, then run: node scripts/run-urfall-benchmark.cjs
// The research media is prepared by prepare-urfall-benchmark.py and stays gitignored.
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));

const baseUrl = process.env.ARTAE_BENCHMARK_URL || 'http://127.0.0.1:3000';
const output = path.resolve(__dirname, '../artifacts/urfall/evaluation.json');
const root = path.resolve(__dirname, '..');

async function fileHash(relativePath) {
  return crypto.createHash('sha256')
    .update(await fs.readFile(path.join(root, relativePath)))
    .digest('hex');
}

(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    page.on('pageerror', (error) => console.error('PAGE:', error.message));
    await page.goto(`${baseUrl}/evaluation/fall?dataset=urfall`, { waitUntil: 'domcontentloaded' });
    const datasetButton = page.getByRole('button', { name: /UR Fall research set/ });
    await datasetButton.waitFor({ timeout: 30000 });
    assert.equal(await datasetButton.getAttribute('aria-pressed'), 'true');
    const manifest = await page.evaluate(async () =>
      (await fetch('/vision/urfall/manifest.json')).json());
    console.log(`Running ${manifest.cases.length} UR Fall clips`);
    for (const item of manifest.cases) {
      const actual = await fileHash(`apps/web/public${item.videoUrl}`);
      assert.equal(actual, item.videoSha256, `Media changed since preparation: ${item.id}`);
    }
    await page.getByRole('button', { name: 'Run evaluation' }).click();
    await page.getByRole('button', { name: 'Download JSON' }).waitFor({ timeout: 45 * 60 * 1000 });
    const promise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download JSON' }).click();
    const download = await promise;
    await fs.mkdir(path.dirname(output), { recursive: true });
    const result = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
    assert.equal(result.status, 'complete');
    assert.equal(result.results.length, manifest.cases.length);
    assert.equal(result.dataset.datasetId, manifest.datasetId);
    result.provenance.localSourceHashes = Object.fromEntries(await Promise.all([
      'apps/web/src/lib/browser-pose.ts',
      'apps/web/src/lib/fall-evaluation.ts',
      'apps/web/src/components/fall-evaluation-runner.tsx',
      'apps/web/public/vision/pose-worker.js',
      'apps/web/public/vision/urfall/manifest.json',
    ].map(async (filename) => [filename, await fileHash(filename)])));
    result.provenance.localGitRevision = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: root, encoding: 'utf8',
    }).trim();
    result.provenance.localGitDirty = execFileSync('git', ['status', '--porcelain'], {
      cwd: root, encoding: 'utf8',
    }).trim().length > 0;
    await fs.writeFile(output, JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({
      output,
      temporal: result.summary,
      postureBaseline: result.postureBaselineSummary,
      partitions: result.partitions,
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

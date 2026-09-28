// Start the local web app, then run: node scripts/run-urfall-benchmark.cjs
// The research media is prepared locally and stays gitignored.
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));

const baseUrl = process.env.ARTAE_BENCHMARK_URL || 'http://127.0.0.1:3000';
const dataset = process.env.ARTAE_BENCHMARK_DATASET || 'urfall';
assert.ok(['urfall', 'gmdcsa24'].includes(dataset), 'Unsupported benchmark dataset');
const output = path.resolve(__dirname, `../artifacts/${dataset}/evaluation.json`);
const root = path.resolve(__dirname, '..');
const manifestPath = `apps/web/public/vision/${dataset}/manifest.json`;

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
    await page.goto(`${baseUrl}/evaluation/fall?dataset=${dataset}`, { waitUntil: 'domcontentloaded' });
    const datasetButton = page.getByRole('button', {
      name: dataset === 'urfall' ? /UR Fall research set/ : /GMDCSA-24 subject split/,
    });
    await datasetButton.waitFor({ timeout: 30000 });
    assert.equal(await datasetButton.getAttribute('aria-pressed'), 'true');
    const manifest = await page.evaluate(async (datasetId) =>
      (await fetch(`/vision/${datasetId}/manifest.json`)).json(), dataset);
    console.log(`Running ${manifest.cases.length} ${dataset} clips`);
    for (const item of manifest.cases) {
      const actual = await fileHash(`apps/web/public${decodeURIComponent(item.videoUrl)}`);
      assert.equal(actual, item.videoSha256, `Media changed since preparation: ${item.id}`);
    }
    await page.getByRole('button', { name: 'Run evaluation' }).click();
    let lastProgress = -1;
    const progressTimer = setInterval(async () => {
      try {
        const value = Number(await page.getByRole('progressbar').getAttribute('aria-valuenow'));
        if (value >= lastProgress + 10) {
          lastProgress = value;
          console.log(`${dataset}: ${value}% processed`);
        }
      } catch { /* Page may be closing. */ }
    }, 30000);
    try {
      await Promise.race([
        page.getByRole('button', { name: 'Download JSON' }).waitFor({ timeout: 45 * 60 * 1000 }),
        page.getByText('Evaluation failed', { exact: true }).waitFor({ timeout: 45 * 60 * 1000 })
          .then(async () => { throw new Error(await page.getByRole('alert').textContent() || 'Evaluation failed'); }),
      ]);
    } finally {
      clearInterval(progressTimer);
    }
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
      'apps/web/src/lib/pose-window-fall.ts',
      'apps/web/src/lib/fall-window-model.json',
      'scripts/train-pose-window-fall.py',
      'apps/web/public/vision/pose-worker.js',
      manifestPath,
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
      windowCandidate: result.windowModelSummary,
      partitions: result.partitions,
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

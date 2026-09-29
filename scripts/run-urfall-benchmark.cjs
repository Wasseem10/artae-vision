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
assert.ok(['urfall', 'gmdcsa24', 'caucafall', 'realbiomfall', 'imuadlfall', 'mpfdd'].includes(dataset), 'Unsupported benchmark dataset');
const poseModel = process.env.ARTAE_BENCHMARK_POSE_MODEL || 'lite';
assert.ok(['lite', 'full', 'heavy'].includes(poseModel), 'Unsupported pose model');
const detectorMode = process.env.ARTAE_BENCHMARK_DETECTOR || 'legacy';
assert.ok(['legacy', 'multi'].includes(detectorMode), 'Unsupported detector mode');
const personCrops = process.env.ARTAE_BENCHMARK_PERSON_CROPS === '1';
if (personCrops) assert.ok(dataset === 'mpfdd' && detectorMode === 'multi' && poseModel === 'lite', 'Person-crop comparison supports MPFDD multi-pose Lite only');
const output = path.resolve(__dirname, `../artifacts/${dataset}/evaluation${detectorMode === 'multi' ? '-multiperson' : ''}${poseModel === 'lite' ? '' : `-${poseModel}`}${personCrops ? '-person-crops' : ''}.json`);
const root = path.resolve(__dirname, '..');
const manifestPath = `apps/web/public/vision/${dataset}/manifest.json`;
const poseModelPath = path.join(root, `apps/web/public/vision/pose_landmarker_${poseModel}.task`);

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
    if (personCrops) {
      await page.route('**/vision/pose-worker.js', (route) => route.fulfill({
        path: path.join(root, 'scripts/experiments/person-crop-pose-worker.js'), contentType: 'text/javascript',
      }));
      await page.route('**/vision/person_detector.tflite', (route) => route.fulfill({
        path: path.join(root, 'artifacts/person-crops/efficientdet_lite0_uint8.tflite'),
        contentType: 'application/octet-stream',
      }));
    }
    if (poseModel !== 'lite') {
      await fs.access(poseModelPath);
      // Swap only the worker's model response. Every clip and detector rule is unchanged.
      await page.route('**/vision/pose_landmarker_lite.task', (route) =>
        route.fulfill({ path: poseModelPath, contentType: 'application/octet-stream' }));
    }
    await page.goto(`${baseUrl}/evaluation/fall?dataset=${dataset}&detector=${detectorMode}`, { waitUntil: 'domcontentloaded' });
    if (detectorMode === 'multi') await page.getByRole('heading', { name: 'Multi-person fall evaluation' }).waitFor();
    const datasetButton = page.getByRole('button', {
      name: dataset === 'urfall' ? /UR Fall research set/ :
        dataset === 'gmdcsa24' ? /GMDCSA-24 subject split/ :
          dataset === 'caucafall' ? /CAUCAFall independent source/ :
          dataset === 'realbiomfall' ? /RealBiomFall fresh source/ :
            dataset === 'mpfdd' ? /MPFDD multi-person source/ : /IMU-video fresh source/,
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
    result.provenance.detector.model = `MediaPipe Pose Landmarker ${poseModel} float16/1`;
    result.provenance.detector.modelSha256 = await fileHash(`apps/web/public/vision/pose_landmarker_${poseModel}.task`);
    result.provenance.detector.modelAsset = `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${poseModel}/float16/1/pose_landmarker_${poseModel}.task`;
    if (personCrops) {
      result.provenance.detector.worker = 'scripts/experiments/person-crop-pose-worker.js';
      result.provenance.detector.personModel = 'EfficientDet Lite0 uint8, person class';
      result.provenance.detector.personModelAsset = 'https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite';
      result.provenance.detector.personModelSha256 = await fileHash('artifacts/person-crops/efficientdet_lite0_uint8.tflite');
      result.provenance.detector.candidateWorkerSha256 = await fileHash('scripts/experiments/person-crop-pose-worker.js');
    }
    result.provenance.localSourceHashes = Object.fromEntries(await Promise.all([
      'apps/web/src/lib/browser-pose.ts',
      'apps/web/src/lib/multi-person-fall.ts',
      'apps/web/src/lib/fall-evaluation.ts',
      'apps/web/src/components/fall-evaluation-runner.tsx',
      'apps/web/src/lib/pose-window-fall.ts',
      'apps/web/src/lib/fall-window-model.json',
      'apps/web/src/lib/fall-window-model-v2.json',
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
      windowCandidateV2: result.windowModelV2Summary,
      partitions: result.partitions,
    }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });

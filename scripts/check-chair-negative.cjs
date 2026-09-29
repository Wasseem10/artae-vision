// Start the web app, then run: node scripts/check-chair-negative.cjs
// Replays two people-free chair scenes through the actual browser pose worker.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(require.resolve('playwright', {
  paths: [path.resolve(__dirname, '../apps/web')],
}));

const baseUrl = process.env.ARTAE_BENCHMARK_URL || 'http://127.0.0.1:3000';
const poseModel = process.env.ARTAE_CHAIR_POSE_MODEL || 'lite';
assert.ok(['lite', 'full', 'heavy'].includes(poseModel), 'Unsupported pose model');
const fixtures = ['empty-chairs.jpg', 'empty-classroom.jpg'];

(async () => {
  const browser = await chromium.launch({
    channel: 'chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage();
    await page.route('**/chair-test/*', async (route) => {
      const filename = new URL(route.request().url()).pathname.split('/').pop();
      assert.ok(fixtures.includes(filename), 'Unexpected fixture request');
      await route.fulfill({
        path: path.join(__dirname, 'fixtures/chair-negative', filename),
        contentType: 'image/jpeg',
      });
    });
    if (poseModel !== 'lite') {
      await page.route('**/vision/pose_landmarker_lite.task', (route) =>
        route.fulfill({
          path: path.resolve(__dirname, `../apps/web/public/vision/pose_landmarker_${poseModel}.task`),
          contentType: 'application/octet-stream',
        }));
    }
    await page.goto(`${baseUrl}/live`, { waitUntil: 'domcontentloaded' });
    for (const filename of fixtures) {
      const result = await page.evaluate(async (name) => {
        const image = new Image();
        image.src = `/chair-test/${name}`;
        await image.decode();
        const worker = new Worker('/vision/pose-worker.js');
        const receive = (type, send) => new Promise((resolve, reject) => {
          const listener = ({ data }) => {
            if (data.type === 'error' || data.type === type) {
              worker.removeEventListener('message', listener);
              if (data.type === 'error') reject(new Error(data.message));
              else resolve(data);
            }
          };
          worker.addEventListener('message', listener);
          send();
        });
        try {
          await receive('ready', () => worker.postMessage({ type: 'init', numPoses: 4 }));
          let framesWithPose = 0;
          let maximumPoses = 0;
          for (let index = 0; index < 31; index++) {
            const bitmap = await createImageBitmap(image);
            const frame = await receive('result', () => worker.postMessage({
              type: 'frame', bitmap, timestamp: index * 100,
            }, [bitmap]));
            const count = frame.poses?.length || 0;
            framesWithPose += Number(count > 0);
            maximumPoses = Math.max(maximumPoses, count);
          }
          return { name, frames: 31, framesWithPose, maximumPoses };
        } finally {
          worker.terminate();
        }
      }, filename);
      console.log(JSON.stringify({ model: poseModel, ...result }));
      assert.equal(result.framesWithPose, 0, `${filename}: a chair was detected as a pose`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
